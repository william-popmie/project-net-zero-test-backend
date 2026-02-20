"""Emission measurement via subprocess + CodeCarbon."""

import ast
import json
import os
import subprocess
import tempfile

from optimizer.state import ITERATIONS, PYTHON, PROJECT_DIR


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
