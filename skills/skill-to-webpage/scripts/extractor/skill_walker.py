"""Zero-LLM structural decomposition of a Claude Code Skill's SKILL.md."""

import re
from pathlib import Path

from .node_schema import Node, ResourceRef, SkillBackbone
from .slicer import slice_lines

FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
RESOURCE_RE = re.compile(r"(?<![\w/-])((?:scripts|templates|references|examples|assets)/[\w./-]+\.\w+)")

_KNOWN_FM_KEYS = {"name", "description"}


def scan_headings(all_lines: list[str], body_start_line: int) -> list[dict]:
    """Return fenced-code-aware H1-H6 headings with their structural parent."""
    start_idx = body_start_line - 1
    headings, stack, in_fence = [], [], False
    for i in range(start_idx, len(all_lines)):
        if FENCE_RE.match(all_lines[i]):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(all_lines[i])
        if not match:
            continue
        level = len(match.group(1))
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        heading = {
            "title": match.group(2).strip(),
            "line": i + 1,
            "level": level,
            "parent": stack[-1]["line"] if stack else None,
        }
        headings.append(heading)
        stack.append(heading)
    return headings


def _normal_title(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip().lower()


def analyze_heading_hierarchy(
    all_lines: list[str], body_start_line: int, skill_name: str = ""
) -> dict:
    """Map source headings to relative L1/L2/L3 workflow structure.

    Clear singleton document wrappers are removed before the first remaining
    observed source level becomes the node level. Only the first three
    remaining levels are structural; deeper headings stay in source text.
    """
    headings = scan_headings(all_lines, body_start_line)
    observed = sorted({h["level"] for h in headings})
    if not observed:
        return {
            "observed_levels": [],
            "ignored_wrappers": [],
            "relative_mapping": {"1": 2, "2": 3, "3": 4},
            "node_level": 2,
            "step_level": 3,
            "detail_level": 4,
        }

    active, ignored = list(observed), []
    while len(active) > 1:
        level, next_level = active[0], active[1]
        at_level = [h for h in headings if h["level"] == level]
        if len(at_level) != 1:
            break
        wrapper = at_level[0]
        first_deeper = next(
            (h for h in headings if h["line"] > wrapper["line"] and h["level"] > level),
            None,
        )
        if first_deeper is None:
            break
        direct = all_lines[wrapper["line"]:first_deeper["line"] - 1]
        direct_lines = sum(1 for line in direct if line.strip())
        title_matches_name = bool(skill_name) and _normal_title(wrapper["title"]) == _normal_title(skill_name)
        next_has_siblings = sum(1 for h in headings if h["level"] == next_level) >= 2
        shallow_document_title = level == 1 and next_has_siblings and direct_lines <= 2
        if not (title_matches_name or shallow_document_title):
            break
        ignored.append({
            "level": level,
            "line": wrapper["line"],
            "title": wrapper["title"],
            "reason": "single document wrapper",
        })
        active.pop(0)

    # Hard invariant: H1 is always the document title, never a node boundary —
    # regardless of whether the heuristic above recognized it as a "wrapper".
    # A descriptive H1 (title != skill name, with real prose/warnings under it)
    # would otherwise fall through and get promoted to node_level.
    if active and active[0] == 1:
        lvl = active.pop(0)
        at_level = [h for h in headings if h["level"] == lvl]
        wrapper = at_level[0] if len(at_level) == 1 else None
        ignored.append({
            "level": lvl,
            "line": wrapper["line"] if wrapper else None,
            "title": wrapper["title"] if wrapper else None,
            "reason": "H1 is always the document title, never a node boundary",
        })

    if not active:
        return {
            "observed_levels": observed,
            "ignored_wrappers": ignored,
            "relative_mapping": {"1": 2, "2": 3, "3": 4},
            "node_level": 2,
            "step_level": 3,
            "detail_level": 4,
        }

    chosen = active[:3]
    mapping = {str(i + 1): level for i, level in enumerate(chosen)}
    return {
        "observed_levels": observed,
        "ignored_wrappers": ignored,
        "relative_mapping": mapping,
        "node_level": chosen[0],
        "step_level": chosen[1] if len(chosen) > 1 else None,
        "detail_level": chosen[2] if len(chosen) > 2 else None,
    }


def detect_node_level(all_lines: list[str], body_start_line: int) -> int:
    """Backward-compatible node-level accessor for callers and tests."""
    return analyze_heading_hierarchy(all_lines, body_start_line)["node_level"]


class SkillMdNotFoundError(Exception):
    pass


def _format_node_id(index: int) -> str:
    return f"n{index + 1:02d}"


def parse_frontmatter(text: str) -> tuple[dict, int]:
    """Return (frontmatter dict, 1-indexed line number where the body starts).

    Only supports single-line scalar `key: value` frontmatter entries, which
    is the format every Claude Code Skill in this project uses for `name`
    and `description`.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, 1
    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        frontmatter[key.strip()] = value
    body_start_line = match.group(0).count("\n") + 1
    return frontmatter, body_start_line


def split_into_nodes(all_lines: list[str], body_start_line: int, node_level: int = 2) -> list[Node]:
    """Split the SKILL.md body into one Node per top-level heading.

    Each node's `line_start`/`line_end` cover the heading line itself through
    the last line before the next heading (or end of file) — that whole span
    is the node's evidence range. `content` holds only the text after the
    heading line. If there are no headings at the given level, the whole body
    becomes a single "Overview" node (or no nodes, if the body is blank).
    """
    heading_re = re.compile(r"^" + "#" * node_level + r"\s+(.*)$")
    start_idx = body_start_line - 1
    headings: list[tuple[int, str]] = []
    in_fence = False
    for i in range(start_idx, len(all_lines)):
        if FENCE_RE.match(all_lines[i]):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = heading_re.match(all_lines[i])
        if m:
            headings.append((i, m.group(1).strip()))

    if not headings:
        content = slice_lines(all_lines, body_start_line, len(all_lines)).strip("\n")
        if not content.strip():
            return []
        return [Node(
            id=_format_node_id(0),
            title="Overview",
            content=content,
            line_start=body_start_line,
            line_end=len(all_lines),
        )]

    nodes = []
    for idx, (line_idx, title) in enumerate(headings):
        end_idx = headings[idx + 1][0] - 1 if idx + 1 < len(headings) else len(all_lines) - 1
        heading_line = line_idx + 1
        end_line = end_idx + 1
        content = slice_lines(all_lines, heading_line + 1, end_line).strip("\n")
        nodes.append(Node(
            id=_format_node_id(idx),
            title=title,
            content=content,
            line_start=heading_line,
            line_end=end_line,
        ))
    return nodes


def merge_short_nodes(
    nodes: list[Node], min_content_lines: int = 3, child_heading_level: int = 3
) -> list[Node]:
    """Fold nodes whose content has fewer than `min_content_lines` non-blank
    lines into a neighbor, so near-empty sections don't render as their own
    near-empty page. A short node merges into the previous node; if the very
    first node is short, it merges forward into the next one instead.
    """
    if len(nodes) <= 1:
        return nodes

    def content_line_count(node: Node) -> int:
        return len([line for line in node.content.splitlines() if line.strip()])

    child_heading = "#" * max(1, min(child_heading_level, 6)) + " "
    result = list(nodes)
    i = 0
    while len(result) > 1 and i < len(result):
        if content_line_count(result[i]) >= min_content_lines:
            i += 1
            continue
        if i == 0:
            absorbed = result[0]
            target = result[1]
            target.content = (
                child_heading + absorbed.title + "\n" + absorbed.content + "\n\n" + target.content
            ).strip("\n")
            target.line_start = absorbed.line_start
            target.resources = absorbed.resources + target.resources
            del result[0]
        else:
            prev = result[i - 1]
            absorbed = result[i]
            prev.content = (
                prev.content + "\n\n" + child_heading + absorbed.title + "\n" + absorbed.content
            ).strip("\n")
            prev.line_end = absorbed.line_end
            prev.resources = prev.resources + absorbed.resources
            del result[i]

    for idx, node in enumerate(result):
        node.id = _format_node_id(idx)
    return result


def find_resources(content: str, skill_dir: Path) -> list[ResourceRef]:
    """Find references to files under scripts/templates/references/examples/assets
    inside a node's content, and check whether each referenced file actually
    exists under skill_dir. Deduplicates by path, keeping first-seen order.
    """
    seen: dict[str, ResourceRef] = {}
    for match in RESOURCE_RE.finditer(content):
        rel_path = match.group(1)
        if ".." in rel_path.split("/"):
            continue
        if rel_path in seen:
            continue
        seen[rel_path] = ResourceRef(path=rel_path, exists=(skill_dir / rel_path).exists())
    return list(seen.values())


def walk_skill(skill_dir: Path) -> SkillBackbone:
    """Run the full zero-LLM Step 1a pipeline against a Claude Code Skill
    directory: locate SKILL.md, parse frontmatter, split into nodes, merge
    short nodes, and scan each node for resource references.
    """
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise SkillMdNotFoundError(
            "skill-to-webpage needs a Claude Code Skill directory path that "
            f"contains SKILL.md. Not found: {skill_md_path}"
        )
    text = skill_md_path.read_text(encoding="utf-8")
    text = text.lstrip("﻿").replace("\r\n", "\n")
    all_lines = text.splitlines()
    frontmatter, body_start_line = parse_frontmatter(text)
    extra_metadata = {k: v for k, v in frontmatter.items() if k not in _KNOWN_FM_KEYS and v}
    skill_name = frontmatter.get("name") or skill_dir.resolve().name
    heading_hierarchy = analyze_heading_hierarchy(
        all_lines, body_start_line, skill_name=skill_name
    )
    node_level = heading_hierarchy["node_level"]
    nodes = split_into_nodes(all_lines, body_start_line, node_level=node_level)
    child_heading_level = heading_hierarchy.get("step_level") or min(node_level + 1, 6)
    nodes = merge_short_nodes(nodes, child_heading_level=child_heading_level)
    for node in nodes:
        node.resources = find_resources(node.content, skill_dir)

    return SkillBackbone(
        skill_name=skill_name,
        description=frontmatter.get("description", ""),
        source_path=str(skill_md_path),
        nodes=nodes,
        extra_metadata=extra_metadata,
        node_level=node_level,
        heading_hierarchy=heading_hierarchy,
    )
