# 组件层(components.md)

Agent 渲染时从这里挑范式,抄 HTML + 填数据。所有样式与交互 JS 已内置在 `base.html`,组件片段**不需要**自带 CSS/JS,除非标注"需注入"。

## 通用约定(每个组件都遵守)

1. **出处**:每个内容块加 `data-source="SKILL.md:起始行-结束行"`(资源类内容可用文件路径)。
2. **追问**:每个带 `data-source` 的块,内部末尾加追问按钮,概念名 = 该块标题/核心概念:

```html
<button class="deep-dive-btn" title="追问" onclick="openDeepDive('概念名','SKILL.md:N-M')">?</button>
```

3. **JS 安全**:内联 onclick 里的字符串禁用中文弯引号;跳转一律用 `showNode('nXX')` / `showStep('nXX','eYY')`。
4. **衔接层**:每个 panel 开头必有 `.lead` 段首引语(Agent 现写);卡片标题口语化重写,不照搬原文小标题。

---

## 1. 节点总览(rail)分组 + 节点(rail_groups 槽位)

节点按语义分组:理念/准备类、**执行主线**(实线 accent 边框 + `.main`)、支撑/边界类。组间用 `⇒`,组内用 `→`。**芯片副标题写节点语义**("书 → 本地知识库"),不写渲染元数据(步数/环数)。

```html
<div class="group" data-label="理念与准备">
  <button class="node-chip" data-node="n01"><span class="nid">n01</span><span class="nt">哲学</span><span class="sub">3 条设计原则</span></button>
  <span class="arrow">→</span>
  <button class="node-chip" data-node="n02"><span class="nid">n02</span><span class="nt">运行入口</span><span class="sub">2 路分叉</span></button>
</div>
<span class="arrow big">⇒</span>
<div class="group main" data-label="执行主线">
  <button class="node-chip" data-node="n04"><span class="nid">n04</span><span class="nt">阶段 1 · 全书拆解</span><span class="sub">书 → 本地知识库</span></button>
</div>
```

## 2. 侧栏目录项(toc_items 槽位)

每个节点一行,带行号区间:

```html
<button data-node="n04"><span class="tid">n04</span><span class="tt">阶段 1:全书拆解</span><span class="tl">37-130</span></button>
```

## 3. 详情面板骨架(panels 槽位,每节点一个)

```html
<section class="panel" id="p-n04">
  <div class="panel-head">
    <span class="ph-id">n04 · 执行主线 · 含子流程</span>
    <h2>节点标题</h2>
    <p class="lead">段首引语(Agent 现写,一句提纲挈领)。</p>
  </div>
  <!-- 组件 4-11 按内容性质挑选放这里 -->
  <div class="pager"></div><!-- 上一步/下一步由 JS 自动填充,保留空容器 -->
</section>
```

## 4. 子流程图(大节点必用:节点内有相对 L2 子步骤时)

盒子横排 + SVG 连线层自动绘制:顺序边直线箭头;**环画成真实的边**(回边 = 上方虚线弧,自环 = 头顶小环,带流动动画和标签)。环数据写进 `{{subflow_loops_json}}`(key = stepper 的 id):

```html
<div class="stepper" id="st-n04">
  <div class="subflow">
    <div class="sf-canvas">
      <svg class="sf-svg"></svg>
      <div class="sf-row">
        <button class="sf-node" data-x="e141"><span class="sn">1.1</span>提取全文</button>
        <button class="sf-node" data-x="e144"><span class="sn">1.4</span>REPL 切片</button>
        <!-- 每个相对 L2 子步骤一个盒子,data-x 指向对应 explain-card 的 id -->
      </div>
    </div>
  </div>
  <div class="explain-card" id="e141" data-source="SKILL.md:47-56">
    <h4>Step 1.1 · 提取全文</h4>
    <p>子步骤正文…(可内嵌组件 5-10)</p>
    <button class="deep-dive-btn" title="追问" onclick="openDeepDive('Step 1.1 提取全文','SKILL.md:47-56')">?</button>
  </div>
  <!-- 每个盒子一张 explain-card,首个自动展开 -->
</div>
```

```json
{ "st-n04": [
    { "from": "e141", "to": "e141", "label": "提取失败 → 诊断 → 重试" },
    { "from": "e145", "to": "e144", "label": "逐章循环 · 下一章" }
] }
```

环说明卡(放在环的源/目标步骤的 explain-card 里,补充语义 + 跳转):

```html
<p class="loop-note">↻ <strong>迭代环:</strong>本步与 <button class="jump" onclick="showStep('n04','e145')">1.5 章节摘要</button> 逐章循环,直到全部完成。</p>
```

## 5. 理念/要点卡片组(2-4 条并列要点)

```html
<div class="cards">
  <article class="card" data-source="SKILL.md:12">
    <h3>口语化标题</h3>
    <p>要点正文,关键词用 <strong>加粗</strong>。</p>
    <button class="deep-dive-btn" title="追问" onclick="openDeepDive('口语化标题','SKILL.md:12')">?</button>
  </article>
</div>
```

两列版用 `<div class="cards two">`。

## 6. 分叉卡(入口/条件分支,点击跳转目标节点)

```html
<div class="forks">
  <button class="fork" data-source="SKILL.md:18" onclick="showNode('n04')">
    <span class="fk-tag">入口 ①</span>
    <h3>分支名</h3>
    <p>触发条件与去向说明。</p>
    <span class="fk-go">进入 n04 · 目标节点 →</span>
  </button>
</div>
```

## 7. 决策表格(可点行 → 结论回显)

适用:决策矩阵、模式选择表。加 `rowsel` class + `data-echo` 模板(`{N}` 为列号,回显行自动插在表格下方):

```html
<div class="scroll">
  <table class="tbl rowsel" data-echo="{0} ⇒ 首选 {2} · 备选 {3}">
    <thead><tr><th>性质</th><th>依据</th><th>首选</th><th>备选</th></tr></thead>
    <tbody><tr><td>因果推进</td><td>A→B→C 链条</td><td>causal_chain</td><td>accordion</td></tr></tbody>
  </table>
</div>
```

纯展示表格用 `<table class="tbl">`(不加 rowsel),始终包 `<div class="scroll">` 防溢出。

## 8. 可勾选清单(自检/检查点类内容)

`ul` 的 id 用 `ckl` 前缀,徽章 id 把 `ckl` 换成 `ck`(JS 按此配对,支持多份清单):

```html
<p style="margin-bottom:6px"><strong>人工核对清单</strong><span class="ck-badge" id="ck257">0/8</span></p>
<ul class="checklist" id="ckl257">
  <li><label><input type="checkbox"><span>核对项文字</span></label></li>
</ul>
```

## 9. 手风琴(字段定义/分层揭示)

```html
<div class="acc">
  <details><summary>字段名 · 中文名</summary><div class="acc-body">定义说明。</div></details>
</div>
```

## 10. 文件树(产物结构/目录说明,逐文件点开)

```html
<div class="tree">
  <details><summary>├ INDEX.md</summary><div class="tree-desc">用途说明。</div></details>
  <details><summary>└ metadata.json</summary><div class="tree-desc">用途说明。</div></details>
</div>
```

## 11. 规则列表(错误处理/边界,可挂 fallback 守护链接)

```html
<ul class="rules">
  <li data-source="SKILL.md:387"><strong>场景</strong> → 处理动作
    <span class="fb"><button class="jump" onclick="showStep('n04','e141')">⤓ 守护 Step 1.1 提取全文</button></span>
    <button class="deep-dive-btn" title="追问" onclick="openDeepDive('场景','SKILL.md:387')">?</button>
  </li>
</ul>
```

## 12. 命令块(自动获得复制按钮,无需额外标记)

```html
<pre class="code">python3 scripts/extract.py &lt;skill目录&gt; --output-dir ./output</pre>
```

注意:内容里的 `<` `>` 必须转义为 `&lt;` `&gt;`。

---

## 内容性质 → 组件决策表

| 内容性质 | 首选组件 | 备选 |
|---|---|---|
| 节点含相对 L2 子步骤(执行序列) | 4 子流程图 | 9 手风琴 |
| 步骤间有循环/重试/回退 | 4 的环边 + 环说明卡 | — |
| 并列原则/要点(2-4 条) | 5 卡片组 | 9 手风琴 |
| 入口/条件分支(去向不同节点) | 6 分叉卡 | 11 规则列表 |
| 多维决策/选型 | 7 可点行表格 | 5 卡片组 |
| 自检/验收清单 | 8 可勾选清单 | 11 规则列表 |
| 字段/术语定义集 | 9 手风琴 | 7 表格 |
| 目录/产物结构 | 10 文件树 | 12 命令块 |
| 错误处理/边界声明 | 11 规则列表(带守护链接) | 7 表格 |
| 命令/代码 | 12 命令块 | — |

---

## 语义层标记(引擎内置;有 `semantics.json` 时使用,没有则完全不出现)

`base.html` 已内置这套视觉词汇(样式 + 绘制逻辑),**不是另一种页面**:同一模板,语义字段有多少就多画多少,`/1` 页面一个选择器都不会命中。渲染 `/2` 页时只需按下表输出标记,并经 `{{component_scripts}}` 注入两行数据:

```js
SEM_EDGES = {"st-n03": {"arcs": [{"from": "e32", "to": "e35", "label": "榜上命中", "inf": true}], "end": {"from": "e36", "label": "安装完成", "inf": true}}};
RAIL_LINKS = [{"from": "n02", "to": "n03"}];
semDrawRail();
```

真实示例:`examples/find-skills-semantic-workflow.html`。`verify-page.js` 的边计数不受影响(顺序边仍是 `<line>`,环仍是 `path.ed-l`,其余新边是别的 class 的 `<path>`)。

| 语义字段 | 标记 | 视觉 |
|---|---|---|
| `layers` | 主线:`<div class="rail-sem" id="railSem"><svg class="rail-svg" id="railSvg"></svg><div class="rail-main">…R / W 节点的 .group…</div><div class="rail-sat" data-label="支撑层 S / A · 点线 = 依赖边">…S / A 芯片…</div></div>`;芯片 `.nid` 写 `n02 · A`,支撑芯片副标题末尾写 `→ Step N`;`RAIL_LINKS` 每个「支撑节点 → 它依赖到的主线节点」一项(多目标多项) | 主线行 + 支撑行:支撑芯片由 JS 定位到其关联主线节点正下方(重叠成簇共同居中,左侧留标签栏),依赖线正交布线、每线一轨、端口分散、轨道次序取交叉最少;同行芯片等宽 |
| 节点总览主行相邻节点间的 `fallback` 边 | `<span class="arrow big cap" data-cap="找不到时 ⤓">⇒</span>` | 箭头下的橙色小字 |
| `subflows[].type` | `.sf-node` 编号行内:`<span class="sn">3<span class="sf-type t-tool">TOOL_CALL</span></span>`(族:`t-tool` / `t-gate` / `t-out` / `t-fb`,其余不加族);标题写在 `<span class="st">` | 编号行右侧的等宽类型徽章(不单独占一行);卡片标题用同族 `.tbadge`。同一行的 `.sf-node` 由 JS 统一为等宽(自然宽取最大,112–200px),高度随行拉伸、内容垂直居中 |
| 上一步 → 本步的 `condition_*` 边 | 目标盒子第一行 `<span class="sf-when">⇢ 排行榜未覆盖</span>` | 入口条件写在盒子里,不悬在箭头上 |
| `checkpoints` / `approval` 边 | 盒子内 `<span class="sf-gate">◆ 验证闸口</span>` 或 `⏸ 用户同意安装`(审批边的条件文案);卡片标题 `.gate-badge` | 橙色闸口行 |
| `subflows[].implicit` | `.sf-node.implicit` + `<span class="sf-imp">隐含</span>` | 虚线框 |
| 同节点非相邻步骤的 `condition_*` 边 | `SEM_EDGES[sid].arcs` 项 `{from,to,label,inf}` | 上方蓝色弧(推断为虚线);与环一起**按跨度分层避让**,顶部留白自动撑开 |
| `retry` / `loop` 边 | 仍走 `SUBFLOW_LOOPS`(`{{subflow_loops_json}}`) | 橙色流动虚线弧 / 自环,参与同一分层 |
| 跨节点 `dependency` 入边 / `fallback` 出边 | `.sf-canvas` 内 `<div class="sf-lane">` + 每个外部节点一个 `<button class="sf-ext in" data-at="e33,e36" data-inf="0,0" onclick="showNode('n02')"><span class="xid">n02 · A</span><span class="xt">Skills CLI</span><small>find 命令 → Step 3 · add 命令 → Step 6</small></button>`(出边用 `class="sf-ext out" data-from="e33,e34"`,`small` 写 `← Step 3 条件 · ← Step 4 条件 (推断)`);图例放画布外:`.subflow` 之后 `<div class="sf-legend">外部节点 · ◂ 点线 = 依赖来源 · ⤓ 橙线 = 兜底去向</div>` | 盒子下方一条外部节点栏:外部框由 JS 放到关联步骤正下方(重叠成簇共同居中)、同栏等宽等高;连线**正交布线**——每条线独占一条水平轨道,端口沿盒边按对侧位置分散,轨道次序穷举取交叉最少(≤8 条),栏与主行的间距随线数撑开;依赖 = 点线上箭头汇入步骤,兜底 = 橙线下箭头汇入外部框;**同一外部节点只画一个框**,多条线汇入 |
| `termination` | `.sf-row` 末尾 `<span class="sf-end">⦿<small>END</small></span>` + `SEM_EDGES[sid].end` | 最后一步 → ⦿,标签在图标下 |
| 步骤 8 维语义 / 6 类附件 | 卡片内 `<p class="sem-h">判据</p>` + 组件:procedure→`ol.sem-list`、criteria / quality_standards→`ul.checklist`(配 `.ck-badge`)、heuristics→`ul.sem-list.tips`、failure_modes→`ul.sem-list.fail`、examples(含 ` → `)→`table.rowsel`、tools→`pre.code`、governance→`.gov`、presentation→`.acc` 内原文 | 每条 `li.claim` 带 `data-source`;`<q class="qt">quote</q>` 默认隐藏,开「显示出处」时显示逐字引文;`basis=inferred` 加 `.inf` |
| 每步流向 | 卡片末尾 `<p class="flow">`(`.fk` 字形 + `.jump` 按钮) | 统一的"→ 去哪 / ◂ 来源"行 |
| `reconciliation` | 伪节点 `recon`(NODES 末尾、TOC 一项、`<section class="panel" id="p-recon">`) | `.recon-sum` 摘要胶囊 + `.recon-tbl` 目录 vs 分层表 + 偏差清单 |
| `routing.triggers` / `exclusions` | 目录里已有 R 层节点 → 进该节点面板的"触发条件(R 层)";没有 R 层节点(触发信息只在 frontmatter)→ 渲染器合成 `rt` 节点:流程带首位 `R · 触发` 芯片 + 目录项 + 面板(description 原文卡 + 触发条件清单),不进 skeleton | 何时触发 |
| `wsa_profile` | Hero `thesis` 内 `<span class="wsa">W 3 · S 2 · A 2 → …</span>` | 总纲下的徽章 |

### 合成 `rt` 节点的触发判定(`render.py` 的 `R_TITLE_RE`)

只有目录里**没有** R 层节点时才合成 `rt`。判定顺序:`layers` 里有 `layer == "R"` 的节点 → 不合成;否则用 `R_TITLE_RE` 匹配节点标题(**不区分大小写**),命中即视为已有「何时使用」节点:

`when to use` · `when to apply` · `when to request` · `when to trigger` · `when to run|invoke|use this` · `when not to use` · `use when` · `trigger` · `activation` · `applicability` · `何时触发|使用|用` · `使用时机` · `触发条件|时机`

改这个列表时同步改这里,并加一条 `tests/test_render_units.py` 的用例。

---

## 组合总览页组件(`templates/bundle.html`;由 `render_bundle.py` 填,Agent 不手写)

总览页与单页共用主题 CSS 变量、顶栏、`data-source` 出处开关、追问弹窗,组件只有五个。坐标由渲染器算好写进 `style`,连线由页面 JS 按 DOM 实际位置画(`drawFig`),所以**不要**手改坐标。

| 组件 | 标记 | 视觉 / 行为 |
|---|---|---|
| **chip**(图 1:一个 skill) | `<a class="chip" data-key="<skill>" href="<skill>/<skill>-workflow.html" style="left:…;top:…;width:…"><span class="nid">skill 名</span><span class="nt">短标题</span><span class="sub">副标题</span></a>`;无跨 skill 边的成员加 `.iso` | 绝对定位的芯片,点进该成员单页;`.iso` 虚线边框,排在右侧单列 |
| **cluster**(图 2:一个 skill 展开) | `<div class="cluster" data-skill="<skill>" data-layer="<层号 或 iso>" style="left:…;top:…;width:…"><span class="cl">skill 名</span><div class="nrow">…nbox…</div></div>` | 虚线分组框,与图 1 同一套分层坐标;`data-layer` 是它所在的行(展开时 JS 按行重排要用)。**孤立 skill(没有任何跨 skill 边)在图 2 里单独排成最后一行**(`data-layer="iso"`),不像图 1 那样挂在右侧单列 |
| **nbox**(图 2:一个节点) | `<a class="nbox" data-key="<skill>:nXX" href="<skill>/<skill>-workflow.html#nXX" title="全称"><span class="nn">nXX</span><span class="nt">短标题</span></a>`;折叠时非主线且不参与跨 skill 边的加 `.hidden`,并在行尾放 `<span class="more">+N 支撑</span>` | 点进成员页并按 hash 定位到该节点;`#c2.expanded` 时 `.hidden` 恢复显示、`.more` 隐藏 |
| **fe**(两张图的连线) | 由 `drawFig` 生成 `<path class="fe <type>[ back][ mutual]" data-i="<在 LAYOUT 边表里的下标>" data-source=…><title>from → to · type · source\nquote</title></path>`,画进 `#s1` / `#s2` | 实线 = `delegate`,点线 = `dependency`(`.fe.dependency`),回弧 / 互调 = 强调色;hover 加粗并出 tooltip |
| **展开开关** | `<label class="toggle"><input type="checkbox" id="expandAll"> 全部展开</label>`,`onchange` 加减 `#c2.expanded` 后重画 | 折叠态只看主线,展开态看全部节点;**连线条数两态一致**(`verify-page.js` 会核) |

数据槽位:`{{layout_json}}` 注入 `{fig1:{edges:[…]}, fig2:{edges:[…]}}`,边的 `from` / `to` 是 chip 的 `data-key`(图 1,skill 名)或 nbox 的 `data-key`(图 2,`<skill>:nXX`)。`verify-page.js` 对 `body[data-page="bundle"]` 自动切到 13 项检查:两张图与 skill 数一致、`#s1 path.fe` 数 = `LAYOUT.fig1.edges.length`、`#s2 path.fe` 数 = `LAYOUT.fig2.edges.length`、全部展开后 `.nbox` 全可见且连线数不变、每条图 2 连线的起点落在来源 skill 的分组框内(靠 path 上的 `data-i` 回指 `LAYOUT.fig2.edges`,不能按下标对位——端点不可见的边会被 `drawFig` 跳过)、每个 chip 的 `href` 文件存在,外加与单页共用的占位符残留(总览页整份扫 `{{…}}`,不靠固定清单)/ data-source 出处 / 4 主题 / 出处开关 / 追问弹窗 / 375px / 无 JS 错误。
