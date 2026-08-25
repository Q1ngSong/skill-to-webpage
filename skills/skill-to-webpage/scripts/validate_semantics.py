#!/usr/bin/env python3
"""渲染端契约校验(references/semantics-contract.md「渲染端校验与回落」)。仅标准库。

用法:python3 scripts/validate_semantics.py <semantics目录或文件> --static <static目录> [--skill-dir <源skill目录>] [--json]
      旧布局(semantics.json 与 INDEX.md 同目录)可省略 --static。
退出码:0 = 可用(可能有作废条目) · 1 = 整体回落 · 2 = semantics.json 不存在
--json 额外输出校验后(作废条目已剔除)的 semantics,供渲染脚本直接消费。
也可作为模块使用:Validator(sem_path, static_dir, skill_dir).validate() -> (code, sem, dropped, fatal)
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s2w_common import load_static, parse_ep, ref_backs_edge  # noqa: E402

SCHEMAS = {"s2w-semantics/1", "s2w-semantics/2", "s2w-semantics/3"}
SRC_RE = re.compile(r"^SKILL\.md:(\d+)(?:-(\d+))?$")
QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def norm(s):
    return re.sub(r"\s+", " ", s.translate(QUOTE_MAP)).strip()


class Validator:
    def __init__(self, kb, skill_dir=None, emit_json=False, static=None, bundle=None):
        kb = Path(kb)
        self.sem_file = kb if kb.is_file() else kb / "semantics.json"
        self.kb = self.sem_file.parent
        self.static = Path(static) if static else self.kb
        self.skill_dir = Path(skill_dir) if skill_dir else None
        self.emit_json = emit_json
        self.sem = None
        self.fatal, self.dropped, self.ok = [], [], 0
        self.src_lines = []
        self.ids = []
        self.subflows = {}
        # s2w-semantics/3:组上下文(带 skill 前缀的端点、delegate 边核验)
        self.bundle, self.bundle_dir = None, None
        self.member_ids, self.member_steps, self.cross_refs, self.self_name = {}, {}, [], None
        if bundle:
            bp = Path(bundle).resolve()
            self.bundle_dir = bp.parent
            self.bundle = json.loads(bp.read_text(encoding="utf-8"))
            cr = self.bundle_dir / self.bundle.get("cross_refs", "bundle/static/cross-refs.json")
            if cr.exists():
                self.cross_refs = json.loads(cr.read_text(encoding="utf-8")).get("refs", [])

    # ---- helpers ----
    def fail(self, msg):
        self.fatal.append(msg)

    def drop(self, where, why):
        self.dropped.append(f"{where}: {why}")

    def load_source(self, sem):
        cands = [self.skill_dir / sem["source"]["file"]] if self.skill_dir else []
        cands.append(self.static / "full_text.md")
        for p in cands:
            if p.exists():
                raw = p.read_bytes()
                text = raw.decode("utf-8").lstrip("﻿").replace("\r\n", "\n")
                self.src_lines = text.split("\n")
                if self.src_lines and self.src_lines[-1] == "":
                    self.src_lines.pop()
                return p, hashlib.sha256(raw).hexdigest()
        return None, None

    def load_members(self):
        """组成员的节点 id 与步数(优先成员已有的语义层 subflows,否则数静态相对 L2),供前缀端点核对。"""
        if not self.bundle:
            return
        meta = json.loads((self.static / "metadata.json").read_text(encoding="utf-8"))
        # 组内身份认目录名(cross-refs 的 from_skill / to_skill、member_ids 都是目录名);
        # frontmatter 的 name 只在这份 static 不属于任何成员时兜底。
        here = self.static.resolve()
        self.self_name = next((m["name"] for m in self.bundle.get("members", [])
                               if (self.bundle_dir / m["static"]).resolve() == here), None) or meta.get("skill_name")
        for m in self.bundle.get("members", []):
            sdir = self.bundle_dir / m["static"]
            if not (sdir / "INDEX.md").exists():
                continue
            self.member_ids[m["name"]] = sorted(set(re.findall(r"\b(n\d{2})\b", (sdir / "INDEX.md").read_text(encoding="utf-8"))))
            steps = {}
            for cand in ("merged", "agent"):
                f = self.bundle_dir / m["name"] / cand / "semantics.json"
                if f.exists():
                    try:
                        steps = {k: len(v) for k, v in json.loads(f.read_text(encoding="utf-8")).get("subflows", {}).items()}
                    except Exception:  # noqa: BLE001
                        steps = {}
                    break
            if not steps:
                # 手数某个绝对标题层级既不适应源文档层级,也会把围栏内标题误算为子步骤;
                # load_static 走映射后的 steps_in_range,与渲染端对步骤的切法完全一致(围栏感知)。
                steps = {n["id"]: len(n["steps"]) for n in load_static(sdir)["nodes"]}
            self.member_steps[m["name"]] = steps

    def ep_ok(self, ep):
        skill, node, step = parse_ep(ep)
        if node is None:
            return False
        if node == "END":
            return True
        if skill is None:
            if node not in self.ids:
                return False
            return step is None or 1 <= step <= len(self.subflows.get(node, []))
        if node not in self.member_ids.get(skill, []):
            return False
        return step is None or 1 <= step <= self.member_steps.get(skill, {}).get(node, 0)

    @staticmethod
    def ep_prefixed(ep):
        return parse_ep(ep)[0] is not None

    def delegate_backed(self, e):
        """delegate 边必须对应至少一条 cross-ref:同 from_skill、同 to_skill,且引用行落在边的 source 行内或同一节点。"""
        to_skill = parse_ep(e["to"])[0]
        from_node = parse_ep(e["from"])[1]
        for r in self.cross_refs:
            if r["from_skill"] != self.self_name or r["to_skill"] != to_skill:
                continue
            if ref_backs_edge(r, e.get("source", ""), from_node):   # 与 render_bundle 的印证判定同一份
                return True
        return False

    def check_claim(self, where, c):
        """source 越界 / quote 不在引用行内 → 作废。返回 True = 保留。"""
        src = c.get("source")
        if not src:
            self.drop(where, "缺 source")
            return False
        m = SRC_RE.match(src)
        if not m:
            self.drop(where, f"source 格式错 {src!r}")
            return False
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if not (1 <= a <= b <= len(self.src_lines)):
            self.drop(where, f"source 越界 {src}")
            return False
        q = c.get("quote")
        if q is not None and norm(q) not in norm(" ".join(self.src_lines[a - 1:b])):
            self.drop(where, f"quote 不在 {src} 内: {q!r}")
            return False
        self.ok += 1
        return True

    def keep(self, where, items):
        return [c for c in items if self.check_claim(where, c)]

    # ---- main ----
    def validate(self):
        """静默校验。返回 (code, sem_or_None, dropped, fatal)。"""
        code = self._validate()
        return code, self.sem, self.dropped, self.fatal

    def run(self):
        code = self._validate()
        if code == 2:
            print("semantics.json 不存在 → 临场语义判断")
            return 2
        if self.sem is None:
            print("整体回落:JSON 非法")
            return 1
        return self.report(self.sem, code)

    def _validate(self):
        f = self.sem_file
        if not f.exists():
            return 2
        try:
            sem = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            self.fail(f"JSON 非法 {e}")
            return 1
        self.sem = sem
        if sem.get("schema") not in SCHEMAS:
            self.fail(f"schema 不支持 {sem.get('schema')!r}")
        p, sha = self.load_source(sem)
        if p is None:
            self.fail("找不到源文件(需 --skill-dir 或 kb/full_text.md)")
        else:
            if self.skill_dir and sha != sem["source"].get("sha256"):
                self.fail("sha256 不符(源已变更,需重跑拆解器)")
            if sem["source"].get("lines") != len(self.src_lines):
                self.fail(f"source.lines={sem['source'].get('lines')} ≠ 实际 {len(self.src_lines)}")
        if self.fatal:
            return 1

        self.ids = sorted(set(re.findall(r"\b(n\d{2})\b", (self.static / "INDEX.md").read_text(encoding="utf-8"))))
        self.subflows = sem.get("subflows", {})
        self.load_members()
        v2 = sem["schema"].split("/")[-1] in ("2", "3")
        if v2:
            missing = [n for n in self.ids if n not in sem.get("layers", {})]
            if missing:
                self.fail(f"layers 未覆盖节点 {missing}")
            rec = sem.get("reconciliation")
            if rec is None:
                self.fail("缺 reconciliation")
            elif rec.get("unanchored"):
                self.fail(f"unanchored 非空 {rec['unanchored']}")
            if self.fatal:
                return 1

        if sem.get("thesis"):
            if not self.check_claim("thesis", sem["thesis"]):
                sem["thesis"] = None
        for g in sem.get("groups", []):
            bad = [n for n in g.get("nodes", []) if n not in self.ids]
            if bad:
                self.drop(f"groups[{g.get('label')}]", f"未知节点 {bad}")
                g["nodes"] = [n for n in g["nodes"] if n in self.ids]
        for n in list(sem.get("node_summaries", {})):
            if n not in self.ids:
                self.drop("node_summaries", f"未知节点 {n}")
                del sem["node_summaries"][n]
        for n, ly in list(sem.get("layers", {}).items()):
            if n not in self.ids:
                self.drop("layers", f"未知节点 {n}")
                del sem["layers"][n]
            elif "source" in ly:
                self.check_claim(f"layers[{n}]", ly)
        for key in ("triggers", "exclusions"):
            if sem.get("routing", {}).get(key):
                sem["routing"][key] = self.keep(f"routing.{key}", sem["routing"][key])
        for node, steps in list(self.subflows.items()):
            if node not in self.ids:
                self.drop("subflows", f"未知节点 {node}")
                del self.subflows[node]
                continue
            for i, s in enumerate(steps, 1):
                w = f"{node}.{i}"
                if s.get("goal") and not self.check_claim(f"{w}.goal", s["goal"]):
                    s["goal"] = None
                for dim, items in (s.get("semantics") or {}).items():
                    s["semantics"][dim] = self.keep(f"{w}.{dim}", items)
                for cat, items in (s.get("attachments") or {}).items():
                    s["attachments"][cat] = self.keep(f"{w}.att.{cat}", items)
        for scope in ("semantics", "attachments"):
            for k, items in (sem.get("global", {}).get(scope) or {}).items():
                sem["global"][scope][k] = self.keep(f"global.{scope}.{k}", items)

        kept_edges = []
        for e in sem.get("edges", []):
            w = f"edge {e.get('from')}→{e.get('to')}"
            if (self.ep_prefixed(e.get("from")) or self.ep_prefixed(e.get("to"))) and not self.bundle:
                self.drop(w, "带 skill 前缀的端点需 --bundle")
                continue
            if e.get("type") == "delegate" and not self.ep_prefixed(e.get("to")):
                self.drop(w, "delegate 的 to 必须带 skill 前缀")
                continue
            if not (self.ep_ok(e.get("from")) and self.ep_ok(e.get("to"))):
                self.drop(w, "端点不存在 / 越界")
                continue
            if not self.check_claim(w, e):
                continue
            if e.get("type") == "delegate" and not self.delegate_backed(e):
                self.drop(w, "delegate 无对应 cross-ref(引用行不在 source 行内,也不在同一节点)")
                continue
            kept_edges.append(e)
        sem["edges"] = kept_edges
        for key in ("checkpoints", "termination"):
            kept = []
            for c in sem.get(key, []):
                w = f"{key} {c.get('at')}"
                if not self.ep_ok(c.get("at")):
                    self.drop(w, "位置不存在")
                    continue
                if self.check_claim(w, c):
                    kept.append(c)
            sem[key] = kept

        def has_edge(types, a, b):
            return any(e["type"] in types and e["from"] == a and e["to"] == b for e in kept_edges)

        derived = (
            ("loops", {"retry", "loop"}, lambda x: (f"{x['node']}.{x['from']}", f"{x['node']}.{x['to']}")),
            ("jumps", {"condition_true", "condition_false"}, lambda x: (f"{x['node']}.{x['from']}", f"{x['node']}.{x['to']}")),
            ("guards", {"fallback"}, lambda x: (f"{x['protects']['node']}.{x['protects']['step']}", x["guard"])),
        )
        for key, types, endpoints in derived:
            kept = []
            for x in sem.get(key, []):
                w = f"{key} {json.dumps(x, ensure_ascii=False)[:60]}"
                try:
                    a, b = endpoints(x)
                except (KeyError, TypeError):
                    self.drop(w, "字段缺失")
                    continue
                if not (self.ep_ok(a) and self.ep_ok(b)):
                    self.drop(w, "端点越界")
                    continue
                if not self.check_claim(w, x):
                    continue
                if v2 and not has_edge(types, a, b):
                    self.drop(w, f"无对应 {'/'.join(sorted(types))} 边")
                    continue
                kept.append(x)
            sem[key] = kept
        if v2:
            rec = sem["reconciliation"]
            for key in ("implicit_steps", "order_deviations", "judgment_calls"):
                rec[key] = self.keep(f"reconciliation.{key}", rec.get(key, []))
        return 0

    def report(self, sem, code):
        print(f"schema {sem.get('schema')} · generator {sem.get('generator')}")
        if self.fatal:
            print("整体回落:")
            for m in self.fatal:
                print("  ✗", m)
            return 1
        print(f"claims 通过 {self.ok} · 作废 {len(self.dropped)}")
        for d in self.dropped:
            print("  ✗", d)
        rec = sem.get("reconciliation")
        if rec:
            print(f"印证:节点 {rec.get('nodes_classified')}/{rec.get('nodes_total')} 归类 · 步骤 {rec.get('steps_typed')}/{rec.get('steps_total')} 分型 · "
                  f"非流程标题 {len(rec.get('non_workflow_nodes', []))} · 隐含步骤 {sum(x.get('count', 1) for x in rec.get('implicit_steps', []))} · "
                  f"顺序偏差 {len(rec.get('order_deviations', []))} · 跨锚定 {len(rec.get('cross_anchored', []))}")
        edges = sem.get("edges", [])
        cross = [e for e in edges if parse_ep(e["to"])[1] != "END" and parse_ep(e["from"])[:2] != parse_ep(e["to"])[:2]]
        xskill = [e for e in edges if parse_ep(e["from"])[0] or parse_ep(e["to"])[0]]
        print(f"edges {len(edges)}(跨节点 {len(cross)} · 跨 skill {len(xskill)})· checkpoints {len(sem.get('checkpoints', []))} · termination {len(sem.get('termination', []))} · "
              f"loops {len(sem.get('loops', []))} · jumps {len(sem.get('jumps', []))} · guards {len(sem.get('guards', []))}")
        if self.emit_json:
            print(json.dumps(sem, ensure_ascii=False))
        return code


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kb", help="semantics.json 所在目录或文件")
    ap.add_argument("--static", help="阶段 1 static/ 目录(含 INDEX.md、full_text.md);省略则与 kb 同目录")
    ap.add_argument("--skill-dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--bundle", help="组清单 bundle.json;启用带 skill 前缀的端点(s2w-semantics/3)与 delegate 核验")
    args = ap.parse_args()
    sys.exit(Validator(args.kb, args.skill_dir, args.json, args.static, bundle=args.bundle).run())
