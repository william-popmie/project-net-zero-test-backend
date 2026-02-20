# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the optimizer

```bash
# Requires .env with ANTHROPIC_API_KEY set
venv/bin/python optimizer.py
```

The script reads `input_data/mock-data-2.json`, optimizes the `unoptimized_code` field using Claude, and writes the result back to `optimized_code` in the same file.

## Environment setup

All dependencies are pre-installed in `venv/` (Python 3.13). No install step needed.

Create a `.env` file at the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## Architecture

`optimizer.py` implements a LangGraph state machine that iteratively optimizes Python functions for lower carbon emissions:

**State flow:**
```
START → measure_baseline → optimize → run_tests
                                          ↓ (pass)       ↓ (fail, retries left)
                                    measure_emissions → optimize
                                          ↓ (improved or max attempts)
                                        output → END
```

**Key design decisions:**
- Emission measurement runs code in a **subprocess** (not in-process) via `run_emissions()` to isolate CodeCarbon's `EmissionsTracker`. The runner script is written to a tempfile, executed with `venv/bin/python`, and the result is parsed from JSON on stdout.
- Tests are run **in-process** via `exec()` in `node_run_tests()`.
- Up to 5 attempts by default (`max_attempts`). Failed attempts accumulate in `state["feedback"]` and are fed back to Claude on the next attempt.
- The best-emissions code (not just the last) is tracked in `state["best_code"]` / `state["best_emissions"]` and written to the JSON on exit.

**Input data formats:**
- `mock-data-2.json` — flat format: `{unoptimized_code, test_code, optimized_code}`
- `mock-data.json` — graph format: nodes with `depends_on`/`depended_by`, `execution_order`, top-level `original_code`/`optimized_code`/`spec_code`

**CodeCarbon output** is written to `codecarbon_output/` (tracked in git).
