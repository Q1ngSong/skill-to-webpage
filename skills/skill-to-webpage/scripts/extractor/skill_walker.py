"""Zero-LLM structural decomposition of a Claude Code Skill's SKILL.md."""

import re
from pathlib import Path

from .node_schema import Node, ResourceRef, SkillBackbone
from .slicer import slice_lines

FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
HEADING_RE = re.compile(r"^##\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
RESOURCE_RE = re.compile(r"(?<![\w/-])((?:scripts|templates|references|examples|assets)/[\w./-]+\.\w+)")


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


def split_into_nodes(all_lines: list[str], body_start_line: int) -> list[Node]:
    """Split the SKILL.md body into one Node per top-level (##) heading.

    Each node's `line_start`/`line_end` cover the heading line itself through
    the last line before the next heading (or end of file) — that whole span
    is the node's evidence range. `content` holds only the text after the
    heading line. If there are no `##` headings at all, the whole body
    becomes a single "Overview" node (or no nodes, if the body is blank).
    """
    start_idx = body_start_line - 1
    headings: list[tuple[int, str]] = []
    in_fence = False
    for i in range(start_idx, len(all_lines)):
        if FENCE_RE.match(all_lines[i]):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(all_lines[i])
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


def merge_short_nodes(nodes: list[Node], min_content_lines: int = 3) -> list[Node]:
    """Fold nodes whose content has fewer than `min_content_lines` non-blank
    lines into a neighbor, so near-empty sections don't render as their own
    near-empty page. A short node merges into the previous node; if the very
    first node is short, it merges forward into the next one instead.
    """
    if len(nodes) <= 1:
        return nodes

    def content_line_count(node: Node) -> int:
        return len([line for line in node.content.splitlines() if line.strip()])

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
                "### " + absorbed.title + "\n" + absorbed.content + "\n\n" + target.content
            ).strip("\n")
            target.line_start = absorbed.line_start
            target.resources = absorbed.resources + target.resources
            del result[0]
        else:
            prev = result[i - 1]
            absorbed = result[i]
            prev.content = (
                prev.content + "\n\n### " + absorbed.title + "\n" + absorbed.content
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
    nodes = split_into_nodes(all_lines, body_start_line)
    nodes = merge_short_nodes(nodes)
    for node in nodes:
        node.resources = find_resources(node.content, skill_dir)

    return SkillBackbone(
        skill_name=frontmatter.get("name") or skill_dir.resolve().name,
        description=frontmatter.get("description", ""),
        source_path=str(skill_md_path),
        nodes=nodes,
    )
