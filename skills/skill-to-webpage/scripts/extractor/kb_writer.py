"""Serializes a SkillBackbone to a <skill-name>.kb/ directory on disk."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .node_schema import Node, SkillBackbone

SOURCE_FILENAME = "SKILL.md"


def _slugify(title: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in title)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "node"


def _node_filename(node: Node) -> str:
    return f"{node.id}-{_slugify(node.title)}.md"


def _render_node_md(node: Node) -> str:
    lines = [
        "---",
        f"id: {node.id}",
        f"title: {json.dumps(node.title, ensure_ascii=False)}",
        f"line_start: {node.line_start}",
        f"line_end: {node.line_end}",
        f"source: {SOURCE_FILENAME}",
        "---",
        "",
        node.content,
        "",
    ]
    if node.resources:
        lines.append("## Resources")
        for res in node.resources:
            status = "exists" if res.exists else "missing"
            lines.append(f"- {res.path} ({status})")
        lines.append("")
    return "\n".join(lines)


def _render_index_md(backbone: SkillBackbone) -> str:
    lines = [
        f"# {backbone.skill_name} — Workflow Backbone Index",
        "",
        "## Routing Header (R)",
        "",
        f"> {backbone.description}" if backbone.description else "> (no description found)",
        "",
        "## Nodes",
        "",
        "| # | Title | Lines |",
        "|---|---|---|",
    ]
    for node in backbone.nodes:
        lines.append(f"| {node.id} | {node.title} | {SOURCE_FILENAME}:{node.line_start}-{node.line_end} |")
    lines.append("")
    return "\n".join(lines)


def _produced_by_us(kb_dir: Path) -> bool:
    """A directory is ours if it carries the metadata.json marker we write."""
    meta = kb_dir / "metadata.json"
    if not meta.exists():
        return False
    try:
        return "skill_name" in json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False


def write_knowledge_base(backbone: SkillBackbone, kb_dir: Path) -> None:
    if kb_dir.exists():
        if not (kb_dir.name.endswith(".kb") or _produced_by_us(kb_dir)):
            raise ValueError(
                "Refusing to overwrite a directory that does not look like a "
                "knowledge base (expected a name ending in '.kb' or a metadata.json "
                f"marker written by skill-to-webpage): {kb_dir}"
            )
        shutil.rmtree(kb_dir)
    nodes_dir = kb_dir / "nodes"
    nodes_dir.mkdir(parents=True)

    (kb_dir / "INDEX.md").write_text(_render_index_md(backbone), encoding="utf-8")

    for node in backbone.nodes:
        node_path = nodes_dir / _node_filename(node)
        node_path.write_text(_render_node_md(node), encoding="utf-8")

    full_text = Path(backbone.source_path).read_text(encoding="utf-8")
    (kb_dir / "full_text.md").write_text(full_text, encoding="utf-8")

    metadata = {
        "skill_name": backbone.skill_name,
        "source_path": backbone.source_path,
        "node_count": len(backbone.nodes),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (kb_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
