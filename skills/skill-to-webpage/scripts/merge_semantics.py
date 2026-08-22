#!/usr/bin/env python3
"""合并多份解析器产物(各 <output_dir>/<parser>/semantics.json)为 <output_dir>/merged/。仅标准库。

用法:python3 scripts/merge_semantics.py <output_dir> --parsers my-parser agent [--static static]
        [--prefer my-parser] [--skill-dir DIR] [--report-only]

规则(见 references/parser-protocol.md):
  1. 静态骨架永远赢结构:节点 / 步骤 / 行号取自 static/,解析器只能在其上叠加。
  2. 同一锚点的语义断言一致 → 采纳并记 by=[解析器…];只有一家说 → 采纳并标来源;
     不一致 → 记入 conflicts,默认按「explicit 优于 inferred,其次 --prefer / 列表顺序」暂选,
     由渲染 Agent 回读原文裁决后改 merged/semantics.json。
  3. 每份产物先过 validate_semantics.py;不合格的解析器整体作废,不影响其他。
退出码:0 写出 merged;1 没有任何可用解析器。
"""
import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s2w_common import load_static, normalize_semantics, skeleton_of  # noqa: E402
from validate_semantics import Validator  # noqa: E402


def _key_claim(c):
    return (c.get("source", ""), c.get("quote", c.get("text", "")))


def _merge_claims(lists_by_parser):
    """{parser: [claim]} → 去重合并,claim 带 by。"""
    out, seen = [], {}
    for name, items in lists_by_parser.items():
        for c in items or []:
            k = _key_claim(c)
            if k in seen:
                seen[k]["by"].append(name)
                if c.get("basis", "explicit") == "explicit":
                    seen[k]["basis"] = "explicit"
            else:
                d = dict(c)
                d["by"] = [name]
                out.append(d)
                seen[k] = d
    return out


class Merger:
    def __init__(self, out_dir, parsers, static, prefer, skill_dir, bundle=None):
        self.out_dir = Path(out_dir)
        self.bundle = bundle
        self.static_dir = self.out_dir / (static or "static")
        self.static = load_static(self.static_dir)
        self.names = parsers
        self.prefer = prefer or (parsers[0] if parsers else None)
        self.skill_dir = skill_dir
        self.sems, self.invalid, self.dropped = {}, {}, {}
        self.conflicts, self.agree, self.single = [], 0, 0

    def load(self):
        shas = {}
        for name in self.names:
            v = Validator(self.out_dir / name, self.skill_dir, False, self.static_dir, bundle=self.bundle)
            code, sem, dropped, fatal = v.validate()
            if code != 0 or sem is None:
                self.invalid[name] = "不存在" if code == 2 else "; ".join(fatal) or "校验失败"
                continue
            self.sems[name] = normalize_semantics(sem)
            self.dropped[name] = dropped
            shas[name] = sem["source"].get("sha256")
        if len(set(shas.values())) > 1:
            base = shas.get(self.prefer) or list(shas.values())[0]
            for name, sha in list(shas.items()):
                if sha != base:
                    self.invalid[name] = "sha256 与其它解析器不一致(源版本不同)"
                    del self.sems[name]
        if self.prefer not in self.sems and self.sems:
            self.prefer = list(self.sems)[0]
        return bool(self.sems)

    # ---- 冲突裁决 ----
    def pick(self, key, cands, sources=None):
        """cands: {parser: value}。一致 → 采纳;不一致 → 记冲突并按规则暂选。"""
        vals = {json.dumps(v, ensure_ascii=False, sort_keys=True): v for v in cands.values()}
        if len(vals) == 1:
            if len(cands) > 1:
                self.agree += 1
            else:
                self.single += 1
            return list(vals.values())[0], list(cands)
        chosen_parser = self.prefer if self.prefer in cands else list(cands)[0]
        rule = "--prefer / 列表顺序"
        explicit = [p for p, v in cands.items() if isinstance(v, dict) and v.get("basis", "explicit") == "explicit"]
        if isinstance(list(cands.values())[0], dict) and 0 < len(explicit) < len(cands):
            chosen_parser = explicit[0] if self.prefer not in explicit else self.prefer
            rule = "explicit 优于 inferred"
        self.conflicts.append({"key": key, "candidates": cands, "sources": sources or {}, "chosen": chosen_parser, "rule": rule})
        return cands[chosen_parser], [chosen_parser]

    # ---- 步骤顺序 ----
    @staticmethod
    def _order_disagrees(tokens):
        """两两比较共有 token 的相对顺序;顺序不同才算分歧(各家步骤集合不同不算)。"""
        ps = [n for n, seq in tokens.items() if seq]
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                a, b = tokens[ps[i]], tokens[ps[j]]
                if [t for t in a if t in b] != [t for t in b if t in a]:
                    return True
        return False

    def order_steps(self, node, sn, static_by_line, imp, tokens):
        """按 prefer 解析器给出的排列输出步骤:静态步骤仍以静态行号为准,隐含步骤留在它的相对位置。

        解析器把隐含步骤插在静态步骤之间时,若一律「静态在前、隐含追加」,
        edges/checkpoints/loops/jumps/guards 里的步号会整体错位(下标仍在范围内,校验器看不出来)。"""
        static_order = [str(st["line_start"]) for st in sn["steps"]]

        def label(t):
            return static_by_line[t[1]]["title"] if t[0] == "s" else (imp[t].get("title") or imp[t].get("lines", ""))

        src = self.prefer if tokens.get(self.prefer) else next((n for n in self.sems if tokens.get(n)), None)
        seq = tokens.get(src) or []
        mentioned = {t[1] for t in seq if t[0] == "s"}
        out, placed, used = [], set(), set()
        for t in seq:
            if t[0] == "s":
                if t[1] in placed:
                    continue
                for x in static_order:  # 补上 prefer 没提到、且行号更靠前的静态步骤
                    if x not in placed and x not in mentioned and int(x) < int(t[1]):
                        placed.add(x)
                        out.append(static_by_line[x])
                placed.add(t[1])
                out.append(static_by_line[t[1]])
            else:
                used.add(t)
                out.append(imp[t])
        for x in static_order:
            if x not in placed:
                out.append(static_by_line[x])
        extra = [k for k in imp if k not in used]
        for k in extra:  # 只有非 prefer 解析器提到的隐含步骤:附在最后
            out.append(imp[k])
        reasons = []
        if self._order_disagrees(tokens):
            reasons.append("各解析器给的步骤顺序不一致")
        if extra:
            # 位置信息只有别家有,附在末尾就丢了 —— 必须让它出现在 merge-report.md 里
            reasons.append("%s 没提到的隐含步骤(%s)对不上位置,附在末尾" % (src, "、".join(label(k) for k in extra)))
        if reasons:
            self.conflicts.append({"key": "subflows.%s.order" % node,
                                   "candidates": {n: [label(t) for t in seq2] for n, seq2 in tokens.items() if seq2},
                                   "sources": {}, "chosen": src,
                                   "rule": ";".join(reasons) + " —— 暂按 --prefer / 列表顺序"})
        return out

    def merge(self):
        names = list(self.sems)
        first = self.sems[self.prefer]
        M = {"schema": "s2w-semantics/%d" % max([2] + [int(self.sems[n]["schema"].split("/")[-1]) for n in names]), "generator": "merge(" + ",".join(names) + ")",
             "generated_at": _dt.date.today().isoformat(), "source": dict(first["source"]),
             "skeleton": skeleton_of(self.static)}
        # thesis / groups / node_summaries:表述类,取 prefer,缺则补
        for key in ("thesis", "groups", "node_summaries"):
            for n in [self.prefer] + [x for x in names if x != self.prefer]:
                if self.sems[n].get(key):
                    M[key] = self.sems[n][key]
                    M[key + "_by"] = n
                    break
        # layers:逐节点表决
        M["layers"] = {}
        for node in [n["id"] for n in self.static["nodes"]]:
            cands = {n: self.sems[n]["layers"][node] for n in names if node in self.sems[n].get("layers", {})}
            if not cands:
                continue
            val, by = self.pick("layers." + node, {n: {"layer": v["layer"], "role": v.get("role", "")} for n, v in cands.items()},
                                {n: v.get("source", "") for n, v in cands.items()})
            entry = dict(cands[by[0]])
            entry.update(val)
            entry["by"] = by if len(by) > 1 or len(cands) == 1 else by
            M["layers"][node] = entry
        M["routing"] = {k: _merge_claims({n: self.sems[n].get("routing", {}).get(k, []) for n in names}) for k in ("triggers", "exclusions")}
        # subflows:静态步骤按行号对齐,隐含步骤按 (lines, title) 合并,顺序取 prefer 解析器的排列
        M["subflows"] = {}
        for sn in self.static["nodes"]:
            node = sn["id"]
            per = {n: self.sems[n].get("subflows", {}).get(node, []) for n in names}
            if not any(per.values()):
                continue
            static_by_line = {}
            for st in sn["steps"]:
                cands = {}
                for n, steps in per.items():
                    for s in steps:
                        if not s.get("implicit") and str(s.get("lines", "")).split("-")[0] == str(st["line_start"]):
                            cands[n] = s
                base = {"title": st["title"], "lines": "%d-%d" % (st["line_start"], st["line_end"])}
                if cands:
                    labels = {n: s["title"] for n, s in cands.items() if s.get("title") and s["title"] != st["title"]}
                    if labels:  # 解析器给的步骤别名(转述),静态标题仍是 title
                        base["label"], base["label_by"] = self.pick("subflows.%s.%s.label" % (node, st["line_start"]), labels) if len(set(labels.values())) > 1 else (list(labels.values())[0], list(labels))
                    types = {n: s.get("type") for n, s in cands.items() if s.get("type")}
                    if types:
                        base["type"], base["type_by"] = self.pick("subflows.%s.%s.type" % (node, st["line_start"]), types,
                                                                  {n: s.get("goal", {}).get("source", "") if isinstance(s.get("goal"), dict) else "" for n, s in cands.items()})
                    goals = {n: s["goal"] for n, s in cands.items() if s.get("goal")}
                    if goals:
                        base["goal"] = goals[self.prefer] if self.prefer in goals else list(goals.values())[0]
                        base["goal"]["by"] = [self.prefer] if self.prefer in goals else [list(goals)[0]]
                    base["semantics"] = {}
                    base["attachments"] = {}
                    for dim in sorted({d for s in cands.values() for d in (s.get("semantics") or {})}):
                        base["semantics"][dim] = _merge_claims({n: (s.get("semantics") or {}).get(dim, []) for n, s in cands.items()})
                    for cat in sorted({d for s in cands.values() for d in (s.get("attachments") or {})}):
                        base["attachments"][cat] = _merge_claims({n: (s.get("attachments") or {}).get(cat, []) for n, s in cands.items()})
                    base["by"] = list(cands)
                static_by_line[str(st["line_start"])] = base
            # 隐含步骤:同一 lines 上可以有多条(标题不同),按 (lines, title, 本解析器内第几次) 配对;
            # 同时记下每个解析器给出的步骤排列 token,供下面复原顺序
            imp, tokens = {}, {}
            for n, steps in per.items():
                seq, occ = [], {}
                for s in steps:
                    if s.get("implicit"):
                        lines, title = str(s.get("lines", "")), s.get("title", "")
                        idx = occ.get((lines, title), 0)
                        occ[(lines, title)] = idx + 1
                        k = ("i", lines, title, idx)
                        if k in imp:
                            imp[k]["by"].append(n)
                        else:
                            d = dict(s)
                            d["by"] = [n]
                            imp[k] = d
                        seq.append(k)
                    else:
                        ls = str(s.get("lines", "")).split("-")[0]
                        if ls in static_by_line and ("s", ls) not in seq:
                            seq.append(("s", ls))
                tokens[n] = seq
            M["subflows"][node] = self.order_steps(node, sn, static_by_line, imp, tokens)
        # edges / checkpoints / termination / 派生视图:按键并集
        def union(key, keyf):
            out, seen = [], {}
            for n in names:
                for item in self.sems[n].get(key, []):
                    k = keyf(item)
                    if k in seen:
                        seen[k]["by"].append(n)
                        if item.get("basis", "explicit") == "explicit":
                            seen[k]["basis"] = "explicit"
                    else:
                        d = dict(item)
                        d["by"] = [n]
                        out.append(d)
                        seen[k] = d
            return out
        # 边按 (from, to, type) 配对(loop 与 retry 视为同型);同端点多种边型是合法的
        # (例如 n02.11 → END 既是 termination 又是 fallback),只有各解析器给的边型集合
        # 不一致时才算冲突。
        etype = lambda t: "retry" if t in ("loop", "retry") else t  # noqa: E731
        M["edges"] = union("edges", lambda e: (e.get("from"), e.get("to"), etype(e.get("type"))))
        pairs = {}
        for n in names:
            for e in self.sems[n].get("edges", []):
                pairs.setdefault((e.get("from"), e.get("to")), {}).setdefault(n, set()).add(etype(e.get("type")))
        for (a, b), by_parser in pairs.items():
            if len({tuple(sorted(v)) for v in by_parser.values()}) > 1:
                self.conflicts.append({"key": "edges.%s->%s" % (a, b),
                                       "candidates": {n: sorted(v) for n, v in by_parser.items()}, "sources": {},
                                       "chosen": "全部保留", "rule": "同端点边型各家不一致,需回原文裁决"})
        M["checkpoints"] = union("checkpoints", lambda c: (c.get("at"), c.get("kind")))
        M["termination"] = union("termination", lambda c: c.get("at"))
        M["loops"] = union("loops", lambda l: (l.get("node"), l.get("from"), l.get("to")))
        M["jumps"] = union("jumps", lambda j: (j.get("node"), j.get("from"), j.get("to")))
        M["guards"] = union("guards", lambda g: (g.get("guard"), json.dumps(g.get("protects"), sort_keys=True)))
        M["global"] = {"semantics": {}, "attachments": {}}
        for scope in ("semantics", "attachments"):
            for k in sorted({d for n in names for d in (self.sems[n].get("global", {}).get(scope) or {})}):
                M["global"][scope][k] = _merge_claims({n: (self.sems[n].get("global", {}).get(scope) or {}).get(k, []) for n in names})
        profs = {n: self.sems[n]["wsa_profile"] for n in names if self.sems[n].get("wsa_profile")}
        if profs:
            M["wsa_profile"] = profs[self.prefer] if self.prefer in profs else list(profs.values())[0]
        # reconciliation:覆盖率按合并后重算,清单并集
        steps_total = sum(len(n["steps"]) for n in self.static["nodes"])
        typed = sum(1 for node, steps in M["subflows"].items() for s in steps if not s.get("implicit") and s.get("type"))
        R = {"nodes_total": len(self.static["nodes"]), "nodes_classified": len(M["layers"]), "steps_total": steps_total, "steps_typed": typed}
        for key in ("non_workflow_nodes", "implicit_steps", "order_deviations", "cross_anchored", "judgment_calls", "unanchored", "notes"):
            seen, items = set(), []
            for n in names:
                for x in self.sems[n].get("reconciliation", {}).get(key, []) or []:
                    k = json.dumps(x, ensure_ascii=False, sort_keys=True) if not isinstance(x, str) else x
                    if k not in seen:
                        seen.add(k)
                        items.append(x)
            R[key] = items
        M["reconciliation"] = R
        M["ambiguities"] = sorted({a for n in names for a in self.sems[n].get("ambiguities", [])})
        # 只有当分层覆盖全部静态节点时才是合格的 /2;否则(如仅 /1 解析器)降级为 /1,校验器按 /1 规则接受
        if len(M["layers"]) != len(self.static["nodes"]):
            M["schema"] = "s2w-semantics/1"
        M["merge"] = {"parsers": names, "invalid": self.invalid, "prefer": self.prefer, "agreements": self.agree,
                      "singletons": self.single, "conflicts": self.conflicts,
                      "dropped_claims": {n: len(d) for n, d in self.dropped.items()}}
        return M

    def report_md(self, M):
        L = ["# 合并报告 · %s" % self.static["skill_name"], "",
             "解析器:%s · 优先:%s · 一致 %d · 独有 %d · **冲突 %d**" % (", ".join(M["merge"]["parsers"]), self.prefer, self.agree, self.single, len(self.conflicts)), ""]
        if self.invalid:
            L += ["## 作废的解析器", ""] + ["- `%s`:%s" % (n, r) for n, r in self.invalid.items()] + [""]
        if self.dropped:
            L += ["## 各解析器作废条目", ""] + ["- `%s`:%d 条" % (n, len(d)) + ("" if not d else "  \n  " + "  \n  ".join(d[:8])) for n, d in self.dropped.items()] + [""]
        L += ["## 冲突明细(请回读原文裁决;改 merged/semantics.json 或加 --prefer 重跑)", ""]
        if not self.conflicts:
            L.append("无。")
        else:
            L += ["| 锚点 | 候选 | 依据 | 暂选 | 规则 |", "|---|---|---|---|---|"]
            for c in self.conflicts:
                cand = "<br>".join("`%s`: %s" % (p, json.dumps(v, ensure_ascii=False)) for p, v in c["candidates"].items())
                srcs = "<br>".join("`%s`: %s" % (p, s) for p, s in c["sources"].items())
                L.append("| %s | %s | %s | %s | %s |" % (c["key"], cand, srcs, c["chosen"], c["rule"]))
        L += ["", "## 覆盖", "", "节点 %d/%d 归类 · 步骤 %d/%d 分型 · 边 %d · 检查点 %d · 终止 %d" % (
            M["reconciliation"]["nodes_classified"], M["reconciliation"]["nodes_total"], M["reconciliation"]["steps_typed"],
            M["reconciliation"]["steps_total"], len(M["edges"]), len(M["checkpoints"]), len(M["termination"])), ""]
        return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output_dir")
    ap.add_argument("--parsers", nargs="+", required=True, help="解析器文件夹名(与 <output_dir>/<name>/semantics.json 对应)")
    ap.add_argument("--static", default="static")
    ap.add_argument("--prefer")
    ap.add_argument("--skill-dir")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--bundle", help="组清单 bundle.json(s2w-semantics/3:带前缀端点的校验需要)")
    a = ap.parse_args()
    m = Merger(a.output_dir, a.parsers, a.static, a.prefer, a.skill_dir, bundle=a.bundle)
    if not m.load():
        print("没有可用的解析器产物:" + json.dumps(m.invalid, ensure_ascii=False))
        return 1
    M = m.merge()
    report = m.report_md(M)
    if a.report_only:
        print(report)
        return 0
    out = Path(a.output_dir) / "merged"
    out.mkdir(parents=True, exist_ok=True)
    (out / "semantics.json").write_text(json.dumps(M, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "merge-report.md").write_text(report, encoding="utf-8")
    print("[merged] %s · 解析器 %s · 一致 %d · 独有 %d · 冲突 %d · 作废解析器 %s" % (
        out, ",".join(M["merge"]["parsers"]), m.agree, m.single, len(m.conflicts), list(m.invalid) or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
