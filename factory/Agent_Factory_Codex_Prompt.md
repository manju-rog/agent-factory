# Codex implementation prompt: adaptive agent factory

Use this prompt with the accompanying Axiom source. It supersedes any earlier interpretation that contextual email templates are the main product. The target is a general factory for reusable AI agents inside custom business workflows.

---

You are implementing a production-quality adaptive agent workflow product. Inspect the repository and its current verification report first. Preserve working functionality, identify which requirements below are already implemented, and deliver executable increments with tests. Do not present simulated providers, generated screenshots, fixture integrations, or interface-only controls as completed production functionality.

## Product objective

Administrators create custom agents by describing the outcome they want and selecting the authority and data those agents may use. They place these agents into visual workflows. During a run, each agent adapts its actions to the actual case, retrieves additional permitted information, chooses tools, handles missing information, and revises its approach after observing results.

Send Mail after CSR versus Jira is only an illustrative case. The architecture must support other domains and newly registered capabilities without changing the planning loop. Do not implement one hardcoded planner branch per business scenario or require a new agent implementation whenever wording or context changes.

## Core abstractions

1. **Capability contract:** stable ID, version, clear business description, structured input/output schemas, semantic field meaning, read/write effect, authorization scope, adapter binding, idempotency/reconciliation behaviour, and suitable examples. Executable capability code is registered by a developer through an approved delivery process.
2. **Agent specification:** stable identity and version; mission; operating instructions; allowed capability IDs; initial context bindings; result schema; stop/escalation rules; time, model-call, tool-call and cost limits; applicable policies; evaluation cases. This is reviewed configuration for a shared runtime.
3. **Workflow definition:** deterministic Action nodes and adaptive Goal Agent nodes, explicit dependencies, role-controlled human stages, conditional paths with defined join semantics, timeouts, and versioned publication. Published runs pin the definitions and contracts they use.
4. **Agent session:** durable observations, decisions, requests for information, prepared actions, policy outcomes, model/provider metadata, resource consumption, and final output. Durable session history is separate from the current model context.
5. **Prepared action:** exact destination and arguments, evidence references, applicable policy, content hash, stable operation identity, approval state, execution receipt, and reconciliation state.

Names may follow existing repository conventions. These are architectural responsibilities, not permission to duplicate existing subsystems.

## Actual AI behaviour

Implement a provider interface for a real configured model. Do not silently fall back to a deterministic script and label the result AI. An absent or incompatible provider must produce a useful visible configuration/error state. Permit approved hosted or self-hosted providers through adapters; credentials stay server-side.

For each decision, provide the mission, relevant permitted context, observations, outstanding questions, tool contracts, constraints, and remaining budget. Require a structured decision such as:

```json
{
  "kind": "call",
  "toolId": "a_registered_capability",
  "arguments": {},
  "summary": "A short operational explanation based on the current observation"
}
```

The exact IR should follow the implemented engine contract. Other supported decisions request missing information or propose a typed final result. Reject unknown fields and invalid alternatives. Never execute model-generated shell commands, source code, arbitrary URLs, or invented tool IDs through this interface.

After a tool executes, record its real result and give that observation to the next model call. This must be an adaptive loop, not a single model call that writes an unchangeable plan. Model calls occur outside the persistence lock. Apply results only to the session revision and worker lease that requested them; ignore stale completions.

The model can choose its method within scope. It cannot change access rights, remove required approvals, change its mission, or declare an external operation successful without its result. Tool content is evidence rather than higher-priority instructions. Log concise operational explanations; do not request or display private chain-of-thought.

## Workflow integration

Saved and approved agent versions must appear as reusable Goal Agent entries in the workflow palette. A placement supplies its case-specific objective/context and retains the selected version. On activation, it creates or resumes one durable child session. The parent waits while the child investigates, requests information, or awaits an action approval. Verified child completion supplies a typed output to downstream nodes.

Propagate failure, cancellation, budget exhaustion, missing input, and approval state explicitly. Distinguish a node-level approval to start a task from approval for a consequential operation later discovered inside the task. Never interpret one as blanket approval for the other.

A new published agent version must not alter an already running parent or child. Stable IDs and exact bindings govern data flow; canvas position and display labels do not.

## Context and capability discovery

Support guaranteed initial bindings and controlled retrieval. Do not pass the entire application database, every workflow output, secrets, or all conversation history to every agent. Authorize access before selecting context. Preserve source identity, freshness, record ownership, and semantic types where available.

For large registries, search only among capabilities the agent and caller may use; retrieve full schemas after candidate selection. Treat discovery and authorization as distinct operations. Missing capabilities produce a concrete explanation and escalation, not invented actions.

Allow meaningful new task combinations using existing primitives. New executable tools still require a developer integration and validation. Do not add runtime self-modification merely to make the demo look autonomous.

## Effects and durable execution

The trusted registry and policy service determine effects and approvals. For a consequential action, resolve authoritative fields and persist the exact prepared payload before review. An approval binds that payload, version, destination, and operation identity. Edited payloads require another decision.

After approval, execute the stored action rather than asking the model to recreate it. Use adapter-specific idempotency and reconciliation. Distinguish a failed request from an unknown remote outcome. Do not claim generic exactly-once delivery across unrelated services.

Where an action depends on mutable business state, retain source versions and recheck its business preconditions immediately before commit. Changed policy, ownership, balances, account state, or record versions can invalidate a previously prepared action even if its content hash is unchanged. Use conditional writes where the destination supports them.

Separate observation, preparation, approval, commit, and verification records. Reads can be retried according to policy; write retries need the adapter's contract. A crash or model timeout must not hold a global lock, lose approval state, or stall unrelated workflows.

## Agent factory interface

Provide a coherent workspace with:

- An agent catalog showing mission, version, authority, compatible tools, verification status, and actual usage.
- An editor for mission, permitted context, selected capabilities, expected result, and resource limits. Use plain business labels with advanced schema editing available when needed.
- An optional AI authoring assistant that proposes an agent specification from a business request. The proposal is validated and reviewed before activation; its suggested permissions do not authorize themselves.
- A run inspector showing actual action/observation order, requests for information, changing operational plans, prepared actions, and evidence-linked results.
- Clear configured-model, scripted-fixture, simulation, and production adapter labels.
- Keyboard and screen-reader support, useful empty/error states, responsive layouts, unsaved-change protection, stale-result handling, and no dead controls.

Do not bury this in an email-template editor. Agent creation and reuse in custom workflows are primary product journeys.

## Outcome verification and productive differentiation

A correct output schema proves shape, not business success. Add trusted outcome validators for supported domains: source-record comparisons, existing-record checks, post-action reads, or explicit human acceptance. Distinguish observed facts, inferred conclusions, and unresolved questions.

Add a behaviour-preview workspace. Run one agent version against a controlled variation set: normal, missing evidence, conflicting records, duplicate operation, denied capability, unavailable service, and a changed business condition. Compare actions, completion evidence, time, and cost. Fixture tests establish runtime behaviour; live model evaluations establish planning quality. Keep them separate in the UI and reports.

Show capability gaps and plan changes with their triggering observations. Promote reusable procedures mined from successful traces only after evaluation and review. Do not automatically modify published agents from isolated successes. Multi-agent delegation is an optional later capability for separable tasks, with explicit child budgets and reduced authority; it is not required for every problem.

## Required demonstrations

Use at least three different business tasks with one shared runtime. Suitable examples include support-case triage, document review, and vendor or account onboarding. Real integrations may differ according to available contracts.

For at least one saved agent, show two inputs causing different tool sequences because a tool returned different evidence. Show an existing record being reused, a missing fact causing a clarification and resume, a write awaiting exact approval, an unavailable capability producing a useful partial outcome, and a registered capability that the runtime was not coded specifically to recognize.

A scripted provider is acceptable for deterministic tests and labeled offline demonstrations. Also implement the real provider adapter and its error handling. Do not claim model quality, external delivery, or production authorization from scripted tests.

## Verification and delivery

Test registry allowlists, strict schemas, budget exhaustion, selected-context boundaries, observation-dependent decisions, clarification, output/evidence validation, unchanged prepared-action approval, duplicate-safe local effects, restart, version pinning, stale concurrent responses, and the parent/child workflow bridge. Reuse relevant existing tests and avoid superficial tests that merely repeat implementation constants.

Add focused HTTP integration tests and actual browser checks when a browser is available. A DOM stub or view-function test is not browser, accessibility, drag-and-drop, or visual verification. Report limitations explicitly and do not keep retrying unavailable infrastructure without a concrete reason.

Keep fixture services and developer identity switching isolated from production settings. Production completion requires actual authentication and tenant isolation, least-privilege credentials, observability, retention, provider evaluations, adapter reconciliation, and load/failover validation. Do not label the local reference production-ready because these items appear in a document.

Deliver the running implementation, startup instructions, reproducible tests and examples, architecture/decision notes, provider setup, and a concise feature matrix separating implemented, verified, integration-required, and proposed features. Preserve the original custom workflow and agent-factory goal throughout the work.
