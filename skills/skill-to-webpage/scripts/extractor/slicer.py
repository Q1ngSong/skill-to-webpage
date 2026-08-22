def slice_lines(all_lines: list[str], line_start: int, line_end: int) -> str:
    """Return the text spanning 1-indexed, inclusive [line_start, line_end]."""
    if line_start > line_end:
        return ""
    return "\n".join(all_lines[line_start - 1:line_end])
