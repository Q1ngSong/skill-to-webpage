#!/usr/bin/env python3
"""组级零 LLM 抽取:对组目录下每个 <name>/SKILL.md 跑静态拆解,扫描成员之间的跨引用事实,写 bundle.json。

用法:python3 scripts/extract_bundle.py <组目录> --output-dir output/<组名> [--name <组名>]
产物:output/<组名>/bundle.json · output/<组名>/bundle/static/cross-refs.json · output/<组名>/<成员>/static/
"""
import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extractor.kb_writer import write_knowledge_base
from extractor.skill_walker import SkillMdNotFoundError, walk_skill
from s2w_common import load_static

CROSS_REF_SCHEMA = "s2w-cross-refs/1"
BUNDLE_SCHEMA = "s2w-bundle/1"


def find_members(group_dir):
    return sorted(p for p in Path(group_dir).iterdir() if p.is_dir() and (p / "SKILL.md").exists())


def ref_patterns(names):
    """按名字长度降序,避免前缀误配。返回 [(kind, compiled_regex)],group(1) 是成员名的书写形式
    (规范化回成员名见 canon_name)。
    kind:token(`x:<name>`)· path(`skills/<name>`)· name(反引号 / 加粗 / 斜杠)· word(裸成员名,词边界;噪音最高,由语义层裁定)。

    四类都认名字的空格 / 大小写变体:`Executing Plans` · `**Subagent-Driven Development**` ·
    `test driven development` —— 连字符位可写成空格或连字符,整体不区分大小写;
    `to_skill` 由 canon_name 规范化回成员名,`quote` 保留原样书写。"""
    ordered = sorted(names, key=len, reverse=True)
    alt = "|".join("[- ]".join(re.escape(p) for p in n.split("-")) for n in ordered)
    return [
        ("token", re.compile(r"(?<![\w/-])[a-z0-9_-]+:(%s)(?![\w-])" % alt, re.I)),
        ("path", re.compile(r"skills/(%s)(?![\w-])" % alt, re.I)),
        ("name", re.compile(r"`(%s)`" % alt, re.I)),
        ("name", re.compile(r"\*\*(%s)\*\*" % alt, re.I)),
        ("name", re.compile(r"(?<![\w/-])/(%s)(?![\w-])" % alt, re.I)),
        ("word", re.compile(r"(?<![\w/:`*-])(%s)(?![\w`*-])" % alt, re.I)),
    ]


def canon_name(matched, names_lower):
    """匹配到的书写形式 → 成员名:小写、空格折回连字符。认不出就原样返回(交给未知名过滤)。"""
    return names_lower.get(matched.lower().replace(" ", "-"), matched)


def node_at(static, ln):
    for n in static["nodes"]:
        if n["line_start"] <= ln <= n["line_end"]:
            return n["id"]
    return None


def scan_cross_refs(members, statics):
    """members: [(name, skill_dir)];statics: {name: load_static(...)}。返回事实表列表(同一行同一目标只记一条)。"""
    names = [n for n, _ in members]
    pats = ref_patterns(names)
    names_lower = {n.lower(): n for n in names}
    known = set(names)
    refs = []
    for name, sdir in members:
        lines = (sdir / "SKILL.md").read_text(encoding="utf-8").lstrip("﻿").replace("\r\n", "\n").split("\n")
        seen = set()
        for i, line in enumerate(lines, 1):
            for kind, rx in pats:
                for m in rx.finditer(line):
                    to = canon_name(m.group(1), names_lower)
                    if to not in known or to == name or (i, to) in seen:
                        continue
                    seen.add((i, to))
                    refs.append({"from_skill": name, "from_node": node_at(statics[name], i), "source": "SKILL.md:%d" % i,
                                 "quote": m.group(0), "to_skill": to, "kind": kind})
    return refs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("group_dir")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--name", default=None, help="组名,默认组目录名")
    a = ap.parse_args()
    group = Path(a.group_dir).resolve()
    out = Path(a.output_dir).resolve()
    name = a.name or group.name
    member_dirs = find_members(group)
    if not member_dirs:
        sys.exit("组目录下没有任何 <name>/SKILL.md:%s" % group)
    out.mkdir(parents=True, exist_ok=True)
    members, statics, rows = [], {}, []
    for d in member_dirs:
        try:
            backbone = walk_skill(d)
        except SkillMdNotFoundError as exc:
            sys.exit(str(exc))
        kb = out / d.name / "static"
        write_knowledge_base(backbone, kb)
        st = load_static(kb)
        statics[d.name] = st
        members.append((d.name, d))
        raw = (d / "SKILL.md").read_bytes()
        rows.append({"name": d.name, "skill_dir": str(d), "static": "%s/static" % d.name,
                     "page": "%s/%s-workflow.html" % (d.name, d.name),
                     "sha256": hashlib.sha256(raw).hexdigest(), "lines": len(st["lines"]), "nodes": len(st["nodes"])})
        print("[static] %-32s nodes %d" % (d.name, len(st["nodes"])))
    refs = scan_cross_refs(members, statics)
    (out / "bundle" / "static").mkdir(parents=True, exist_ok=True)
    (out / "bundle" / "static" / "cross-refs.json").write_text(json.dumps(
        {"schema": CROSS_REF_SCHEMA, "bundle": name, "generated_at": _dt.date.today().isoformat(), "refs": refs},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "bundle.json").write_text(json.dumps(
        {"schema": BUNDLE_SCHEMA, "name": name, "generated_at": _dt.date.today().isoformat(),
         "members": rows, "cross_refs": "bundle/static/cross-refs.json"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    linked = {(r["from_skill"], r["to_skill"]) for r in refs}
    print("[bundle] %s · 成员 %d · 跨引用 %d 条(%d 对 skill)" % (out / "bundle.json", len(rows), len(refs), len(linked)))


if __name__ == "__main__":
    main()
