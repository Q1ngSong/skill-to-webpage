# 语义拆解契约(s2w-semantics/2 · 组合扩展 /3)

skill-to-webpage 与**外接拆解 skill** 之间的数据契约。任何 skill 只要按本文产出合法数据就能接入——本项目不关心它内部用什么方法。当前版本 `/2`;渲染端同时接受 `/1`(其字段是 `/2` 的子集)与 `/3`(`/2` + 跨 skill 扩展,见文末「s2w-semantics/3」)。

## 原则:静态骨架是坐标系

1. **结构拆解永远先跑**(零 LLM:扫描围栏外 H1–H6;仅跳过标题与 frontmatter `name` 一致的单例包装层,或正文极短且下层有多个标题的单例 H1;将前三个有效层级映射为相对 L1 节点 / L2 步骤 / L3 展示小节,并保留行号、资源)。它的产物是**目录**。拆解 skill 不得跳过它、不得替换它、不得重切节点。
2. **语义层只能叠加与印证**。语义产物写成 `<解析器名>/semantics.json`,每条断言都锚定到目录里的某个节点或步骤。语义抽取发现目录没有的东西——无标题的隐含步骤、跨章节的依赖、文档顺序 ≠ 执行顺序、标题其实不是流程节点——**不改目录,写进 `reconciliation`(印证区)作为偏差报告**。
3. **抽全不省**。能在文本里指认的都抽:分层归属、步骤分型、全部非顺序边(含跨节点)、检查点、终止、每步 8 维语义、6 类附件、W/S/A 强度。显式与推断都收,用 `basis` 区分。
4. **每条可机核**。断言带 `source`(行号)与 `quote`(该行号范围内的逐字片段);`scripts/validate_semantics.py` 逐条回读核对,对不上的条目作废。
5. 渲染方按自己的词汇消费,用不到的字段忽略(前向兼容)。

(`/1` 的 "L2 整体替换" 已废除——与原则 1 冲突。)

## 通用断言(claim)格式

凡是"说了某件事"的条目都是一个 claim:

```json
{ "text": "装机量优先 1K+,<100 当心", "source": "SKILL.md:69", "quote": "Prefer skills with 1K+ installs", "basis": "explicit" }
```

| 键 | 必填 | 说明 |
|---|:---:|---|
| `text` | ✓ | 中文转述(或原文) |
| `source` | ✓ | `SKILL.md:X` 或 `SKILL.md:X-Y` |
| `quote` | ✓ | 引用行范围内的**逐字**子串(≤ 80 字符;比对时空白归一、弯引号视同直引号) |
| `basis` | — | `explicit`(直接陈述,默认)/ `inferred`(上下文强烈暗示,如条件句的逆命题) |

位置引用(endpoint):`"n03"`(节点)、`"n03.2"`(节点第 2 步,1 起)、`"END"`(终止)。

## semantics.json 顶层字段

```json
{
  "schema": "s2w-semantics/2",
  "generator": "my-parser/1.0",
  "generated_at": "2026-08-21",
  "source": { "file": "SKILL.md", "sha256": "…", "lines": 141 },
  "skeleton": { "from": "static/INDEX.md", "nodes": [ { "id": "n03", "title": "How to Help Users Find Skills", "lines": "33-104", "steps": 6 } ] },

  "thesis": claim,
  "groups": [ { "label": "执行主线", "nodes": ["n03"], "main": true } ],
  "node_summaries": { "n03": "需求 → 推荐 → 安装" },
  "layers": { "n03": { "layer": "W", "role": "main_flow", "source": "SKILL.md:33-104", "quote": "How to Help Users Find Skills" } },
  "routing": { "triggers": [ claim ], "exclusions": [ claim ] },

  "subflows": { "n03": [ step, … ], "n06": [ { "implicit": true, … } ] },
  "edges": [ { "from": "n03.2", "to": "n03.5", "type": "condition_true", "condition": "榜上命中", "source": "SKILL.md:53", "quote": "If the leaderboard doesn't cover", "basis": "inferred" } ],
  "checkpoints": [ { "at": "n03.4", "kind": "validate", "source": "SKILL.md:67", "quote": "Always verify" } ],
  "termination": [ { "at": "n03.6", "text": "安装完成即结束", "source": "SKILL.md:99-103", "quote": "skips confirmation prompts", "basis": "inferred" } ],
  "global": { "semantics": { "heuristics": [ claim ] }, "attachments": { "tools": [ claim ] } },
  "wsa_profile": { "W": 3, "S": 2, "A": 2, "label": "Full Runtime Workflow Skill", "notes": [ "…" ] },

  "loops": [ … ], "jumps": [ … ], "guards": [ … ],
  "reconciliation": { … },
  "ambiguities": [ "…" ]
}
```

| 字段 | 必填 | 内容 | 渲染端用途 |
|---|:---:|---|---|
| `schema` `generator` `generated_at` `source` | ✓ | 同 `/1`;`source.lines` 必须等于 `wc -l` | 校验 / 过期检测 / 页脚 |
| `skeleton` | ✓ | **目录快照**:从 `static/` 抄来的节点 id / 标题 / 行号 / 相对 L2 步骤数 | 印证基准 |
| `thesis` `groups` `node_summaries` | — | 同 `/1` | Hero 总纲 / 节点总览分组 / 节点副标题 |
| `layers` | ✓ | 每个静态节点归入 `R`(路由/激活)`W`(流程)`S`(语义/知识)`A`(附件/工具/资源),附 `role` 短标签与出处;**必须覆盖全部节点** | 节点总览分组依据;非 W 节点可弱化显示 |
| `routing` | — | R 层:触发条件 / 排除条件 claim 数组 | Hero 区 |
| `subflows` | — | 每节点步骤数组:静态相对 L2 步骤原样 + `type`(19 型,见拆解器 `references/taxonomy.md`)+ `goal` + `semantics`(8 维 claim 数组)+ `attachments`(6 类 claim 数组)。目录没有、文本里按序做的动作可追加为步骤,必须 `"implicit": true` 并在印证区登记 | 子流程盒子链;步骤类型徽章;步骤卡"怎样算做对 / 常见翻车" |
| `edges` | — | **全部非顺序边**(相邻步骤的顺序边由目录隐含,不列):`type` ∈ `dependency` `condition_true` `condition_false` `loop` `retry` `fallback` `parallel` `approval` `termination`;端点可跨节点;`condition` 为条件文案 | 子流程图回边/自环;节点总览跨节点弧;跳转链接 |
| `checkpoints` | — | `{at, kind: approval \| validate, source, quote}` | 步骤徽章 / 菱形闸口 |
| `termination` | — | 终止条件 claim(`at` 指明在哪结束) | 子流程终点标记 |
| `global` | — | 不属于任何单步的语义/附件(全局规则、未被步骤使用的工具) | 侧栏 / 页脚 |
| `wsa_profile` | — | W/S/A 三层强度 0–3 + 一个类型标签 + 理由(解析器自定义口径,可省略) | 页脚 / Hero 角标 |
| `loops` `jumps` `guards` | — | **派生视图**(供 `/1` 渲染器,带 source/quote):必须与 `edges` 一致——`loops` ↔ `retry`/`loop` 边,`jumps` ↔ `condition_*` 边,`guards` ↔ `fallback` 边;无对应边的派生项校验时作废 | `{{subflow_loops_json}}` / 跳转链接 / `⤓ 守护` |
| `reconciliation` | ✓ | **印证区**,见下 | 交付时给用户看;页脚可摘要 |
| `ambiguities` | — | 自由备注 | 不渲染 |

### reconciliation(印证区)

```json
"reconciliation": {
  "nodes_total": 6, "nodes_classified": 6,
  "steps_total": 6, "steps_typed": 6,
  "non_workflow_nodes": [ { "node": "n04", "layer": "S", "why": "查询词表,不是流程节点" } ],
  "implicit_steps":     [ { "anchor": "n06", "count": 3, "source": "SKILL.md:129-131", "quote": "Acknowledge that no existing skill was found" } ],
  "order_deviations":   [ claim ],
  "cross_anchored":     [ { "item": "n03.3 heuristics", "from_node": "n05", "source": "SKILL.md:121-123" } ],
  "judgment_calls":     [ claim + "anchor" ],
  "unanchored":         [],
  "notes":              [ "全文无显式终止词,终止条件均为推断" ]
}
```

| 键 | 含义 |
|---|---|
| `nodes_total` / `nodes_classified`、`steps_total` / `steps_typed` | 覆盖率,必须相等(目录每一项都被语义层处理过) |
| `non_workflow_nodes` | 目录里的标题不是流程节点(归入 R/S/A)——**"目录 ≠ 流程图"的主要偏差来源** |
| `implicit_steps` | 文本里按顺序做事、但没有映射为相对 L2 标题的步骤 |
| `order_deviations` | 文档顺序 ≠ 执行顺序 |
| `cross_anchored` | 某步骤的语义/附件来自别的节点(知识写在远处) |
| `judgment_calls` | 容易误判之处及裁定(如"判据列表不是子步骤") |
| `unanchored` | 锚不到任何目录节点的断言——**必须为空**,否则整体回落 |

## s2w-semantics/3:跨 skill 扩展(组合总览页)

`/3` = `/2` + 以下三项。校验器与渲染器同时接受 `/1` `/2` `/3`;旧文件不改。只有渲染**一组 skill**(bundle)时才需要 `/3`;单 skill 页面用 `/2` 即可。

### 3a. 端点前缀

`<skill>:<node>[.step]`,如 `writing-plans:n02.3`;无前缀 = 本 skill。允许出现在 `edges.from/to`、`checkpoints.at`、`termination.at`、`reconciliation.cross_anchored.from_node`。

校验:带前缀的端点到 `bundle.json` 中该成员的 `static/` 核对节点 / 步骤存在;`quote` 仍在**本** skill 的 SKILL.md 回读(引用发生在哪就在哪取证)。前缀不在成员列表 → 该条作废。带前缀的端点必须配 `validate_semantics.py --bundle <bundle.json>`,否则作废。

解析端点用 `scripts/s2w_common.py` 的 `parse_ep(ep) → (skill|None, node, step)` 与 `fmt_ep(skill, node, step)`,不要各自写正则。

### 3b. 边类型 `delegate`

语义:本 skill 的某一步把控制权交给另一个 skill(对方跑完回来与否都算)。与 `dependency`(拿对方的产物 / 知识)区分。字段同其他边;`to` **必须**带前缀,否则作废;可选 `mode`(`sub-skill` / `handoff`)与 `condition`。跨 skill 的 `dependency` / `fallback` / `loop` / `condition_*` 同样允许带前缀。

核验:每条 `delegate` 边必须对应至少一条 cross-ref(同 `from_skill`、同 `to_skill`,且**引用行落在边的 `source` 行范围内,或同一节点**),否则作废——这是跨 skill 边的「回原文」。

### 3c. `bundle.json`(`s2w-bundle/1`)

由 `scripts/extract_bundle.py` 零 LLM 产出,是组的清单与坐标系索引:

```json
{ "schema": "s2w-bundle/1", "name": "superpowers", "generated_at": "2026-08-21",
  "members": [ { "name": "brainstorming", "skill_dir": "/abs/.agents/skills/superpowers/brainstorming",
                 "static": "brainstorming/static", "page": "brainstorming/brainstorming-workflow.html",
                 "sha256": "…", "lines": 164, "nodes": 6 } ],
  "cross_refs": "bundle/static/cross-refs.json" }
```

### 3d. `cross-refs.json`(事实表,零 LLM)

每条:`{ "from_skill", "from_node", "source": "SKILL.md:42", "quote": "superpowers:writing-plans", "to_skill", "kind": "token|path|name|word" }`。

识别规则(只认 `members` 里的名字;自引用忽略;围栏代码块内也算;同一行同一目标只记一条,取先匹配的 kind):

| kind | 匹配 | 例 |
|---|---|---|
| `token` | `<任意前缀>:<name>` | `superpowers:writing-plans` |
| `path` | `skills/<name>` | `skills/writing-plans` |
| `name` | 反引号或 `**` 包裹的成员名、`/<name>` | `` `writing-plans` `` · `**writing-plans**` · `/writing-plans` |
| `word` | 裸成员名,词边界;**连字符位可写成空格,且不区分大小写** | `writing-plans` · `Executing Plans` · `Subagent-Driven Development` · `test driven development` |

`word` 噪音最高(一个普通英文词组也可能命中),它只是**候选事实**,由语义层决定要不要落成一条边;`quote` 保留原样书写(`Executing Plans`),`to_skill` 规范化回成员名(`executing-plans`)。`from_node` 由 static 的节点行号区间定位;落在 frontmatter 或节点外的行记 `from_node: null`。

**不变**:`extract.py`、`skeleton`、`layers` 覆盖全部节点、`unanchored` 必须为空。

## 渲染端校验与回落(消费方行为)

`python3 scripts/validate_semantics.py output/<skill>/<解析器名> --static output/<skill>/static --skill-dir <源skill目录>`,按序:

1. 文件不存在 → 临场语义判断(现状)。
2. JSON 非法 / `schema` 不在 {`/1`, `/2`, `/3`} / `sha256` 不符 / `lines` ≠ 实际 / `unanchored` 非空 / `layers` 未覆盖全部节点 → **整体回落** + 告知。
3. 单条 claim:`source` 越界、`quote` 在引用行内找不到、端点不存在、步骤序号越界、派生视图无对应边 → **仅作废该条**,其余照用,交付时列出作废原因。
4. 通过的字段直接采用;渲染 Agent 只做排版与衔接文案;页脚 `generator` 注明拆解器,并摘要印证区。

## 合并后的附加字段(merged/semantics.json)

`scripts/merge_semantics.py` 的产物仍是本契约格式,额外带:每条采纳项的 `by: [解析器…]`;顶层 `merge: {parsers, invalid, prefer, agreements, singletons, conflicts[], dropped_claims}`。渲染端把 `conflicts` 列进印证区,渲染 Agent 回读原文裁决。

## 拆解器的发现与调用(编排方行为)

- **声明**:拆解 skill 的 `description` 含字面标记 `s2w-semantics/<版本>`(当前 `s2w-semantics/2`)。
- **发现**:Step 0 依次 grep `.agents/skills/*/SKILL.md`、`.claude/skills/*/SKILL.md`、`~/.claude/skills/*/SKILL.md` 中的 `s2w-semantics/`,列出命中者与版本。
- **调用**:结构拆解完成后用 Skill 工具调用;Skill 工具报 `Unknown skill`(装在 `.agents/skills/` 时必然如此——该目录不被 Skill 工具加载)则直接读取其 SKILL.md 代为执行,交付时提示可软链进 `.claude/skills/`。
- **安装**:普通 Claude Code Skill,`git clone` / `npx skills add` 到任一 skills 目录。

## 写你自己的解析器

解析器就是一个普通 skill:读 `static/`,按你关心的维度抽取,产出本契约格式的 `semantics.json`。字段可以只填一部分——只做 `edges` + 每步 `attachments.tools`(只关心工具调用),或只做 `checkpoints` + `governance`(只关心安全约束),都合法:用 `/1` 声明即可;要声明 `/2`,`layers` 须覆盖全部节点并给出印证区。唯一硬要求是每条断言带 `source` + `quote`,机器可核。多个解析器并跑后由 `merge_semantics.py` 合并、冲突回原文裁决。示例产物:`examples/find-skills-semantic-workflow.html`(由一个外部解析器 skill 产出)。
