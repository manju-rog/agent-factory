# Axiom complete Codex build prompt

Paste this entire document into Codex in the target repository. It is an implementation directive, not a request for a proposal. Build an original application with owned source; do not embed or rebrand n8n, Dify, or a commercial workflow editor. Use the meeting requirements and the implementation contracts below. Working product name: Axiom.

## A Product ambition and completion standard

Build a company-neutral system where a business outcome becomes an inspectable, executable process. The interface must connect requirements, typed agent plans, graph edits, scenario tests, evidence, human decisions, external effects, and release history. Implement the workflows between these objects rather than building disconnected feature pages.

The important user journey is: describe an outcome -> inspect a proposed change -> resolve assumptions -> validate the graph and authority -> rehearse business consequences -> approve a release -> start a task -> perform role-controlled actions -> investigate evidence -> recover safely -> turn failures into regression cases.

This is a serious application build. Do not stop at a landing page, a beautiful static graph, browser-only persistence, generated mock screenshots, unconnected tabs, or text describing imagined features. Deliver source, migrations, deployable local development configuration, seeded examples, test evidence, and precise remaining limitations. Do not fabricate live model outputs or successful external integrations. The application must be useful when no model provider is configured.

Use the supplied local reference application as an interaction reference if it is present. It is Python/SQLite with local fixtures and limited DAG semantics; it does not settle the production architecture. Preserve useful UI and contracts, but replace development identities, local scheduler, storage, and fixture adapters with production implementations as required. Never deploy that development account switch as production authentication.

Implementation order is P0 core application, P1 intelligent construction/evidence/rehearsal, P2 bounded specialist teams and controlled improvement, then final end-to-end validation. P0 and P1 are required for the first integrated milestone. P2 belongs to the full product goal and must have concrete implementations and tests before being declared complete. Keep a machine-readable feature status with implemented, verified, integration-required, and not-implemented states. A phase boundary is a checkpoint, not permission to stop work.

## B Interface direction and exact interaction model

Design a dense, precise application workspace rather than a generic dashboard. Use a compact global navigation rail, context header, large horizontal workflow canvas, searchable capability palette, and a contextual right workbench. Give the canvas most of the screen. Preserve the same graph positions across Design, Rehearse, and Run. Add a lower dock for validation, test outcomes, or events that can collapse completely.

Visual direction: warm light canvas, deep ink chrome, cobalt for interaction, restrained lime/teal for successful operational states, amber for waiting, and red for failure. Make all colors accessible and themeable. Use a neutral UI typeface and monospace only for IDs, field paths, and payloads. Create a real token system for type, spacing, surfaces, shadows, focus, statuses, and node categories. Avoid decorative gradients, excessive rounded cards, fake metrics, giant empty headings, and glowing network art.

Desktop layout targets: compact 56–72px navigation rail; optional 200–240px workspace drawer; 280–340px contextual inspector; remaining width belongs to the canvas. At narrower widths collapse panels into explicit drawers, preserve full-size labels, and prioritize Tasks/Decision Inbox. The graph viewport can pan/zoom; ordinary application content must not require horizontal scrolling. Test real 1440px and 1280px desktop layouts and 390px task/inbox layouts.

The six primary workspaces are:

| Workspace | Required working interactions |
| --- | --- |
| Studio | Select template, add/drag/connect/configure nodes, map data, undo/redo, validate, compare, propose/apply AI patches, submit release. |
| Agent Registry | Find capability, inspect schema/effects/evidence contract, test, version/configure, inspect consumers, deprecate safely. |
| Runs | Start task, inspect pinned graph, perform permitted manual actions, view evidence/effects/timeline, cancel/recover, export. |
| Decision Inbox | Review template releases and run actions in distinct queues, inspect payload/evidence, approve/reject, send scoped reminders. |
| Rehearsal Lab | Create fixture case, inject failures, compare versions, run suites, inspect final state and invariant failures. |
| Connections | Configure approved adapters/environments, test connectivity, inspect credential identity/scope, revoke access, inspect usage. |

Node cards at working zoom show title, capability/version, gate/owner, side-effect class, and status. Reveal schema ports and mappings when selected or zoomed in. Overview zoom groups stages; never shrink all labels until unreadable. Type-specific icons support text rather than replace it.

Dragging an agent into the empty dotted Step 1 creates an instance and BOTH Next step and Add parallel agent targets. Reusing an agent creates another node instance. Placeholders are not runtime nodes. Provide keyboard insertion/connection and an accessible ordered/table representation. Auto-layout is explicit and undoable; it does not erase a user's careful arrangement while editing.

The right workbench switches among selected-node configuration, AI patch review, role preview, and run action/evidence. Do not permanently stack all of them. Selected-object changes synchronize canvas, outline, inspector, and event focus. Command palette and search should navigate actual objects/actions, not decorative placeholders.

Every button must perform its named action or be disabled with an actionable reason. Every mutation has pending/success/error feedback. Include stale-edit conflicts, disconnected events, empty lists, invalid data, and denied permission states. Motion reflects actual layout/state changes and respects reduced-motion preference.

## C One executable contract

Create a versioned intermediate representation independent of the editor library and runtime engine. Keep business semantics separate from node positions. The same contract powers validation, publishing, execution, simulation, semantic comparison, role preview, and evidence export.

At minimum model:

```typescript
type EffectClass = 'none' | 'read' | 'write';
type EvidenceKind = 'source' | 'extraction' | 'calculation' | 'inference' | 'human';
interface BusinessContract {
  schemaVersion: string;
  id: string;
  outcome: { description: string; ownerId: string; acceptanceCaseIds: string[] };
  requirements: Array<{ id: string; text: string; sourceRef?: string; nodeIds: string[] }>;
  assumptions: Array<{ id: string; text: string; blocking: boolean; resolution?: string }>;
  inputSchemaRef: string;
  graph: ExecutableGraph;
  policies: PolicyBinding[];
  evidenceObligations: EvidenceObligation[];
  budgets: { maxDurationSeconds: number; maxModelTokens: number; maxModelCost?: number; currency?: string };
  pins: { interpreterVersion: string; agentVersions: Record<string,string>; policyVersion: string };
}
interface ChangeProposal {
  id: string;
  baseRevision: number;
  contractId: string;
  provider: string;
  operations: TypedGraphOperation[];
  requirementLinks: Array<{ operationIndex: number; requirementId: string }>;
  assumptions: Array<{ text: string; blocking: boolean }>;
  suggestedScenarioIds: string[];
  validation: ValidationReport;
  expiresAt: string;
}
```

Define every referenced type in a shared contracts package; this sketch is a starting boundary, not a complete schema. Choose a constrained JSON Schema subset and implement assignability for its supported types, required/optional fields, nullability, enums, arrays, and object fields. Reject unsupported schema constructs instead of claiming full JSON Schema theorem proving. Persist schema versions and migration rules.

Bind graph edits to expected revision. An AI patch, manual edit, imported template, or reusable block insertion all use the same validated transaction. Publication freezes resolved defaults, compiled plan, agent versions, policies, schemas, assumptions, and graph hash. Layout changes produce a layout diff; behavior changes produce a semantic diff.

## D AI outcome compiler

Implement a provider-neutral planning pipeline:

1. Resolve the user's current workspace, allowed capabilities, published templates, connection metadata, and known requirements.
2. Retrieve only relevant schema/description metadata permitted for that user. Never place secret values into prompts.
3. Generate a typed ChangeProposal, with no arbitrary code and no direct execution rights.
4. Validate syntax, schema, graph structure, mappings, policy compatibility, budgets, and referenced IDs deterministically.
5. Permit a bounded correction attempt using the concrete validation errors, then stop with an inspectable unresolved issue if still invalid.
6. Display the exact graph/field diff, assumptions, affected policies, and suggested scenarios.
7. Apply only after an authorized user accepts it against the same base revision. Changed context requires revalidation.

Supported operations initially include add node, remove draft node, update allowed config, bind field, add/remove permitted edge, insert approval, create structured parallel branch, and replace an approved capability with another eligible version. The planner cannot create credentials, grant roles, change egress policy, suppress audit, publish a release, or silently execute a task.

Intent examples must work: add a reviewer before a ticket write; parallelize two independent reads; make a step manual for Contributors; add an enrichment capability; change a timeout within policy; explain why a graph cannot publish. For unknown or underspecified intent, show the unresolved assumption and offer concrete choices rather than inventing business policy.

Use an explicit planner state label: local deterministic planner, configured model/provider, or unavailable. Show actual usage when observed and unknown when not. Do not invent confidence percentages. Keep a local deterministic mode for demos and tests, visibly labeled; it is not evidence of LLM capability.

A Find a template task-entry assistant is separate from graph generation. It searches only templates the user may start, explains the match, and invokes ordinary form/permission validation after selection. It does not invent template IDs or automatically perform side effects.

## E Formal checks with honest scope

The first graph language is a bounded structured DAG with explicit sequence, condition/merge, parallel split/join, manual start, approval, outcome, and end. Bounded specialist loops remain inside declared team nodes; do not introduce arbitrary graph cycles until their semantics and limits are implemented.

Define protected writes and check that each applicable path reaches a required approval gate before the write. Use graph dominance/control-flow analysis within the restricted language, plus predicate-aware checks where explicitly supported. For dynamic targets or conditional authority, enforce a dispatch-time check even if the graph passes static validation. Display the specific property checked: for example, all protected writes have a prior approval gate. Never label the workflow universally safe or formally proven correct.

Reject invalid branch crossings, unresolved required fields, incompatible mappings, missing default branches, stale capability versions, unapproved connections, unreachable required work, duplicate IDs, unbounded resource use, and unresolved blocking assumptions at publication. Store the validator/compiler version with each release.

Add policy fixtures that intentionally remove an approval, change a role, create an alternative bypass path, or move a sensitive output to an unauthorized sink. Verify server rejection through direct API calls. Models must not be the authority for structural or permission decisions.

## F Bounded specialist teams

Implement a TeamRecipe registry alongside ordinary agents. A recipe defines participant roles, allowed tools and data scopes, deliverable schemas, delegation rules, maximum turns, token/time/cost budgets, and stopping conditions. Start with executor/researcher/reviewer roles only where the work needs them.

The coordinator is deterministic infrastructure. Model suggestions may select from an approved recipe's eligible roles, but cannot recruit arbitrary tools or broaden access. Use explicit structured messages and shared artifact references. Store concise decisions and objections, not hidden chain-of-thought. Display who produced which deliverable and which evidence supports it.

Only one designated commit actor can reserve and dispatch a consequential action ID. Team members may draft alternatives; they cannot independently send the same ticket/email. Treat reviewer agreement as a signal to evaluate, not independent proof of truth.

Create a single-agent baseline using the same model/tool budget. Compare it with fixed and adaptive recipes on held-out cases. Require measured outcome improvement at an acceptable cost/latency tradeoff before enabling a recipe by default. No assumption that more agents are better.

## G Evidence graph and decision packets

Implement SourceSnapshot, EvidenceItem, Claim, Transformation, DecisionPacket, and ActionReceipt as first-class records. Each evidence item includes ID, kind, source/version/hash, field path or excerpt span, observed time, access label, producer version, and links to transformations. Derived records inherit appropriate access restrictions.

A claim links to supporting and conflicting evidence. Validate references, excerpt boundaries, and deterministic fields such as IDs/amounts/dates. Model-based support checks are labeled evaluations and cannot replace deterministic validation. Keep unsupported assertions visible; do not fill missing facts with plausible text.

The Evidence Lens lets a user click a mapping, output, condition, or recommendation to inspect its lineage. A decision summary is generated from recorded public artifacts and events, with links to sources. It must not fabricate an explanation after the fact or expose private model reasoning.

An approval packet contains exact action target/payload, observed evidence, policy obligations, remaining uncertainty, expiration, and what approval unlocks. Fingerprint the protected action inputs and version. A modified protected payload invalidates the approval; current eligibility is checked at submission and dispatch. Two competing approvers produce one effective outcome.

Keep two hashes distinct. The stable actionFingerprint includes workspace, run/node/action generation, canonical payload, method, destination/resource, and connection/environment identity. The approvalEnvelopeHash binds that action fingerprint to policy version, evidence snapshot, reviewer scope, and expiry. Rebinding a connection to another destination changes the action and requires fresh approval. Reject reuse of an operation key with a different actionFingerprint. Renewing approval for the same action must preserve its operation identity; an expiry change alone must not create a second external write.

For an agent that generates a consequential tool call dynamically, a gate before the agent starts cannot approve arguments that do not yet exist. Implement prepare -> approve -> commit: the agent proposes a validated immutable action payload, the reviewer approves its fingerprint, and the adapter commits exactly that payload. Intercept every protected tool call at this boundary. The per-agent Approval required setting compiles to this action gate for dynamic writers; for a deterministic writer whose final payload is already resolved, it can appear immediately before execution. Explain the scope in the UI. Template publication never authorizes arbitrary future tool calls.

Runtime inspector actions come from a server allowed-actions response with reasons. Manual Execute, Approve/Reject, and Reminder are distinct. Preview role experience is read-only policy inspection, never authentication as another person. Corporate identity mapping belongs behind a verified OIDC/directory integration.

## H Scenario laboratory and release experiments

Create a versioned Scenario with initial fixture state, input manifest, graph/policy/adapter/model pins, injected events, simulated human decisions, expected final state, and invariant assertions. Expose a table of cases and a case-detail timeline/graph. Expected outcomes are explicit, never inferred as passing merely because a run completed.

Required scenarios: happy path; missing input; dependency timeout; approval rejection; approval expiry; revoked role; duplicate callback; conflicting evidence; write accepted but acknowledgement lost; malicious instructions in external content. All run in isolated mode with no production write credentials or egress.

Provide three clearly distinct commands: inspect history, replay recorded outputs in isolation, and re-execute a sandbox case. The third may call a configured model and incur cost; require appropriate budget and show its mode. A model-emulated API is an optional approximate fixture, not a substitute for known-answer deterministic tests.

A suite records actual paths, attempted effects, final fixture state, observed costs/latency, deterministic invariant results, and labeled evaluator results. Store failures as reusable regression cases. Run repeated trials for stochastic steps and report per-run success and all-trials-success per case; show counts and uncertainty. Do not manufacture a single quality score.

Version comparison uses paired scenarios. A candidate that lowers cost but violates a permission or duplicates an external action cannot pass a release gate. Use held-out cases for model/prompt/team changes and preserve the evaluator version. Promotion changes future runs only. Read-only shadow mode must use isolated effect adapters; the word shadow does not authorize duplicate production writes.

## I Effect ledger and repair

Implement a ledger per logical external operation. Record prepared, dispatched, acknowledged, unknown, reconciled, and compensated states as applicable. Stable operation identity survives worker/activity retries and safe operator recovery. Downstream idempotency support or an explicit reconciliation contract is required for safe write recovery; a local database row cannot close every remote failure window.

The Recovery Workbench shows what already changed, what is still pending, what is uncertain, and which actions are actually available. RepairProposal uses an allowlist: retry safe operation, reconcile known operation, select approved fallback, create mapping/config correction in a new draft, or request human investigation. No arbitrary repair script.

A model may draft a diagnosis and proposal from redacted evidence. Deterministic capability rules decide whether it is executable. Revalidate and rehearse the affected scenario. Bind acceptance to graph revision, run state, action IDs, and payload fingerprint. A stale proposal cannot execute.

Unknown write outcome means reconcile first. Do not label retry, compensation, cancellation, and new run as equivalents. Compensation is a new externally visible action with its own authority/evidence. Historical runs remain immutable even when a repair inspires a new template release.

Include the critical test: fixture ticket write commits, acknowledgement is lost, worker restarts, recovery finds or idempotently reuses the same ticket, and downstream state contains one ticket. Then run the same experiment against an adapter without idempotency/reconciliation and verify the system refuses automatic retry.

## J Reusable blocks connectors and developer experience

Provide versioned insertion blocks with explicit boundary inputs/outputs. Inserting a block expands independent node instances with fresh IDs and source provenance. Updating the source block never mutates already published templates. Shared executable sub-workflows are a separate feature with their own pins and lifecycle.

Developers register versioned capabilities through an SDK manifest. The manifest declares schemas, effect classes, authentication requirements, retry/reconcile/compensation support, evidence outputs, fixtures, and resource limits. Add a scaffolding command that produces a manifest, implementation skeleton, known-answer fixture, and contract test. Runtime validates both inputs and outputs.

Support approved HTTP/OpenAPI adapters first. Add MCP through explicit tool discovery approval, schema pinning, per-tool scopes, and server-side authorization. Tool metadata is untrusted input; a changed server tool requires review before expanded authority. Do not imply MCP itself solves identity or permission policy.

OCI authentication must use the appropriate official SDK method and server-side secret/principal configuration. Jira and CSR require actual service contracts. Keep customer-specific adapters isolated from the company-neutral domain. Never mislabel local fixture records as live external records.

Provide local development observability, health/readiness, typed errors, correlation IDs, connector contract tests, and a reproducible seed/scenario runner. Do not require a paid developer account to run the base application.

## K System architecture and implementation boundaries

Use one canonical durable execution authority. The greenfield production recommendation is React/TypeScript, custom React Flow core nodes/edges or an equivalent owned canvas layer, a modular TypeScript API, PostgreSQL, artifact storage, and self-hosted Temporal. Validate current licenses and supported versions. If an existing substantial application has a different stack, integrate instead of rebuilding it gratuitously.

Keep modules for contracts, graph compiler, policy, agent SDK, model gateway, evidence, scenarios, effects/recovery, releases, and UI. Use one API application initially and separate workers. A bounded specialist runtime executes inside the durable authority; it is not a competing queue/scheduler. Avoid infrastructure proliferation without a demonstrated need.

Give each consequential tool call within a specialist team its own durable boundary or an explicitly tested checkpoint/reservation protocol. Retrying a whole team Activity must not rerun already committed internal actions. The designated commit actor coordinates authority but is not, by itself, a durability mechanism.

Use an outbox for database-to-runtime commands and idempotent receivers. Persist run-event projections and reconcile them after missed delivery. SSE/WebSocket reconnect must restore missed events. A UI timer may animate transitions but cannot determine actual progress.

Pin graph, agent, policy, schema, model/prompt, and interpreter versions where relevant. Record provider responses for replay. Maintain compatible workers or an explicit versioning/patching strategy for active workflows. Keep secrets and large document bodies out of execution histories; protect sensitive payloads and storage.

Every tenant-scoped object is authorized server-side, including evidence, exports, live event subscriptions, model retrieval context, and connection references. The local reference's permissive development session must fail closed in a production profile. Rate limits and budget checks run before costly dispatch; cancellation is propagated where supported.

## L Delivery stages and demonstrable completion

Implement P0: authentic identities/roles, registry, interactive editor, persisted drafts, graph validation, exact-snapshot review/publication, template-selected tasks/uploads, actual durable execution, manual gates, human approval, reminders, evidence outputs, safe cancellation/retry, and a coherent interface.

The minimum effect ledger and prepared-action approval binding are P0 infrastructure because P0 includes external writes and recovery. P1 adds richer evidence navigation, diagnosis, repair proposals, and scenario comparison over those records.

Implement P1: typed AI patch pipeline, requirement/assumption links, role preview, evidence lens, effect ledger, isolated scenario suite, semantic version review, recovery proposals, and regression-case capture. Provide a configured-model adapter and deterministic fixtures for repeatable tests. Do not claim live-model quality if credentials/provider tests are unavailable.

Implement P2: bounded team recipes with single-agent baselines; versioned block insertion; permission-filtered template finder; agent-version impact analysis; paired model/prompt/workflow release experiments; environment promotion through reviewed connection rebinding. Shared sub-workflow execution and arbitrary graph loops are outside the initial graph language unless separately specified and verified.

The final demonstration must cover both the exact CSR-to-Jira meeting example and an unrelated business process reusing capabilities. It should show AI graph patch review, a policy error caught before publication, a failed rehearsal that becomes a regression, reviewer publication, manual execution, approval evidence, worker restart, safe effect recovery, and preserved version history.

Verification includes meaningful compiler/policy unit tests, database/runtime integration tests, connector contract tests, browser journeys, keyboard/accessibility checks, screenshots at realistic widths, and controlled failure injection. Measure large-graph render/edit performance and runtime load with stated environment and limits. Do not declare scale or an SLA without measurements.

Maintain a feature completion matrix and docs/IMPLEMENTATION_STATUS.md throughout. On a genuine tool/network/credential blocker, finish independent work and state exactly what remains unverified. Do not silently substitute mock state for missing functionality. If interrupted by a session limit, leave a runnable checkpoint and precise continuation tasks; resume rather than calling the project finished.

These gates supplement and take precedence over the inherited milestone table below:

| Release gate | Required demonstration |
| --- | --- |
| P0 actions | A dynamically prepared payload is approved and committed unchanged; altered arguments require fresh approval; denied actor cannot dispatch. |
| P0 effect authority | Connection rebinding, revoked permission before dispatch, duplicate operation key with a different payload, and competing recovery commands produce zero unauthorized effects, not merely an API error. |
| P1 planner | Malformed, stale, unauthorized, or unknown-reference model proposals fail server validation; accepted proposal remains editable/undoable and links to requirements. |
| P1 evidence | Missing/contradictory evidence stays visible; cross-scope evidence/export access fails; recorded claims link to real source spans. |
| P1 rehearsal | Known-answer scenario suites compare expected final state with actual fixture state; all rehearsal writes remain isolated. |
| P1 recovery | Unknown write outcome requires reconciliation; a repair proposal with stale run state cannot apply; regression case is saved. |
| P2 teams | Recipe budgets stop work; tool scopes cannot expand; one commit actor owns an action; matched-budget single-agent baseline is reported. |
| P2 reuse | Block insertion creates fresh instance IDs and pins provenance; changing the source block leaves existing releases untouched. |
| P2 release | Paired held-out cases expose a seeded regression and block promotion; future starts select the promoted version while active runs retain their pins. |

Add explicit API/resources and migrations for contracts/requirements, proposals/apply, evidence/claims, prepared actions/decisions/effects, scenarios/suites/results, repairs, team recipes, blocks, and release experiments. Do not squeeze these into arbitrary JSON blobs without validated schemas and authorization boundaries.

## M Research foundations and evidence discipline

Use these primary sources as design foundations, not imported performance promises:

- [Constrained structured generation](https://arxiv.org/abs/2109.05093)
- [Dependency-aware tool planning](https://arxiv.org/abs/2312.04511)
- [Programmable multi-agent collaboration](https://arxiv.org/abs/2308.08155)
- [Multi-agent failure taxonomy](https://arxiv.org/abs/2503.13657)
- [Provenance model](https://www.w3.org/TR/prov-dm/Overview.html)
- [Retrieval-supported attribution](https://arxiv.org/abs/2210.08726)
- [Tool-environment risk testing](https://arxiv.org/abs/2309.15817)
- [Outcome and repeated-trial evaluation](https://arxiv.org/abs/2406.12045)
- [Prompt-injection evaluation](https://arxiv.org/abs/2406.13352)
- [Policy schema validation](https://docs.cedarpolicy.com/policies/validation.html)

Track each proposed advantage as a measurable hypothesis: authoring time/correction rate; reviewer comprehension; seeded regression detection; duplicate side effects; time to diagnose; and team outcome success at matched budget. Separate product targets from achieved results. No claim of universal superiority, unique invention, formal business correctness, or production readiness without the appropriate evidence.

The detailed meeting-derived implementation contract follows. All requirements remain applicable. Where an older scope label calls a feature later or optional, the P0/P1/P2 requirements above define the expanded product target. Current verified status must remain honest.

---

You are the lead product engineer, workflow systems architect, and product designer for this implementation. Build a complete, working, company-neutral platform for configuring reusable agents, designing governed workflow templates, and running tasks through those templates. Deliver implementation, migrations, seed data, verification, and run instructions. Do not stop at a plan, static screens, or a canvas with simulated production execution.

## 1 Product objective and constraints

Developers supply executable agent implementations. Administrators configure reusable agents and compose templates visually. Reviewers approve template releases. Contributors start tasks from published templates. Human assignees complete approval gates. Operators investigate execution and recover safely from failures.

The core experience is one workflow canvas in three modes: Design, Simulate, and Run. Users should recognize the same steps and layout in each mode. An agent means a reusable executable capability; it can be deterministic application logic, an API adapter, or an optional AI capability. It does not imply an LLM everywhere.

Build our application, user experience, domain model, validation, permissions, and governance in-house. Use permissively licensed infrastructure where appropriate. No required paid enterprise edition, paid canvas feature, mandatory SaaS workflow engine, proprietary designer, paid icon set, or required model API subscription. Operating infrastructure and optional external services can still cost money. Keep the product complete without an AI provider.

Do not hardcode MUFG, banking language, customer branding, Oracle credentials, or a specific industry. Use supplier onboarding as a demonstration domain and the meeting's CSR to Jira example with local fixture adapters to prove reuse.

Meeting requirements to preserve:

- Main sections: Workflow templates, Agents, and Tasks or Upload and run tasks.
- Agent list and new-agent configuration with name, type, configuration, edit, and delete/deprecate.
- Admin drag-and-drop templates with sequential and parallel agents, automatic insertion targets, and a right settings pane when selecting a node.
- Multiple instances of the same agent and multiple agents within a parallel stage.
- Template name and configuration, draft/review/publication, template selection during task creation, uploads, live statuses, and manual approvals.
- Role-controlled human actions and execution configuration.
- Future reusable blocks are an extension, not a reason to leave the core unfinished.

The supplied transcript clarifies that the discussion was about OCI keys, not the OCA wording in the earlier summary. Provide an OCI connection/authentication adapter boundary using official SDK authentication mechanisms; never treat an OCI signing key as a generic bearer token. Resolve private keys through server-side secret references and use an appropriate deployed principal when available. Test with fixtures until the actual OCI service, tenancy permissions, and credentials are supplied. Do not invent Oracle approval or a live integration. Preserve CSR as the meeting's named capability until its precise service contract is confirmed.

The existing application uses a Mermaid view that cannot support the requested editing. Replace or integrate that view with a genuine interactive designer; Mermaid is acceptable for architecture documentation, not the product's editable canvas. Venkat explicitly asked for an enterprise product rather than a throwaway POC and rejected n8n as the chosen foundation. Do not embed n8n or make it a runtime dependency.

## 2 Start by inspecting the repository

Read applicable AGENTS.md and project instructions. Inspect the actual frontend, backend, authentication, database, tests, package manager, deployment files, and design system. Preserve user changes and integrate with the existing stack when it is substantive. Do not replace an existing application merely to match these defaults.

If greenfield, use this default stack:

- TypeScript monorepo using pnpm workspaces with a committed lockfile.
- Web: React, Vite, React Router, React Flow core, TanStack Query, a small UI state store, accessible Radix-based primitives, and CSS design tokens. Use a form library with JSON Schema-aware validation. Do not duplicate server state in a global store.
- API: NestJS modular application, PostgreSQL, Prisma migrations, OpenAPI contracts, and strict DTO validation.
- Runtime: self-hosted Temporal with the TypeScript SDK and a separate worker process. Build a versioned interpreter for validated workflow definitions. Do not build a second durable job scheduler.
- Identity: OIDC adapter and a Keycloak local profile for real identity testing; application-owned workspace permissions. A strictly local development profile may use seeded users with real server sessions. Production must refuse development authentication.
- Files: ArtifactStore interface; local persisted volume for development and a documented S3-compatible adapter boundary for deployment. No mandatory commercial object store.
- Events: persisted run-event projections streamed through authenticated SSE with reconnect cursors.
- Quality: unit tests for workflow/policy logic, database/runtime integration tests, and Playwright for the principal user journeys.
- Local startup: Docker Compose with health checks, persistent database and Temporal storage, API, worker, web, and deterministic fixture connector. Clearly separate development service configuration from production deployment.

Use supported mutually compatible dependency versions verified from official sources during implementation. Pin images and packages; avoid floating latest tags. Keep a dependency and license inventory. React Flow core and Temporal server are MIT licensed. Use only core capabilities covered by the chosen licenses; do not copy paid examples. If an existing Java/Spring system or a firm BPMN requirement makes Flowable OSS a better fit, document that decision and implement one engine consistently. Do not combine Temporal and Flowable.

Suggested greenfield modules:

```text
apps/web
apps/api
apps/worker
packages/contracts
packages/workflow-domain
packages/agent-sdk
packages/ui
services/fixture-connector
infra
docs
```

Use a modular monolith API and separate runtime workers. Do not introduce Kafka, Kubernetes, microservices per feature, or an additional queue without a demonstrated requirement.

Create docs/IMPLEMENTATION_PLAN.md with milestones and docs/DECISIONS.md with brief architecture decisions. Then implement immediately. Use safe defaults for reversible choices. Ask only when a missing fact materially blocks correctness or an external action requires authorization. Do not deploy publicly, contact people, or invoke real third-party write operations merely to demonstrate a feature.

## 3 Product screens and interaction quality

Create a coherent desktop application with a restrained light theme, optional dark theme, neutral surfaces, one accent, readable typography, an 8px spacing rhythm, and consistent status vocabulary. Use real content, concise labels, and proportionate information density. Avoid oversized dashboard cards, decorative charts, glowing connectors, and gratuitous AI branding.

Global navigation: Templates, Agents, Tasks, My work, and Administration. An overview may summarize real data and link to the matching records. Show the active workspace and signed-in person. Put developer details in expandable inspection areas, not in ordinary business flows.

### Agent catalog and configuration

Catalog supports search, type/status filters, visible stable Agent ID, owner, version, last test result, and where-used information. Show the created Agent ID after creation. Provide genuine empty, loading, error, and permission-denied states.

New agent has guided sections: identity, registered implementation, schema/configuration, connection and permissions, test, and save. Agent defaults and template-specific overrides are separate. Developers register implementation manifests through code/SDK; administrators configure instances through the UI. Never allow an administrator to paste arbitrary server-side JavaScript or Python into a form.

An agent details screen shows schemas, configuration, versions, owner, deprecation, consuming templates, and fixture test results. Delete only unreferenced drafts. Deprecate referenced versions and block new use where appropriate; preserve historical runs. Revocation of a connection or implementation must surface as a blocked dispatch with an operator-readable reason, not quietly continue because a template pinned an old version.

### Template library

Show name, stable Template ID, lifecycle, published version, draft owner, last change, and number of associated tasks. Actions: create, duplicate, edit draft, compare, submit for review, publish when eligible, archive, export, and validated import. A template can have a published version and a separate draft simultaneously.

Use server autosave with debounce and revision/ETag conflict protection. Show Saving, Saved, Offline or Failed, and Conflict distinctly. Never overwrite another edit silently. Unpublished drafts may be incomplete. Publication must pass server validation.

### Workflow designer

Left: searchable agent and control palette. Center: canvas. Right: inspector. Top: name, current version/lifecycle, save state, validation, Simulate, Submit for review or Publish according to role. Bottom: collapsible validation/results panel.

Support drag from the palette, click-to-add as a keyboard-accessible alternative, insertion on an edge, sequential next-step drop targets, and add-parallel-branch targets. Each successful agent drop produces one actual node with a unique instance ID, then shows BOTH a dotted Next step target and an Add parallel agent target. Unfilled dotted targets are editor affordances, not executable nodes. Permit another instance of the same agent. Define parallel placement relative to the selected stage explicitly; do not guess dependencies from screen coordinates.

Provide select, move, connect allowed ports, remove with dependency warning, duplicate, undo/redo, zoom, fit, and auto-layout. Preserve manually arranged positions; auto-layout is explicit. Use Dagre initially if it covers the supported graph structure. Use a layout library; do not assume React Flow has an automatic layout engine.

Node cards show title, agent type/version, execution mode or required role, and validation or runtime state. Inspector tabs: General, Inputs, Connection, Access, Reliability, and Test as relevant. Invalid connections explain the reason immediately; the server repeats all validation.

On each Agent instance expose Execution mode (Automatic or Manual start), Allowed executor roles, Approval required (Yes/No), and Approver roles when Yes. These are independent fields. Default to automatic execution with no extra approval, subject to mandatory workspace policy. Approval gates bind prepared actions as defined in section G. For a deterministic writer with resolved arguments, the gate can appear immediately before execution. For a dynamic AI writer, preparation may run first, but the consequential call must pause for approval of its exact arguments. Manual Execute authorizes the eligible executor to start or resume the permitted phase; it never authorizes bypassing a protected action gate. An explicit Approval control node may represent the same gate and must not accidentally create a duplicate. Approval alone does not satisfy a separate manual-start requirement. Preserve dependency and version checks at both preparation and commit.

For automatic nodes, treat allowed executor roles as the initiating user's delegated authorization and recheck it before dispatch, separately from the automation service principal's connection permission. If long-lived service-owned tasks are later supported, require an explicit delegated policy instead of silently inheriting an absent user's rights. For manual nodes, evaluate the currently authenticated executor. Explain these identities in configuration help.

Add a read-only Preview role experience in Design mode: show which configured role could view, execute, approve, or send reminders at each node, and identify steps with no eligible role. This is policy inspection, never impersonation. In Run mode use a server-returned allowedActions contract to render actual permitted actions and denial reasons; reauthorize every submitted action.

Input mapping uses a searchable picker of available upstream outputs with data types and sample values. Display sources such as task.supplierName or extract.supplier.name in readable chips. Store typed references, not evaluated JavaScript strings. Show required, optional, missing, and sensitive fields clearly. Only permit mappings that exist on every applicable execution path, or require an explicit fallback/optional schema.

Publish validation errors must name the exact node/field and focus it when selected. An accessible ordered workflow outline exposes selection, insertion, configuration, and statuses without requiring pointer dragging.

### Tasks and live execution

Create task: select a published template version, render its schema-driven input form, upload allowed files, inspect required roles/connections, then start. A start confirmation identifies any real external writes. Do not silently use a draft or the latest unapproved version.

Task detail combines a business summary, the exact pinned workflow, a timeline, outputs/artifacts, and the next required human action. Run view uses server events; it must never simulate real progress with frontend timers. Show branch states, attempt counts, elapsed time, retry countdown, and blockers. A node explains its inputs, outputs, redacted error, and why it is waiting. Keep raw logs behind an inspector tab.

Users can reconnect or refresh without losing progress. If the projection is stale, display its last-update time and a reconnecting state; do not report completion from an animation. Cancel means request cancellation; it becomes cancelled only after runtime acknowledgement. Never describe cancellation as undoing external effects.

For a ready manual step, show Execute only to an eligible executor and repeat authorization server-side. Display the unmet dependency or approval when not ready. Persist and deduplicate execute requests through the outbox. On a pending approval node, the right inspector provides Send reminder: preview eligible recipients/message, then enqueue through a Notification adapter. Use an actual local SMTP capture service in development and label captured messages; do not send external emails by default. Track queued/sent/failed states, rate-limit reminders, audit the initiator, and deduplicate delivery according to the provider contract. Recipients come from eligible workspace identities, never arbitrary addresses in uploaded content. Email contains an authenticated deep link to the approval page; opening a GET link cannot approve. Expose that page in-app without requiring a popup or headless browser.

### My work

List eligible approval/manual tasks with requester, workflow, age, due time, and current owner. An approval detail shows evidence, proposed action, relevant checks, and approve/reject with comment. Require a comment for rejection. Enforce separation of duties where configured. Repeated or competing submissions produce one decision, with a clear already-decided response to later callers.

Template review and runtime approval are separate experiences and entities. For v1 runtime approval supports approve, reject, and expiry; rejection ends the run as rejected. Request-changes loops are later work and must not appear as enabled buttons until implemented.

### Administration

Manage workspace memberships, role grants, connection metadata and secret references, agent revocation/deprecation, and audit search. A user must never retrieve secret values through the API, export, inspector, or logs. Provide authorized connection testing with redacted results.

Make the main designer usable at normal laptop widths; collapse the palette/inspector on smaller widths. Tasks and My work should work well on mobile. Use keyboard navigation, visible focus, dialog focus management, accessible names, reduced-motion support, and text/icons alongside status colors. Target WCAG 2.2 AA; verify the principal flows rather than merely claiming conformance.

## 4 Domain model and invariants

Implement these concepts distinctly, with migrations and indexes:

| Entity | Responsibility |
| --- | --- |
| Workspace and Membership | Scope ownership and assign current roles; every domain resource has workspace scope. |
| AgentDefinition | Stable reusable catalog identity, owner, type, lifecycle. |
| AgentVersion | Immutable implementation key/version, input/output/config schemas, supported adapter capabilities, defaults, and content hash. |
| Connection and SecretReference | Workspace-scoped endpoint metadata and a reference to credentials; not plaintext secrets in graph JSON. |
| WorkflowTemplate | Stable template identity and selected active published version. |
| TemplateDraft | Editable graph, revision, metadata, input schema, and UI layout. |
| TemplateVersion | Immutable canonical execution graph, compiled plan, node-level resolved config, agent pins, policy snapshot, layout snapshot, interpreter version, and content hash. |
| TemplateReview | Exact submitted snapshot hash, author, eligible reviewer, outcome, comment, and timestamps. |
| Task | Business request, requester, input manifest, attachments, and chosen template version. |
| WorkflowRun | Durable runtime identifier and product projection; links to task and pinned versions. |
| NodeExecution and NodeAttempt | Logical node state versus each actual attempt, timings, operation key, and output references. |
| ApprovalRequest and ApprovalDecision | Gate, eligibility policy, evidence/input hash, expiry, current state, immutable final decision, and delivery/application state. |
| Artifact | Scoped storage key, content hash, size, verified type, scan state, retention metadata, and provenance. |
| RunEvent | Redacted inspectable timeline event, deduplication ID, and per-run monotonic cursor. |
| AuditEvent | Actor, action, target, redacted change summary, correlation ID, and timestamp. |
| OutboxCommand | Durable, idempotently delivered runtime start/manual-execute/approval/cancel/retry command. |
| NotificationDelivery | Reminder request, scoped recipients, delivery state, provider correlation, and deduplication key. |

Use foreign keys and composite workspace constraints where feasible, plus authorization in repositories/services. Include tests for cross-workspace resource IDs, files, SSE subscriptions, and connection references. A workspace identifier from a client does not itself confer access.

Separate execution JSON from editor layout. Canonical hashing excludes incidental edit timestamps and positions when computing semantic execution differences, while the published layout is retained for the Run view. Defaults must be resolved into the published snapshot so changing an agent default cannot change an existing run.

The starter/initiator, a human approver, and an automation service principal are different identities. All three are represented explicitly. Store UTC timestamps; display the user's selected timezone. Paginate list APIs and index workspace/status/created-time queries.

## 5 Permissions and lifecycle

Use capability checks rather than scattered role-name comparisons. Seed roles with these starting capabilities:

| Role | Default scope |
| --- | --- |
| Developer | Register and test implementation versions in authorized workspaces. |
| Workflow administrator | Configure agents and connections, author templates, submit releases. |
| Template reviewer | Review and publish eligible exact snapshots; cannot approve their own submission under the default policy. |
| Contributor | Start allowed published templates and see permitted tasks. |
| Human approver | Decide assigned/eligible runtime approval gates. |
| Operator | Inspect permitted runs, request allowed cancellation/recovery. |
| Auditor | Read permitted history without mutation privileges. |

People may have multiple roles, but separation-of-duties rules still apply. Avoid a production role-switch control. Demo accounts are distinct authenticated users; show development mode explicitly. OIDC establishes identity, while the application enforces permissions on every API/action.

Template review: draft -> submitted snapshot -> approved and published, or rejected. Editing after submission creates a new draft revision and invalidates its eligibility for the previous approval. A publish operation must compare the approved content hash with the version being published atomically. Published versions are immutable. Archive blocks new starts, not reads of existing runs. Changing the active published version affects future tasks only.

Record the policy version at start for explanation, but current revocations take precedence. Recheck workspace/role/connection permission before a human decision or privileged activity dispatch. If an identity loses access while a run waits, block or reassign through an audited action. Do not leave an in-flight remote call described as automatically reversible after access changes.

## 6 Workflow semantics before execution

V1 is a bounded, structured directed acyclic graph with exactly one Start and one End. Support Agent, Condition with explicit merge, Parallel split with matching Join, Human approval, Outcome, and optional bounded Delay. Outcome declares terminal business rejection with a reason, closes active scopes without executing successors, and finalizes through the single End once active work settles. End is a finalization point, not an all-predecessors-success join. No arbitrary cycles, dynamic code, unconstrained loops, first-wins races, or implicit merges.

Allow structured nesting with clear paired branch/merge nodes. Reject crossing branch boundaries that cannot be compiled safely. An explicit graph compiler produces a small versioned execution plan containing Sequence, Agent, ManualStartGate, Decision, Parallel, Approval, Outcome, and End constructs. Do not create a new deployed Temporal workflow implementation per customer template.

- Sequence executes the next node after its predecessor succeeds.
- Parallel starts all declared branches with bounded concurrency and waits for all to succeed before its paired join. Outputs are namespaced by node ID; branches cannot race to overwrite shared values.
- After a branch failure exhausts automatic retries, let already-dispatched siblings settle, retain their results, block new downstream work, and enter needs_attention. Document this policy in UI and tests. Cancellation is an explicit separate command.
- Condition evaluates a validated, deterministic typed rule and chooses exactly one branch; require a default outcome. Nonselected nodes are marked skipped. Its merge waits only for the selected branch, so unselected branches never cause a deadlock.
- Conditions use a limited rule AST supporting equality, typed comparison, exists, and/or/not with complexity/depth limits. No eval, arbitrary expressions, scripts, or network lookups inside conditions.
- Approval waits durably for an eligible recorded decision or timer. Approve continues; reject ends as rejected; expiry ends as expired in v1. Retries never turn rejection into approval.
- End reports completion only after required activated nodes succeed and no unresolved approval remains.

A terminal rejection, expiry, unrecoverable failure, or acknowledged cancellation stops new dispatch and invalidates remaining human gates. Request cancellation of cancellable active work, retain completed external effects, and wait for acknowledgements or bounded activity timeouts. If an external result remains ambiguous, expose needs_attention with the recorded intended terminal outcome until reconciled. First terminal intent accepted by the runtime's deterministic ordered state machine wins; later errors/cancellation requests are recorded without overwriting it. Do not claim fair wall-clock ordering across concurrent requests.

Publish validation rejects cycles, duplicate IDs, unsupported versions/types, unreachable executable nodes, dangling edges, mismatched splits/joins, missing condition defaults, invalid port cardinality, absent schemas/config, unavailable or forbidden agent versions, missing role grants, invalid connection references, and mappings unavailable on a selected path. Partial drafts can save with errors; published templates cannot.

Set configurable initial bounds, for example 50 executable nodes, nesting depth 5, and external concurrency 4. These are initial implementation limits, not measured capacity promises. Show actionable errors for limits and benchmark supported workloads before raising them.

## 7 Durable runtime and recovery

Temporal is the execution authority. Application tables are domain records and query projections, not another scheduler. Deterministic workflow code orchestrates; Activities perform I/O, database interaction, secrets resolution, file access, HTTP calls, and optional model calls. Never read wall-clock time, uncontrolled randomness, environment configuration, or external state directly in workflow logic.

At start, pin template version, agent versions, interpreter version, policy snapshot, input manifest hashes, and resolved non-secret configuration. Use a compact immutable plan and artifact references. Put document bodies and large outputs in artifact storage. Secrets must never enter Temporal history. Use deployment payload protection for sensitive metadata and audit access to history.

Implement reliable API-to-runtime delivery:

1. A database transaction persists the Task/Run or approval decision plus an OutboxCommand.
2. A dispatcher delivers it to Temporal using deterministic workflow/command IDs and retries safe delivery.
3. The receiver deduplicates commands; reconciliation repairs missing acknowledgements/projections.
4. The UI distinguishes command accepted, runtime applied, and terminal outcome.

Do not claim a database transaction and a Temporal signal are atomic. Each gate has exactly one effective transition from pending to approved, rejected, or expired in deterministic runtime processing. Temporal's ordered processing of the decision command versus durable expiry event is execution authority. Document and test the handler/timer ordering rule when both arrive in one workflow task. The API records a submission pending application; only runtime acknowledgement makes it effective. If expiry wins, record a later submission as not applied. A database commit before the deadline does not guarantee delivery before expiry. Use generation/approval IDs so old decisions cannot satisfy another gate. Test repeated delivery.

Persist projection events idempotently with stable event IDs. SSE supports Last-Event-ID/cursor replay, scoped authorization, retention-aware resynchronization, and reconnect. A repair job can reconcile product projections with runtime state. The browser cannot schedule agents.

Classify errors: validation, authorization, revoked credential, and permanent business rejection are not automatically retried; transient network/rate-limit failures may retry within configured attempts and total duration. Respect Retry-After when supported. Configure per-agent execution timeouts, heartbeat/cancellation for long activities, bounded concurrency, and retry budgets. Default example: at most three automatic attempts with capped backoff, configurable by policy.

Use a stable side-effect operation key derived from workspace, run, logical node, and operation generation. Keep it stable across activity and operator retries of the same intended action. Prefer downstream idempotency support. For systems without it, require reconciliation or mark an ambiguous result needs_attention; never blindly repeat a write after an unknown outcome. A local ledger alone cannot guarantee exactly-once remote effects.

Distinguish three actions:

- Runtime history replay reconstructs state using recorded activity outcomes; it is not a request to repeat external writes.
- Retry failed step reuses the same run and operation identity, only where the adapter and observed outcome make retry safe. For v1 retry a failed Agent node after already-dispatched siblings settle, with unchanged inputs/configuration. Preserve successful sibling/upstream results; never rewind completed conditions or approvals. Changed inputs/configuration require an explicitly authorized new run. Keep a recoverable workflow waiting in needs_attention; do not terminate it and pretend to resume it.
- Start new run creates a new execution with explicit new side effects and provenance; it must be clearly labeled and authorized.

Historical playback is a read-only event viewer. Do not label it re-execution. Do not add time travel that silently replays real writes.

Retain compatible interpreter/worker versions for active runs. Document a supported Temporal worker versioning or patching strategy and include replay compatibility checks for interpreter changes. Pinned JSON alone does not protect against nondeterministic code upgrades.

Run state vocabulary: queued, running, waiting_for_approval, waiting_for_execution, needs_attention, cancelling, completed, rejected, expired, failed, cancelled. Derive aggregate state from execution; when useful work runs in another branch, show running with waiting detail rather than implying everything stopped. Node states: pending, ready, running, retrying, waiting_for_approval, waiting_for_execution, succeeded, skipped, failed, cancelled. Document valid transitions and terminal states.

## 8 Agent SDK and connections

Define an AgentManifest with implementationKey, version, description, inputSchema, outputSchema, configSchema, capabilities, sideEffectClass, retrySafety, and fixture scenarios. JSON Schema must be constrained and versioned consistently across UI/API/worker.

Define a typed execute(context, inputs, config) interface. Context includes scoped run/node identity, operation key, deadline, cancellation, artifact access, structured redacted logging, and a restricted connector client. Return validated structured outputs and artifact references. AI output is untrusted data and must pass the same output schema.

Ship working built-in implementations:

1. Structured intake parser for sample JSON/CSV or text; do not claim OCR if no OCR is implemented.
2. Completeness and business-rule check.
3. Supplier lookup through a local fixture service using an actual HTTP call.
4. Service-ticket creation through that service with persistent records and idempotency.
5. Summary builder producing an inspectable artifact.

Human approvals and conditions are runtime control nodes, not hidden LLM calls. An optional AI extraction/drafting adapter can be a later extension with schema validation, evidence references, token/time budgets, and a model-provider interface. Do not fabricate OCR accuracy or model confidence percentages.

HTTP adapters use administrator-approved, environment-specific host/network allowlists and allowed methods. Intentional internal enterprise endpoints and the Docker fixture service can be allowlisted; block unapproved destinations, metadata endpoints, redirect escapes, DNS rebinding, and uncontrolled headers. Never accept arbitrary URLs/credentials from task uploads. Restrict egress at deployment as well as application validation. Templates store secret references resolved only at dispatch. Never put secret values in audit diffs or exports.

## 9 Uploads and application security

Implement server-enforced file size, count, extension/type allowlists, content-type verification, safe filenames, and bounded parsing. Store uploads outside the executable/web root. No shell commands using uploaded names. All downloads verify workspace/object permission and use controlled delivery or short-lived scoped URLs.

Model quarantine and scan status. A development fixture bypass may be explicit and local-only; a production profile must fail closed when required scanning is unavailable. Do not send uploads to an external model without a configured and authorized connector. Define retention/deletion behavior for stored files, histories, and audit records; append-only application audit is not a claim of tamper-proof storage against a database administrator.

Use secure session/cookie handling, CSRF defense for cookie-authenticated mutations, validated OIDC tokens/issuer/audience, deny-by-default authorization, rate limits on expensive endpoints, and output/log redaction. Never trust client-supplied role headers or workspace claims without membership validation. Test tenant isolation from server endpoints directly.

## 10 Differentiators to implement after the core vertical slice

### Safe simulation

Simulate a saved draft through the same compiler and execution semantics using deterministic fixture adapters. Use a separate execution mode/task queue and credentials-free context with live-write egress disabled. Label all simulated inputs/outputs. Never implement simulation by setting a flag on a production writer that it may ignore.

Provide scenarios: success, missing input/document, lookup timeout, denied approval, and expired approval. Simulation records node outcomes and exposes mapping values. Timings and outcomes are illustrative fixtures, not predictions of live behavior.

### Readable version review

Compare semantic changes by stable node IDs: added/removed agent, changed pinned version, changed mapping, role, retry policy, or connection reference. Separate layout-only changes. Present a readable summary backed by exact field diffs. Do not use an LLM to decide what changed. Show the precise snapshot being approved and published.

### Explain waiting and failure

Compute explanations from actual runtime state: waiting for a named eligible role, retry scheduled after a transient response, missing connection permission, failed branch preventing join, or input requiring correction. Link to the relevant action. Do not invent explanations with a chat model.

### Evidence and run export

Export a redacted JSON run manifest and human-readable Markdown report containing version pins, input hashes, outcome timeline, actual approval decisions, adapter attempts, and output artifact metadata. Include an export schema version and source IDs. Do not include credentials or sensitive raw payloads by default. Exports are access-controlled and audited.

### Practical next release upgrades

Implement these two bounded features in P2 after P0 and P1 are verified. They are required for the expanded product target; do not label P0 completion as full product completion.

First, reusable insertion blocks: save a structured group as a versioned block with explicit input/output boundaries. Inserting it expands independent node instances with fresh IDs and records source block/version provenance. This matches the meeting's quick-insertion idea without coupling existing templates to live block changes. Shared executable sub-workflows require separate semantics later.

Second, Find a template: a New Task search assistant that suggests only published templates the current user may start, explains its match, and asks for selection before instantiation. Ship deterministic keyword/tag matching first; an optional approved model can rerank the authorized set. Never invent template IDs or bypass ordinary inputs/permissions. This is the specific AI placement proposed in the transcript.

### Later backlog

Shared executable sub-workflows, authenticated webhooks/schedules, collaborative editing, request-changes loops, and further connectors are outside the initial graph language. Typed natural-language graph proposals are required in P1. If unimplemented, keep the feature in documentation rather than an enabled placeholder button. Do not let these delay the complete required slice.

Implement agent-version impact analysis and reviewed environment promotion in P2. Saved scenario comparison is required in P1 and supplies evidence for P2 release experiments. Promotion preserves the immutable release and reviews connection-reference rebinding. Do not claim these exist unless implemented and verified.

## 11 API and service expectations

Use consistent typed errors with errorCode, userMessage, fieldErrors, and correlationId. Generate OpenAPI and a typed client where practical. Every route below is workspace-scoped and authorized:

- agents and versions: list, create/configure, inspect, test, deprecate, permitted delete.
- templates: list, draft CRUD with expected revision, validate, simulate, submit review, decide review, publish approved hash, compare, export/import, archive.
- tasks: create with idempotency key, list, detail, inputs/artifacts, selected run.
- runs: detail, nodes/attempts, events stream, eligible manual execute, allowed recovery/cancel commands, history export.
- approvals: eligible inbox, detail, claim where supported, decide with request ID and expected version.
- notifications: preview/enqueue eligible reminders and inspect permitted delivery outcomes.
- connections: metadata CRUD, test, revoke; secret handling is write-only/reference-based.
- administration: memberships, grants, audit search, health/readiness.

Prefer command endpoints for lifecycle actions over generic patches to status fields. Use transactions and database uniqueness constraints for publication, starts, approval decisions, and event deduplication. Import is schema/version validated and never activates an unreviewed template or imports secrets.

## 12 Seeded demonstration and observable outcomes

Seed separate authenticated developer, author, template reviewer, contributor, runtime approver, operator, and auditor accounts with clearly documented development-only credentials. Seed at least two workspaces to verify isolation. Avoid hidden access shortcuts.

Primary template: Supplier onboarding. Intake -> parse -> parallel supplier lookup and completeness check -> paired join -> condition. Complete branch: procurement approval -> create service ticket -> summary -> condition merge -> End. Incomplete branch: Outcome(rejected, incomplete information), which finalizes without ever dispatching ticket creation. Approval rejection/expiry also prevents ticket creation. The validator must accept this through normal paths.

Use real local fixture API records for ticket creation. Label the connection Demo service desk. Do not pretend to have created a real Jira ticket. Include a second meeting-faithful CSR to Jira template: developer-provided Demo CSR capability -> reused ticket adapter configured for Demo Jira. Both are fixture services with persistent local records. Make CSR require manual execution by an eligible contributor and independently demonstrate Approval required on the ticket step. This proves both the meeting example and company-neutral reuse.

Provide deterministic sample files and scenarios. Populate historical demo states through a seed scenario runner or label imported fixture histories clearly. Never insert fake live-success UI data to conceal missing execution.

The five-minute demonstration should show:

1. Agent schema and reuse; drag an agent into a draft; automatically receive the next insertion target.
2. Add parallel work and map an upstream field; introduce and fix an actual validation error.
3. Simulate a successful and a failing input without creating any fixture or external tickets.
4. Submit the exact draft snapshot; sign in as a separate reviewer and publish it.
5. Start a task with an upload; reach a persisted approval; refresh or restart the worker; the gate remains.
6. Approve using the eligible account; the run completes and exactly one ticket exists in the tested idempotent fixture service.
7. Recover a seeded failed attempt without rerunning already successful steps.
8. Publish a new template version and show the old task retains its original executable definition.

## 13 Implementation milestones

Execute these in order and keep the application runnable after each. Finish all required milestones; do not treat the list as an invitation to stop after scaffolding.

1. Foundation: inspect/record decisions, establish modules, migrations, identity, workspace authorization, seed accounts, shell, and local startup.
2. First executable slice: versioned agent registry, template persistence and validation, minimal designer, approved publication, task upload/start, actual worker execution of a sequence, status events, outputs.
3. Complete core: structured parallel/condition semantics, data mapping, right inspector, review separation, runtime approval/expiry, cancellation, outbox/reconciliation, retry safety, immutable versions, and audit.
4. Product differentiation: safe simulation, readable diffs, why-waiting, evidence exports, accessible outline, visual refinement, full loading/error/conflict states.
5. Intelligent construction and evidence: implement the full P1 contract, typed planner pipeline, evidence records, prepared-action decisions, scenario comparisons, effect ledger, and repair workflow defined above.
6. Bounded teams and improvement: implement P2 team recipes/baselines, block insertion, authorized template finding, impact analysis, release experiments, and environment promotion.
7. Verification and handoff: failure injection, worker restart, advanced acceptance gates, privacy/isolation checks, browser journeys, performance measurements, README and deployment limitations.

Delegate independent frontend, domain/runtime, and test/review tasks if parallel agents are available, using explicit file ownership and shared contracts. Integrate and verify; do not leave incompatible partial implementations.

## 14 Acceptance criteria and meaningful tests

The full build is complete when all required acceptance gates pass. Report blocked or unverified gates explicitly; they remain incomplete:

| Test | Required result |
| --- | --- |
| Clean startup | Documented command starts dependencies/app, migrates safely, seeds idempotently, and exposes health checks. |
| Agent lifecycle | Create/configure/test/version/deprecate works; deleting a referenced version is refused. |
| Designer persistence | Drag, insert, parallel branch, inspector edits, mappings, undo/redo, autosave, and reload retain intended graph/configuration. |
| Graph rejection | Cycles, missing mappings, crossing branches, invalid joins, and unreachable required nodes fail on the server. |
| Publish approval | Self-approval fails; altered content cannot reuse an old approval; published versions cannot be patched. |
| Version pinning | Publishing v2 never changes active/completed v1 runs or their resolved defaults. |
| Actual concurrency | Parallel branch Activities overlap under configured limits; joins wait for the correct branches. |
| Condition semantics | Nonselected branches are skipped; their merges do not wait forever; invalid cross-branch mappings are refused. |
| Durable approval | Browser refresh and worker restart preserve the pending gate; an eligible decision resumes it. |
| Manual execution | An eligible executor may start the permitted preparation phase after dependencies. A protected effect dispatches only after exact-action approval and any separate manual-start requirement; wrong roles and duplicate commands cannot bypass either gate. |
| Role preview | Design-mode role preview is read-only; runtime actions come from current server policy; stale UI permission never authorizes a request. |
| Reminder delivery | Eligible recipients and safe deep link are previewed; local SMTP captures the message; duplicate/rate-limited requests are handled; GET never approves. |
| Approval races | Duplicate decisions, competing actors, late decisions, stale gate IDs, and decision/expiry races produce one effective outcome. |
| Outbox reliability | Crash after database commit but before runtime delivery recovers without duplicate tasks or lost decisions. |
| Crash after write | Fixture ticket is persisted, worker is interrupted before acknowledging success, retry reconciles or reuses the same operation key; one ticket remains. |
| Operator recovery | Safe failed node can retry; completed siblings/upstream outputs remain; unsafe ambiguous writes require reconciliation. |
| Cancellation | New dispatch stops and cancellable work acknowledges; completed external effects remain visible. |
| Simulation isolation | Simulation cannot reach live-write adapters or production credentials and creates no live records. |
| Authorization | Direct API attempts by wrong role/workspace fail, including artifacts, connections, exports, and SSE. |
| Privacy | Seeded sentinel secrets do not appear in graph JSON, API responses, logs, history payloads, or exports. |
| Event recovery | Disconnect/reconnect returns missed events without duplication; stale UI is visible. |
| Browser flow | Real create -> design -> review -> publish -> task -> approval -> completion works. |
| Accessibility | Keyboard-only main journey, labeled controls, focus management, non-color statuses, and no critical automated accessibility findings on core screens. |

Test the engine and API directly as well as the browser. Test authorization with ordinary sessions, not test-only bypasses. Use controlled fixture failures and real process restarts for durability evidence. Record measured performance for a 50-node fixture and a modest concurrent-run workload with machine/environment details; do not assert a capacity or SLA without measurement.

Run lint, typecheck, domain unit tests, migrations/integration tests, runtime tests, and critical Playwright journeys. Inspect screenshots of the designer, task run, approval drawer/page, and empty/error states at representative laptop/mobile widths. Fix concrete defects before handoff. If tooling or network access prevents a check, mark it unverified with the command and cause; never imply it passed.

## 15 Deliverables and completion report

Deliver working source, lockfiles, migrations, seed/scenario runner, sample inputs, fixture connector, local Compose configuration, .env.example without secrets, and these concise documents:

- README with exact setup/run/test commands and development accounts.
- Architecture decisions and domain/state/graph semantics.
- Agent SDK guide and how to register a new implementation safely.
- Permissions matrix and template/runtime approval rules.
- Operations notes for worker upgrades, backup/restore, reconciliation, retention, secrets, and production identity.
- Dependency/license inventory and known limitations.
- Demo script and acceptance results with evidence.

Keep docs/IMPLEMENTATION_STATUS.md updated with completed milestones, commands/results, blockers, and precise next work so another Codex session can continue without guessing. If a session limit interrupts execution, leave a runnable checkpoint and accurate status; do not declare the task finished.

The final completion report should state what works end to end, where to run it, what was verified, and material remaining limitations. Do not label it production-ready merely because the UI looks finished. Begin repository inspection and implementation now.
