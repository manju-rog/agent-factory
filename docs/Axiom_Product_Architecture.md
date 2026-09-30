# Axiom product architecture and research direction

## Product decision

Axiom is an original, company-neutral application for turning business intent into governed agent workflows. Its primary object is an executable business contract. A graph, an approval packet, a scenario test, and an execution history are coordinated views of that contract.

The ambition is to make a process understandable from the original requirement to the external action it caused. A person should be able to ask what the workflow will do, why it is allowed, what evidence it used, how it behaves under failure, and what has already changed outside the application. Those answers should point to inspectable records.

This direction preserves the meeting's agent catalog, administrator composition, drag-and-drop sequential/parallel designer, node configuration, template-selected tasks, manual execution, role policies, approval toggle, reminders, and draft/review/publication. It extends those requirements through AI-assisted construction, evidence, testing, and controlled repair.

The research is a bounded primary-source review, not an exhaustive market benchmark. Features described as proposed are design hypotheses. No evidence supports claiming that this product already outperforms every available product. The accompanying application is a runnable local reference implementation; the production specification identifies the additional engineering and integrations required.

## The distinction that matters

Tool approval, persistent human interrupts, and model evaluations already exist in current platforms. Merely placing them in a new sidebar is not a defensible advantage. n8n documents human review of tool calls; LangGraph documents durable interrupts; LangSmith documents evaluation datasets and experiments. [n8n tool approvals](https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools.md), [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation).

Axiom's proposed advantage is the continuity between six objects:

| Object | User's question | Inspectable answer |
| --- | --- | --- |
| Requirement | What am I trying to achieve? | Outcome, constraints, assumptions, owner, acceptance cases. |
| Executable plan | What will happen? | Typed nodes, dependencies, decision rules, allowed effects. |
| Scenario | What if a dependency fails? | Pinned starting state, injected event, observed result. |
| Evidence | Why is this recommendation justified? | Source snapshot, field/path, transformation, claim type. |
| Decision | What exactly am I approving? | Bound action payload, policy, scope, expiry, effects. |
| Receipt | What actually happened? | Versioned events, attempts, external effect records, unresolved uncertainty. |

All six should share stable references. An AI edit that removes an approval should immediately affect the policy lens and scenario expectations. A runtime failure should become a reproducible regression case. A corrected template should have a visible link back to the failure that motivated it.

## Seven systems within one product

### 1 Outcome designer

The user supplies an outcome and constraints: “Create a CSR request, check ownership and policy in parallel, require a reviewer before creating a Jira ticket, and collect the decision evidence.” The system resolves eligible capabilities and proposes a graph patch with explicit assumptions. It does not silently invent an integration, credential, reviewer role, or business rule.

The patch contains typed operations rather than source code. A compiler checks supported node types, connections, input compatibility, dependency boundaries, graph limits, and policy rules. Accepting it uses the same editor transaction as a manual graph change. Users can compare, edit, apply, or reject it; undo remains available.

Research connection: PICARD shows the value of constraining generated structure, while LLMCompiler separates planning, dependency dispatch, and execution. Their results motivate this architecture; they do not prove a proposed business process is correct. [PICARD](https://arxiv.org/abs/2109.05093), [LLMCompiler](https://arxiv.org/abs/2312.04511).

### 2 Specialist steps

An ordinary Agent node executes one capability. A Specialist Team node performs bounded work that benefits from multiple roles, such as extracting facts, researching context, and challenging a proposed response. Users inspect each role's deliverable and evidence, not an unlimited conversation between bots.

Every team recipe declares available tools, data scopes, turn limits, spend limits, stopping rules, and one actor authorized to commit effects. A verifier can object; it cannot grant itself broader authority. Begin with a single-agent baseline and retain a team only if testing shows enough improvement to justify cost and latency.

Research connection: AutoGen supports programmable collaboration, while MAST documents ways multi-agent systems fail. Adding more agents is a hypothesis to test rather than a quality guarantee. [AutoGen](https://arxiv.org/abs/2308.08155), [MAST](https://arxiv.org/abs/2503.13657).

### 3 Evidence lens

Selecting a fact, condition, recommendation, or approval reveals where it came from. Label direct extraction, deterministic calculation, model inference, and human assertion differently. Keep contradictory and missing sources visible.

Evidence records contain source IDs, versions/hashes, field paths or excerpt ranges, timestamps, access labels, and transformation IDs. Generated explanations summarize those records and cite them. The product does not invent a retrospective explanation or expose private model reasoning as an audit trail.

Research connection: W3C PROV supplies a useful provenance vocabulary. RARR investigates attribution and revision supported by retrieval. Provenance makes inspection possible; it is not proof that the source itself is true. [W3C PROV](https://www.w3.org/TR/prov-dm/Overview.html), [RARR](https://arxiv.org/abs/2210.08726).

### 4 Rehearsal laboratory

The laboratory tests business consequences. Compare the same case across two workflow versions; inject missing inputs, an unavailable approver, a timeout after a write was accepted, or an adversarial tool response. Show the actual path, effect attempts, invariant checks, and final fixture state.

Separate three operations in both terminology and implementation: inspecting recorded history, replaying pinned outcomes in isolation, and executing models/tools again. The latter may change results and incur costs. No rehearsal receives production write credentials. A model-emulated service is visibly approximate and supplements deterministic fixtures rather than replacing them.

Research connection: ToolEmu explores agent risk testing using emulated tools; tau-bench emphasizes policy-sensitive outcomes, final state, and reliability across repeated trials. [ToolEmu](https://arxiv.org/abs/2309.15817), [tau-bench](https://arxiv.org/abs/2406.12045).

### 5 Decision inbox

The reviewer sees the action, exact target/payload, supporting facts, applicable rule, unresolved concerns, and what approval unlocks. Approving a graph release is separate from approving an action in a run. A human who only approves cannot automatically execute a manual step unless independently authorized.

An approval binds the run, node, action fingerprint, graph version, reviewer policy, and expiry. Changing the recipient, amount, target, or other protected input invalidates it. Permissions are checked again at decision and dispatch time. The right pane provides eligible reminders and authenticated deep links; opening an email never approves a task.

In Design mode, Preview role experience shows whether an intended role could view, execute, or approve. This is inspection rather than impersonation. Policy validation is separate from authorization; a valid policy can still express the wrong business rule. [Cedar validation](https://docs.cedarpolicy.com/policies/validation.html).

### 6 Recovery workbench

On failure, show completed work, remaining work, known external effects, and uncertain results. A repair proposal is one of a restricted set: retry a safe read, reconcile a possible write, correct a mapping in a new draft, choose an approved fallback, or request human intervention.

The proposal points to evidence, describes which effect identities will be retained, and includes a matching regression scenario. It is revalidated and rehearsed before any authorized live action. An unknown write result cannot become an automatic retry merely because a model calls it safe.

Prompt injection remains relevant when tool responses and documents become planning evidence. AgentDojo supplies a useful evaluation pattern: malicious instructions in external data should not change authority. This is an ongoing security property to test, not a problem solved by one system prompt. [AgentDojo](https://arxiv.org/abs/2406.13352).

### 7 Release laboratory

Compare a proposed workflow, agent recipe, model, prompt, or connector change with the active version on pinned cases. Surface improvements and regressions separately: valid outcomes, policy violations, human review load, latency, and cost. Show sample size and uncertainty rather than a single unsupported quality score.

Release rules combine deterministic invariants with evaluated quality. A model judge cannot overrule a failed permission check. Active runs retain their pinned definition. Promotion changes future starts; migration of existing executions is a separate controlled procedure.

## Interaction design

The application should feel like a professional engineering workspace whose complexity unfolds on selection. Use a compact global rail, a process context bar, a large horizontal canvas, a searchable capability palette, and a right-hand workbench. A collapsible bottom area shows events, tests, or validation related to the selected work.

| Surface | Primary behavior | Important secondary behavior |
| --- | --- | --- |
| Studio | Build and inspect the process. | AI patch preview, role lens, outline/table, reusable blocks. |
| Agent registry | Understand and configure capabilities. | Schemas, side effects, versions, evaluations, consuming templates. |
| Runs | Operate actual work. | Timeline, evidence, effects, recovery, exact published version. |
| Decision inbox | Make a well-informed decision. | Compare outgoing action with evidence; remind or escalate. |
| Rehearsal lab | Explore failure and compare outcomes. | Save cases, run suites, capture regressions, review releases. |
| Connections | Bind approved capabilities to environments. | Server-side credentials, test results, identity, egress scope. |

Use spatially stable nodes across modes. A selected step remains selected when switching from design to a run. Overview zoom shows stages; working zoom shows node contracts; detailed inspection reveals fields and ports. Do not shrink hundreds of labels until they become unreadable. The keyboard outline supports the same authoring actions.

The proposed visual direction uses warm neutral canvas surfaces, deep ink navigation, cobalt interaction accents, restrained status color, and clear typography. Use meaningful operational density rather than oversized card grids. Nodes show action, capability, owner/gate, and effect class. Warnings appear beside the affected field or path. Animation conveys insertions, graph changes, or actual state transitions; it never manufactures progress.

## Architecture

Build an original product with owned source and behavior. Do not fork, embed, or rebrand n8n or Dify. Permissive foundational libraries are acceptable after license review. n8n's Sustainable Use terms and Dify's modified license require more care than a blanket “open source” label. [n8n license](https://github.com/n8n-io/n8n/blob/master/LICENSE.md), [Dify license](https://github.com/langgenius/dify/blob/main/LICENSE).

For the production target, use a TypeScript frontend, modular application API, PostgreSQL product records, object storage for evidence, and a durable runtime such as self-hosted Temporal. Keep business rules, typed contracts, graph compiler, policies, and agent SDK independent of the UI. Use an OIDC identity provider and application-owned permissions. An existing Java/BPMN application can reasonably use Flowable OSS instead; select one orchestration authority.

The durable runtime owns progress, timers, retries, and terminal decisions. Agents do I/O through Activities. A bounded agent team may run inside an Activity or child workflow with recorded outputs; it must not become a second hidden scheduler. Every consequential internal tool call needs its own durable boundary or a persisted reservation/checkpoint protocol. Retrying the team must not repeat completed writes. Runtime code must remain replay compatible. Model/tool results are recorded artifacts; they must not be silently regenerated while reconstructing historical state.

The AI gateway is provider-neutral. It supports a local/self-hosted model or an approved remote provider through server-side configuration. It enforces structured outputs, budgets, cancellation, redaction, data-residency policy, and observed usage. No unconfigured provider should appear live. Manual authoring, execution, and policy remain complete when AI is disabled.

The reference application uses a small Python/SQLite implementation to make interactions runnable without installing commercial infrastructure or obtaining credentials. Its state machine and API demonstrate local behavior; they are not a replacement for production tenancy, identity, durable infrastructure, or real connector validation. The master prompt contains the migration and completion requirements.

## Specific engineering contracts

### Graph and approval correctness

Use a restricted structured control model so validation can have precise meaning. Check graph well-formedness, supported types, field assignability, branch scopes, finite bounds, and required approvals on all protected paths. Checking that a gate dominates a protected write is a useful structural property; it is not proof of arbitrary business correctness. Dynamic targets must be checked at dispatch.

Published executable definitions are immutable. Separate layout changes from semantic changes. Resolve defaults and pin implementation versions, policy version, schema version, and interpreter version. Store explicit provenance from requirement to proposed patch to released node.

### Effects and recovery

Maintain logical action identities and an effect ledger with states such as prepared, dispatched, acknowledged, unknown, reconciled, and compensated where supported. This minimum ledger belongs in the core release because safe retries depend on it. Stable idempotency keys must survive retries of the same action; reject reuse with a different action fingerprint. Compensating a ticket creation is not the same as erasing the fact it happened. Capabilities declare whether they can reconcile, retry, cancel, or compensate.

Use prepare → approve → commit for protected actions. A gate before an AI step cannot approve tool arguments that the model has not generated yet. Intercept each dynamic write, prepare its exact target and payload, bind the decision, and recheck authority before committing. The stable action fingerprint includes workspace, run/node/action generation, canonical payload, method, destination/resource, and connection/environment identity. A separate approval-envelope hash adds policy version, evidence snapshot, reviewer scope, and expiry. Payload edits or connection rebinding invalidate approval. Renewing an expired approval for an unchanged action preserves its operation identity so renewal cannot create a duplicate write.

### Data ownership

Every input, artifact, evidence item, model output, template, run, decision, and export is scoped. Derived evidence does not escape the original access constraints. Long-lived approvals recheck current grants. Logs and histories must not contain credential values. Run exports are redacted by default and link to authorized evidence.

### Testing

Maintain independent fixture cases with expected final states. Include authoring errors, branch failures, duplicate delivery, lost acknowledgement, late approval, revoked identity, stale draft, malformed model output, and injected instructions in evidence. Seeded failure tests demonstrate implemented properties; they do not certify every future integration.

## Business value and evaluation

| Hypothesis | Measure | Evidence required before claiming improvement |
| --- | --- | --- |
| Typed AI patches speed authoring. | Time to valid workflow, corrections, first-run success. | Paired user tasks against manual authoring; disclose sample size. |
| Evidence packets improve decisions. | Correct understanding of next action, decision time, post-approval corrections. | Blinded review tasks including misleading and contradictory evidence. |
| Rehearsal prevents regressions. | Seeded defects detected, escaped regressions, prohibited effect count. | Held-out scenarios and real adapter sandbox tests. |
| Recovery workbench reduces investigation. | Time to diagnose, safe recovery rate, duplicate writes. | Repeatable crash/timeout scenarios with downstream state inspected. |
| Teams help difficult cases. | Outcome success at matched cost/latency. | Single-agent versus team experiments on held-out cases. |

Targets in a roadmap are not achieved metrics. Avoid invented confidence percentages or a composite quality score that hides policy failures. Early product research can set candidate targets, then revise them when actual data exists.

## The complete demonstration

Begin with the meeting's CSR-to-ticket process. Show the available capabilities, then express an outcome with parallel ownership and policy checks. Inspect the proposed graph patch and one explicit assumption. Apply it, preview the Contributor and Reviewer roles, and inspect the exact outgoing ticket action.

Run a rehearsal suite. Missing data should prevent the write. A timeout scenario should expose a recoverable failure. In the production target's after-write-timeout case, the effect ledger should identify the ambiguity and choose reconciliation. Compare observed results with expected invariants.

Submit the draft; a different reviewer publishes it. Start a task against that version. Show a manual step that cannot run until the correct person acts, followed by a separate approval gate. Restart the worker while waiting. Resume, create one fixture ticket, and inspect its evidence receipt. Publish a new version and demonstrate that the original run remains unchanged.

The final part should show a failed case becoming a saved regression scenario and a reviewed repair. This links AI assistance to an observable business outcome rather than ending the demonstration with generated text.

## Delivery truth

The accompanying status and test report are authoritative about what the local application implements. Research proposals, production architecture, local fixture behavior, and verified integrations are separate categories. OCI, Jira, corporate identity, production email, and model quality cannot be declared verified without their actual contracts and test environments.

Full source access means the application, schema, graph rules, adapters, and tests are provided. It does not remove third-party license obligations or grant access to external services. The system should remain adaptable across companies and industries without hardcoding one customer's organization model.
