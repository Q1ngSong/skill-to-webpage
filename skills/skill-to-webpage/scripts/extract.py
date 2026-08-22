#!/usr/bin/env python3
"""Phase 1 (Step 1a): decompose a Claude Code Skill directory into a local
knowledge base of directory/heading nodes. Zero LLM calls."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extractor.kb_writer import write_knowledge_base
from extractor.skill_walker import SkillMdNotFoundError, walk_skill


def main():
    parser = argparse.ArgumentParser(
        description="Decompose a Claude Code Skill into a local knowledge base (.kb/)."
    )
    parser.add_argument("skill_dir", help="Path to the Claude Code Skill directory (must contain SKILL.md)")
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory under which the knowledge base is created. Defaults to the skill directory's parent.",
    )
    parser.add_argument(
        "--name", default=None,
        help="Name of the knowledge-base directory under --output-dir (default: <skill-name>.kb). "
             "The one-sentence orchestration uses --name static so parsers can sit beside it.",
    )
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    try:
        backbone = walk_skill(skill_dir)
    except SkillMdNotFoundError as exc:
        sys.exit(str(exc))

    output_root = Path(args.output_dir).resolve() if args.output_dir else skill_dir.parent
    kb_name = args.name or f"{backbone.skill_name}.kb"
    kb_dir = output_root / kb_name
    if kb_dir.resolve().parent != output_root:
        sys.exit(
            f"Knowledge-base name {kb_name!r} is not a valid directory name; "
            "refusing to write outside the output directory."
        )
    write_knowledge_base(backbone, kb_dir)

    print(f"[OK] knowledge base: {kb_dir}")
    print(f"     nodes: {len(backbone.nodes)}")


if __name__ == "__main__":
    main()
