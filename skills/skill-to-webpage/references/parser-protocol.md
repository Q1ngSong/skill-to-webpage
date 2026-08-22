# 解析器协议(parser protocol)

skill-to-webpage 把"非静态的 skill 解析"外包给**任何**解析器 skill。本文是双方的握手约定;数据格式见 `semantics-contract.md`。解析器**不需要**在本项目里注册——用户给路径(或名字)即可。

## 目录约定

```
output/<skill名>/
├── static/            阶段 1 零 LLM 产物 —— 坐标系(INDEX.md · nodes/ · full_text.md · metadata.json)
├── <解析器名>/         每个解析器一个文件夹:semantics.json(必需)+ 它想放的任何东西(报告、中间产物)
├── merged/            merge_semantics.py 产物:semantics.json(每条带 by 来源)+ merge-report.md
├── <skill名>-workflow.html
└── <skill名>-workflow.md
```

`<解析器名>` = 该 skill frontmatter 的 `name`。编排 Agent 自己的临场语义判断也是一个解析器,文件夹名固定 `agent/`(允许 `/1` 子集:groups / node_summaries / loops / jumps / guards)。

渲染一**组** skill 时,上面这棵树整体下沉一层,组根多出清单与事实表:

```
output/<组名>/
├── bundle.json                     组清单(s2w-bundle/1):成员、skill_dir、static、page、sha256
├── bundle/static/cross-refs.json   跨引用事实表(零 LLM,token/path/name/word 四类)
├── <成员名>/                        每个成员就是上面那棵完整的树(static/ · <解析器名>/ · merged/ · 页)
├── <组名>-workflow.html            组合总览页
└── <组名>-workflow.md
```

## 编排方怎么调用一个解析器

1. **加载**:Skill 工具能按名字找到就用 Skill 工具;否则**直接读取其 SKILL.md 并按其步骤执行**(装在 `.agents/skills/` 等未注册目录时必然如此)。两者等价。
2. **交给它三样东西**:源 skill 目录的绝对路径;`static/` 的绝对路径;它自己的输出目录 `output/<skill名>/<解析器名>/`(已创建)。外加契约文件路径 `references/semantics-contract.md`。
3. **可选的第四个输入 `bundle.json`**:渲染的是**一组** skill(bundle)时,再给一个 `output/<组名>/bundle.json` 的绝对路径。拿到它的解析器可以写 `s2w-semantics/3`:跨 skill 边的端点带前缀(`<skill>:nXX[.k]`)、边型 `delegate`,并按 `bundle/static/cross-refs.json` 的事实表回原文取证(规则见契约「s2w-semantics/3」)。没拿到就当单 skill 处理,产出 `/2` 即可——**不给 bundle.json 时写前缀端点会被作废**。
4. **要求**:只在自己的输出目录里写;不改 `static/`;产出 `semantics.json` 符合契约,`skeleton` 抄自 `static/`。
5. **验收**:`python3 scripts/validate_semantics.py output/<skill>/<解析器名> --static output/<skill>/static --skill-dir <skill目录> [--bundle output/<组名>/bundle.json]`。退出码 1(整体回落)→ 该解析器作废;单条作废只减条目。
6. **互不影响**:多个解析器顺序跑,一个失败不影响其他;全部失败 → 没有 merged,渲染退回 static 基线 + Agent 临场(= `agent/` 解析器)。

## 合并与排错(Step 4)

`python3 scripts/merge_semantics.py output/<skill> --parsers <名1> <名2> … [--prefer <名>] --skill-dir <skill目录> [--bundle output/<组名>/bundle.json]`

- **静态永远赢结构**:节点、步骤、行号只来自 `static/`;解析器的步骤按行号对齐到静态步骤,对不上的只能是 `implicit` 步骤。
- **顺序按解析器给的排**:静态步骤之间插入的 `implicit` 步骤留在它的相对位置(否则 `edges` / `checkpoints` / `loops` / `jumps` / `guards` 里的步号会整体错位);各家顺序不一致时记 `subflows.<node>.order` 冲突,暂选 `--prefer`。
- **一致则采纳,独有则保留并标来源**(`by: [...]`)。同端点的多种边型(如 `n02.11 → END` 既 `termination` 又 `fallback`)来自同一解析器时是合法的,不算冲突;`loop` 与 `retry` 视为同型配对。
- **冲突**(同一锚点不同值:节点分层、步骤类型、步骤顺序、同端点边型各家不一致):写进 `merge-report.md` 的冲突表,默认按 `explicit 优于 inferred → --prefer → 列表顺序` 暂选;**渲染 Agent 必须回读 `static/full_text.md` 原文裁决**,把结论改进 `merged/semantics.json`(或加 `--prefer` 重跑),并在交付时说明每处裁决依据的行号。
- 只有一个解析器时 merged = 它 + 来源标记,冲突为空。

## 解析器 skill 的最小义务

- 接受上面三个输入;把产物写到指定目录。
- `semantics.json` 每条断言带 `source` + `quote`(机器可核),显式 / 推断分清。
- 可选:`description` 含 `s2w-semantics/<版本>` 字样,便于用户只说名字时被 Step 0 的扫描找到。

例子:只关心工具调用的解析器可以只产出 `edges`(dependency)+ 每步 `attachments.tools`;只关心安全约束的解析器可以只产出 `checkpoints` + `governance`;做全量语义分层的解析器产出完整 `/2`。它们都能并跑、合并、相互印证。
