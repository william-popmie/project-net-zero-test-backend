#!/usr/bin/env python3
"""Carbon-optimizing code optimizer using LangGraph + Claude API."""

import ast
import json
import os
import subprocess
import sys
import tempfile
from typing import TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

console = Console()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(PROJECT_DIR, "venv", "bin", "python")
INPUT_FILE = os.path.join(PROJECT_DIR, "input_data", "mock-data-2.json")
ITERATIONS = 1_000_000


# ─── State ────────────────────────────────────────────────────────────────────

class OptimizationState(TypedDict):
    unoptimized_code: str      # original, never changes
    test_code: str             # test suite, never changes
    current_code: str          # latest LLM attempt
    baseline_emissions: float  # emissions of unoptimized_code (measured once at start)
    current_emissions: float   # emissions of current_code after last measure
    attempt: int               # current attempt number
    max_attempts: int          # e.g. 5
    feedback: list[str]        # history of failure reasons
    best_code: str             # best valid optimized code found so far
    best_emissions: float      # emissions of best_code
    done: bool
    test_passed: bool          # set by run_tests node
    carbon_improved: bool      # set by measure_emissions node


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_func_name(code: str) -> str:
    """Parse code with ast to find the first function name."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            return node.name
    raise ValueError("No function definition found in code")


def make_runner(code: str, func_name: str, iterations: int) -> str:
    """Build the subprocess runner script."""
    project_dir_repr = json.dumps(PROJECT_DIR)
    return f"""import json, sys, os
os.chdir({project_dir_repr})
from codecarbon import EmissionsTracker

{code}

tracker = EmissionsTracker(
    project_name="optimizer",
    log_level="ERROR",
    save_to_file=False,
    save_to_api=False,
    save_to_logger=False,
)
tracker.start()
for _ in range({iterations}):
    {func_name}()
tracker.stop()

emissions = tracker.final_emissions or 0.0
energy = 0.0
if tracker.final_emissions_data:
    energy = tracker.final_emissions_data.energy_consumed or 0.0
print(json.dumps({{"emissions": emissions, "energy": energy}}))
"""


def run_emissions(code: str, iterations: int = ITERATIONS) -> float:
    """Run code in a subprocess under CodeCarbon. Returns kg CO2eq."""
    func_name = get_func_name(code)
    runner_src = make_runner(code, func_name, iterations)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(runner_src)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [PYTHON, tmp_path],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_DIR,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Subprocess error:\n{result.stderr[-1000:]}")
        # Find JSON line in stdout (CodeCarbon may print other things)
        for line in reversed(result.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                return float(data["emissions"])
        raise RuntimeError(f"No JSON in subprocess output.\nstdout: {result.stdout[-500:]}")
    finally:
        os.unlink(tmp_path)


def strip_markdown(code: str) -> str:
    """Strip markdown code fences from LLM response."""
    lines = code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ─── Nodes ────────────────────────────────────────────────────────────────────

def node_measure_baseline(state: OptimizationState) -> dict:
    console.print("\n[bold cyan][Step 0] Measuring baseline emissions...[/bold cyan]")
    try:
        emissions = run_emissions(state["unoptimized_code"])
    except Exception as e:
        console.print(f"  [red]Baseline measurement failed: {e}[/red]")
        console.print("  [yellow]Using fallback baseline of 1e-10 kg CO2eq[/yellow]")
        emissions = 1e-10
    console.print(f"  Baseline: {emissions * 1000:.7f} g CO2eq  ✓")
    return {
        "baseline_emissions": emissions,
        "best_emissions": emissions,
        "best_code": state["unoptimized_code"],
        "current_emissions": emissions,
    }


def node_optimize(state: OptimizationState) -> dict:
    attempt = state["attempt"] + 1
    console.print(
        f"\n[bold yellow][Attempt {attempt}] Asking Claude to optimize...[/bold yellow]"
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_msg = (
        "You are a Python performance optimizer focused on minimizing CPU cycles and memory usage "
        "to reduce carbon emissions. Return ONLY the raw Python function code with no explanation, "
        "no markdown, no imports unless strictly required."
    )

    if state["feedback"]:
        feedback_text = "\n".join(f"- {f}" for f in state["feedback"])
        user_msg = (
            f"Previous attempts failed for these reasons:\n{feedback_text}\n\n"
            f"Try a different optimization approach for:\n\n{state['unoptimized_code']}\n\n"
            f"It must pass these tests:\n{state['test_code']}"
        )
    else:
        user_msg = (
            f"Optimize this Python function to be more carbon-efficient "
            f"(fewer CPU operations, less memory):\n\n{state['unoptimized_code']}\n\n"
            f"It must pass these tests:\n{state['test_code']}"
        )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system_msg,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text
    current_code = strip_markdown(raw)

    return {"current_code": current_code, "attempt": attempt}


def node_run_tests(state: OptimizationState) -> dict:
    console.print("  Running tests... ", end="")
    code = state["current_code"]
    test_code = state["test_code"]
    combined = code + "\n\n" + test_code

    try:
        namespace: dict = {}
        exec(compile(combined, "<optimizer>", "exec"), namespace)
        test_funcs = [
            v for k, v in namespace.items() if k.startswith("test_") and callable(v)
        ]
        if not test_funcs:
            raise AssertionError("No test_ functions found in test code")
        for fn in test_funcs:
            fn()
        console.print("[green]✓ Tests passed[/green]")
        return {"test_passed": True}
    except Exception as e:
        err = f"Attempt {state['attempt'] + 1}: {type(e).__name__}: {e}"
        console.print(f"[red]✗ Tests failed: {e}[/red]")
        return {
            "test_passed": False,
            "feedback": state["feedback"] + [err],
        }


def node_measure_emissions(state: OptimizationState) -> dict:
    console.print("  Measuring emissions...")
    try:
        emissions = run_emissions(state["current_code"])
    except Exception as e:
        console.print(f"  [red]Emissions measurement failed: {e}[/red]")
        feedback_entry = (
            f"Attempt {state['attempt']}: Emissions measurement error: {e}"
        )
        return {
            "carbon_improved": False,
            "feedback": state["feedback"] + [feedback_entry],
        }

    baseline = state["baseline_emissions"]
    change_pct = (emissions - baseline) / baseline * 100 if baseline > 0 else 0
    improved = emissions < baseline

    table = Table(show_header=True, header_style="bold")
    table.add_column("", style="bold", min_width=12)
    table.add_column("Emissions", justify="right", min_width=18)
    table.add_column("Change", justify="right", min_width=14)
    table.add_row("Original", f"{baseline * 1000:.7f} g CO2", "—")
    change_str = f"{change_pct:+.1f}%"
    change_display = f"{change_str} ✓" if improved else f"{change_str} ✗"
    table.add_row("Optimized", f"{emissions * 1000:.7f} g CO2", change_display)
    console.print(table)

    updates: dict = {
        "current_emissions": emissions,
        "carbon_improved": improved,
    }

    if improved and emissions < state["best_emissions"]:
        updates["best_code"] = state["current_code"]
        updates["best_emissions"] = emissions

    if not improved:
        feedback_entry = (
            f"Attempt {state['attempt']}: Carbon emissions did not improve "
            f"({change_str}). Try a different algorithmic approach."
        )
        updates["feedback"] = state["feedback"] + [feedback_entry]

    return updates


def node_output(state: OptimizationState) -> dict:
    baseline = state["baseline_emissions"]
    best = state["best_emissions"]
    change_pct = (best - baseline) / baseline * 100 if baseline > 0 else 0

    if best < baseline:
        title = "Success!"
        summary = (
            f"Optimized in {state['attempt']} attempt(s). "
            f"Carbon reduction: {abs(change_pct):.1f}%"
        )
        border = "green"
    else:
        title = "Completed (no carbon improvement found)"
        summary = (
            f"Ran {state['attempt']} attempt(s). "
            f"Best result: {change_pct:+.1f}% vs baseline."
        )
        border = "yellow"

    console.print(
        Panel(
            f"{summary}\n\n{state['best_code']}",
            title=title,
            border_style=border,
        )
    )

    # Write optimized_code back to JSON
    with open(INPUT_FILE) as f:
        data = json.load(f)
    data["optimized_code"] = state["best_code"]
    with open(INPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    console.print(f"[dim]Written optimized_code to {INPUT_FILE}[/dim]")

    return {"done": True}


# ─── Routing ──────────────────────────────────────────────────────────────────

def route_after_tests(state: OptimizationState) -> str:
    if state["test_passed"]:
        return "measure_emissions"
    elif state["attempt"] >= state["max_attempts"]:
        return "output"
    return "optimize"


def route_after_measure(state: OptimizationState) -> str:
    if state["carbon_improved"] or state["attempt"] >= state["max_attempts"]:
        return "output"
    return "optimize"


# ─── Graph ────────────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(OptimizationState)

    g.add_node("measure_baseline", node_measure_baseline)
    g.add_node("optimize", node_optimize)
    g.add_node("run_tests", node_run_tests)
    g.add_node("measure_emissions", node_measure_emissions)
    g.add_node("output", node_output)

    g.add_edge(START, "measure_baseline")
    g.add_edge("measure_baseline", "optimize")
    g.add_edge("optimize", "run_tests")
    g.add_conditional_edges(
        "run_tests",
        route_after_tests,
        {"optimize": "optimize", "measure_emissions": "measure_emissions", "output": "output"},
    )
    g.add_conditional_edges(
        "measure_emissions",
        route_after_measure,
        {"optimize": "optimize", "output": "output"},
    )
    g.add_edge("output", END)

    return g.compile()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error: ANTHROPIC_API_KEY not set. Create a .env file.[/red]")
        sys.exit(1)

    with open(INPUT_FILE) as f:
        data = json.load(f)

    unoptimized_code: str = data["unoptimized_code"]
    test_code: str = data["test_code"]

    console.print(
        Panel(
            f"Input: {unoptimized_code!r}\n"
            f"Test:  {test_code!r}\n"
            f"Max attempts: 5",
            title="Carbon Code Optimizer",
            border_style="blue",
        )
    )

    initial_state: OptimizationState = {
        "unoptimized_code": unoptimized_code,
        "test_code": test_code,
        "current_code": "",
        "baseline_emissions": 0.0,
        "current_emissions": 0.0,
        "attempt": 0,
        "max_attempts": 5,
        "feedback": [],
        "best_code": unoptimized_code,
        "best_emissions": float("inf"),
        "done": False,
        "test_passed": False,
        "carbon_improved": False,
    }

    graph = build_graph()
    graph.invoke(initial_state)


if __name__ == "__main__":
    main()
