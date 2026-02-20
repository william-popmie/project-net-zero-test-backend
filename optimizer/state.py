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
