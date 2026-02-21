# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the optimizer

```bash
# Requires .env with ANTHROPIC_API_KEY set
venv/bin/python main.py
```

Reads `input_data/unoptimized_code.py` and `input_data/test_code.py`, optimizes the code using Claude, and writes the result to `input_data/optimized_code.py`.

## Validate CodeCarbon setup

```bash
venv/bin/python test_scripts/test_codecarbon.py
```

## Environment setup

All dependencies are pre-installed in `venv/` (Python 3.13). No install step needed.

Create a `.env` file at the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
```

CodeCarbon is configured via `.codecarbon.config` (output dir: `codecarbon_output/`, tracking mode: process).

## Architecture

`main.py` reads input files, builds the initial `OptimizationState`, and invokes the LangGraph state machine defined in the `optimizer/` package.

### optimizer/ package

| File | Purpose |
|------|---------|
| `graph.py` | LangGraph graph definition and conditional routing |
| `nodes.py` | Node implementations: `node_measure_baseline`, `node_optimize`, `node_run_tests`, `node_measure_emissions`, `node_output` |
| `emissions.py` | Subprocess-isolated CodeCarbon measurement via `run_emissions()` |
| `state.py` | `OptimizationState` TypedDict; path constants `PYTHON`, `INPUT_DIR`, `UNOPTIMIZED_FILE`, `TEST_FILE`, `OPTIMIZED_FILE`; `ITERATIONS = 1_000_000` |
| `utils.py` | `strip_markdown()` to remove ``` fences from LLM responses |

### State flow

```
START → measure_baseline → optimize → run_tests
                                          ↓ (pass)       ↓ (fail, retries left)
                                    measure_emissions → optimize
                                          ↓ (improved or max attempts)
                                        output → END
```

### Key design decisions

- **Subprocess isolation**: `run_emissions()` in `emissions.py` writes a runner script to a tempfile and executes it via `venv/bin/python` to avoid CodeCarbon's singleton `EmissionsTracker` conflicts. JSON result is parsed from stdout.
- **In-process test execution**: `node_run_tests()` runs tests via `exec()`. Test functions are discovered by scanning the namespace for callables prefixed with `test_`.
- **Best-effort tracking**: `state["best_code"]` / `state["best_emissions"]` track the lowest-emissions valid result across all attempts. Only best code is written to `optimized_code.py` on exit.
- **Feedback accumulation**: Failed attempts (test failures or no emission improvement) append error messages to `state["feedback"]`, which are included in Claude's next prompt.
- **Emissions runner**: `emissions.py` uses `ast` to auto-detect the function name and argument count, then generates a zero-argument call (e.g. `f(0, 0)`) to loop `ITERATIONS` times under the tracker.
- **Model**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) is called from `node_optimize()`.
