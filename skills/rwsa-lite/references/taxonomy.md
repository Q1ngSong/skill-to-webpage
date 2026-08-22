# 分类表(蒸馏自 wsa_skill_parser)

## 节点分层(每个静态节点归一层)

| layer | 含义 | 常见 role | 文本信号 |
|---|---|---|---|
| `R` | 路由 / 激活:什么时候用这个 skill | activation, scope, exclusions | "Use this skill when", "When to use", "Do not use when" |
| `W` | 流程:按序做事的节点 | main_flow, fallback, setup, finalize | Step N、祈使句序列、first / then / finally |
| `S` | 语义 / 知识:怎样做对、判据、词表、技巧 | domain_rules, heuristics, criteria, taxonomy, quality_standards | 表格、prefer / avoid、tips、分类列表 |
| `A` | 附件:工具、资源、输入输出、治理、呈现 | tool_action, resources, governance, presentation, io | 命令清单、URL、"do not … without"、示例格式 |

## 步骤类型(19 型,W 节点内每步一个)

`INTAKE` `READ` `RETRIEVE` `PARSE` `PLAN` `REASON` `CLASSIFY` `TRANSFORM` `GENERATE` `TOOL_CALL` `OBSERVE` `STATE_READ` `STATE_WRITE` `VALIDATE` `ASK_USER` `APPROVE` `OUTPUT` `TERMINATE` `FALLBACK`

选型提示:拿外部数据 = RETRIEVE;从用户话里提结构 = PARSE;跑命令 = TOOL_CALL;核验闸口 = VALIDATE;给用户看 = OUTPUT;兜底动作 = FALLBACK;一步里既问又做 → 按主动作定型,审批用 checkpoint + `approval` 边表达。

## 边类型(10 型;相邻步骤的 sequence 由目录隐含,不列)

| type | 何时 | condition 写什么 |
|---|---|---|
| `dependency` | 某步用到别处的知识 / 工具 / 资源 | 用到的是什么 |
| `condition_true` / `condition_false` | if / unless / otherwise 的两支 | 条件文案(逆命题记 inferred) |
| `loop` | 逐个 / 直到 | 循环对象 |
| `retry` | 失败 / 无结果后换法再来 | 触发条件 |
| `fallback` | 失败 / 找不到时的兜底去向 | 触发条件 |
| `parallel` | 可同时进行 | — |
| `approval` | 需用户同意才能继续 | 同意什么 |
| `termination` | 到此结束(端点 `END`) | 结束条件 |

## 语义 8 维 / 附件 6 类

语义:`goal` · `procedure` · `criteria` · `domain_rules` · `heuristics` · `examples` · `quality_standards` · `failure_modes`
附件:`tools` · `resources` · `inputs` · `outputs` · `governance` · `presentation`

示例只有在"示范怎么做这一步"时才是 `examples`;只示范输出格式的是 `presentation`。禁令与确认要求归 `governance`(同时可记 `failure_modes`)。

## W/S/A 强度与八分类

强度:0 缺失 / 1 弱 / 2 中 / 3 强。标签按"有无"(强度 ≥ 1 记 1):

| W | S | A | label |
|---|---|---|---|
| 0 | 0 | 0 | Prompt Fragment |
| 0 | 0 | 1 | Attachment Wrapper Skill |
| 0 | 1 | 0 | Semantic Guideline Skill |
| 0 | 1 | 1 | Semantic Resource Skill |
| 1 | 0 | 0 | Bare Workflow Skill |
| 1 | 0 | 1 | Tool-driven Workflow Skill |
| 1 | 1 | 0 | Semantically Guided Workflow Skill |
| 1 | 1 | 1 | Full Runtime Workflow Skill |
