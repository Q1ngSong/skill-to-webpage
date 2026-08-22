# s2w-semantics/2 快照(以调用方契约为准)

便携快照;与调用方(skill-to-webpage)`references/semantics-contract.md` 冲突时,**一律以调用方为准**。

通用 claim:`{ "text", "source": "SKILL.md:X[-Y]", "quote": "<引用行内逐字片段 ≤80字符>", "basis": "explicit|inferred" }`
位置引用:`"n03"` / `"n03.2"`(节点第 2 步,1 起)/ `"END"`

```json
{
  "schema": "s2w-semantics/2", "generator": "rwsa-lite/0.2", "generated_at": "YYYY-MM-DD",
  "source": { "file": "SKILL.md", "sha256": "<64 hex>", "lines": 0 },
  "skeleton": { "from": "static/INDEX.md", "nodes": [ { "id": "n03", "title": "…", "lines": "33-104", "steps": 6 } ] },
  "thesis": claim, "groups": [ { "label": "执行主线", "nodes": ["n03"], "main": true } ], "node_summaries": { "n03": "…" },
  "layers": { "n03": { "layer": "W", "role": "main_flow", "source": "…", "quote": "…" } },
  "routing": { "triggers": [ claim ], "exclusions": [ claim ] },
  "subflows": { "n03": [ { "title": "…", "lines": "35-42", "type": "PARSE", "goal": claim,
                           "semantics": { "procedure": [ claim ] }, "attachments": { "tools": [ claim ] } },
                         { "implicit": true, "title": "…", "lines": "129", "type": "OUTPUT" } ] },
  "edges": [ { "from": "n03.2", "to": "n03.5", "type": "condition_true", "condition": "…", "source": "…", "quote": "…", "basis": "inferred" } ],
  "checkpoints": [ { "at": "n03.4", "kind": "validate", "source": "…", "quote": "…" } ],
  "termination": [ { "at": "n03.6", "text": "…", "source": "…", "quote": "…", "basis": "inferred" } ],
  "global": { "semantics": {}, "attachments": { "tools": [ claim ] } },
  "wsa_profile": { "W": 3, "S": 2, "A": 2, "label": "Full Runtime Workflow Skill", "notes": [] },
  "loops": [ { "node": "n03", "from": 3, "to": 3, "label": "…", "source": "…", "quote": "…" } ],
  "jumps": [ { "node": "n03", "from": 2, "to": 5, "when": "…", "source": "…", "quote": "…", "basis": "inferred" } ],
  "guards": [ { "guard": "n06", "protects": { "node": "n03", "step": 3 }, "source": "…", "quote": "…" } ],
  "reconciliation": {
    "nodes_total": 6, "nodes_classified": 6, "steps_total": 6, "steps_typed": 6,
    "non_workflow_nodes": [ { "node": "n04", "layer": "S", "why": "…" } ],
    "implicit_steps": [ { "anchor": "n06", "count": 3, "source": "…", "quote": "…" } ],
    "order_deviations": [ claim ], "cross_anchored": [ { "item": "n03.3 heuristics", "from_node": "n05", "source": "…" } ],
    "judgment_calls": [ { "anchor": "n03.1", "text": "…", "source": "…", "quote": "…" } ],
    "unanchored": [], "notes": [ "…" ]
  },
  "ambiguities": []
}
```

必填:`schema` `generator` `source` `skeleton` `layers`(覆盖全部节点)`reconciliation`(`unanchored` 必须空)。派生视图 `loops` / `jumps` / `guards` 必须各有对应的 `retry|loop` / `condition_*` / `fallback` 边。
