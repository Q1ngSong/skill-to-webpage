#!/usr/bin/env python3
"""组合总览页:读 bundle.json + 各成员 merged/semantics.json(缺则退化为静态目录),出 <组名>-workflow.html + .md。

用法:python3 scripts/render_bundle.py output/<组名> [--theme docs] [--overrides output/<组名>/overrides.json]

不给 --overrides 时自动读 <组名>/overrides.json(存在才读)。
"""
import argparse
import datetime as _dt
import html as _html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bundle_layout import break_cycles, layer_skills, mutual_pairs, order_layers, place_chips
from s2w_common import load_static, normalize_semantics, parse_ep, fmt_ep, ref_backs_edge, source_span
from validate_semantics import Validator

REPO = Path(__file__).resolve().parent.parent
E = lambda s: _html.escape(str(s), quote=True)  # noqa: E731
CHIP_W, GAP_X, ROW_H = 150, 24, 84
MIN_W, ROW_GAP, FIG_PAD = 600, 36, 40   # 画布最小宽 / 行间距 / 画布下边留白
TARGET_W = 1200                         # 图 2 每行的目标宽度:超了就给分组框减列(靠换行长高)
NODE_W, NODE_H, NODE_GAP, CL_PAD_TOP, CL_PAD, ARROW_W = 112, 30, 12, 30, 16, 14   # NODE_GAP/CL_PAD 兼作框内竖直走廊
PER_ROW = 5


def _etype(t):
    """type 会被拼进 SVG 的 class 与 <title>(innerHTML),只留标识符字符。"""
    return re.sub(r"[^a-z_]", "", str(t or "").lower()) or "dependency"


def _flat(item):
    """印证条目可能是字符串,也可能是 {note/text/why/…} 之类的对象——摊平成一行文字。"""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return " ".join(str(v).strip() for v in item.values() if isinstance(v, (str, int, float)))
    return ""


class BundleRenderer:
    def __init__(self, out_dir, theme="docs", overrides=None):
        self.out = Path(out_dir).resolve()
        self.b = json.loads((self.out / "bundle.json").read_text(encoding="utf-8"))
        self.name = self.b["name"]
        self.theme = theme
        # 不给 --overrides 时按目录约定自动认 <output_dir>/overrides.json(与单页 render.py 一致);
        # 显式给了却不存在 → 报错,别静默当没转述层(路径写错时最容易踩)
        if overrides and not Path(overrides).exists():
            raise SystemExit("--overrides 指定的文件不存在:%s" % overrides)
        ovp = Path(overrides) if overrides else (self.out / "overrides.json")
        self.ov = json.loads(ovp.read_text(encoding="utf-8")) if ovp.exists() else {}
        self.ov_from = str(ovp) if self.ov else ""
        cr = self.out / self.b.get("cross_refs", "bundle/static/cross-refs.json")
        self.has_cross_refs = cr.exists()
        self.cross_refs = json.loads(cr.read_text(encoding="utf-8")).get("refs", []) if self.has_cross_refs else []
        self.members = [m["name"] for m in self.b["members"]]
        self.static, self.sem, self.notes = {}, {}, {}
        for m in self.b["members"]:
            sp = self.out / m["static"]
            if not (sp / "metadata.json").exists():
                raise SystemExit("[bundle] 成员 %s 缺静态产物 %s —— 先跑 scripts/extract_bundle.py 重建这个组" % (m["name"], sp))
            self.static[m["name"]] = load_static(sp)
            f = self.out / m["name"] / "merged" / "semantics.json"
            if f.exists():
                code, sem, dropped, fatal = Validator(f, m["skill_dir"], False, self.out / m["static"],
                                                      bundle=self.out / "bundle.json").validate()
                if code == 0 and sem:
                    self.sem[m["name"]] = normalize_semantics(sem)
                    self.notes[m["name"]] = "作废 %d 条" % len(dropped)
                else:
                    self.notes[m["name"]] = "整体回落:" + "; ".join(fatal)
            else:
                self.notes[m["name"]] = "无语义层(静态目录)"
        # 跨 skill 边(节点级):端点补全 skill 前缀,只保留两端都是本组成员的边;
        # 同一条边两侧都写了时按 (from,to,type) 去重(与 render.py 的入边去重同键)
        self.xedges, seen = [], set()
        for s, sem in self.sem.items():
            for e in sem.get("edges", []):
                fs, fn, fstep = parse_ep(e.get("from", ""))
                ts, tn, tstep = parse_ep(e.get("to", ""))
                if not fn or not tn:
                    continue
                if not (ts or fs):
                    continue
                frm = fmt_ep(fs or s, fn, fstep)
                to = fmt_ep(ts or s, tn, tstep)
                if parse_ep(frm)[0] not in self.members or parse_ep(to)[0] not in self.members:
                    continue
                if parse_ep(frm)[0] == parse_ep(to)[0]:
                    continue
                key = (frm, to, e["type"])
                if key in seen:
                    continue
                seen.add(key)
                self.xedges.append({"from": frm, "to": to, "type": e["type"], "condition": e.get("condition", ""),
                                    "source": "%s/%s" % (s, e.get("source", "")), "quote": e.get("quote", ""),
                                    "basis": e.get("basis", "explicit"), "owner": s})

    # ---- 图 1 ----
    def skill_graph(self):
        pairs = {}
        for e in self.xedges:
            a, b = parse_ep(e["from"])[0], parse_ep(e["to"])[0]
            pairs.setdefault((a, b), {"types": set(), "edges": []})
            pairs[(a, b)]["types"].add(e["type"])
            pairs[(a, b)]["edges"].append(e)
        # 分层只看 delegate(交棒 = 控制权转移);dependency / fallback 等仍然画、仍然进清单,
        # 但不参与分层——否则「A 交棒给 B、B 只是取用 A」会被当成互调,把两层压成一层。
        deleg = [k for k, v in pairs.items() if "delegate" in v["types"]]
        lay_edges = deleg or list(pairs)          # 整组都没有交棒边时退回全部边
        touched = {n for k in pairs for n in k}
        layers, off_layer = layer_skills(self.members, lay_edges)
        isolated = [n for n in self.members if n not in touched]
        # 只有取用边、没有交棒边的 skill:按邻居的层就近插队,而不是丢进孤立列
        li = {n: i for i, l in enumerate(layers) for n in l}
        for n in sorted(x for x in off_layer if x in touched):
            outs = [li[b] for a, b in pairs if a == n and b in li]
            ins = [li[a] for a, b in pairs if b == n and a in li]
            i = max(0, min(outs) - 1) if outs else (max(ins) + 1 if ins else 0)
            while len(layers) <= i:
                layers.append([])
            layers[i].append(n)
            li[n] = i
        layers = order_layers([l for l in layers if l], list(pairs))
        li = {n: i for i, l in enumerate(layers) for n in l}
        _, back = break_cycles(self.members, lay_edges)
        mutual = mutual_pairs(lay_edges)
        pos = place_chips(layers, CHIP_W, GAP_X, ROW_H)
        width = max([p["x"] + p["w"] for p in pos.values()] + [MIN_W])
        # 孤立 skill:右侧单列
        for i, n in enumerate(isolated):
            pos[n] = {"x": width + GAP_X * 2, "y": i * ROW_H, "w": CHIP_W, "layer": -1, "index": i}
        chips = []
        for n in self.members:
            p = pos[n]
            tag = "孤立" if n in isolated else "L%d" % (li[n] + 1)      # 上排写层号,别把 skill 名印两遍
            chips.append('<a class="chip%s" data-key="%s" data-layer="%s" href="%s" style="left:%dpx;top:%dpx;width:%dpx"><span class="nid">%s</span><span class="nt">%s</span><span class="sub">%s</span></a>' % (
                " iso" if n in isolated else "", E(n), "iso" if n in isolated else li[n],
                E(self.page_of(n)), p["x"], p["y"], p["w"],
                E(tag), E(self.chip_title(n)), E(self.chip_sub(n))))
        height = max([p["y"] for p in pos.values()] + [0]) + 64
        # 互调对同层相邻,合成一条双箭头横连接(端点按名字排序,与成员顺序无关)
        fig_edges, done = [], set()
        for (a, b), v in sorted(pairs.items()):
            if (a, b) in done:
                continue
            two_way = (a, b) in mutual                       # 双向都是交棒才算互调
            rev = pairs.get((b, a)) if two_way else None
            types = set(v["types"]) | (set(rev["types"]) if rev else set())
            e0 = v["edges"][0]
            # 非互调边:落在同层或往回指的,走右侧回弧
            back_edge = not two_way and ((a, b) in back or li.get(b, 0) <= li.get(a, 0))
            fig_edges.append({"from": a, "to": b, "type": _etype("delegate" if "delegate" in types else sorted(types)[0]),
                              "back": back_edge, "mutual": two_way,
                              "source": E(e0["source"]), "quote": E(e0["quote"])})
            done.add((a, b))
            if rev:
                done.add((b, a))
        return {"layers": layers, "isolated": isolated, "pos": pos, "back": back, "pairs": pairs, "layer_of": li,
                "html": '<div class="fig-inner" style="height:%dpx;min-width:%dpx">%s</div>' % (height, width + (CHIP_W + GAP_X * 2 if isolated else 0), "".join(chips)),
                "edges": fig_edges}

    # ---- 图 2 ----
    def node_graph(self, g1):
        shown, allnodes, wmain = {}, {}, {}
        for s in self.members:
            st = self.static[s]
            ids = [n["id"] for n in st["nodes"]]
            allnodes[s] = ids
            sem, main = self.sem.get(s), []
            involved = {parse_ep(e["from"])[1] for e in self.xedges if parse_ep(e["from"])[0] == s} | \
                       {parse_ep(e["to"])[1] for e in self.xedges if parse_ep(e["to"])[0] == s}
            if sem:
                main = [n for n in ids if sem.get("layers", {}).get(n, {}).get("layer") == "W"]
                shown[s] = [n for n in ids if n in main or n in involved]
            else:
                shown[s] = ids
            wmain[s] = list(main) if sem else list(ids)
        # 宽度按**折叠态**内容算(展开的节点在同一宽度里换行,框变高不变宽);
        # 行的纵向位置由页面上的 relayoutFig2() 按实测高度重排,这里只给一份无 JS 时也能看的初值
        def box_w(cols):
            return cols * NODE_W + (cols - 1) * (NODE_GAP * 2 + ARROW_W) + CL_PAD * 2

        items = {s: len(shown[s]) + (1 if len(allnodes[s]) > len(shown[s]) else 0) for s in self.members}
        cols = {s: min(PER_ROW, max(2, items[s])) for s in self.members}
        # 孤立 skill 排成最后一行(而不是右侧一列),省下的横向空间让整图挤得进一屏
        fig_rows = [(str(i), l) for i, l in enumerate(g1["layers"])] + ([("iso", g1["isolated"])] if g1["isolated"] else [])
        # 行太宽就把该行最宽的框少放一列(下限 2 列,节点换行、框变高),让整图尽量不用横向滚动
        for _, l in fig_rows:
            def row_w():
                return sum(box_w(cols[s]) for s in l) + GAP_X * (len(l) - 1)
            while row_w() > TARGET_W and any(cols[s] > 2 for s in l):
                widest = max((s for s in l if cols[s] > 2), key=lambda s: (cols[s], s))
                cols[widest] -= 1
        widths, heights = {}, {}
        for s in self.members:
            rows = -(-max(items[s], 1) // cols[s])
            widths[s] = box_w(cols[s])
            heights[s] = CL_PAD_TOP + rows * (NODE_H + NODE_GAP) + CL_PAD
        row_of = {s: k for k, l in fig_rows for s in l}
        pos, y = {}, 0
        total_w = max([sum(widths[s] for s in l) + GAP_X * (len(l) - 1) for _, l in fig_rows] + [MIN_W])
        for k, l in fig_rows:
            row_w = sum(widths[s] for s in l) + GAP_X * (len(l) - 1)
            x = (total_w - row_w) / 2
            for s in l:
                pos[s] = {"x": x, "y": y, "w": widths[s], "h": heights[s]}
                x += widths[s] + GAP_X
            y += max(heights[s] for s in l) + ROW_GAP
        clusters = []
        for s in self.members:
            p = pos[s]
            boxes = []
            # 主线节点之间按文档顺序补顺序小箭头(规范 §5.3);折叠节点不参与,展开后箭头照旧
            seq = [n for n in wmain[s] if n in shown[s]]
            for n in allnodes[s]:
                hidden = n not in shown[s]
                title = self.node_title(s, n)
                boxes.append('<a class="nbox%s" data-key="%s" href="%s#%s" title="%s"><span class="nn">%s</span><span class="nt">%s</span></a>' % (
                    " hidden" if hidden else "", E(fmt_ep(s, n)), E(self.page_of(s)), n, E(title), n, E(title)))
                if n in seq and seq.index(n) < len(seq) - 1:
                    boxes.append('<span class="narr" aria-hidden="true">→</span>')
            more = len(allnodes[s]) - len(shown[s])
            if more:
                boxes.append('<span class="more">+%d 支撑</span>' % more)
            clusters.append('<div class="cluster" data-skill="%s" data-layer="%s" style="left:%dpx;top:%dpx;width:%dpx"><span class="cl">%s</span><div class="nrow">%s</div></div>' % (
                E(s), E(row_of[s]), p["x"], p["y"], p["w"], E(s), "".join(boxes)))
        height = max([p["y"] + p["h"] for p in pos.values()] + [0]) + FIG_PAD
        # 画线按节点粒度:分组框里的盒子是节点(data-key="skill:nXX"),端点带步号时落到所属节点
        edges, seen, li = [], set(), g1["layer_of"]
        for e in self.xedges:
            fs, fn, _ = parse_ep(e["from"])
            ts, tn, _ = parse_ep(e["to"])
            key = (fmt_ep(fs, fn), fmt_ep(ts, tn), e["type"])
            if key in seen:
                continue
            seen.add(key)
            back = (fs, ts) in g1["back"] or li.get(ts, 0) <= li.get(fs, 0)   # 与图 1 同一判定:同层或往回指 = 回弧
            edges.append({"from": key[0], "to": key[1], "type": _etype(e["type"]), "back": back,
                          "source": E(e["source"]), "quote": E(e["quote"])})
        return {"html": '<div class="fig-inner" style="height:%dpx;min-width:%dpx">%s</div>' % (height, total_w, "".join(clusters)),
                "edges": edges, "shown": shown, "all": allnodes}

    # ---- 文案 ----
    def page_of(self, s):
        return next(m["page"] for m in self.b["members"] if m["name"] == s)

    def chip_title(self, s):
        return self.ov.get("chip_titles", {}).get(s) or s

    def chip_sub(self, s):
        sem = self.sem.get(s)
        if sem:
            for n, ly in sem.get("layers", {}).items():
                if ly.get("layer") == "W" and ly.get("role") == "main_flow" and sem.get("node_summaries", {}).get(n):
                    return sem["node_summaries"][n][:12]
            for v in sem.get("node_summaries", {}).values():
                return v[:12]
        d = self.static[s]["description"]
        return (d[:20] + "…") if len(d) > 20 else d

    def node_title(self, s, n):
        sem = self.sem.get(s)
        t = (sem or {}).get("node_summaries", {}).get(n)
        if not t:
            t = next(x["title"] for x in self.static[s]["nodes"] if x["id"] == n)
        return t if len(t) <= 14 else t[:13] + "…"

    # ---- 表格 / 印证 ----
    def edges_table(self):
        rows = ""
        for e in self.xedges:
            # 追问按钮:把这条边的出处 + 依赖打包给 Agent(弹窗逻辑与单页同一份)
            dd = '<button class="deep-dive-btn" type="button" title="追问这条边" data-dd-label="%s" data-dd-source="%s">?</button>' % (
                E("%s → %s" % (e["from"], e["to"])), E(e["source"]))
            rows += '<tr data-source="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class="src">%s</td><td class="qt">%s</td><td class="dd">%s</td></tr>' % (
                E(e["source"]), E(e["from"]), E(e["to"]), E(e["type"]), E(e["condition"]), E(e["source"]), E(e["quote"]), dd)
        if not rows:
            rows = '<tr><td colspan="7">无跨 skill 边</td></tr>'
        return '<div class="scroll"><table class="tbl"><thead><tr><th>来源</th><th>目标</th><th>类型</th><th>条件</th><th>出处</th><th class="qt">引文</th><th></th></tr></thead><tbody>%s</tbody></table></div>' % rows

    def stats_table(self):
        rows = ""
        for s in self.members:
            o = sum(1 for e in self.xedges if parse_ep(e["from"])[0] == s)
            i = sum(1 for e in self.xedges if parse_ep(e["to"])[0] == s)
            rows += "<tr><td>%s</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td></tr>" % (
                E(s), o, i, "孤立" if not (o or i) else "", E(self.notes.get(s, "")))
        return '<div class="scroll"><table class="tbl"><thead><tr><th>skill</th><th>出边</th><th>入边</th><th></th><th>语义层</th></tr></thead><tbody>%s</tbody></table></div>' % rows

    # ---- 引用采纳 / 未采纳原因 ----
    def node_range(self, skill, node):
        for n in self.static.get(skill, {}).get("nodes", []):
            if n["id"] == node:
                return n["line_start"], n["line_end"]
        return None

    def ref_adopted(self, r):
        """引用被某条边采纳:引用行落在边 source 的行范围内、或两者同节点(与 validate_semantics 同一判定),
        或边的出处落在这条引用所在节点的行范围内(规范 §3b:节点级锚定也算采纳)。"""
        rng = self.node_range(r["from_skill"], r.get("from_node"))
        for e in self.xedges:
            if parse_ep(e["from"])[0] != r["from_skill"] or parse_ep(e["to"])[0] != r["to_skill"]:
                continue
            if ref_backs_edge(r, e["source"], parse_ep(e["from"])[1]):
                return True
            span = source_span(e["source"])
            if rng and span and rng[0] <= span[0] <= rng[1]:
                return True
        return False

    def recon_texts(self, skill):
        """成员语义层里可能解释「为什么没成边」的文字:印证的 notes / judgment_calls,以及 ambiguities。"""
        sem = self.sem.get(skill) or {}
        rec = sem.get("reconciliation") or {}
        items = list(rec.get("notes") or []) + list(rec.get("judgment_calls") or []) + list(sem.get("ambiguities") or [])
        return [x for x in (_flat(i) for i in items) if x]

    def ref_reason(self, r):
        """规范 §5.5:未采纳的引用要给出语义层的说法。只认确切行号(`:32` 不能命中 `:320`,
        中文写法「第 32 行」同样算),裸提一句目标 skill 名不作数——那样会把无关的印证条目挂上来。"""
        span = source_span(r["source"])
        if not span:
            return "语义层未说明"
        pat = re.compile(r"(?:SKILL\.md)?:%d(?!\d)|第\s*%d\s*行" % (span[0], span[0]))
        hits = [txt for txt in self.recon_texts(r["from_skill"]) if pat.search(txt)]
        for txt in hits:                                  # 同时点名目标 skill 的说法更贴题,优先
            if r["to_skill"] in txt:
                return txt
        return hits[0] if hits else "语义层未说明"

    def recon_html(self):
        orphan = [r for r in self.cross_refs if not self.ref_adopted(r)]
        lis = "".join('<li data-source="%s/%s"><code>%s</code> → <code>%s</code> %s · %s<span class="q">%s</span><span class="why">原因:%s</span></li>' % (
            E(r["from_skill"]), E(r["source"]), E(r["from_skill"]), E(r["to_skill"]), E(r.get("from_node") or "frontmatter"),
            E(r["source"]), E(r["quote"]), E(self.ref_reason(r))) for r in orphan)
        if not self.has_cross_refs:
            h = '<p class="sem-h">cross-refs</p><ul class="sem-list"><li>未生成 bundle/static/cross-refs.json,无法核对引用——重跑 scripts/extract_bundle.py</li></ul>'
        else:
            h = '<p class="sem-h">cross-refs 未被任何边采纳(%d / %d)</p><ul class="sem-list">%s</ul>' % (
                len(orphan), len(self.cross_refs), lis or "<li>无</li>")
        h += '<p class="sem-h">成员语义层</p><ul class="sem-list">%s</ul>' % "".join(
            '<li><a href="%s">%s</a> · %s</li>' % (E(self.page_of(s)), E(s), E(self.notes.get(s, ""))) for s in self.members)
        return h, orphan

    # ---- 组装 ----
    def render(self):
        tpl = (REPO / "templates/bundle.html").read_text(encoding="utf-8")
        themes = "".join((REPO / "templates/themes" / f).read_text(encoding="utf-8")
                         for f in ["docs.css", "blueprint.css", "ide.css", "whiteboard.css"])
        g1 = self.skill_graph()
        g2 = self.node_graph(g1)
        recon, orphan = self.recon_html()
        iso = len(g1["isolated"])
        deleg = sum(1 for e in self.xedges if e["type"] == "delegate")
        hero = '<p class="lede">%s</p>' % (self.ov.get("description_html") or E(
            "%d 个 skill · %d 条跨 skill 边(delegate %d)· 孤立 %d · 引用事实 %d 条 · 语义层 %d/%d 成员" % (
                len(self.members), len(self.xedges), deleg, iso, len(self.cross_refs), len(self.sem), len(self.members))))
        if self.ov.get("thesis_html"):
            hero += '<div class="thesis"><span>%s</span></div>' % self.ov["thesis_html"]
        layout = {"fig1": {"edges": g1["edges"]}, "fig2": {"edges": g2["edges"]}}
        footer = "由 <strong>skill-to-webpage</strong> 生成 · 组:<code>%s</code>(%d 个成员)· 跨引用零 LLM 抽取(cross-refs.json)· 跨 skill 边来自各成员语义层(带前缀端点,经 validate_semantics.py --bundle 回读)· %s" % (
            E(self.name), len(self.members), _dt.date.today().isoformat())
        slots = {"{{lang}}": "zh-CN", "{{title}}": "%s · Skill Bundle" % self.name, "{{theme_styles}}": themes,
                 "{{default_theme}}": self.theme, "{{group}}": E(self.name),
                 "{{eyebrow}}": "SKILL BUNDLE · %d SKILLS · %d CROSS-SKILL EDGES" % (len(self.members), len(self.xedges)),
                 "{{hero_html}}": hero, "{{fig1_html}}": g1["html"], "{{fig2_html}}": g2["html"],
                 "{{edges_table}}": self.edges_table(), "{{stats_table}}": self.stats_table(),
                 "{{recon_html}}": recon, "{{footer_note}}": footer,
                 "{{flow_lib}}": (REPO / "templates/flow-lib.js").read_text(encoding="utf-8").rstrip("\n"),
                 "{{skill_dirs}}": json.dumps({m["name"]: m.get("skill_dir", "") for m in self.b["members"]}, ensure_ascii=False),
                 "{{layout_json}}": json.dumps(layout, ensure_ascii=False)}
        # 模板新增了槽位而这里没填:正文槽位出坏版式,<script> 里的会让整段 JS 解析失败。
        # 扫整份模板(不只 <script> 段),且在替换之前扫 —— 替换后原文引文里的 {{…}} 会误报。
        left = sorted(set(re.findall(r"\{\{[a-z_0-9]+\}\}", tpl)) - set(slots))
        if left:
            raise SystemExit("templates/bundle.html 的槽位没填全:%s" % ", ".join(left))
        for k, v in slots.items():
            tpl = tpl.replace(k, v)
        out_html = self.out / ("%s-workflow.html" % self.name)
        out_html.write_text(tpl, encoding="utf-8")
        self.write_md(g1, orphan)
        print("[bundle] %s · skills %d · 跨 skill 边 %d · 孤立 %d · 未采纳引用 %d%s" % (
            out_html, len(self.members), len(self.xedges), iso, len(orphan),
            (" · overrides %s" % self.ov_from) if self.ov_from else ""))

    def write_md(self, g1, orphan):
        L = ["# %s · Skill Bundle(叙事版)" % self.name, "",
             "成员 %d · 跨 skill 边 %d" % (len(self.members), len(self.xedges)), ""]
        for i, l in enumerate(g1["layers"]):
            L.append("- 第 %d 层:%s" % (i + 1, " · ".join(l)))
        if g1["isolated"]:
            L.append("- 孤立:%s" % " · ".join(g1["isolated"]))
        L += ["", "## 跨 skill 边", ""]
        for e in self.xedges:
            L.append("- `%s` → `%s` %s%s(%s)%s · 引文:%s" % (
                e["from"], e["to"], e["type"], "(条件:%s)" % e["condition"] if e["condition"] else "",
                e["source"], ",推断" if e["basis"] == "inferred" else "", e["quote"]))
        L += ["", "## 未采纳的引用(%d)" % len(orphan), ""] + [
            "- %s → %s(%s)· 引文:%s · 原因:%s" % (
                r["from_skill"], r["to_skill"], r["source"], r["quote"], self.ref_reason(r)) for r in orphan]
        (self.out / ("%s-workflow.md" % self.name)).write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output_dir")
    ap.add_argument("--theme", default="docs", choices=["docs", "blueprint", "ide", "whiteboard"])
    ap.add_argument("--overrides", help="默认 <output_dir>/overrides.json(存在才读)")
    a = ap.parse_args()
    BundleRenderer(a.output_dir, a.theme, a.overrides).render()


if __name__ == "__main__":
    main()
