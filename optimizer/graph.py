"""LangGraph state machine: routing functions and graph builder."""

from langgraph.graph import END, START, StateGraph

from optimizer.nodes import (
    node_assemble_output,
    node_extract_functions,
    node_find_or_create_spec,
    node_measure_baseline,
    node_measure_emissions,
    node_optimize,
    node_run_tests,
    node_save_function_result,
)
from optimizer.state import OptimizationState


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


def route_after_save(state: OptimizationState) -> str:
    # current_func_idx was already incremented by node_save_function_result
    if state["current_func_idx"] < len(state["all_functions"]):
        return "find_or_create_spec"
    return "assemble_output"


def build_graph():
    g = StateGraph(OptimizationState)

    g.add_node("extract_functions", node_extract_functions)
    g.add_node("find_or_create_spec", node_find_or_create_spec)
    g.add_node("measure_baseline", node_measure_baseline)
    g.add_node("optimize", node_optimize)
    g.add_node("run_tests", node_run_tests)
    g.add_node("measure_emissions", node_measure_emissions)
    g.add_node("save_function_result", node_save_function_result)
    g.add_node("assemble_output", node_assemble_output)

    g.add_edge(START, "extract_functions")
    g.add_edge("extract_functions", "find_or_create_spec")
    g.add_edge("find_or_create_spec", "measure_baseline")
    g.add_edge("measure_baseline", "optimize")
    g.add_edge("optimize", "run_tests")
    g.add_conditional_edges(
        "run_tests",
        route_after_tests,
        {
            "optimize": "optimize",
            "measure_emissions": "measure_emissions",
            # "output" maps to save_function_result to keep route_after_tests logic unchanged
            "output": "save_function_result",
        },
    )
    g.add_conditional_edges(
        "measure_emissions",
        route_after_measure,
        {
            "optimize": "optimize",
            "output": "save_function_result",
        },
    )
    g.add_conditional_edges(
        "save_function_result",
        route_after_save,
        {
            "find_or_create_spec": "find_or_create_spec",
            "assemble_output": "assemble_output",
        },
    )
    g.add_edge("assemble_output", END)

    return g.compile()
