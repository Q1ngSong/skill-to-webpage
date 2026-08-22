"""skill-to-webpage 共用读取逻辑:静态知识库(static/)与语义文件的归一化。仅标准库。"""
import json
import re
from pathlib import Path

FENCE = ("```", "~~~")


def parse_frontmatter_block(text):
    """返回 (dict, body)。frontmatter 形如 ---\\nk: v\\n---。"""
    m = re.match(r"\A---\n(.*?\n)---\n", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def steps_in_range(lines, line_start, line_end):
    """在 full_text 的 [line_start, line_end](1 起,含)范围内定位 ### 标题 → 子步骤;围栏内不算。行号精确。"""
    steps, fence = [], False
    for ln in range(line_start, line_end + 1):
        line = lines[ln - 1] if ln - 1 < len(lines) else ""
        if line.lstrip().startswith(FENCE):
            fence = not fence
            continue
        if not fence and line.startswith("### "):
            steps.append({"title": line[4:].strip(), "line_start": ln})
    for j, s in enumerate(steps):
        s["line_end"] = steps[j + 1]["line_start"] - 1 if j + 1 < len(steps) else line_end
        s["content"] = "\n".join(lines[s["line_start"]:s["line_end"]]).strip("\n")
    return steps


def load_static(static_dir):
    """读取阶段 1 产物:INDEX.md(R 层)+ nodes/*.md + full_text.md + metadata.json。"""
    static_dir = Path(static_dir)
    meta = json.loads((static_dir / "metadata.json").read_text(encoding="utf-8"))
    full = (static_dir / "full_text.md").read_text(encoding="utf-8").lstrip("﻿").replace("\r\n", "\n")
    lines = full.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    index = (static_dir / "INDEX.md").read_text(encoding="utf-8")
    m = re.search(r"^> (.*)$", index, re.M)
    description = m.group(1).strip() if m and not m.group(1).startswith("(no description") else ""
    nodes = []
    for f in sorted((static_dir / "nodes").glob("n*.md")):
        fm, body = parse_frontmatter_block(f.read_text(encoding="utf-8"))
        # kb_writer 在 frontmatter 后写了一个空行再写 content;content 首行对应 SKILL.md 的 line_start + 1
        if body.startswith("\n"):
            body = body[1:]
        resources = []
        if "\n## Resources" in "\n" + body:
            main, _, res = body.partition("## Resources")
            body = main
            for line in res.splitlines():
                mm = re.match(r"- (\S+) \((exists|missing)\)", line.strip())
                if mm:
                    resources.append([mm.group(1), mm.group(2) == "exists"])
        ls, le = int(fm["line_start"]), int(fm["line_end"])
        # 节点正文从 ## 标题的下一行开始:kb 里 content 不含标题行,首行号 = line_start + 1
        steps = steps_in_range(lines, ls, le)
        nodes.append({
            "id": fm["id"], "title": json.loads(fm["title"]) if fm["title"].startswith('"') else fm["title"],
            "line_start": ls, "line_end": le, "content": body.strip("\n"), "resources": resources,
            "steps": steps,
        })
    return {
        "skill_name": meta["skill_name"], "source_path": meta.get("source_path", ""),
        "description": description, "nodes": nodes, "lines": lines,
        "generated_at": meta.get("generated_at", ""),
    }


def skeleton_of(static):
    return {"from": "static/INDEX.md", "nodes": [
        {"id": n["id"], "title": n["title"], "lines": "%d-%d" % (n["line_start"], n["line_end"]), "steps": len(n["steps"])}
        for n in static["nodes"]]}


def src_text(static, source, strip_fence=True):
    m = re.match(r"SKILL\.md:(\d+)(?:-(\d+))?$", source)
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    ls = static["lines"][a - 1:b]
    if strip_fence:
        ls = [l for l in ls if not l.strip().startswith(FENCE)]
    return "\n".join(ls).strip("\n")


def normalize_semantics(sem):
    """把 /1 的派生视图(loops/jumps/guards)折算成 edges;补齐缺省容器。原地修改并返回。"""
    sem.setdefault("edges", [])
    have = {(e.get("from"), e.get("to"), e.get("type")) for e in sem["edges"]}
    # 同义边型:loops 折算成 retry,但同端点已有 loop 就算已存在;jumps 折算成 condition_true,
    # 同端点已有 condition_true / condition_false 也算已存在(否则一条边会被画两遍)
    loopy = {(e.get("from"), e.get("to")) for e in sem["edges"] if e.get("type") in ("retry", "loop")}
    condy = {(e.get("from"), e.get("to")) for e in sem["edges"] if e.get("type") in ("condition_true", "condition_false")}

    def add(frm, to, typ, cond, src, equiv=None):
        key = (frm, to, typ)
        if key in have or (equiv is not None and (frm, to) in equiv):
            return
        have.add(key)
        if equiv is not None:
            equiv.add((frm, to))
        e = {"from": frm, "to": to, "type": typ, "condition": cond, "source": src.get("source", "")}
        if src.get("quote"):
            e["quote"] = src["quote"]
        if src.get("basis"):
            e["basis"] = src["basis"]
        e["derived_from"] = "view"
        sem["edges"].append(e)

    for l in sem.get("loops", []):
        add("%s.%d" % (l["node"], l["from"]), "%s.%d" % (l["node"], l["to"]), "retry", l.get("label", ""), l, loopy)
    for j in sem.get("jumps", []):
        add("%s.%d" % (j["node"], j["from"]), "%s.%d" % (j["node"], j["to"]), "condition_true", j.get("when", ""), j, condy)
    for g in sem.get("guards", []):
        p = g["protects"]
        add("%s.%d" % (p["node"], p["step"]), g["guard"], "fallback", g.get("label", ""), g)
    for key in ("layers", "node_summaries", "subflows", "routing", "global", "reconciliation"):
        sem.setdefault(key, {} if key != "routing" else {"triggers": [], "exclusions": []})
    for key in ("checkpoints", "termination", "groups", "ambiguities", "loops", "jumps", "guards"):
        sem.setdefault(key, [])
    return sem


EP_RE = re.compile(r"^(?:([a-z0-9][a-z0-9_-]*):)?(n\d{2})(?:\.(\d+))?$")


def parse_ep(ep):
    """端点 → (skill|None, node|None, step|None)。支持 `n03` / `n03.2` / `writing-plans:n02.3` / `END`(s2w-semantics/3)。
    非法输入返回 (None, None, None)。"""
    if not isinstance(ep, str):
        return None, None, None
    if ep == "END":
        return None, "END", None
    m = EP_RE.match(ep)
    if not m:
        return None, None, None
    return m.group(1), m.group(2), int(m.group(3)) if m.group(3) else None


def fmt_ep(skill, node, step=None):
    s = node if step is None else "%s.%d" % (node, step)
    return "%s:%s" % (skill, s) if skill else s


SRC_SPAN_RE = re.compile(r":(\d+)(?:-(\d+))?\s*$")


def source_span(source):
    """出处 → (起行, 止行)。`SKILL.md:13` → (13, 13);`alpha/SKILL.md:13-15` → (13, 15);取不到返回 None。"""
    m = SRC_SPAN_RE.search(str(source or ""))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return (a, b) if a <= b else (b, a)


def ref_backs_edge(ref, edge_source, from_node=None):
    """一条 cross-ref 是否支撑这条边:引用行落在边 source 的行范围内,或两者出自同一个节点。
    validate_semantics(校验 delegate 边有引用撑腰)与 render_bundle(印证区判断引用是否被采纳)共用同一判定。"""
    span, rl = source_span(edge_source), source_span(ref.get("source"))
    if span and rl and span[0] <= rl[0] <= span[1]:
        return True
    return bool(ref.get("from_node") and from_node and ref["from_node"] == from_node)

