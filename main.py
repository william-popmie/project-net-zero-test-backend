#!/usr/bin/env python3
"""Entry point for the carbon code optimizer."""

import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()

from optimizer import build_graph
from optimizer.state import UNOPTIMIZED_FILE, TEST_FILE, OptimizationState

console = Console()


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error: ANTHROPIC_API_KEY not set. Create a .env file.[/red]")
        sys.exit(1)

    with open(UNOPTIMIZED_FILE) as f:
        unoptimized_code = f.read()
    with open(TEST_FILE) as f:
        test_code = f.read()

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
