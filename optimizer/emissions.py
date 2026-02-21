"""Emission measurement via subprocess + CodeCarbon."""

import ast
import json
import os
import subprocess
import tempfile

from optimizer.state import ITERATIONS, PYTHON, PROJECT_DIR


def get_named_func_call(code: str, func_name: str) -> str:
    """Return a call expression for the named function using default/placeholder values."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            n_args = len(node.args.args)
            n_defaults = len(node.args.defaults)
            n_no_default = n_args - n_defaults
            arg_values = []
            for i in range(n_args):
                default_idx = i - n_no_default
                if default_idx >= 0:
                    arg_values.append(ast.unparse(node.args.defaults[default_idx]))
                else:
                    arg_values.append("1")
            return f"{func_name}({', '.join(arg_values)})"
    raise ValueError(f"Function '{func_name}' not found in code")


def make_runner(code: str, func_call: str, iterations: int) -> str:
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
    {func_call}
tracker.stop()

emissions = tracker.final_emissions or 0.0
energy = 0.0
if tracker.final_emissions_data:
    energy = tracker.final_emissions_data.energy_consumed or 0.0
print(json.dumps({{"emissions": emissions, "energy": energy}}))
"""


def run_emissions(
    code: str,
    func_name: str,
    iterations: int = ITERATIONS,
    python_interpreter: str = PYTHON,
) -> float:
    """Run code in a subprocess under CodeCarbon. Returns kg CO2eq.

    Args:
        code: Full file context (preamble + all functions).
        func_name: Name of the function to benchmark.
        iterations: Number of loop iterations for the benchmark.
        python_interpreter: Path to the Python interpreter to use.
    """
    func_call = get_named_func_call(code, func_name)
    runner_src = make_runner(code, func_call, iterations)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(runner_src)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [python_interpreter, tmp_path],
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
