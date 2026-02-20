"""LangGraph node functions."""

import os

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from optimizer.emissions import run_emissions
from optimizer.state import OPTIMIZED_FILE, OptimizationState
from optimizer.utils import strip_markdown

console = Console()


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

    with open(OPTIMIZED_FILE, "w") as f:
        f.write(state["best_code"])
    console.print(f"[dim]Written optimized_code to {OPTIMIZED_FILE}[/dim]")

    return {"done": True}
