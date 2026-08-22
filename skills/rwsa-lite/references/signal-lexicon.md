# 控制流信号词典(中英双语)

蒸馏自 wsa_skill_parser「Extraction Signals」,补中文等价词。命中仅是候选:还须判定方向与端点,`quote` 必须落在证据行内。

| 类别 | 英文 | 中文 | 成边 / 产物 |
|---|---|---|---|
| 重试 / 环 | repeat, retry, iterate, until, again, re-run, try alternative, doesn't work → try | 重试, 重复, 再次, 直到, 逐个 / 逐章, 换…再, 回到 Step X, 反复 | `retry`(自环或回退)/ `loop` |
| 条件 / 改道 | if, unless, otherwise, when, in case, only if, doesn't cover → | 如果, 若, 否则, 视情况, 命中则, 已存在则跳过, 不够再 | `condition_true` + `condition_false`(逆命题 inferred) |
| 兜底 | fallback, if failed, if no…, if none found, degrade | 兜底, 失败则, 找不到时, 无结果, 退化为, 保底 | `fallback` 边;目标节点 role=fallback |
| 审批 | ask, confirm, approve, review, offer to, wants to proceed, consent | 征得同意, 询问用户, 确认后, 同意后再 | `approval` 边 + checkpoint(approval) |
| 验证闸口 | verify, validate, do not X until / unless, never X without, always check | 核验, 校验, 验证后才, 绝不直接, 必须先…再 | checkpoint(validate)+ governance + failure_mode |
| 依赖 | see…, use the following, consider these, refer to, run `cmd` | 参见, 按下表, 参考, 用…命令 | `dependency` 边(常跨节点)+ `cross_anchored` |
| 并行 | in parallel, simultaneously, meanwhile | 同时, 并行 | `parallel` |
| 终止 | finish, stop, complete, done, deliver, return, terminate | 完成, 停止, 交付, 收尾, 到此为止 | `termination` 边 → `END`;全文没有 → 记 inferred + 备注 |
| 顺序(辅助) | first, then, next, before, after, finally | 先, 然后, 接着, 之前, 之后, 最后 | 不成边(目录隐含);用于判断顺序偏差 |

## 判定提醒

1. 示例代码块 / 示例回复里的 if、命令不算控制流,算 `examples` 或 `presentation`。
2. 跨节点边**照成**,端点写 `nXX` 或 `nXX.k`;不要塞进 ambiguities。
3. 一句话同时含多类信号(如"找不到就换词重试")→ 同时成 `retry` 与 `fallback`,各挂同一 source。
4. "列表里有 3 项"不等于"3 个步骤":问自己"这是按序做的动作,还是某一步要看的内容?"
