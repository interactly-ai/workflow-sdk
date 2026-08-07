# Phase 1.3 — drift review: harness output vs the plan's §1

Both harnesses were run and their output checked against the hand-written findings in
`WORKFLOW_SDK_UPDATE_PLAN.md` §1, as Phase 1.3 requires. **The plan's findings all survived, and the
harnesses found more.** Nothing in §1 was contradicted; the additions are listed below and need to be
folded into Phase 2.

| Harness | Command | Report | Result |
|---|---|---|---|
| Source parity | `make parity-check` | `config-parity-2026-08-06.md` | **143 differences** + 2 placement |
| Live schema | `make schema-check` | `schema-drift-2026-08-06.md` | **50 findings**, 33 schemas, 0 errors |

The two agree wherever they overlap, which is the useful signal: source parity says the mirror lags
upstream's *code*, and the live check confirms the deployed dev server serves the newer shape. Neither
subsumes the other — parity sees things not yet deployed, the live check sees what the server computes
at runtime.

---

## What the harnesses confirmed

Every hand-written finding in §1.3, §1.5, §1.6 and §1.10 was reproduced independently:

- **All 7 new event types** (§1.5) appear as missing classes.
- `SelfLoopConfig`, `CompanionThreadConfig`, `EvaluateWhileWaitingConfig`,
  `WaitingEvaluationTriggerMode`, `NoOpNodeConfig/RunInput/RunOutput`, `RatingConfig/RatingValue/RatingRequest`,
  `CommentRequest` (§1.3) — all missing.
- `BEDROCKModel` missing; `BedrockLLMConfig` wrong on four fields (§1.6).
- **LLM enum drift confirmed live against dev**, exactly as §1.6 predicted: 9 values the mirror offers
  that the server would reject (`gemini-1.5-pro`, `gemini-2.0-flash*`, `claude-*-20250514`,
  `gpt-5-chat-latest`, `gpt-5.1-chat-latest`) and 12 the server offers that the mirror lacks
  (`claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-opus-4-7/4-8`, `claude-haiku-4-5`,
  `gemini-3.6-flash`, `gemini-3.5/3.1/2.5-flash-lite`, `gpt-5.4-pro`, `gpt-5.2-pro`).
- All six pre-existing gaps from §1.10 (`named_llm_config_*`, `side_effect`, `args_schema`,
  `access_config`, `voice_conversation_id`, `welcome_message`), plus both placement divergences
  (`BaseEntityConfig`, `WorkflowCommand`) and all three naming divergences.
- The live check independently found `self_loop_config` missing on **18 node schemas** and
  `side_effect` on **4 tool schemas** — the blast radius §1.3/§1.10 described but did not quantify.

---

## 🆕 What the harnesses found that §1 missed

These are **new to the plan** and are added to Phase 2's work list.

### 1. The mirror vendors from three upstream locations, not one

The single most consequential finding, because it invalidates the *method* behind §1.10, not just its
result. `interactly_configs` mirrors:

| Upstream | Mirror |
|---|---|
| `agentic_workflow_framework/configs/**` | `interactly_configs/**` |
| `agentic_workflow_framework/runtime/event.py` | `interactly_configs/events/event.py` |
| `common/models/acls.py` | `interactly_configs/acls.py` |

The §1.10 audit compared only modules sharing a path under `configs/`, so **`events/event.py` and
`acls.py` were never compared at all** — which is precisely why the event drift did not appear there
and had to be found by reading. The harness now covers all three (`UPSTREAM_SOURCES`).

### 2. Five more missing classes, all in the event module

Not in §1.5's list of seven:

| Class | Why it matters |
|---|---|
| `GuardrailEscalationEdgeEvent` | A real event type the runtime emits; the mirror cannot represent it |
| `WorkflowIterationMetrics` | Per-iteration metrics carried on iteration events |
| `IterationCallLatencyStats` | Latency breakdown embedded in the above |
| `StructuredOutputRetryAttempt` | Structured-output retry telemetry on LLM events |
| `StructuredOutputRetryMetadata` | Container for the above |

### 3. Two missing ACL enums

`UILoginRole` and `UISpecialFieldTypes` exist upstream in `common/models/acls.py` and are absent from
the mirror's `acls.py`. Low urgency — the mirror deliberately drops the UI annotations that *use*
these — but they are part of the vendored module's contract, and `acls.py` also carries an
`AccessControlLevelConfig` that upstream does not have.

### 4. 46 field-level gaps and 28 type mismatches

More than §1 enumerated, because §1 worked class-by-class. Notable beyond what is already listed:

- `StoredEvents` → `List` on **21** run-output classes (§1.3 flagged the rename; the harness shows it
  touches every `*RunOutput`).
- `List[NodeConfig]` vs `List[SerializeAsAny[BaseNodeConfig]]` — needs adjudication in Phase 2:
  probably an intentional serialisation choice in the mirror, but it is currently undocumented.
- One `str` → `Optional[str]` requiredness divergence.

### 5. `no_op` has no local model at all

The live harness reports `/v1/nodes/schema/no_op` as **unmapped** — the server serves a schema the
mirror has no class to compare against. This is the one finding that would have been silently skipped
by a naive schema check that iterated over *local* models instead of *server* types, and it is why
`resolve_local_models` enumerates node types from the server.

---

## False positives found and fixed (recorded so they are not re-litigated)

Building the harnesses surfaced four ways a naive comparison lies. Each is now handled in code:

1. **Inheritance.** Upstream re-declares `tool_id` on four tool subclasses; the mirror declares it once
   on `BaseToolConfig`. Field resolution now walks base classes, removing 4 phantom gaps.
2. **Module relocation.** `event.py` → `events/event.py` produced **44** identical placement
   differences. `KNOWN_MODULE_MAPPING` reduces placement noise to the 2 real ones.
3. **Forced type substitutions.** `AnyMessage`/`AIMessage` → `Any` (no `langchain_core` dependency) and
   `list`/`dict` → `List`/`Dict` (house style) accounted for 18 phantom type mismatches.
4. **Schema envelopes and `$ref`.** Node schemas arrive as
   `{config_schema, run_input_schema, run_output_schema}`, and `super_node`'s `config_schema` is a
   bare `$ref` into `$defs`. Unresolved, it read as zero server properties and reported all 23 of the
   mirror's fields as extras. Root-`$ref` resolution took `extra-property` from 23 to **0**.

Raw counts before and after this work: source parity 174 → **143**, live schema 176 → **50**. Every
removed item was verified as a false positive, not suppressed.

---

## Consequences for Phase 2

1. **Phase 2.9 grows.** Add `GuardrailEscalationEdgeEvent`, `WorkflowIterationMetrics`,
   `IterationCallLatencyStats`, `StructuredOutputRetryAttempt`, `StructuredOutputRetryMetadata` to the
   seven already planned.
2. **New step 2.16** — reconcile `acls.py`: add `UILoginRole` and `UISpecialFieldTypes`, and decide
   whether `AccessControlLevelConfig` stays.
3. **Adjudicate two deliberate-looking divergences** rather than blindly "fixing" them:
   `SerializeAsAny[BaseNodeConfig]` and `Optional[Event]` → `Optional[Any]`. If they are intentional
   they belong in `KNOWN_DIVERGENCES`, not in the diff.
4. **Work from the reports, not from §1.** §1 is now the narrative; `config-parity-2026-08-06.md` is
   the checklist. Re-run `make sync-check` after each Phase 2 step and watch the count fall.
