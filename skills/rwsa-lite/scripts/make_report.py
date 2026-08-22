#!/usr/bin/env python3
"""把 <kb>/semantics.json(s2w-semantics/2)渲染成 <kb>/semantics-report.md(印证报告)。仅标准库。
用法:python3 make_report.py <kb目录>"""
import json
import sys
from pathlib import Path


def tbl(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def claim_counts(step):
    ns = sum(len(v) for v in (step.get("semantics") or {}).values())
    na = sum(len(v) for v in (step.get("attachments") or {}).values())
    return ns, na


def basis_counts(obj):
    ex = inf = 0
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if "source" in o and "quote" in o:
                if o.get("basis", "explicit") == "inferred":
                    inf += 1
                else:
                    ex += 1
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return ex, inf


def main(kb):
    kb = Path(kb)
    sem = json.loads((kb / "semantics.json").read_text(encoding="utf-8"))
    sk = sem.get("skeleton", {})
    rec = sem.get("reconciliation", {})
    prof = sem.get("wsa_profile", {})
    layers = sem.get("layers", {})
    L = []
    L.append(f"# 语义印证报告 · {sem['source']['file']}({sem['generator']},{sem.get('generated_at', '')})\n")
    L.append(f"schema `{sem['schema']}` · 源 {sem['source']['lines']} 行 · sha256 `{sem['source']['sha256'][:12]}…`  ")
    if prof:
        L.append(f"W/S/A 强度 **{prof.get('W')}/{prof.get('S')}/{prof.get('A')}** → **{prof.get('label', '')}**")
        for n in prof.get("notes", []):
            L.append(f"- {n}")
    if sem.get("thesis"):
        L.append(f"\n> 总纲:{sem['thesis']['text']}({sem['thesis']['source']})\n")

    L.append("## 1 · 目录(静态)vs 分层(语义)\n")
    rows = []
    for n in sk.get("nodes", []):
        ly = layers.get(n["id"], {})
        verdict = "流程节点" if ly.get("layer") == "W" else f"非流程标题 → {ly.get('layer', '?')} 层"
        rows.append([n["id"], n["title"], n["lines"], n.get("steps", 0), f"{ly.get('layer', '?')} / {ly.get('role', '')}", verdict])
    L.append(tbl(["节点", "标题", "行号", "### 步数", "归属 / 角色", "印证结论"], rows))
    L.append(f"\n覆盖:节点 {rec.get('nodes_classified', '?')}/{rec.get('nodes_total', '?')} 已归类,"
             f"步骤 {rec.get('steps_typed', '?')}/{rec.get('steps_total', '?')} 已分型。\n")

    L.append("## 2 · 步骤分型与语义密度\n")
    rows = []
    for node, steps in sem.get("subflows", {}).items():
        for i, s in enumerate(steps, 1):
            ns, na = claim_counts(s)
            rows.append([f"{node}.{i}", s["title"], s.get("type", ""), "隐含" if s.get("implicit") else "目录", s.get("lines", ""), ns, na])
    L.append(tbl(["步骤", "标题", "类型", "来源", "行号", "语义条", "附件条"], rows))

    edges = sem.get("edges", [])
    L.append("\n## 3 · 边(非顺序)\n")
    L.append(tbl(["from", "to", "type", "condition", "basis", "source"],
                 [[e["from"], e["to"], e["type"], e.get("condition", ""), e.get("basis", "explicit"), e["source"]] for e in edges]))
    cross = [e for e in edges if e["to"] != "END" and e["from"].split(".")[0] != e["to"].split(".")[0]]
    L.append(f"\n共 {len(edges)} 条,其中跨节点 {len(cross)} 条。\n")

    L.append("## 4 · 检查点与终止\n")
    rows = [[c["at"], c["kind"], c.get("basis", "explicit"), c["source"], c.get("quote", "")] for c in sem.get("checkpoints", [])]
    rows += [[t["at"], "termination", t.get("basis", "explicit"), t["source"], t.get("text", "")] for t in sem.get("termination", [])]
    L.append(tbl(["位置", "类型", "basis", "source", "依据 / 说明"], rows))

    L.append("\n## 5 · 印证:目录与实际流程的偏差\n")

    def sect(title, items, fmt):
        L.append(f"**{title}**({len(items)})\n")
        if items:
            for x in items:
                L.append(f"- {fmt(x)}")
        else:
            L.append("- 无")
        L.append("")

    sect("非流程标题", rec.get("non_workflow_nodes", []), lambda x: f"`{x['node']}` → {x['layer']} 层:{x.get('why', '')}")
    sect("隐含步骤(文本有、目录无)", rec.get("implicit_steps", []), lambda x: f"锚 `{x['anchor']}`,{x['count']} 步({x['source']})")
    sect("顺序偏差(文档顺序 ≠ 执行顺序)", rec.get("order_deviations", []), lambda x: f"{x['text']}({x['source']})")
    sect("跨锚定(知识写在别处)", rec.get("cross_anchored", []), lambda x: f"{x['item']} ← `{x['from_node']}`({x['source']})")
    sect("裁定记录", rec.get("judgment_calls", []), lambda x: f"`{x.get('anchor', '')}` {x['text']}({x['source']})")
    sect("无法锚定", rec.get("unanchored", []), lambda x: str(x))
    for n in rec.get("notes", []):
        L.append(f"> {n}")
    ex, inf = basis_counts(sem)
    L.append(f"\n断言总数 {ex + inf}:explicit {ex} · inferred {inf}\n")

    L.append("## 6 · 逐步语义明细\n")
    for node, steps in sem.get("subflows", {}).items():
        for i, s in enumerate(steps, 1):
            L.append(f"### {node}.{i} {s['title']} · {s.get('type', '')}{' · 隐含' if s.get('implicit') else ''}")
            if s.get("goal"):
                L.append(f"- goal:{s['goal']['text']}({s['goal']['source']})")
            for dim, items in (s.get("semantics") or {}).items():
                for it in items:
                    L.append(f"- {dim}:{it['text']}({it['source']}{', inferred' if it.get('basis') == 'inferred' else ''})")
            for cat, items in (s.get("attachments") or {}).items():
                for it in items:
                    L.append(f"- 附件/{cat}:{it['text']}({it['source']})")
            L.append("")
    g = sem.get("global", {})
    if g:
        L.append("### 全局(不属于单步)")
        for dim, items in (g.get("semantics") or {}).items():
            for it in items:
                L.append(f"- {dim}:{it['text']}({it['source']})")
        for cat, items in (g.get("attachments") or {}).items():
            for it in items:
                L.append(f"- 附件/{cat}:{it['text']}({it['source']})")
        L.append("")

    out = kb / "semantics-report.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[report] {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: make_report.py <kb目录>")
    main(sys.argv[1])
