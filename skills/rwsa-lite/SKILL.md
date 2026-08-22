---
name: rwsa-lite
description: Use when a skill already has a static knowledge base (static/ from skill-to-webpage 结构拆解) and its workflow semantics must be extracted in full and reconciled against that static skeleton — skill-to-webpage 拆解模式选了语义富化, someone asks what a skill's real execution graph is, or whether its headings (目录) deviate from its actual flow. Implements s2w-semantics/2. Not for skills without a static/ knowledge base yet (run 结构拆解 first).
---

# rwsa-lite

RWSA(`Skill = R + (W+S+A)`)的语义抽取,叠加在静态骨架之上。

## 总纲

- **静态骨架是坐标系。** `static/` 的节点(`##`)与步骤(`###`)是目录;你不重切、不替换,只归类、分型、连边、挂语义,并把目录与实际流程的差异写进印证区。没有 `static/` → 停下,先跑结构拆解。
- **抽全不省。** 19 型步骤、10 型边、8 维语义、6 类附件、检查点、终止、W/S/A 强度——能在文本里指认的都抽。渲染器显不显示不是你该考虑的事。
- **显式与推断都收,但分清。** 直接陈述 `explicit`;上下文强烈暗示(如条件句的逆命题)`inferred`。
- **每条可机核。** 每条断言带 `source` 行号 + `quote`(引用行内逐字片段,≤ 80 字符)。写不出 quote 的断言不算数。

## 输入 / 输出

- 输入(调用方按 parser-protocol 给三样):① 源 skill 目录(回读原文、算 sha256 与 `wc -l`);② 静态知识库目录 `static/`(结构拆解产物,只读);③ 本解析器的输出目录(通常 `output/<skill>/rwsa-lite/`)。
- 输出:`<输出目录>/semantics.json`(契约以调用方 `semantics-contract.md` 为准,快照见 `references/schema-snapshot.md`;`skeleton` 抄自 `static/`)+ `<输出目录>/semantics-report.md`(`python3 scripts/make_report.py <输出目录>` 生成)。**不写 `static/`,不写别的解析器的目录。**

## 步骤

1. **L0 目录** — 读 `static/INDEX.md`、`metadata.json`、`nodes/*.md`;抄成 `skeleton`(`from: static/INDEX.md`,id / 标题 / 行号 / `###` 数)。这是印证基准。
2. **L1 分层** — 每个节点归 `R` / `W` / `S` / `A` + `role`(见 `references/taxonomy.md`)。覆盖率必须 100%。R 层触发/排除条件写进 `routing`。
3. **L2 W 层** — 对每个 W 节点:`###` 步骤逐个分型(19 型);找**全部非顺序边**(对照 `references/signal-lexicon.md`):条件两支、重试/环、兜底、审批、依赖(含 S/A 节点 → 步骤的跨节点依赖)、终止;标 `checkpoints`;文本里按序做事却没标题的 → 追加 `"implicit": true` 步骤。
4. **L3 S/A 层** — 每步 `goal` + 8 维语义(goal / procedure / criteria / domain_rules / heuristics / examples / quality_standards / failure_modes)+ 附件(tools / resources / inputs / outputs / governance / presentation)。只记文本里有的维度;写在别的节点里的知识照样挂到用它的步骤上,并登记 `cross_anchored`;不属于任何步骤的放 `global`。
5. **L4 印证** — 填 `reconciliation`:覆盖率、非流程标题、隐含步骤、顺序偏差、跨锚定、裁定记录、`unanchored`(必须空)、备注。派生 `loops` / `jumps` / `guards`(与 `edges` 一致,同样带 source/quote)。给出 `wsa_profile`。
6. **L5 校验写出** — `source.lines` = `wc -l`;每条 `quote` 回读核对;端点与序号在界内;`python3 <skill-to-webpage>/scripts/validate_semantics.py <输出目录> --static <static目录> --skill-dir <skill目录>` 零作废后才算写出成功;再跑 `make_report.py <输出目录>`,把报告的第 5 节(偏差)讲给用户。

## 速查

| 文本特征 | 产出 |
|---|---|
| `###` 标题 | 静态步骤(只分型,不新增) |
| 编号 / 顺序动作但无标题 | `implicit` 步骤 + 印证区登记 |
| 列表是"识别什么 / 包含什么 / 满足什么" | `procedure` / `quality_standards` / `criteria`,**不是步骤** |
| if / unless / doesn't → | `condition_true` + `condition_false` 两条边(逆命题记 `inferred`) |
| retry / try alternative / until / 再 | `retry` / `loop` 边 |
| if no… / if failed / 找不到 | `fallback` 边;目标节点 role=fallback |
| ask / confirm / wants to proceed | `approval` 边 + checkpoint |
| do not X / always verify / never | `validate` checkpoint + governance + failure_mode |
| 别处的技巧、词表、命令被某步使用 | `dependency` 边(跨节点)+ `cross_anchored` |
| 无 finish / stop / complete | `termination` 记 `inferred` + 备注"无显式终止" |

## 常见错误

- 把判据列表当子步骤(如"识别领域 / 任务 / 是否常见"是 procedure,不是三步)。
- 把示例代码块里的 `if` 当分支;把示例回复里的命令当工具调用。
- 把跨节点边塞进 `ambiguities` 而不成边(0.1 版就是这样丢掉了 4 条依赖边)。
- `split("\n")` 数行数多 1;`quote` 改写了原文(必须逐字)。
- 把条件句的逆命题标成 `explicit`。

## 红线(这些念头出现就是在偷懒)

| 念头 | 事实 |
|---|---|
| "这个 skill 太小,抽不出什么" | 小 skill 照样有分层、隐含步骤、顺序偏差;印证区本身就是产出 |
| "渲染器反正不显示" | 显示是消费方的事;契约要求抽全 |
| "省点 token,砍两个维度" | 读都读了,多写几条 claim 成本可忽略;砍维度 = 丢信息 |
| "这条边太明显,不用写证据" | 无 quote 的断言会被校验器作废 |

## 文件

`references/taxonomy.md`(分层 / 步骤型 / 边型 / 强度标签)· `references/signal-lexicon.md`(双语信号词)· `references/schema-snapshot.md`(格式快照)· `scripts/make_report.py`(印证报告)
