"""Shared state type and project-wide constants."""

import os
from typing import TypedDict


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(PROJECT_DIR, "venv", "bin", "python")
INPUT_DIR        = os.path.join(PROJECT_DIR, "input_data")
UNOPTIMIZED_FILE = os.path.join(INPUT_DIR, "unoptimized_code.py")
TEST_FILE        = os.path.join(INPUT_DIR, "test_code.py")
OPTIMIZED_FILE   = os.path.join(INPUT_DIR, "optimized_code.py")
ITERATIONS = 1_000_000


class OptimizationState(TypedDict):
    # Per-run file context (set once at startup)
    input_file: str            # absolute path to target .py file
    target_python: str         # python interpreter path (default: PYTHON)
    all_functions: list        # [{"name": str, "source": str}, ...] from AST
    file_preamble: str         # imports + module-level code before first function
    full_source: str           # complete original file content
    raw_test_file: str         # full content of --tests file (empty string if none)
    current_func_idx: int      # index into all_functions
    function_results: dict     # {func_name: {"code": str, "baseline": float, "best_emissions": float}}

    # Per-function fields (reset by node_find_or_create_spec each iteration)
    unoptimized_code: str      # current function source (original), never changes within a function
    test_code: str             # test suite for current function
    current_code: str          # latest LLM attempt
    baseline_emissions: float  # emissions of unoptimized_code (measured once per function)
    current_emissions: float   # emissions of current_code after last measure
    attempt: int               # current attempt number
    max_attempts: int          # e.g. 5
    feedback: list[str]        # history of failure reasons
    best_code: str             # best valid optimized code found so far
    best_emissions: float      # emissions of best_code
    done: bool
    test_passed: bool          # set by run_tests node
    carbon_improved: bool      # set by measure_emissions node
