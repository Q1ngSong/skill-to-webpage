---
name: skill-to-webpage
description: 把一个 Claude Code Skill(SKILL.md + scripts/templates 等资源)拆解成本地知识库,再渲染成可交互的单文件 workflow HTML 页——节点总览(按语义分组)、子流程图(环与跳转画成真实的边)、逐步骤点开、出处行号标注、追问打包(提问+位置+依赖文件复制给 Agent)。支持用任意解析器 skill(可多个)叠加语义层并相互印证;也支持一整组 skill——出组合总览页(skill 调用图 + 节点调用图)加每个成员一页。当用户想可视化一个 skill 的执行策略/workflow、想看一组 skill 之间怎么互相调用、想用某个解析器分析一个 skill、或想逐步探索某个 skill 怎么工作时使用。
---

# skill-to-webpage

把 Skill 变成可交互的 workflow 页。**静态拆解永远先跑**(零 LLM,产出目录坐标系);**语义层由任意解析器 skill 叠加**(可多个并跑,互不影响,不需要在本 skill 里注册);合并 → 校验 → 渲染成单文件 HTML。

## 哲学

- **呈现的是 workflow,不是文档**:主轴是"节点做什么、怎么推进、哪里分叉、哪里成环"。节点总览只放节点语义,渲染元数据(步数/环数)不上主视图。
- **静态骨架是坐标系**:阶段 1 纯结构解析会扫描围栏外 H1–H6,跳过明确的单一文档包装标题(H1 的浅包装,或标题与 frontmatter `name` 一致),再把前三个有效层级映射为相对 L1 节点 / L2 步骤 / L3 卡片小节(行号、资源一并保留),零 token。任何语义层都只能**叠加**在它上面,不能替换、不能重切;目录与实际流程的差异写进印证区而不是改目录。
- **解析器可插拔**:解析器就是普通 skill,用路径或名字指定;握手约定见 `references/parser-protocol.md`,数据格式见 `references/semantics-contract.md`。一个失败不影响其他。
- **冲突回原文**:多份语义产物不一致时,以 SKILL.md 原文裁决(每条断言都带 `source` + `quote`,回读即可)。
- **原文与转述分层**:带 `data-source` 的内容块是逐字原文;分组名、节点副标题、总纲、引语是转述,不冒充引文;页脚披露。
- **单文件零依赖**:产出 HTML 内联全部 CSS/JS/主题,无 CDN、无外部字体、不引 Mermaid。

## 一句话入口与编排

触发句式(任一):`使用 <解析器路径或名字>[ <更多解析器>] 分析并可视化 <skill 路径>` · `可视化这个 skill:<路径>` · `可视化这组 skill:<组目录>`(组目录 = 下辖多个 `<成员名>/SKILL.md` 的目录,出组合总览页 + 每个成员一页)· `把 X 渲染成 workflow 页`。Agent 全程接管,**顺序执行以下 Step,已在请求里给出的信息不重复问**。

### Step 0 · 解析请求

1. **skill 路径**(必填):含 `SKILL.md` 的目录;没给就问。
2. **解析器列表**(可空):按用户给的顺序记录。给的是路径 → 直接用;给的是名字 → 在 `.agents/skills/`、`.claude/skills/`、`~/.claude/skills/` 找同名目录,找不到再 grep 这些目录下 `description` 含 `s2w-semantics/` 的 skill 供用户选。没给 → 不跑外部解析器(Agent 可按「阶段 2」自己当解析器,见 Step 3)。
3. **初始主题**:`docs`(默认)/ `blueprint` / `ide` / `whiteboard`。
4. **输出目录**:默认 `./output/<skill名>/`。
5. **出哪几版 HTML**(AskUserQuestion,`multiSelect: true`):选项按序列出 `merged`(合并结果,**默认选中**)、`static`(静态基线,不吃语义)、以及用户提到的每个解析器各一版(按用户给的顺序,如 `my-parser`)。用户在触发句里说了("出 merged 和 static 两版")就不问。多选结果记为版本列表,第一个为主页面。

### Step 1 · 环境自检

`python3` ≥ 3.10 必需(缺失则告知自行安装);`node` + `playwright` + chromium 仅自动验证需要,缺失时**先征得同意**再装(`npm i --no-save playwright && npx playwright install chromium`,约 130MB),拒绝则改人工核对清单。

### Step 2 · 静态抽取 → `static/`

```bash
python3 scripts/extract.py <skill目录> --output-dir output/<skill名> --name static
```

报告节点数。`static/` 已存在且源 SKILL.md 未变(sha256 同)→ 可复用。

**组目录(bundle)时**:`python3 scripts/extract_bundle.py <组目录> --output-dir output/<组名>` 代替 `extract.py`;之后对每个成员按拓扑顺序(被引用者先)走 Step 3–6,`validate_semantics.py` / `merge_semantics.py` 都加 `--bundle output/<组名>/bundle.json`,语义用 `s2w-semantics/3`(跨 skill 边写 `<skill>:nXX[.k]` 端点,`delegate` 类型);全部成员合并完成后**再对每个成员重跑一遍 `render.py`**——成员页的跨 skill 入边是渲染时从兄弟的 `merged/` 现取的快照,先渲染的成员看不到后合并的调用方,不补这一遍就会缺入边:

```bash
for m in $(python3 -c "import json;print(*[m['name'] for m in json.load(open('output/<组名>/bundle.json'))['members']])"); do
  python3 scripts/render.py "output/<组名>/$m" --skill-dir "<组目录>/$m" --variants merged static
done
python3 scripts/render_bundle.py output/<组名>        # 再出总览页
node scripts/verify-page.js output/<组名>/<组名>-workflow.html   # 13 项
```

总览页的转述层放 `output/<组名>/overrides.json`,render_bundle.py 不给 `--overrides` 时自动读它(显式给了却不存在会报错)。

### Step 3 · 解析器抽取(逐个)→ `<解析器名>/`

对列表里每个解析器,按 `references/parser-protocol.md`:

1. **加载**:Skill 工具能按名字找到就用;否则**直接读取其 SKILL.md 并按其步骤执行**(装在 `.agents/skills/` 等未注册目录时必然如此,两者等价)。
2. **交给它三样东西**:源 skill 目录绝对路径、`static/` 绝对路径、它自己的输出目录 `output/<skill名>/<解析器名>/`(先创建);附契约路径 `references/semantics-contract.md`。
3. **组目录(bundle)时交第四样东西**:`output/<组名>/bundle.json` 的绝对路径 ——**每个解析器 agent 的 prompt 里都要显式给这个路径**,拿到它才能写 `s2w-semantics/3` 的跨 skill 边(`<skill>:nXX[.k]` 端点、`delegate` 类型),并按 `bundle/static/cross-refs.json` 的事实表逐条回原文核实。**漏了这一条,47 条引用事实会全部原地"未采纳",组合总览页里所有成员都显示孤立** —— 这不是零星丢失,是必然结果,派发解析器 agent 前先确认 prompt 里有没有这个路径。
4. **验收**:`python3 scripts/validate_semantics.py output/<skill名>/<解析器名> --static output/<skill名>/static --skill-dir <skill目录> [--bundle output/<组名>/bundle.json]`(组目录时必须加 `--bundle`,否则带前缀的端点会被作废)。整体回落 → 该解析器作废并记录原因;单条作废只减条目。
5. 下一个解析器,互不影响。

**没有外部解析器但要语义层时**:Agent 自己按下方「阶段 2 · 临场语义判断」产出 `output/<skill名>/agent/semantics.json`(`/1` 子集即可),同样走验收;`agent` 就是一个普通解析器名。

### Step 4 · 合并与排错 → `merged/`

```bash
python3 scripts/merge_semantics.py output/<skill名> --parsers <名1> [<名2> …] --skill-dir <skill目录> [--bundle output/<组名>/bundle.json]
```

组目录时**必须加 `--bundle`**——漏了这个参数,每个成员各自 merge 出来的 `merged/semantics.json` 都不会有跨 skill 边,即使 Step 3 已经拿到了带前缀的端点。

读 `merged/merge-report.md`:**每处冲突回读 `static/full_text.md` 原文裁决**,把结论改进 `merged/semantics.json`(或加 `--prefer <名>` 重跑),记下依据行号。0 个可用解析器 → 跳过本步,后续渲染静态基线。

### Step 5 · 渲染

```bash
python3 scripts/render.py output/<skill名> --variants <Step 0 选的版本…> [--theme docs] [--overrides output/<skill名>/overrides.json] --skill-dir <skill目录>
```

**组目录时**:上面这条命令要对**每个成员**跑一遍,而且**全部成员的 Step 4(merge)都跑完之后,要对每个成员重跑第二遍**(见 Step 2 bundle 分支的 for 循环)——先渲染的成员看不到后合并出来的兄弟入边,不补第二遍就会缺边,即使 Step 3/4 的跨 skill 边全部正确写出。

每个版本写进**自己的文件夹**:`output/<skill名>/<版本>/<skill名>-workflow.html`(+ `.md`);根目录 `output/<skill名>/<skill名>-workflow.html` 放 **merged 版**(未选 merged 时放列表第一个);多版时页面顶栏有版本切换链接。`merged` 吃 `static/` + `merged/`,`static` 只吃 `static/`(静态基线页),`<解析器名>` 吃该解析器自己的 `semantics.json`(合并前的单家视角,便于对照)。语义文件缺失或校验整体回落的版本会被跳过并告知。`render.py` 自动:分层节点总览、子流程图(类型徽章 / 闸口 / 条件弧 / 环 / 外部节点栏 / 终止)、由 8 维语义生成的步骤卡、印证报告面板、叙事版 `.md`。静态版直接展开原文;语义版保持卡片简洁,不重复提供完整原文折叠,通过「显示出处」查看断言的逐字引文。**Agent 的转述层**写进 `overrides.json` 再渲染,**不要手改生成的 HTML**:

```json
{ "chip_titles": { "n03": "帮用户找 skill" }, "leads": { "n03": "段首引语(可含 HTML)" },
  "description_html": "description 的中文转述", "thesis_html": "总纲下的一段说明", "eyebrow_extra": "" }
```

转述层规则:节点短标题 ≤ 12 字写"节点做什么";引语一句话点出该节点在流程里的位置;强调色克制;`overrides` 里的 HTML 片段遵守下方 JS 安全规则(不含脚本)。

### Step 6 · 验证

```bash
node scripts/verify-page.js output/<skill名>/<skill名>-workflow.html          # 根目录(merged)
node scripts/verify-page.js output/<skill名>/<版本>/<skill名>-workflow.html   # 每个选中的版本
```

单页 13 项自动检查(占位符残留、节点切换、子流程图边数、支撑/外部连线、步骤展开、4 主题、出处、追问弹窗、**子流程边可点选并高亮两端**、375px 不溢出、无 JS 错误);总览页(`<body data-page="bundle">`)自动切到 13 项(两张图与 skill 数一致、图 1 弧数、图 2 折叠态连线数、全部展开、**图 2 连线起点落在来源分组框内**、成员链接存在 + 占位符残留 / data-source 出处 / 主题 / 出处开关 / 追问弹窗 / 375px / JS 错误)。失败项修复后重跑直到全过。人工再核对:节点总览分组语义正确;环与跳转有原文依据;追问打包含位置 + 行号 + 依赖文件;无 `{{…}}` 残留。

### Step 7 · 交付

发所有选中的版本(根目录 `<skill名>-workflow.html` + 各 `<版本>/<skill名>-workflow.html`,附 `.md`),说明:用了哪些解析器、各作废几条、冲突几处及裁决依据行号、印证摘要(非流程标题 / 隐含步骤 / 顺序偏差 / 跨锚定);页面用法一句话(主题切换、显示出处看逐字引文、追问打包)。

**重入**:`static/` 在且源未变 → 跳过 Step 2;某解析器产物在且 sha256 一致 → 可复用;只换主题、改转述或补出另一版 → 直接 Step 5。

## 目录约定

```
output/<skill名>/
├── static/             阶段 1 零 LLM —— 坐标系(INDEX.md · nodes/ · full_text.md · metadata.json)+ 选中时的静态基线页
├── <解析器名>/          每个解析器一个文件夹:semantics.json(必需)+ 它的报告 + 选中时该解析器单家视角的页
├── agent/              Agent 自己临场判断时的解析器文件夹(可选)
├── merged/             merge_semantics.py:semantics.json(每条带 by 来源)+ merge-report.md + merged 版页
├── overrides.json      渲染 Agent 的转述层(可选)
├── <skill名>-workflow.html            根目录 = merged 版(未选 merged 时为列表第一个)
└── <skill名>-workflow.md              对应的叙事版
```

组目录(bundle)时,上面这棵树整体下沉一层,组根多出清单与事实表:

```
output/<组名>/
├── bundle.json                     组清单(s2w-bundle/1):成员、skill_dir、static、page、sha256、节点数
├── bundle/static/cross-refs.json   跨引用事实表(零 LLM;kind = token / path / name / word)
├── <成员名>/                        每个成员就是上面那棵完整的树
├── overrides.json                  总览页的转述层(可选:chip_titles / description_html / thesis_html)
├── <组名>-workflow.html            组合总览页(图 1 skill 调用图 + 图 2 节点调用图 + 清单 + 印证)
└── <组名>-workflow.md              对应的叙事版
```

## 文件结构

| 文件 | 作用 |
|------|------|
| `scripts/extract.py` + `scripts/extractor/` | 阶段 1 静态拆解(零 LLM;自适应相对标题层级) |
| `scripts/extract_bundle.py` | 组级阶段 1(零 LLM):逐成员出 `static/`,扫跨引用事实表 `cross-refs.json`,写 `bundle.json` |
| `scripts/validate_semantics.py` | 解析器产物校验:schema / sha256 / 行数 / 每条 `quote` 逐行回读 / 端点与序号 / 派生视图与边一致;可作模块 |
| `scripts/merge_semantics.py` | 多解析器合并:静态赢结构,一致采纳、独有标来源、冲突记表并暂选 |
| `scripts/render.py` | 渲染器:static(+ merged)→ HTML + 叙事 md;`overrides.json` 承载转述层 |
| `scripts/render_bundle.py` | 组合总览页渲染器:`bundle.json` + 各成员 `merged/` → 两张图 + 清单 + 印证 |
| `scripts/bundle_layout.py` | 总览页布局纯函数:分层、破环、重心排序、skill 卡片坐标(有单测) |
| `scripts/s2w_common.py` | 共用:读 static/、语义归一化(/1 派生视图折算成边)、端点 `parse_ep` / `fmt_ep` |
| `scripts/verify-page.js` | Playwright 自动验证(单页 13 项 / 总览页 13 项,按 `body[data-page]` 自动切) |
| `templates/base.html` | 骨架 + 全部样式 + 交互引擎(含语义层视觉词汇,无数据时静默) |
| `templates/bundle.html` | 组合总览页骨架:两张图容器 + 展开开关 + 清单区 + 印证区(同一套主题 / 出处 / 追问) |
| `templates/flow-lib.js` | 布线库(正交布线 / 轨道避让),由 base.html 与 bundle.html 渲染时内联 |
| `templates/components.md` | 组件范式 + 语义层标记契约 + 总览页组件 |
| `templates/themes/` | 4 套主题 CSS |
| `references/parser-protocol.md` | 解析器握手:目录约定、三个(组内四个)输入、验收、合并规则 |
| `references/semantics-contract.md` | 语义数据格式 `s2w-semantics/2`,组合扩展见其中的 `s2w-semantics/3` 一节 |

## 阶段 1:静态拆解(零 LLM)

frontmatter 提 R 层(description 原样,引号已剥离);扫描围栏外 H1–H6 并统计实际层级;单例标题仅在“标题与 frontmatter `name` 一致”,或“H1 下有多个下一层标题且首个子标题前不超过 2 行直接正文”时视作文档包装并跳过,避免把 `## Start` 这类单节点 workflow 误删;把前三个有效层级压缩映射为相对 L1 节点 / L2 步骤 / L3 展示小节(原文跳级也连续映射);<3 行短节点以映射后的 L2 标题并入邻居;扫描五类资源目录引用并查存在性;每节点记 `SKILL.md:起-止` 行号,映射写入 `static/metadata.json` 与 `INDEX.md`;CRLF/BOM 归一化。目录无 SKILL.md → 报错不硬跑。

## 阶段 2:临场语义判断(Agent 作为解析器 `agent/` 时)

读 `static/INDEX.md` 与 `nodes/*.md`,产出 `agent/semantics.json`(`schema: s2w-semantics/1` 子集即可,字段见契约):

1. **语义分组** `groups`:2–4 组(理念/准备、**执行主线**、支撑/边界为常见形),主线 `main: true`。
2. **节点副标题** `node_summaries`:≤ 12 字写"节点做什么",不写元数据。
3. **环与分叉**(读文本找:重试 / 循环 / 逐章 / 直到 / 回到 Step X / 失败则 / 先…再…):步骤间回退或自身重试 → `loops`;条件跳转 → `jumps`;兜底 → `guards`。**每条带 `source` + `quote`,找不到依据就不写**。
4. **总纲** `thesis`:一句执行总纲,出处指向对应行。

能做到 `/2`(分层、步骤分型、全部边、检查点、终止、每步语义)更好,规则同契约。

## JS 安全规则(CRITICAL)

`base.html` 与 `render.py` 已遵守:`function()` 不用箭头函数;JS 字符串内禁用中文弯引号;DOM 操作前 null 守卫;`var` 不用 `const/let`。`overrides.json` 里的 HTML 片段不得含 `<script>`。

## 错误处理

| 场景 | 处理 |
|------|------|
| 目录无 SKILL.md | 报错:"skill-to-webpage 需要一个包含 SKILL.md 的 Claude Code Skill 目录路径。" |
| SKILL.md 无任何围栏外标题 | 单一 Overview 节点,页面退化为单节点详情 |
| 相对 L1 节点下无 L2 子标题 | 不画子流程图,直接展示原文(语义层有隐含步骤则画虚线框) |
| 解析器找不到 / 读不到 SKILL.md | 该解析器作废并告知,其余照跑 |
| 解析器产物 JSON 非法 / schema 不符 / sha256 过期 / 行数不符 / `layers` 未覆盖 / `unanchored` 非空 | 该解析器整体作废,告知原因 |
| 个别 claim 越界、缺 `source`、`quote` 回读对不上、派生视图无对应边 | 仅作废该条,交付时列出 |
| 解析器之间冲突 | `merge-report.md` 列出,按规则暂选;Agent 回原文裁决后改 `merged/semantics.json` |
| 0 个可用解析器 | 渲染静态基线页,并说明 |
| 引用的资源文件缺失 | 面板里标"缺失",不中断 |

## 不在本次范围

- 环/分支的**脚本级**自动提取(静态拆解仍零 LLM;语义层来自解析器 skill 或 Agent 临场判断)。
- 页面内直接得到回答(追问是打包复制给 Agent)。
- 跨**组**的站点导航(组合总览页 + 成员页已支持,但没有跨组索引页)。
