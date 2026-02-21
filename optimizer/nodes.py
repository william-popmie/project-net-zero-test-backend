"""LangGraph node functions."""

import ast
import os

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from optimizer.emissions import run_emissions
from optimizer.state import OPTIMIZED_FILE, PYTHON, OptimizationState
from optimizer.utils import strip_markdown

console = Console()


def _build_full_context(state: OptimizationState, current_func_source: str) -> str:
    """Build full file context: preamble + all functions with current replaced."""
    current_idx = state["current_func_idx"]
    all_funcs = state["all_functions"]
    parts = []

    preamble = state.get("file_preamble", "")
    if preamble:
        parts.append(preamble)

    for i, func in enumerate(all_funcs):
        if i == current_idx:
            parts.append(current_func_source)
        else:
            parts.append(func["source"])

    return "\n\n".join(parts)


def node_extract_functions(state: OptimizationState) -> dict:
    console.print("\n[bold cyan][Setup] Extracting functions from source file...[/bold cyan]")

    source = state["full_source"]
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    functions = []
    first_func_line = None  # 1-indexed

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_source = ast.get_source_segment(source, node)
            functions.append({"name": node.name, "source": func_source})
            if first_func_line is None:
                first_func_line = node.lineno

    if first_func_line is not None and first_func_line > 1:
        preamble = "".join(lines[: first_func_line - 1]).rstrip()
    else:
        preamble = ""

    if not functions:
        console.print("[yellow]No functions found in the input file. Nothing to optimize.[/yellow]")
    else:
        names = ", ".join(f["name"] for f in functions)
        console.print(f"  Found {len(functions)} function(s): {names}")

    return {
        "all_functions": functions,
        "file_preamble": preamble,
        "current_func_idx": 0,
        "function_results": {},
    }


def node_find_or_create_spec(state: OptimizationState) -> dict:
    current_idx = state["current_func_idx"]
    func_info = state["all_functions"][current_idx]
    func_name = func_info["name"]
    func_source = func_info["source"]
    total = len(state["all_functions"])

    console.print(
        f"\n[bold blue]{'─' * 60}[/bold blue]"
        f"\n[bold blue][Function {current_idx + 1}/{total}] {func_name}[/bold blue]"
    )
    console.print("[bold cyan]  Finding or generating tests...[/bold cyan]")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    raw_test_file = state.get("raw_test_file", "")
    if raw_test_file:
        user_msg = (
            f"Here is a Python function:\n\n{func_source}\n\n"
            f"Here is an existing test file:\n\n{raw_test_file}\n\n"
            f"Extract all test_* functions from the test file that test '{func_name}'. "
            f"If none are found, generate a minimal set of correctness tests for this function. "
            f"Return ONLY raw Python test functions (no imports, no module-level code). "
            f"The tests will be exec()'d in a namespace that already contains the function."
        )
    else:
        user_msg = (
            f"Here is a Python function:\n\n{func_source}\n\n"
            f"Generate a minimal set of correctness tests for this function. "
            f"Return ONLY raw Python test functions (no imports, no module-level code). "
            f"The tests will be exec()'d in a namespace that already contains the function. "
            f"Each test function name must start with 'test_'."
        )

    system_msg = (
        "You are a Python test engineer. Return ONLY raw Python test functions with no imports, "
        "no module-level code, and no markdown. Each function name must start with 'test_'. "
        "Tests will be exec()'d in a namespace that already contains the function under test."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system_msg,
        messages=[{"role": "user", "content": user_msg}],
    )
    test_code = strip_markdown(response.content[0].text)
    console.print(f"  [dim]Tests ready ({len(test_code.splitlines())} lines)[/dim]")

    return {
        "unoptimized_code": func_source,
        "test_code": test_code,
        "current_code": func_source,
        "attempt": 0,
        "feedback": [],
        "best_code": func_source,
        "best_emissions": float("inf"),
        "test_passed": False,
        "carbon_improved": False,
    }


def node_measure_baseline(state: OptimizationState) -> dict:
    console.print("\n[bold cyan][Step 0] Measuring baseline emissions...[/bold cyan]")
    func_name = state["all_functions"][state["current_func_idx"]]["name"]
    full_code = _build_full_context(state, state["unoptimized_code"])
    python = state.get("target_python") or PYTHON

    try:
        emissions = run_emissions(full_code, func_name, python_interpreter=python)
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

    current_idx = state["current_func_idx"]
    all_funcs = state["all_functions"]
    preamble = state.get("file_preamble", "")

    # Build combined: preamble + other functions + current_code + test_code
    parts = []
    if preamble:
        parts.append(preamble)
    for i, func in enumerate(all_funcs):
        if i != current_idx:
            parts.append(func["source"])
    parts.append(state["current_code"])
    parts.append(state["test_code"])
    combined = "\n\n".join(parts)

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
    func_name = state["all_functions"][state["current_func_idx"]]["name"]
    full_code = _build_full_context(state, state["current_code"])
    python = state.get("target_python") or PYTHON

    try:
        emissions = run_emissions(full_code, func_name, python_interpreter=python)
    except Exception as e:
        console.print(f"  [red]Emissions measurement failed: {e}[/red]")
        feedback_entry = f"Attempt {state['attempt']}: Emissions measurement error: {e}"
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


def node_save_function_result(state: OptimizationState) -> dict:
    current_idx = state["current_func_idx"]
    func_name = state["all_functions"][current_idx]["name"]
    baseline = state["baseline_emissions"]
    best = state["best_emissions"]
    change_pct = (best - baseline) / baseline * 100 if baseline > 0 else 0

    if best < baseline:
        status = f"[green]{change_pct:+.1f}%[/green]"
        verdict = "improved"
    else:
        status = f"[yellow]{change_pct:+.1f}%[/yellow]"
        verdict = "no improvement"

    console.print(
        f"\n  [{func_name}] {verdict}: "
        f"{baseline * 1000:.7f} → {best * 1000:.7f} g CO2 ({status})"
    )

    new_function_results = dict(state.get("function_results") or {})
    new_function_results[func_name] = {
        "code": state["best_code"],
        "baseline": baseline,
        "best_emissions": best,
    }

    return {
        "function_results": new_function_results,
        "current_func_idx": current_idx + 1,
    }


def node_assemble_output(state: OptimizationState) -> dict:
    function_results = state.get("function_results") or {}
    parts = []

    preamble = state.get("file_preamble", "")
    if preamble:
        parts.append(preamble)

    for func in state["all_functions"]:
        func_name = func["name"]
        result = function_results.get(func_name)
        code = result["code"] if isinstance(result, dict) and "code" in result else func["source"]
        parts.append(code)

    full_output = "\n\n".join(parts) + "\n"

    # Determine output path
    input_file = state.get("input_file", "")
    if input_file and input_file != OPTIMIZED_FILE:
        stem = os.path.splitext(input_file)[0]
        output_path = stem + "_optimized.py"
    else:
        output_path = OPTIMIZED_FILE

    with open(output_path, "w") as f:
        f.write(full_output)

    # Print final summary table
    table = Table(title="Optimization Summary", show_header=True, header_style="bold")
    table.add_column("Function", style="bold")
    table.add_column("Baseline (g CO2)", justify="right")
    table.add_column("Optimized (g CO2)", justify="right")
    table.add_column("Improvement", justify="right")

    total_baseline = 0.0
    total_best = 0.0

    for func in state["all_functions"]:
        func_name = func["name"]
        result = function_results.get(func_name)
        if isinstance(result, dict) and "baseline" in result:
            b = result["baseline"]
            best = result["best_emissions"]
            total_baseline += b
            total_best += best
            change_pct = (best - b) / b * 100 if b > 0 else 0
            change_str = f"{change_pct:+.1f}%"
            color = "green" if best < b else "yellow"
            table.add_row(
                func_name,
                f"{b * 1000:.7f}",
                f"{best * 1000:.7f}",
                f"[{color}]{change_str}[/{color}]",
            )
        else:
            table.add_row(func_name, "—", "—", "—")

    console.print(table)

    if total_baseline > 0:
        overall_pct = (total_best - total_baseline) / total_baseline * 100
        color = "green" if total_best < total_baseline else "yellow"
        console.print(
            f"\n[bold]Overall:[/bold] "
            f"{total_baseline * 1000:.7f} → {total_best * 1000:.7f} g CO2 "
            f"([{color}]{overall_pct:+.1f}%[/{color}])"
        )

    console.print(f"[dim]Written optimized file to {output_path}[/dim]")

    return {"done": True}
