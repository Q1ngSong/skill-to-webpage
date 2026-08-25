#!/usr/bin/env python3
"""阶段 2 渲染器:static/(+ merged/ 或某个解析器产物)→ 单文件交互 HTML(+ 叙事 .md)。仅标准库。

用法:python3 scripts/render.py <output_dir> [--variants merged static my-parser …] [--theme docs]
        [--overrides overrides.json] [--skill-dir DIR] [--no-md]
    单版兼容:python3 scripts/render.py <output_dir> [--semantics merged] [--out FILE]

- 变体(variant)= 页面吃哪一份语义:`merged`(合并结果)/ `static`(静态基线,不吃语义)/ 任一解析器文件夹名。
  每版写进自己的文件夹:<output_dir>/<变体>/<skill>-workflow.html(+ .md);根目录 <output_dir>/<skill>-workflow.html
  放 merged 版(未选 merged 时放列表第一个)。页面顶栏注入版本切换链接(按所在位置算相对路径)。
  语义文件不存在或校验整体回落的变体会被跳过并告知。
- 没有语义文件(或校验整体回落)→ 静态基线页:相对 L1 节点、L2 步骤、原文;不画任何语义层。
- 有语义文件 → 先经 validate_semantics 校验(作废条目剔除),再按 templates/components.md「语义层标记」渲染。
- overrides.json(可选,渲染 Agent 写的转述层):
  {"lang": "zh-CN", "title": "…", "chip_titles": {"n03": "帮用户找 skill"}, "leads": {"n03": "…"},
   "description_html": "…", "thesis_html": "…", "eyebrow_extra": "…"}
"""
import argparse
import datetime as _dt
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from s2w_common import fmt_ep, load_static, normalize_semantics, parse_ep, src_text  # noqa: E402
from validate_semantics import Validator  # noqa: E402

E = html.escape
FENCE = ("```", "~~~")
LAYER_NAME = {"R": "R 层 · 路由/激活", "W": "W 层 · 流程", "S": "S 层 · 语义/知识", "A": "A 层 · 附件/工具"}
TYPE_FAMILY = {"TOOL_CALL": "t-tool", "STATE_WRITE": "t-tool", "VALIDATE": "t-gate", "APPROVE": "t-gate", "ASK_USER": "t-gate",
               "OUTPUT": "t-out", "TERMINATE": "t-out", "FALLBACK": "t-fb"}
DIM_LABEL = {"procedure": "怎么做", "criteria": "判据", "domain_rules": "规则", "heuristics": "技巧", "examples": "示例",
             "quality_standards": "质量标准", "failure_modes": "常见翻车", "inputs": "输入", "outputs": "输出",
             "tools": "工具", "resources": "资源", "governance": "治理约束", "presentation": "呈现模板"}
DIM_ORDER = ["inputs", "procedure", "domain_rules", "criteria", "quality_standards", "heuristics", "examples",
             "failure_modes", "governance", "tools", "resources", "outputs", "presentation"]
XSKILL_TYPES = ("delegate", "dependency", "fallback")   # 会画成跨 skill 外部节点的边型
EDGE_GLYPH = {"condition_true": "⇢", "condition_false": "⇢", "retry": "↻", "loop": "↻", "fallback": "⤓", "approval": "⏸",
              "termination": "⦿", "dependency": "◂", "parallel": "∥", "delegate": "⧉"}


# ---------- 最小 Markdown → HTML(原文展示用) ----------
def inline(s):
    s = E(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


STEP_PREFIX = re.compile(r"^\s*(?:step|步骤|第)\s*\d+\s*[步]?\s*[:.、·:-]?\s*", re.I)


def step_label(s):
    """步骤显示名:解析器别名(label)优先,否则静态标题去掉自带的 Step N: 前缀。"""
    raw = s.get("label") or s.get("title") or ""
    stripped = STEP_PREFIX.sub("", raw).strip()
    return stripped or raw


STEP_ORD = re.compile(r"^\s*(step|phase|stage|步骤|阶段|第)\s*(\d+)\s*(步)?", re.I)


def doc_step_refs(steps):
    """若节点的每个相对 L2 标题都自带序号前缀(Step 0 / Phase 2 / 第 3 步 …),返回按盒子顺序的文档序号文案列表
    (如 ["Step 0", "Step 1", …]),供编号与「→ Step N」文案沿用文档自己的编号;否则返回 None(沿用 1 起序号)。"""
    refs = []
    for st in steps:
        m = STEP_ORD.match(st.get("title") or "")
        if not m:
            return None
        w, n, tail = m.group(1), m.group(2), m.group(3) or ""
        refs.append(("%s %s %s" % (w, n, tail)).strip() if w == "第" else "%s %s" % (w[:1].upper() + w[1:].lower() if w.isascii() else w, n))
    return refs or None


def md_to_html(md, heading_hierarchy=None):
    source_to_relative = {
        int(source): int(relative)
        for relative, source in (heading_hierarchy or {}).get("relative_mapping", {}).items()
    }
    out, lines, i = [], md.split("\n"), 0
    item_re = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if st.startswith(FENCE):
            fence, buf, j = st[:3], [], i + 1
            while j < len(lines) and not lines[j].strip().startswith(fence):
                buf.append(lines[j])
                j += 1
            out.append('<pre class="code">%s</pre>' % E("\n".join(buf)))
            i = j + 1
            continue
        if st.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            rows, j = [], i
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(lines[j])
                j += 1
            cells = [[inline(c.strip()) for c in r.strip().strip("|").split("|")] for r in rows]
            head = "".join("<th>%s</th>" % c for c in cells[0])
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in cells[2:])
            out.append('<div class="scroll"><table class="tbl"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (head, body))
            i = j
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            source_level = len(m.group(1))
            relative_level = source_to_relative.get(source_level)
            if relative_level is not None:
                lvl = min(relative_level + 2, 6)
            elif source_to_relative and source_level > max(source_to_relative):
                lvl = 6
            else:
                lvl = min(source_level + 1, 6)
            out.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2)), lvl))
            i += 1
            continue
        if item_re.match(line):
            ordered, items, j = bool(re.match(r"^\s*\d+[.)]", line)), [], i
            while j < len(lines) and item_re.match(lines[j]):
                items.append(item_re.sub("", lines[j]))
                j += 1
                while j < len(lines) and lines[j].startswith(("  ", "\t")) and not item_re.match(lines[j]):
                    items[-1] += " " + lines[j].strip()
                    j += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            i = j
            continue
        if line.startswith(">"):
            buf, j = [], i
            while j < len(lines) and lines[j].startswith(">"):
                buf.append(lines[j].lstrip("> "))
                j += 1
            out.append("<blockquote>%s</blockquote>" % inline(" ".join(buf)))
            i = j
            continue
        if st == "":
            i += 1
            continue
        buf, j = [line], i + 1
        while j < len(lines) and lines[j].strip() and not re.match(r"^(#{1,6}\s|\s*([-*+]|\d+[.)])\s|>|\s*\||```|~~~)", lines[j]):
            buf.append(lines[j])
            j += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))
        i = j
    return "\n".join(out)


# ---------- 渲染器 ----------
class Renderer:
    def __init__(self, out_dir, semantics, theme, overrides, skill_dir, variants=None, current=None, link_base="../"):
        self.out_dir = Path(out_dir).resolve()
        self.static = load_static(self.out_dir / "static")
        self.heading_hierarchy = self.static["heading_hierarchy"]
        self.name = self.out_dir.name   # 组内身份 = skill 目录名(bundle.json 成员名、静态路径、端点前缀都按它;frontmatter 的 name 只管页面标题与文件名)
        self.ov = json.loads(Path(overrides).read_text(encoding="utf-8")) if overrides else {}
        self.theme = theme
        self.skill_dir = Path(skill_dir).resolve() if skill_dir else Path(self.static["source_path"]).parent
        self.variants, self.current, self.link_base = variants or [], current or semantics, link_base
        # bundle 成员页?(须在校验之前定下:带 skill 前缀的端点要靠 --bundle 才能通过 validate_semantics)
        self.bundle, self.bundle_name, self.bundle_path = None, None, None
        bundle_note = None
        bj = self.out_dir.parent / "bundle.json"
        if bj.exists():
            try:
                b = json.loads(bj.read_text(encoding="utf-8"))
                me = next((m for m in b.get("members", []) if m.get("name") == self.out_dir.name), None)
                if me:
                    self.bundle, self.bundle_name, self.bundle_path = b, b.get("name"), str(bj)
                    self.name = me["name"]   # 以清单里的写法为准
            except Exception as exc:  # noqa: BLE001
                self.bundle, bundle_note = None, "bundle.json 读不出(%s):按单页渲染,跨 skill 链接与入边都不会出现" % exc
        # 页面文件名:组内成员跟清单里的成员名(= 目录名),才对得上 bundle.json 的 page 与 xlink();单页仍用 frontmatter 的 name
        self.page_name = self.name if self.bundle else self.static["skill_name"]
        self.sem, self.val_notes = None, []
        self.sem_missing = False
        sem_dir = self.out_dir / semantics
        if semantics == "static":
            pass
        elif (sem_dir / "semantics.json").exists():
            v = Validator(sem_dir, str(self.skill_dir), False, self.out_dir / "static", bundle=self.bundle_path)
            code, sem, dropped, fatal = v.validate()
            if code == 0 and sem:
                self.sem = normalize_semantics(sem)
                self.val_notes = ["%s:作废 %d 条" % (semantics, len(dropped))] + dropped[:10]
            else:
                self.val_notes = ["%s 整体回落:%s" % (semantics, "; ".join(fatal) or "无法使用")]
        else:
            self.sem_missing = True
        if bundle_note:
            self.val_notes.append(bundle_note)
        self.nodes = self.static["nodes"]
        self.by_id = {n["id"]: n for n in self.nodes}
        self.ids = [n["id"] for n in self.nodes]
        S = self.sem or {}
        self.layers = S.get("layers", {})
        self.edges = [self.localize(e) for e in S.get("edges", [])] + self.bundle_in_edges()  # + 兄弟 skill 指向本页的边
        self.checks = {self.local_ep(c["at"]): c for c in S.get("checkpoints", [])}
        # 每节点步骤:语义层给了用语义层的(静态步骤 + 隐含),否则用静态相对 L2
        self.steps = {}
        for n in self.nodes:
            ss = S.get("subflows", {}).get(n["id"])
            if not ss:
                ss = [{"title": s["title"], "lines": "%d-%d" % (s["line_start"], s["line_end"])} for s in n["steps"]]
            self.steps[n["id"]] = ss
        self.SUBFLOW_LOOPS, self.SEM_EDGES, self.RAIL_LINKS = {}, {}, []

    # ---- 小工具 ----
    def eid(self, node, k):
        return "e%d%d" % (int(node[1:]), k)

    def local_ep(self, ep):
        """指向本 skill 的前缀端点(`alpha:n01.2` 出现在 alpha 自己的页上)折回本地写法 `n01.2`:
        端点在本类里是靠字符串相等找边的,不折回就既查不到边、又会被当成跨 skill 链接指回自己。"""
        skill, node, step = parse_ep(ep)
        return fmt_ep(None, node, step) if skill == self.name and node else ep

    def localize(self, e):
        loc = {k: self.local_ep(e[k]) for k in ("from", "to") if k in e}
        return dict(e, **loc) if any(loc[k] != e[k] for k in loc) else e

    def ref(self, ep):
        """端点 → (节点, 步骤)。指向本 skill 的前缀(`alpha:n01` 在 alpha 页上)按本地端点处理。"""
        skill, node, step = parse_ep(ep)
        if node is None:
            return (ep, None)
        return (node, step) if skill in (None, self.name) else (fmt_ep(skill, node), step)

    def xref(self, ep):
        """跨 skill 端点 → (skill, node);本页端点(含指向自己的前缀)返回 None。跨页链接只落到节点,步号无用。"""
        skill, node, _ = parse_ep(ep)
        return (skill, node) if skill and skill != self.name else None

    def xlink(self, skill, node=None):
        """跨 skill 页面链接:根页 link_base="" → ../<skill>/…;变体页 link_base="../" → ../../<skill>/…"""
        return "%s../%s/%s-workflow.html%s" % (self.link_base, skill, skill, ("#" + node) if node else "")

    def bundle_in_edges(self):
        """bundle 成员页:把兄弟 skill 指向本页的边反向引入(`from` 带来源 skill 前缀,`to` 落到本页端点),
        这样被委托方也能看到「谁委托了我」——委托关系只写在来源方的语义文件里。
        只读兄弟的 merged/semantics.json:那是 merge_semantics.py 逐条校验过的结果;没有 merged/ 的成员不贡献入边
        (直接读解析器原始产物会把校验作废的边当成已核实的链接放上目标页)。"""
        if not self.bundle or not self.sem:
            return []
        me, found, missing = self.name, [], []
        own = [self.localize(e) for e in self.sem.get("edges", [])]   # 与导入的边同一种写法才比得了
        seen = {(e.get("from"), e.get("to"), e.get("type")) for e in own}
        for m in self.bundle.get("members", []):
            if m.get("name") == me:
                continue
            f = self.out_dir.parent / m["name"] / "merged" / "semantics.json"
            if not f.exists():   # 组内渲染有先后:兄弟还没合并时本页就是少了入边,必须说出来
                missing.append(m["name"])
                continue
            try:
                sib = json.loads(f.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                self.val_notes.append("成员 %s 的 merged/semantics.json 读不出(%s):它指向本页的边未导入" % (m["name"], exc))
                continue
            for e in sib.get("edges", []):
                skill, node, step = parse_ep(e.get("to", ""))
                fs, fn, fk = parse_ep(e.get("from", ""))
                if skill != me or node not in self.by_id or fn is None:
                    continue
                key = (self.local_ep(fmt_ep(fs or m["name"], fn, fk)), fmt_ep(None, node, step), e.get("type"))
                if key in seen:  # 本页语义层已自带同一条入边
                    continue
                seen.add(key)
                found.append(dict(e, **{"from": key[0], "to": key[1]}))
        if missing:
            self.val_notes.append("成员 %s 无 merged/semantics.json:它们指向本页的边未导入" % "、".join(missing))
        return found

    def chip_title(self, n):
        t = self.ov.get("chip_titles", {}).get(n) or self.by_id[n]["title"]
        return t if len(t) <= 26 else t[:25] + "…"

    def step_title(self, node, k):
        ss = self.steps.get(node, [])
        return step_label(ss[k - 1]) if 0 < k <= len(ss) else "Step %d" % k

    def step_ref(self, node, k):
        """「Step N」文案:节点标题自带序号时沿用文档编号(Step 0…),否则 1 起序号。"""
        refs = doc_step_refs(self.steps.get(node, []))
        return refs[k - 1] if refs and 0 < k <= len(refs) else "Step %d" % k

    def step_no(self, node, k):
        """盒子角标:文档自带序号时显示文档的数字,否则 k。"""
        refs = doc_step_refs(self.steps.get(node, []))
        return re.search(r"\d+", refs[k - 1]).group(0) if refs and 0 < k <= len(refs) else str(k)

    def out_edges(self, ep):
        return [e for e in self.edges if e.get("from") == ep]

    def in_edges(self, ep):
        return [e for e in self.edges if e.get("to") == ep]

    def jump_to(self, ep, text=None):
        x = self.xref(ep)
        if x:
            return '<a class="xjump" href="%s">⧉ %s · %s</a>' % (E(self.xlink(x[0], x[1])), E(x[0]), x[1])   # 链接落在节点上,标签不带步号
        n, k = self.ref(ep)
        if ep == "END":
            return "END"
        if n not in self.by_id:
            return E(ep)
        if k:
            return '<button class="jump" onclick="showStep(\'%s\',\'%s\')">%s</button>' % (n, self.eid(n, k), E(text or "%s %s" % (self.step_ref(n, k), self.step_title(n, k))))
        return '<button class="jump" onclick="showNode(\'%s\')">%s</button>' % (n, E(text or "%s %s" % (n, self.chip_title(n))))

    @staticmethod
    def inf(c):
        return ' <span class="inf">推断</span>' if c.get("basis") == "inferred" else ""

    @staticmethod
    def qt(c):
        return ' <q class="qt">%s</q>' % E(c["quote"]) if c.get("quote") else ""

    @staticmethod
    def by(c):
        b = c.get("by")
        return ' <span class="inf" title="来源解析器">%s</span>' % E(",".join(b)) if isinstance(b, list) and len(b) > 0 and False else ""

    def claim_li(self, c, extra=""):
        return '<li class="claim" data-source="%s">%s%s%s%s</li>' % (c.get("source", ""), E(c.get("text", "")), self.qt(c), self.inf(c), extra)

    @staticmethod
    def dd(title, source):
        return '<button class="deep-dive-btn" title="追问" onclick="openDeepDive(\'%s\',\'%s\')">?</button>' % (title.replace("'", "").replace("\\", ""), source)

    def flow_line(self, ep):
        parts = []
        n0, k0 = self.ref(ep)
        for e in self.out_edges(ep):
            tn, tk = self.ref(e.get("to", ""))
            if e["type"] == "condition_false" and tn == n0 and k0 and tk == k0 + 1:
                parts.append('<span class="fk">⇢</span>%s → 顺序进入 %s' % (E(e.get("condition", "")), self.jump_to(e["to"])))
            elif e["type"] == "approval":
                parts.append('<span class="fk">⏸</span>%s → %s' % (E(e.get("condition", "")), self.jump_to(e["to"])))
            elif e.get("from") == e.get("to"):
                # 自环按类型给字形:retry/loop 标「自环」,parallel 标「并行」,其余只给字形
                tag = "(自环)" if e["type"] in ("retry", "loop") else ("(并行)" if e["type"] == "parallel" else "")
                parts.append('<span class="fk">%s</span>%s%s' % (EDGE_GLYPH.get(e["type"], "↻"), E(e.get("condition", "")), tag))
            else:
                parts.append('<span class="fk">%s</span>%s → %s%s' % (EDGE_GLYPH.get(e["type"], "→"), E(e.get("condition", "")), self.jump_to(e["to"]), self.inf(e)))
        ins = [e for e in self.in_edges(ep) if e["type"] in ("dependency", "fallback", "delegate")]
        if ins:
            parts.append('<span class="fk">◂</span>来源:' + "、".join("%s(%s)%s" % (self.jump_to(e["from"]), E(e.get("condition", "")), self.inf(e)) for e in ins))
        return '<p class="flow">%s</p>' % "<br>".join(parts) if parts else ""

    def orig_acc(self, source, content=None, orig_title=None):
        body = md_to_html(
            content if content is not None else src_text(self.static, source, strip_fence=False),
            self.heading_hierarchy,
        )
        head = ("原文 · %s · %s" % (E(orig_title), source)) if orig_title else ("原文 · %s" % source)
        return '<div class="acc"><details><summary>%s</summary><div class="acc-body">%s</div></details></div>' % (head, body)

    # ---- 子流程 ----
    @staticmethod
    def conn_attrs(conns, out):
        """外部节点卡片的公共属性:关联步骤 id 串、推断标记串、副标题(本页节点与跨 skill 节点共用)。"""
        xs = ",".join(c[0] for c in conns)
        infs = ",".join("1" if c[2] else "0" for c in conns)
        small = " · ".join(("← " if out else "") + E(c[1]) + (" (推断)" if c[2] else "") for c in conns)
        return xs, infs, small

    def build_stepper(self, node):
        steps = self.steps[node]
        sid = "st-" + node
        boxes, arcs, ins, outs, end = [], [], {}, {}, None
        xins, xouts = {}, {}
        semantic = bool(self.sem)
        for k, s in enumerate(steps, 1):
            x = self.eid(node, k)
            ep = "%s.%d" % (node, k)
            fam = TYPE_FAMILY.get(s.get("type", ""), "")
            when, approval = "", None
            for e in self.in_edges(ep):
                fn, fk = self.ref(e["from"])
                if fn == node and fk == k - 1:
                    if e["type"] in ("condition_true", "condition_false"):
                        when = e.get("condition", "")
                    elif e["type"] == "approval":
                        approval = e.get("condition", "")
            gate = self.checks.get(ep)
            gate_html = ""
            if gate:
                gate_html = '<span class="sf-gate">%s</span>' % ("◆ 验证闸口" if gate["kind"] == "validate" else ("⏸ " + E(approval) if approval else "⏸ 需用户确认"))
            elif approval:
                gate_html = '<span class="sf-gate">⏸ %s</span>' % E(approval)
            when_html = '<span class="sf-when">⇢ %s</span>' % E(when) if when else ""
            imp = '<span class="sf-imp">步骤</span>' if s.get("implicit") else ""
            type_html = '<span class="sf-type %s">%s</span>' % (fam, E(s["type"])) if s.get("type") else ""
            boxes.append('<button class="sf-node%s" data-x="%s"><span class="sn">%s%s%s</span>%s<span class="st">%s</span>%s</button>'
                         % (" implicit" if s.get("implicit") else "", x, self.step_no(node, k), imp, type_html, when_html, E(step_label(s)), gate_html))
            if not semantic:
                continue
            for e in self.out_edges(ep):
                tn, tk = self.ref(e.get("to", ""))
                xto = self.xref(e.get("to", ""))
                infl = e.get("basis") == "inferred"
                if e["type"] in ("condition_true", "condition_false") and tn == node and tk and tk != k + 1:
                    arcs.append({"from": x, "to": self.eid(node, tk), "label": e.get("condition", ""), "inf": infl})
                elif e["type"] == "termination":
                    end = {"from": x, "label": e.get("condition", ""), "inf": infl}
                elif e["type"] == "fallback" and tn != node and tn in self.by_id:
                    outs.setdefault(tn, []).append((x, "%s %s" % (self.step_ref(node, k), e.get("condition", "")), infl))
                elif xto and e["type"] in XSKILL_TYPES:
                    xouts.setdefault(xto, []).append((x, "%s %s" % (self.step_ref(node, k), e.get("condition", "") or EDGE_GLYPH.get(e["type"], "")), infl))
            for e in self.in_edges(ep):
                fn, fk = self.ref(e.get("from", ""))
                xfrom = self.xref(e.get("from", ""))
                infl = e.get("basis") == "inferred"
                if fn != node and fn in self.by_id and e["type"] in ("dependency", "fallback"):
                    ins.setdefault(fn, []).append((x, "%s → %s" % (e.get("condition", ""), self.step_ref(node, k)), infl))
                if xfrom and e["type"] in XSKILL_TYPES:
                    xins.setdefault(xfrom, []).append((x, "%s → %s" % (e.get("condition", "") or "来自", self.step_ref(node, k)), infl))
        if semantic and steps:
            first = self.eid(node, 1)
            for e in self.in_edges(node):
                fn, fk = self.ref(e.get("from", ""))
                xfrom = self.xref(e.get("from", ""))
                infl = e.get("basis") == "inferred"
                if fn in self.by_id and e["type"] in ("dependency", "fallback"):
                    ins.setdefault(fn, []).append((first, (self.step_ref(fn, fk) + " " if fk else "") + e.get("condition", "") + " → 此处", infl))
                if xfrom and e["type"] in XSKILL_TYPES:
                    xins.setdefault(xfrom, []).append((first, ("Step %d " % fk if fk else "") + (e.get("condition", "") or "来自") + " → 此处", infl))
            for l in (self.sem or {}).get("loops", []):
                if l["node"] == node and 0 < l["from"] <= len(steps) and 0 < l["to"] <= len(steps):
                    self.SUBFLOW_LOOPS.setdefault(sid, []).append({"from": self.eid(node, l["from"]), "to": self.eid(node, l["to"]),
                                                                   "label": l.get("label") or l.get("condition") or ""})
            self.SEM_EDGES[sid] = {"arcs": arcs}
            if end:
                self.SEM_EDGES[sid]["end"] = end

        def ext(n, conns, out):
            xs, infs, small = self.conn_attrs(conns, out)
            go = "showStep('%s','%s')" % (n, self.eid(n, 1)) if self.steps.get(n) else "showNode('%s')" % n
            return '<button class="sf-ext %s" data-%s="%s" data-inf="%s" onclick="%s"><span class="xid">%s · %s</span><span class="xt">%s</span><small>%s</small></button>' % (
                "out" if out else "in", "from" if out else "at", xs, infs, go, n, self.layers.get(n, {}).get("layer", ""), E(self.chip_title(n)), small)
        exts = "".join(ext(n, c, False) for n, c in ins.items()) + "".join(ext(n, c, True) for n, c in outs.items())

        def xext(key, conns, out):
            xskill, xnode = key
            xs, infs, small = self.conn_attrs(conns, out)
            return '<a class="sf-ext xskill %s" data-%s="%s" data-inf="%s" href="%s"><span class="xid">⧉ %s</span><span class="xt">%s</span><small>%s</small></a>' % (
                "out" if out else "in", "from" if out else "at", xs, infs, E(self.xlink(xskill, xnode)), E(xskill), xnode, small)
        exts += "".join(xext(k, c, False) for k, c in xins.items()) + "".join(xext(k, c, True) for k, c in xouts.items())
        lane = ('<div class="sf-lane">%s</div>' % exts) if exts else ""
        bits = ["外部节点 · ◂ 点线 = 依赖来源 · ⤓ 橙线 = 兜底去向%s" % (" · ⧉ = 其他 skill(点击跨页)" if xins or xouts else "")] if exts else []
        bits.append("单击线条高亮两端(其余淡出)· Esc 清除")
        legend = '<div class="sf-legend">%s</div>' % " · ".join(bits)
        end_html = '<span class="sf-end">⦿<small>END</small></span>' if end else ""
        return ('<div class="stepper" id="%s"><div class="subflow"><div class="sf-canvas"><svg class="sf-svg"></svg>'
                '<div class="sf-row">%s%s</div>%s</div></div>%s' % (sid, "".join(boxes), end_html, lane, legend))

    def render_dim(self, node, k, dim, items):
        if not items:
            return ""
        h = '<p class="sem-h">%s</p>' % DIM_LABEL.get(dim, dim)
        if dim in ("criteria", "quality_standards"):
            cid = "ckl%d%d%s" % (int(node[1:]), k, dim[0])
            lis = "".join('<li data-source="%s"><label><input type="checkbox"><span>%s%s%s</span></label></li>' % (c.get("source", ""), E(c["text"]), self.qt(c), self.inf(c)) for c in items)
            return '<p class="sem-h">%s <span class="ck-badge" id="%s">0/%d</span></p><ul class="checklist" id="%s">%s</ul>' % (DIM_LABEL[dim], cid.replace("ckl", "ck"), len(items), cid, lis)
        if dim == "examples" and all(" → " in c["text"] for c in items):
            rows = "".join('<tr data-source="%s"><td>%s</td><td>%s</td></tr>' % (c.get("source", ""), E(c["text"].split(" → ")[0]), E(c["text"].split(" → ", 1)[1])) for c in items)
            return h + '<div class="scroll"><table class="tbl rowsel" data-echo="{0} ⇒ {1}"><thead><tr><th>情形</th><th>做法</th></tr></thead><tbody>%s</tbody></table></div>' % rows
        if dim == "tools":
            return h + "".join('<pre class="code" data-source="%s">%s</pre>' % (c.get("source", ""), E(c["text"])) for c in items)
        if dim == "presentation":
            body = "".join('<details><summary>%s(%s)</summary><div class="acc-body"><pre class="code">%s</pre></div></details>' % (E(c["text"]), c.get("source", ""), E(src_text(self.static, c["source"]))) for c in items if c.get("source"))
            return h + '<div class="acc">%s</div>' % body
        if dim == "governance":
            return h + "".join('<div class="gov" data-source="%s">%s%s%s</div>' % (c.get("source", ""), E(c["text"]), self.qt(c), self.inf(c)) for c in items)
        cls = {"failure_modes": " fail", "heuristics": " tips"}.get(dim, "")
        tag = "ol" if dim == "procedure" else "ul"
        return h + '<%s class="sem-list%s">%s</%s>' % (tag, cls, "".join(self.claim_li(c) for c in items), tag)

    def render_cards(self, node):
        out = []
        static_steps = {s["line_start"]: s for s in self.by_id[node]["steps"]}
        for k, s in enumerate(self.steps[node], 1):
            x = self.eid(node, k)
            src = "SKILL.md:" + str(s["lines"])
            fam = TYPE_FAMILY.get(s.get("type", ""), "")
            gate = self.checks.get("%s.%d" % (node, k))
            gate_html = (' <span class="gate-badge">%s</span>' % ("◆ 验证闸口" if gate["kind"] == "validate" else "⏸ 需用户确认")) if gate else ""
            type_html = ' <span class="tbadge %s">%s</span>' % (fam, E(s["type"])) if s.get("type") else ""
            head = '<h4>%s · %s%s%s%s</h4>' % (self.step_ref(node, k), E(step_label(s)), type_html, gate_html, ' <span class="inf">隐含步骤</span>' if s.get("implicit") else "")
            goal = ('<p class="goal" data-source="%s"><strong>目标</strong> %s%s%s</p>' % (s["goal"].get("source", ""), E(s["goal"]["text"]), self.qt(s["goal"]), self.inf(s["goal"]))) if s.get("goal") else ""
            dims = dict(s.get("semantics") or {})
            dims.update(s.get("attachments") or {})
            body = "".join(self.render_dim(node, k, d, dims.get(d, [])) for d in DIM_ORDER)
            ls = int(str(s["lines"]).split("-")[0])
            st = static_steps.get(ls)
            orig_title = s.get("title") if s.get("label") and s.get("label") != s.get("title") else None
            if not self.sem:  # 静态基线:原文直接展开
                orig = '<div class="card" data-source="%s">%s</div>' % (
                    src,
                    md_to_html(
                        st["content"] if st else src_text(self.static, src, strip_fence=False),
                        self.heading_hierarchy,
                    ),
                )
            else:
                orig = ""  # 语义模式:「显示出处」已提供溯源,原文手风琴多余且破坏卡片简洁性
            out.append('<div class="explain-card" id="%s" data-source="%s">%s%s%s%s%s%s</div>' % (
                x, src, head, goal, body, orig, self.flow_line("%s.%d" % (node, k)) if self.sem else "", self.dd("%s %s" % (self.step_ref(node, k), s["title"]), src)))
        return "".join(out)

    # ---- 面板 ----
    def cross_claims(self, node):
        """其它节点的步骤里引用了本节点行号范围的断言(跨锚定)→ [(claim, 'n03.3')]"""
        n = self.by_id[node]
        out = []
        for nid, steps in self.steps.items():
            if nid == node:
                continue
            for k, s in enumerate(steps, 1):
                for dim, items in list((s.get("semantics") or {}).items()) + list((s.get("attachments") or {}).items()):
                    for c in items:
                        m = re.match(r"SKILL\.md:(\d+)", c.get("source", ""))
                        if m and n["line_start"] <= int(m.group(1)) <= n["line_end"]:
                            out.append((c, "%s.%d" % (nid, k), dim))
        return out

    def panel(self, node):
        n = self.by_id[node]
        ly = self.layers.get(node)
        ph = node + (" · %s · %s" % (LAYER_NAME[ly["layer"]], ly.get("role", "")) if ly else " · SKILL.md:%d-%d" % (n["line_start"], n["line_end"]))
        # overrides 的 leads 是为语义版写的引语(常描述徽章/闸口/弧线等语义层视觉);静态基线页没有这些元素,不吃
        lead = self.ov.get("leads", {}).get(node) if self.sem else None
        if not lead:
            if ly and ly["layer"] == "W" and self.steps.get(node):
                lead = "流程节点。每个步骤的首行 ⇢ 是进入该步的条件;类型徽章来自语义层的步骤分型,◆ 验证闸口、⏸ 需用户确认;上方弧线是条件跳转(蓝,虚线 = 推断)与重试环(橙);下方外部节点栏里,点线是别的节点供给本步的依赖,橙线是兜底去向;⦿ 是终止点。"
            elif ly:
                lead = "%s节点,不是流程步骤。" % LAYER_NAME[ly["layer"]].split(" · ")[1]
            else:
                lead = "原文节点(SKILL.md:%d-%d)。" % (n["line_start"], n["line_end"])
        body = []
        if self.steps.get(node):
            first_step = n["steps"][0]["line_start"] if n["steps"] else None
            intro = n["content"] if first_step is None else "\n".join(self.static["lines"][n["line_start"]:first_step - 1]).strip("\n")
            if intro.strip():
                body.append('<div class="card" data-source="SKILL.md:%d-%d">%s</div>' % (n["line_start"] + 1, (first_step - 1) if first_step else n["line_end"], md_to_html(intro, self.heading_hierarchy)))
            body.append(self.build_stepper(node) + self.render_cards(node))
        else:
            body.append('<div class="card" data-source="SKILL.md:%d-%d">%s%s</div>' % (n["line_start"], n["line_end"], md_to_html(n["content"], self.heading_hierarchy), self.dd(n["title"], "SKILL.md:%d-%d" % (n["line_start"], n["line_end"]))))
        if self.sem:
            if ly and ly["layer"] == "R" and self.sem.get("routing", {}).get("triggers"):
                body.append('<p class="sem-h">触发条件(R 层)</p><ul class="rules">%s</ul>' % "".join(self.claim_li(c) for c in self.sem["routing"]["triggers"]))
            cross = self.cross_claims(node)
            if cross:
                body.append('<p class="sem-h">语义层挂载(本节点内容被哪一步使用)</p><ul class="sem-list">%s</ul>' % "".join(
                    self.claim_li(c, " → %s" % self.jump_to(ep)) for c, ep, dim in cross))
            fl = self.flow_line(node)
            if fl:
                body.append(fl)
        if n["resources"]:
            body.append('<p class="sem-h">引用的资源</p><ul class="sem-list">%s</ul>' % "".join("<li>%s%s</li>" % (E(p), "" if ok else ' <span class="inf">缺失</span>') for p, ok in n["resources"]))
        return '<section class="panel" id="p-%s"><div class="panel-head"><span class="ph-id">%s</span><h2>%s</h2><p class="lead">%s</p></div>%s<div class="pager"></div></section>' % (
            node, E(ph), E(n["title"]), E(lead) if lead == self.ov.get("leads", {}).get(node) else lead, "".join(body))

    # ---- 合成 R 节点:frontmatter description 的路由信息 ----
    R_ID = "rt"

    R_TITLE_RE = re.compile(
        r"when to (use|apply|request|trigger)|when to (run|invoke|use) this|when not to use|use when"
        r"|trigger|activation|applicability|何时(触发|使用|用)|使用时机|触发(条件|时机)", re.I)

    def routing_node(self):
        """构建路由入口节点(rt 芯片 + 目录项 + 面板)。
        内容永远来自 frontmatter description:这是 Agent 路由时唯一能看到的对外信号。
        "When to Use" 类内部节点属于 W/A 层详细指导,不用于 rt。
        语义层已通过 self.layers 显式标注 R-layer 节点时跳过(那时节点已有视觉区分)。"""
        if any(ly.get("layer") == "R" for ly in self.layers.values()):
            return None
        desc = (self.static["description"] or "").strip()
        if not desc:
            return None
        rt = (self.sem or {}).get("routing") or {}
        trig, excl = rt.get("triggers") or [], rt.get("exclusions") or []
        desc_line = next((i + 1 for i, l in enumerate(self.static["lines"]) if l.startswith("description:")), 1)
        src = "SKILL.md:%d" % desc_line
        title = self.ov.get("chip_titles", {}).get(self.R_ID) or "何时触发"
        if trig:
            sub = "%d 类触发信号" % len(trig)
        else:
            first = re.sub(r"\s+", " ", desc).strip()
            sub = (first[:20] + "…") if len(first) > 20 else first
        lead = self.ov.get("leads", {}).get(self.R_ID) or "这是路由层(R):frontmatter description 给出的激活条件,任一出现就进入执行路径。它不是流程步骤,是入口条件。"
        chip = '<button class="node-chip" data-node="%s"><span class="nid">%s%s</span><span class="nt">%s</span><span class="sub">%s</span></button>' % (self.R_ID, self.R_ID, " · R" if self.sem else "", E(title), E(sub))
        toc = '<button data-node="%s"><span class="tid">%s</span><span class="tt">%s</span><span class="tl">%s</span></button>' % (self.R_ID, self.R_ID, E(title), E(src.replace("SKILL.md:", "")))
        body = ['<div class="card" data-source="%s">%s%s</div>' % (src, md_to_html(desc), self.dd(title, src))]
        if trig:
            body.append('<p class="sem-h">触发条件(R 层)</p><ul class="rules">%s</ul>' % "".join(self.claim_li(c) for c in trig))
        if excl:
            body.append('<p class="sem-h">排除条件</p><ul class="rules">%s</ul>' % "".join(self.claim_li(c) for c in excl))
        ph = "%s · %s · activation · frontmatter" % (self.R_ID, LAYER_NAME["R"]) if self.sem else "%s · %s" % (self.R_ID, src)
        panel = '<section class="panel" id="p-%s"><div class="panel-head"><span class="ph-id">%s</span><h2>%s</h2><p class="lead">%s</p></div>%s<div class="pager"></div></section>' % (
            self.R_ID, ph, E(title), lead, "".join(body))
        return {"chip": chip, "toc": toc, "panel": panel, "title": title}

    def recon_panel(self):
        S = self.sem
        rec = S.get("reconciliation") or {}
        if not rec.get("nodes_total") and not S.get("merge"):
            return "", ""
        def bas(o):
            ex = inf = 0
            st = [o]
            while st:
                v = st.pop()
                if isinstance(v, dict):
                    if "source" in v and "quote" in v:
                        if v.get("basis") == "inferred":
                            inf += 1
                        else:
                            ex += 1
                    st.extend(v.values())
                elif isinstance(v, list):
                    st.extend(v)
            return ex, inf
        ex_n, inf_n = bas(S)
        chips = ["schema %s · %s" % (S["schema"], S["generator"]), "断言 %d:explicit %d · inferred %d" % (ex_n + inf_n, ex_n, inf_n)]
        if S.get("wsa_profile"):
            p = S["wsa_profile"]
            chips.append("W/S/A %s/%s/%s · %s" % (p.get("W"), p.get("S"), p.get("A"), p.get("label", "")))
        mg = S.get("merge")
        if mg:
            chips.append("解析器:%s · 一致 %d · 独有 %d · 冲突 %d" % (",".join(mg.get("parsers", [])), mg.get("agreements", 0), mg.get("singletons", 0), len(mg.get("conflicts", []))))
        rows = ""
        for n in self.nodes:
            ly = self.layers.get(n["id"], {})
            w = ly.get("layer") == "W"
            rows += '<tr><td>%s</td><td>%s</td><td>%d-%d</td><td>%d</td><td>%s</td><td class="%s">%s</td></tr>' % (
                n["id"], E(n["title"]), n["line_start"], n["line_end"], len(n["steps"]), "%s / %s" % (ly.get("layer", "?"), ly.get("role", "")) if ly else "—",
                "w" if w else "nw", "流程节点" if w else ("非流程标题 → %s 层" % ly["layer"] if ly else "未归类"))
        def sect(title, items, fmt):
            return '<p class="sem-h">%s(%d)</p><ul class="sem-list">%s</ul>' % (title, len(items), "".join("<li>%s</li>" % fmt(x) for x in items) if items else "<li>无</li>")
        body = '<div class="recon-sum">%s</div>' % "".join("<span>%s</span>" % E(c) for c in chips)
        body += '<p class="sem-h">目录(静态相对 L1)vs 分层(语义)</p><div class="scroll"><table class="tbl recon-tbl"><thead><tr><th>节点</th><th>标题</th><th>行号</th><th>L2 步数</th><th>归属 / 角色</th><th>印证结论</th></tr></thead><tbody>%s</tbody></table></div>' % rows
        body += sect("非流程标题", rec.get("non_workflow_nodes", []), lambda x: "<code>%s</code> → %s 层:%s" % (x.get("node"), x.get("layer"), E(x.get("why", ""))))
        body += sect("隐含步骤(文本有、目录无)", rec.get("implicit_steps", []), lambda x: "锚 %s,%s 步(%s)" % (self.jump_to(x.get("anchor", "")), x.get("count", "?"), x.get("source", "")))
        body += sect("顺序偏差(文档顺序 ≠ 执行顺序)", rec.get("order_deviations", []), lambda x: "%s(%s)" % (E(x.get("text", "")), x.get("source", "")))
        body += sect("跨锚定(知识写在别处)", rec.get("cross_anchored", []), lambda x: "%s ← <code>%s</code>(%s)" % (E(x.get("item", "")), x.get("from_node", ""), x.get("source", "")))
        body += sect("裁定记录", rec.get("judgment_calls", []), lambda x: "<code>%s</code> %s(%s)" % (x.get("anchor", ""), E(x.get("text", "")), x.get("source", "")))
        if mg and mg.get("conflicts"):
            body += '<p class="sem-h">解析器冲突(已按规则暂选,需回原文裁决)</p><div class="scroll"><table class="tbl"><thead><tr><th>锚点</th><th>候选</th><th>暂选</th><th>规则</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (E(c["key"]), E(json.dumps(c["candidates"], ensure_ascii=False)), E(str(c["chosen"])), E(c["rule"])) for c in mg["conflicts"])
        if rec.get("notes"):
            body += '<p class="sem-h">备注</p><ul class="sem-list">%s</ul>' % "".join("<li>%s</li>" % E(x) for x in rec["notes"])
        if self.val_notes:
            body += '<p class="sem-h">校验</p><ul class="sem-list">%s</ul>' % "".join("<li>%s</li>" % E(x) for x in self.val_notes)
        toc = '<button data-node="recon"><span class="tid">⊕</span><span class="tt">印证报告</span><span class="tl">%s</span></button>' % E(S["generator"])
        panel = '<section class="panel" id="p-recon"><div class="panel-head"><span class="ph-id">印证 · 静态目录 vs 语义流程 · %s</span><h2>印证报告</h2><p class="lead">结构拆解的目录是坐标系;语义层只能叠加。这里列出两者对不上的地方,以及多个解析器之间的一致与冲突。</p></div>%s<div class="pager"></div></section>' % (E(S["generator"]), body)
        return panel, toc

    # ---- 流程带 ----
    def rail(self):
        S = self.sem or {}
        def chip(n, sat=False, sub=None):
            if sub is None:
                sub = S.get("node_summaries", {}).get(n) or ""
                if not sub and not self.sem:
                    first = re.sub(r"\s+", " ", re.sub(r"[#*`>|\[\]-]", "", self.by_id[n]["content"])).strip()
                    sub = (first[:20] + "…") if len(first) > 20 else first
            nid = n + (" · " + self.layers[n]["layer"] if n in self.layers else "")
            return '<button class="node-chip%s" data-node="%s"><span class="nid">%s</span><span class="nt">%s</span><span class="sub">%s</span></button>' % (" sat" if sat else "", n, nid, E(self.chip_title(n)), E(sub))
        if self.layers:
            main_nodes = [n for n in self.ids if self.layers.get(n, {}).get("layer") in ("R", "W")]
            sat_nodes = [n for n in self.ids if self.layers.get(n, {}).get("layer") in ("S", "A")]
            other = [n for n in self.ids if n not in main_nodes and n not in sat_nodes]
            main_nodes += other
            parts = []
            rn = self.routing_node()
            if rn:
                parts.append('<div class="group" data-label="R · 触发">%s</div>' % rn["chip"])
                parts.append('<span class="arrow big cap" data-cap="进入">⇒</span>')
            for i, n in enumerate(main_nodes):
                if i:
                    prev = main_nodes[i - 1]
                    fb = [e for e in self.edges if e["type"] == "fallback" and self.ref(e.get("from", ""))[0] == prev and e.get("to") == n]
                    parts.append('<span class="arrow big cap" data-cap="%s">⇒</span>' % ("找不到时 ⤓" if fb else "进入"))
                ly = self.layers.get(n, {})
                role = ly.get("role", "")
                label = {"R": "R · 触发", "W": "W · 执行主线" if role == "main_flow" else ("W · 兜底" if role == "fallback" else "W · 流程")}.get(ly.get("layer"), ly.get("layer", "节点"))
                parts.append('<div class="group%s" data-label="%s">%s</div>' % (" main" if role == "main_flow" else "", E(label), chip(n)))
            sats = []
            for n in sat_nodes:
                tos = sorted({(self.ref(e["to"])[0], self.ref(e["to"])[1]) for e in self.out_edges(n)   # 跨 skill 的步号不是本页的 Step N,别混进来
                              if self.ref(e["to"])[1] and not self.xref(e.get("to", ""))})
                seen = []
                for e in self.out_edges(n):
                    tgt = self.ref(e.get("to", ""))[0]
                    if tgt and tgt in main_nodes and tgt not in seen:
                        seen.append(tgt)
                        self.RAIL_LINKS.append({"from": n, "to": tgt})
                sub = S.get("node_summaries", {}).get(n, "") + ((" · → " + " / ".join(self.step_ref(tn, tk) for tn, tk in tos)) if tos else "")
                sats.append(chip(n, True, sub))
            sat_html = '<div class="rail-sat" data-label="支撑层 S / A · 点线 = 依赖边">%s</div>' % "".join(sats) if sats else ""
            return '<div class="rail-sem" id="railSem"><svg class="rail-svg" id="railSvg"></svg><div class="rail-main">%s</div>%s</div>' % ("".join(parts), sat_html)
        groups = S.get("groups") or [{"label": "节点(文档顺序)", "nodes": self.ids, "main": False}]
        rn = self.routing_node()
        out = []
        for gi, g in enumerate(groups):
            if gi:
                out.append('<span class="arrow big">⇒</span>')
            chips = '<span class="arrow">→</span>'.join(([rn["chip"]] if rn and gi == 0 else []) + [chip(n) for n in g["nodes"] if n in self.by_id])
            out.append('<div class="group%s" data-label="%s">%s</div>' % (" main" if g.get("main") else "", E(g["label"]), chips))
        return "".join(out)

    # ---- 组装 ----
    def render(self, out_file, write_md=True):
        S = self.sem or {}
        base = (REPO / "templates/base.html").read_text(encoding="utf-8")
        themes = "".join((REPO / "templates/themes" / f).read_text(encoding="utf-8") for f in ["docs.css", "blueprint.css", "ide.css", "whiteboard.css"])
        name = self.static["skill_name"]
        nodes_json = self.ids[:]
        titles = {n: self.chip_title(n) for n in self.ids}
        panels = [self.panel(n) for n in self.ids]
        toc = "".join('<button data-node="%s"><span class="tid">%s</span><span class="tt">%s</span><span class="tl">%d-%d</span></button>' % (
            n["id"], n["id"], E(n["title"]), n["line_start"], n["line_end"]) for n in self.nodes)
        rn = self.routing_node()
        if rn:
            nodes_json.insert(0, self.R_ID)
            titles[self.R_ID] = rn["title"]
            panels.insert(0, rn["panel"])
            toc = rn["toc"] + toc
        if self.sem:
            rp, rt = self.recon_panel()
            if rp:
                panels.append(rp)
                toc += rt
                nodes_json.append("recon")
                titles["recon"] = "印证报告"
        desc_line = next((i + 1 for i, l in enumerate(self.static["lines"]) if l.startswith("description:")), 1)
        claims = 0
        if self.sem:
            st = [S]
            while st:
                v = st.pop()
                if isinstance(v, dict):
                    claims += 1 if ("source" in v and "quote" in v) else 0
                    st.extend(v.values())
                elif isinstance(v, list):
                    st.extend(v)
        eyebrow = "SKILL WORKFLOW · %d NODES · SKILL.md %d LINES" % (len(self.ids), len(self.static["lines"]))
        if self.sem:
            eyebrow += " · SEMANTICS BY %s · %d CLAIMS VERIFIED" % (S["generator"].upper(), claims)
        if self.ov.get("eyebrow_extra"):
            eyebrow += " · " + self.ov["eyebrow_extra"]
        steps_total = sum(len(n["steps"]) for n in self.nodes)
        if self.sem and S.get("thesis"):
            thesis_title, thesis_src = "执行总纲:" + S["thesis"]["text"], S["thesis"].get("source", "SKILL.md:%d" % desc_line)
        else:
            thesis_title, thesis_src = "%d 个目录节点 · %d 个子步骤(静态基线,未做语义富化)" % (len(self.ids), steps_total), "SKILL.md:%d" % desc_line
        thesis_html = self.ov.get("thesis_html", "" if self.sem else "按自适应相对层级切分 L1 节点与 L2 子步骤,点节点进入;开启「显示出处」可回查每块内容的行号。")
        if self.sem and S.get("wsa_profile"):
            p = S["wsa_profile"]
            thesis_html += '<br><span class="wsa">W %s · S %s · A %s → %s</span>' % (p.get("W"), p.get("S"), p.get("A"), E(p.get("label", "")))
        gen = S.get("generator", "static")
        footer = "由 <strong>skill-to-webpage</strong> 生成 · 源:<code>%s/SKILL.md</code>(%d 行,%d 个目录节点)· 输出:<code>%s</code> · 拆解零 LLM" % (
            E(name), len(self.static["lines"]), len(self.ids), E(str(self.out_dir.relative_to(REPO)) if str(self.out_dir).startswith(str(REPO)) else str(self.out_dir)))
        if self.sem:
            mg = S.get("merge")
            footer += " · 语义层由 <code>%s</code> 产出,%d 条断言经 <code>validate_semantics.py</code> 逐条回读核对" % (E(gen), claims)
            if mg:
                footer += "(解析器 %s,冲突 %d 处)" % (E(",".join(mg.get("parsers", []))), len(mg.get("conflicts", [])))
            footer += " · 渲染 Agent 负责排版与衔接文案 · 带出处行号的内容为 SKILL.md 原文,开启「显示出处」可见每条断言的逐字引文"
        else:
            footer += " · 静态基线页:未做语义富化,所有内容为 SKILL.md 原文"
        footer += " · " + _dt.date.today().isoformat()
        extra_meta = self.static.get("extra_metadata", {})
        if extra_meta:
            rows = "".join('<tr><th>%s</th><td>%s</td></tr>' % (E(k), E(str(v))) for k, v in extra_meta.items())
            skill_metadata_html = '<details class="skill-info"><summary>Skill Info</summary><table>%s</table></details>' % rows
        else:
            skill_metadata_html = ""
        rail_html = self.rail()  # 必须先于 component_scripts 求值:RAIL_LINKS 在 rail() 里填充
        slots = {
            "{{lang}}": self.ov.get("lang", "zh-CN"),
            "{{title}}": self.ov.get("title", "%s · Skill Workflow" % name),
            "{{theme_styles}}": themes,
            "{{component_styles}}": "/* none */",
            "{{flow_lib}}": (REPO / "templates/flow-lib.js").read_text(encoding="utf-8").rstrip("\n"),
            "{{component_scripts}}": "SEM_EDGES = %s;\nRAIL_LINKS = %s;\nsemDrawRail();%s" % (json.dumps(self.SEM_EDGES, ensure_ascii=False), json.dumps(self.RAIL_LINKS, ensure_ascii=False), self.variant_switcher_js(self.page_name) + self.bundle_back_js()),
            "{{default_theme}}": self.theme,
            "{{eyebrow}}": eyebrow,
            "{{skill_name}}": E(name), "{{skill_name_js}}": name.replace('"', ""),
            "{{skill_dir}}": str(self.skill_dir), "{{kb_dir}}": str(self.out_dir / "static"),
            "{{description_source}}": "SKILL.md:%d" % desc_line,
            "{{description_html}}": self.ov.get("description_html") or E(self.static["description"] or "(无 description)"),
            "{{thesis_source}}": thesis_src, "{{thesis_title}}": E(thesis_title) if "<" not in thesis_title else thesis_title, "{{thesis_html}}": thesis_html,
            "{{footer_note}}": footer,
            "{{nodes_json}}": json.dumps(nodes_json), "{{node_titles_json}}": json.dumps(titles, ensure_ascii=False),
            "{{node_res_json}}": json.dumps({n["id"]: n["resources"] for n in self.nodes} | ({"recon": []} if "recon" in nodes_json else {}) | ({self.R_ID: []} if rn else {}), ensure_ascii=False),
            "{{subflow_loops_json}}": json.dumps(self.SUBFLOW_LOOPS, ensure_ascii=False),
            "{{initial_node_json}}": json.dumps(nodes_json[0] if nodes_json else "n01"),
            "{{skill_metadata_html}}": skill_metadata_html,
            "{{rail_groups}}": rail_html, "{{toc_items}}": toc, "{{panels}}": "\n".join(panels),
        }
        out = base
        # 先按模板声明对账:模板里出现、slots 里没有的槽位一定填不上。
        # 这一步放在替换之前 —— 替换之后再扫全文,原文引文里的 {{…}} 会被误当成漏填。
        left = sorted(set(re.findall(r"\{\{[a-z_0-9]+\}\}", out)) - set(slots))
        if left:
            raise SystemExit("未填充的槽位: %r" % left)
        for k, v in slots.items():
            n = out.count(k)
            if n != 1:  # 0 = 槽位缺失;>1 = 模板里(通常是注释)多写了一份 token,会把内容注入两次并破坏 CSS/JS
                raise SystemExit("槽位 %s 在模板中出现 %d 次,必须恰好 1 次" % (k, n))
            out = out.replace(k, v)
        out_file = Path(out_file) if out_file else self.out_dir / ("%s-workflow.html" % self.page_name)
        out_file.write_text(out, encoding="utf-8")
        if write_md:
            self.write_md(out_file.with_suffix(".md"))
        print("[render] %s (%d bytes) · 语义层:%s · 节点 %d · 步骤 %d%s" % (out_file, len(out), gen, len(self.ids), steps_total,
              (" · 断言 %d" % claims) if self.sem else ""))
        for n in self.val_notes[:3]:
            print("  ·", n)

    def variant_switcher_js(self, name):
        """多版页面:在顶栏「显示出处」前插入版本链接(相对文件名,file:// 与 http 都能用)。"""
        if len(self.variants) < 2:
            return ""
        links = "".join('<a href="%s"%s>%s</a>' % (E("%s%s/%s-workflow.html" % (self.link_base, v, name)), ' class="cur"' if v == self.current else "", E(v)) for v in self.variants)
        html = '<span class="variants"><span class="vl">版本</span>%s</span>' % links
        return ("\n(function () { var host = document.getElementById(\"srcToggle\"); if (!host || !host.parentNode) { return; }"
                " var box = document.createElement(\"span\"); box.innerHTML = %s; host.parentNode.insertBefore(box.firstChild, host); })();" % json.dumps(html, ensure_ascii=False))

    def bundle_back_js(self):
        """bundle 成员页:顶栏 brand 后插入「← <group> 总览」返回链接。"""
        if not self.bundle_name:
            return ""
        href = "%s../%s-workflow.html" % (self.link_base, self.bundle_name)
        html = '<a class="bundle-back" href="%s">← %s 总览</a>' % (E(href), E(self.bundle_name))
        return ("\n(function () { var b = document.querySelector(\".topbar .brand\"); if (!b || !b.parentNode) { return; }"
                " var box = document.createElement(\"span\"); box.innerHTML = %s; b.parentNode.insertBefore(box.firstChild, b.nextSibling); })();" % json.dumps(html, ensure_ascii=False))

    def write_md(self, path):
        S = self.sem or {}
        name = self.static["skill_name"]
        L = ["# %s · Workflow(叙事版)" % name, "", "> %s" % (self.static["description"] or "(无 description)"), ""]
        if S.get("thesis"):
            L += ["**执行总纲**:%s(%s)" % (S["thesis"]["text"], S["thesis"].get("source", "")), ""]
        for n in self.nodes:
            ly = self.layers.get(n["id"])
            L.append("## %s %s(SKILL.md:%d-%d)%s" % (n["id"], self.chip_title(n["id"]) if self.ov.get("chip_titles", {}).get(n["id"]) else n["title"], n["line_start"], n["line_end"], (" · %s / %s" % (ly["layer"], ly.get("role", ""))) if ly else ""))
            L.append("")
            if S.get("node_summaries", {}).get(n["id"]):
                L += [S["node_summaries"][n["id"]], ""]
            for k, s in enumerate(self.steps.get(n["id"], []), 1):
                L.append("%d. **%s**%s(SKILL.md:%s)%s" % (k, step_label(s), (" · " + s["type"]) if s.get("type") else "", s["lines"],
                                                          (" — " + s["goal"]["text"]) if s.get("goal") else ""))
            for e in self.out_edges(n["id"]) + [e for k in range(1, len(self.steps.get(n["id"], [])) + 1) for e in self.out_edges("%s.%d" % (n["id"], k))]:
                if e["type"] not in ("condition_false",):
                    L.append("- %s %s → %s:%s(%s%s)" % (EDGE_GLYPH.get(e["type"], "→"), e.get("from"), e.get("to"), e.get("condition", ""), e.get("source", ""), ",推断" if e.get("basis") == "inferred" else ""))
            L.append("")
        rec = S.get("reconciliation") or {}
        if rec.get("nodes_total"):
            L += ["---", "", "**印证**:节点 %s/%s 归类 · 步骤 %s/%s 分型 · 非流程标题 %d · 隐含步骤 %d · 顺序偏差 %d · 跨锚定 %d" % (
                rec.get("nodes_classified"), rec.get("nodes_total"), rec.get("steps_typed"), rec.get("steps_total"),
                len(rec.get("non_workflow_nodes", [])), sum(x.get("count", 1) for x in rec.get("implicit_steps", [])), len(rec.get("order_deviations", [])), len(rec.get("cross_anchored", []))), ""]
        L += ["---", "由 skill-to-webpage 生成 · 语义层:%s · %s" % (S.get("generator", "static(无语义层)"), _dt.date.today().isoformat())]
        path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output_dir")
    ap.add_argument("--variants", nargs="+", help="要出的版本:merged / static / <解析器名> …;第一个同时作为主页面")
    ap.add_argument("--semantics", default="merged", help="单版模式:语义文件夹名;默认 merged,不存在则渲染静态基线")
    ap.add_argument("--theme", default="docs", choices=["docs", "blueprint", "ide", "whiteboard"])
    ap.add_argument("--overrides")
    ap.add_argument("--skill-dir")
    ap.add_argument("--out")
    ap.add_argument("--no-md", action="store_true")
    a = ap.parse_args()
    if not a.variants:
        Renderer(a.output_dir, a.semantics, a.theme, a.overrides, a.skill_dir).render(a.out, not a.no_md)
        return
    out_dir = Path(a.output_dir).resolve()
    done, skipped = [], []
    for v in a.variants:
        r = Renderer(a.output_dir, v, a.theme, a.overrides, a.skill_dir, variants=a.variants, current=v, link_base="../")
        if v != "static" and (r.sem_missing or r.sem is None):
            skipped.append("%s(%s)" % (v, "没有 semantics.json" if r.sem_missing else "校验整体回落"))
            continue
        folder = out_dir / v
        folder.mkdir(parents=True, exist_ok=True)
        r.render(folder / ("%s-workflow.html" % r.page_name), not a.no_md)
        done.append(v)
    if not done:
        raise SystemExit("没有任何版本可渲染:" + "; ".join(skipped))
    main_v = "merged" if "merged" in done else done[0]
    root = Renderer(a.output_dir, main_v, a.theme, a.overrides, a.skill_dir, variants=a.variants, current=main_v, link_base="")
    root.render(out_dir / ("%s-workflow.html" % root.page_name), not a.no_md)
    print("[main] %s-workflow.html ← %s" % (root.page_name, main_v))
    if skipped:
        print("[skipped] " + "; ".join(skipped))


if __name__ == "__main__":
    main()
