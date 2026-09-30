# Axiom architecture and product decisions

This log records decisions for continued implementation. Each decision is accepted for the local product unless a later entry explicitly replaces it. The production integration gates remain requirements, but they are not represented as working features before real verification.

Implementation checkpoint: the current repository now reflects these decisions through separate domain/compiler/evidence/scenario/SDK/governance modules, ordered SQLite migrations, typed template/agent contracts, task-request/artifact/connection/effect records, and the existing local server/interface. Domain services without an HTTP or interface workflow remain foundations rather than completed user-facing features.

## D-001 — Evolve the existing application

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Continue in the substantive existing application under `app/`: Python standard-library HTTP server, SQLite storage, and vanilla JavaScript/CSS interface. Preserve its working behavior and tests, then extend it in staged, reviewable changes. Do not rebuild the product as a new TypeScript monorepo merely to match a greenfield recommendation.

**Why**

The existing application already exercises real HTTP requests, persisted workflow runs, restart recovery, review/publication, decisions, rehearsal, evidence, and safe fixture writes. The master prompt explicitly permits integration with a substantive repository rather than gratuitous replacement. Rebuilding would discard verified behavior and delay the missing product capabilities.

**Consequences**

- New features use the existing code and test entry points unless a measured limitation justifies a targeted replacement.
- Large responsibilities in `server.py` and `public/app.js` may be extracted into focused Python or JavaScript modules while preserving public behavior.
- React, NestJS, PostgreSQL, and Temporal are not local prerequisites.
- Production readiness must be evaluated from behavior and integration evidence, not from matching a preferred framework list.

## D-002 — One SQLite-backed scheduler is the local durable authority

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Keep the SQLite-backed scheduler in the local application as the sole authority for local run progress, timers, retries, decisions, and recovery. Strengthen it with versioned state transitions, idempotent commands, prepared actions, and an effect ledger. Do not add Temporal, Flowable, Celery, an in-memory queue, or another competing scheduler to the local profile. The current checkpoint has atomic persisted run state, actor-scoped idempotent task starts, a local notification-capture outbox, and the effect ledger; it does not yet claim a general database-to-worker command outbox or monotonic reconnect cursor protocol.

**Why**

One authority makes restart and race behavior testable and prevents two components from independently deciding a run's state. The existing scheduler already has verified restart and failure-isolation behavior. SQLite is appropriate for the self-contained local product but is not evidence of distributed failover or production scale.

**Consequences**

- Browser timers never advance a run.
- Task creation can be deduplicated by an actor-scoped key, and run/effect state survives restart. General command-receiver deduplication remains a broader production-runtime requirement.
- Local durability claims are limited to the tested SQLite/process model.
- Distributed execution remains a separate production integration gate requiring an explicit design, migration path, replay/version strategy, failover testing, and load evidence.

## D-003 — Preserve local zero-install operation

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Keep the base local application runnable with Python 3.10 or newer and no mandatory package download, paid workflow platform, external model, or live business-system credential. Optional test or integration tooling may have documented dependencies, but the core authoring and fixture journey must remain self-contained.

**Why**

The current delivery is easy to inspect and run, and the product requirements explicitly require usefulness without an AI provider or paid workflow service.

**Consequences**

- SQLite migrations and fixture services are owned by the repository.
- Remote assets, external fonts, and mandatory SaaS services are not added to core operation.
- Optional providers must fail clearly and leave manual workflows usable.

## D-004 — Use a versioned executable contract independent of the canvas

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Define one versioned business-contract and compiled-plan format for validation, publication, execution, simulation, comparison, role preview, evidence, and export. Canvas positions are retained for presentation but excluded from semantic behavior hashes.

The initial graph language is a bounded structured directed acyclic graph with Start, End, Agent, Manual start, Condition/merge, Parallel split/join, Approval, Outcome, and optional bounded Delay. Arbitrary cycles, scripts, implicit merges, and first-wins races are rejected.

**Why**

The same saved workflow must mean the same thing in Design, Rehearsal, and Run. A restricted language permits clear validation and reliable recovery; screen coordinates and editor-library objects do not.

**Consequences**

- All edit paths, including AI proposals and block insertion, use the same validated revision transaction.
- Published versions resolve defaults and pin agent, policy, schema, and interpreter versions.
- Layout-only and behavior changes are compared separately.
- Existing simple AND-dependency graphs require a defined migration into the versioned contract.
- Template inputs and built-in agent outputs use the same constrained schema subset. A mapping must name declared source/target fields, come from an upstream value available on every path, and be conservatively type-assignable.

## D-005 — Server decisions are authoritative

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Every permission, lifecycle transition, mapping, graph rule, prepared action, decision, retry, cancellation, reminder, export, and connection use is checked on the server. The interface renders server-returned allowed actions and reasons; hidden or disabled controls are only presentation.

**Why**

Client state can be stale or altered. The product's governance promise depends on direct API requests receiving the same checks as the browser.

**Consequences**

- Capability checks replace scattered interface-only role comparisons.
- Manual execution and approval remain separate permissions.
- Current revocation takes precedence over a previously recorded role or policy snapshot at privileged dispatch.
- The current product has one explicit local workspace. Cross-workspace IDs, evidence, files, connections, exports, and event streams require negative API tests when real multi-workspace scoping is introduced; local fixture behavior is not tenant isolation.

## D-006 — Development identities remain local-only; OIDC is an integration gate

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Retain distinct seeded development users and the visibly labeled account selector for local testing. Bind sessions and CSRF protection on the local server and refuse public binding by default. Do not describe these sessions as corporate authentication.

Production-grade OIDC, directory membership mapping, delegation/revocation, and production refusal of development authentication remain an explicit integration gate.

**Why**

The seeded identities provide repeatable separation-of-duty tests without pretending that a customer identity system is available. Actual issuer, audience, group, lifecycle, and directory contracts cannot be inferred.

**Consequences**

- Local permission behavior can be completed and tested independently.
- A production profile may not fall back to the account selector.
- Production identity is incomplete until tested with the chosen provider and real lifecycle events.

## D-007 — Protected writes use prepared actions and an effect ledger

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Use prepare → approve → commit for protected actions whose final payload is not already approved. A directly guarding explicit Approval control prepares the downstream write before the reviewer decides; a write can also carry its own approval gate. Bind either form to the same immutable action fingerprint and separate approval-envelope hash. Persist each logical external operation in an effect ledger and keep its operation identity stable across eligible retries.

**Why**

Approval before a dynamic payload exists cannot authorize that payload. A local success flag also cannot prove what happened when a remote acknowledgement is lost.

**Consequences**

- Changed payload, destination, method, resource, or connection identity requires fresh approval.
- The local connection identity includes an audited authority generation. Revocation or restore changes that generation, invalidates a stale prepared packet, and is rechecked before decision and dispatch.
- Renewing an unchanged expired approval preserves operation identity and cannot create a duplicate write.
- Unknown writes require reconciliation; they are never blindly retried.
- Retry, reconciliation, compensation, cancellation, and a new run remain distinct actions.
- Exactly-once behavior is claimed only for a tested destination contract, never universally.

## D-008 — Fixtures are first-class tests, not substitutes for live integrations

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Keep deterministic local CSR, directory, ticket, reminder, model, and failure fixtures for development and acceptance tests. Label their records and connections as demo/local. Real Jira, CSR, OCI, production email, and arbitrary approved connectors remain integration gates until their contracts, credentials, network policy, and sandbox behavior are available and verified.

**Why**

Fixtures give repeatable known answers and permit safe failure injection. They cannot establish compatibility, authorization, idempotency, or reliability for a service that was never contacted.

**Consequences**

- Fixture results may prove local workflow behavior, isolation, and recovery.
- They may not be presented as live tickets, delivered production email, Oracle approval, or provider/model quality. A reminder marked `sent` was delivered only to the persisted local capture outbox and resolved local identities.
- Each real connector requires contract tests, destination-specific retry/reconciliation rules, egress restrictions, secret references, and observed receipts.
- OCI authentication must use the official method appropriate to the confirmed OCI service; private keys are never treated as generic bearer tokens.

## D-009 — AI proposes; deterministic code validates and authorizes

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Keep a deterministic local planner for repeatable use and tests. An optional configured model may produce only allowlisted structured proposals. The current server accepts at most 100 `update_node`, `add_node`, `remove_node`, `add_edge`, `remove_edge`, `bind_field`, `insert_approval`, or same-implementation `replace_agent` operations. The graph compiler, schema validator, mapping checks, policy checks, revision checks, and user acceptance determine whether a proposal may enter a draft.

**Why**

Model output is untrusted data. The product must remain useful with no provider and must not confuse structured output with permission or business correctness.

**Consequences**

- A planner cannot create credentials, grant roles, publish, suppress audit, execute a task, remove an approval boundary, or replace a capability with a different implementation/effect class.
- Network model calls release the local store lock and recheck revision and authority afterward.
- Provider identity and observed usage are displayed honestly; unknown cost or confidence is not invented.
- Live model quality remains an integration/evaluation result, not a fixture claim.

## D-010 — Evidence comes from stored records, not retrospective explanation

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Represent sources, evidence items, claims, transformations, decision packets, and receipts as linked, scoped records. Explanations and exports are generated from these records and run events. Preserve missing and conflicting evidence.

**Why**

An audit trail must point to what the system actually observed and did. Generated prose or private model reasoning cannot replace source lineage.

**Consequences**

- Direct extraction, calculation, model inference, and human assertion remain distinguishable.
- Source hashes, versions, paths/spans, timestamps, producers, and access labels are retained.
- Derived evidence inherits access limits.
- Exports are redacted, versioned, authorized, and audited.
- Run exports replace secret-looking values and raw external content, add a human-readable Markdown summary, and seal canonical content with SHA-256. Template packages are likewise hash-checked on import. These hashes detect changed content; they are not HMACs, public-key signatures, or signer identity.

## D-011 — Rehearsal is isolated from fixture and production writes

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Run scenarios through the same compiled semantics but with an isolated store/context and write-disabled or dedicated rehearsal adapters. Keep inspecting history, replaying recorded outputs, and re-executing a sandbox case as separate operations.

**Why**

Testing a workflow must not produce the business effect it is trying to predict. A replay of recorded results is also different from another model or tool execution.

**Consequences**

- Each scenario declares starting state, pins, injected events, decisions, expected final state, and invariants.
- A simulation cannot reach live credentials or production egress.
- Passing means observed state matches the declared expectation, not merely that execution ended.
- Model-emulated services are labeled approximate and cannot replace deterministic fixtures.

## D-012 — The interface stays framework-light and behavior-led

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Continue the current owned HTML/CSS/JavaScript interface and improve it directly. Extract modules when they reduce risk, but do not introduce a frontend framework solely for fashion or parity with a greenfield suggestion.

**Why**

The interface already represents the required workspaces and has no mandatory third-party runtime assets. A recorded desktop/mobile Chromium journey now supplements the view contracts. Ongoing interface work should focus on formal accessibility coverage, broader cross-browser verification, and the remaining integrated product workflows rather than framework churn.

**Consequences**

- The canvas must keep a keyboard-accessible ordered/table alternative.
- The same saved positions and selection should carry across Design, Rehearsal, and Run where applicable.
- Every mutation shows pending/success/error or an actionable disabled reason.
- Node view-contract tests remain useful but cannot establish rendering, pointer behavior, responsiveness, or accessibility by themselves; live browser evidence is recorded separately.

## D-013 — Completion has two separate claims

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Report local product completion separately from production integration readiness.

Local product completion requires all implemented P0, P1, and P2 acceptance gates, real-browser/accessibility verification, restart and failure-injection evidence, complete documentation, and truthful known limitations. Production readiness additionally requires closed OIDC, distributed execution, external connector, storage/scanning, notification, security, operations, and measured load/failover gates.

**Why**

The local application can become a complete and valuable implementation while some customer-specific systems are unavailable. Calling it production-ready without those systems would be false.

**Consequences**

- `implemented`, `verified`, `integration-required`, and `not-implemented` remain distinct states.
- A blocked or unverified gate remains incomplete and is listed with its command, environment, and cause.
- Passing fixture tests never closes a production integration gate.
- Research targets are hypotheses until measured; they are not silently reported as achieved metrics.

## D-014 — Deferred features stay visibly deferred

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Shared executable sub-workflows, arbitrary graph cycles, authenticated schedules/webhooks, collaborative editing, request-changes loops, and unspecified additional connectors remain outside the initial P0/P1/P2 delivery unless a later decision expands scope.

**Why**

Their lifecycle and safety semantics are not fully specified, and they must not delay or destabilize the required integrated product.

**Consequences**

- Do not expose enabled placeholder controls for deferred features.
- Reusable insertion blocks are still required in P2; they expand independent nodes and are not shared executable sub-workflows.
- Existing documentation may describe the deferred roadmap, but feature status must not imply implementation.

## D-015 — Local connection authority is mutable and generation-bound

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Persist local fixture connection records with declared allowed operations, principal reference, ready/revoked status, and monotonic generation. Limit test/revoke/restore to administrators and audit every action. Include the current generation in prepared-write identity and recheck live authority before approval and dispatch.

**Why**

A static connection card cannot model revocation between preparation, review, and execution. Generation binding makes that race deterministic without pretending that the local fixture contains production credentials.

**Consequences**

- Revocation before approval or dispatch creates no new write.
- Restoring authority creates a new generation; an old packet cannot silently become valid again.
- Reconciliation of an already accepted exact write remains possible after revocation because it performs no new provider write.
- A local `test` result means only that the fixture record is ready; it does not establish network, credentials, tenancy, or external-service compatibility.

## D-016 — Task ingress is bounded, atomic, and optionally idempotent

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Accept at most five local UTF-8 JSON, plain-text, or CSV attachments, limited to 256 KiB each and 512 KiB in total. Validate names, base64, encoding, JSON syntax, duplicate names, and bounds before committing the run. Store content locally, expose only metadata and SHA-256 in public/evidence views, and allow an actor-scoped task-start idempotency key to bind the complete request.

**Why**

Bounded artifacts support realistic task context without introducing an unbounded upload surface. Idempotent starts prevent a repeated browser/API submission from creating a second run or storing the same attachments twice.

**Consequences**

- The same actor, key, and exact request return the original run; changed reuse fails.
- Invalid attachments fail the entire start atomically.
- Local MIME/UTF-8/JSON validation is not malware scanning, content trust, object storage, retention policy, or tenant authorization.
- Raw attachment bytes are not included in normal run/evidence/export responses.

## D-017 — Lifecycle changes preserve history; portable records are hash-checked

**Status:** Accepted  
**Date:** 2026-09-24

**Decision**

Make template duplication, archive/restore, and export/import explicit server lifecycle operations. Allow deletion only for unused custom agent registrations; built-ins and any agent referenced by a draft, release, or run remain immutable and may be deprecated instead. Import template packages only after their canonical hash and current graph/schema/approval validation pass.

**Why**

Every historical run must remain interpretable, while authors still need safe copy, retirement, and portability workflows. A content hash catches accidental or malicious package changes without inventing a signing authority.

**Consequences**

- An archived template cannot start a new run, while existing runs and releases remain readable.
- A duplicate or imported template is an independent unpublished draft.
- Hash verification establishes content integrity only. Production signer identity, trust policy, revocation, and signing-key lifecycle remain open gates.
