"""LangGraph state machine: routing functions and graph builder."""

from langgraph.graph import END, START, StateGraph

from optimizer.nodes import (
    node_measure_baseline,
    node_measure_emissions,
    node_optimize,
    node_output,
    node_run_tests,
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


def build_graph():
    g = StateGraph(OptimizationState)

    g.add_node("measure_baseline", node_measure_baseline)
    g.add_node("optimize", node_optimize)
    g.add_node("run_tests", node_run_tests)
    g.add_node("measure_emissions", node_measure_emissions)
    g.add_node("output", node_output)

    g.add_edge(START, "measure_baseline")
    g.add_edge("measure_baseline", "optimize")
    g.add_edge("optimize", "run_tests")
    g.add_conditional_edges(
        "run_tests",
        route_after_tests,
        {"optimize": "optimize", "measure_emissions": "measure_emissions", "output": "output"},
    )
    g.add_conditional_edges(
        "measure_emissions",
        route_after_measure,
        {"optimize": "optimize", "output": "output"},
    )
    g.add_edge("output", END)

    return g.compile()
