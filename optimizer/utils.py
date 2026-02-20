"""Utility helpers."""


def strip_markdown(code: str) -> str:
    """Strip markdown code fences from LLM response."""
    lines = code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
