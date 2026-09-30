# Axiom implementation plan

## Purpose

This plan turns the existing runnable reference application into the complete local Axiom product described by the master prompt. Work continues in the current `app/` codebase: Python standard-library HTTP server, SQLite persistence, and vanilla JavaScript/CSS interface. The plan does not claim that unfinished work already exists, and it does not treat a production integration as verified until it has been tested against the real service.

The implementation order is P0, then P1, then P2, followed by final verification. A phase is complete only when its behavior and its tests pass. The authoritative scope and acceptance gates are in `docs/Axiom_Codex_Master_Prompt.md`; the current local status is in `app/feature_status.json` and `research/QA_NOTES.md`.

The checkpoint described here is Axiom 1.8.0 with SQLite schema 9 and built-in agent contract 1.3.0.

## Working rules

- Preserve the working local application and its passing tests while extending it.
- Keep one local execution authority: the SQLite-backed scheduler in `app/server.py`. Do not add a second local queue or scheduler.
- Use explicit, versioned records for workflow behavior. Keep canvas layout separate from executable meaning.
- Validate every mutation and permission on the server. Interface visibility is never authorization.
- Keep AI optional. Manual authoring, validation, execution, decisions, and recovery must work without a model provider.
- Use fixture services for repeatable local writes. Never label fixture tickets, captured reminders, or deterministic planner output as live external results.
- Keep production OIDC, distributed execution, and real Jira/CSR/OCI/email connectors as integration gates. They do not silently become complete through mocks.
- Every displayed action must work or explain why it is unavailable.
- Keep `app/feature_status.json` and the verification record accurate as work lands.

## Current implementation checkpoint

The current local application includes these implemented foundations, which must not regress:

- template creation, revision checks, validation, frozen review, publication, semantic/layout hashes, compiled release plans, byte-preserved published records, source-bound and separately hashed compatibility snapshots, embedded per-node agent manifests, immutable run snapshots, duplication, archive/restore, and hash-checked export/import;
- agent creation/metadata/deprecation, unused-custom-agent deletion, reference-preserving deletion guards, and local version-impact analysis;
- a constrained schema/type checker, conservative scalar/array/nested/additional-property assignability, typed template inputs and built-in outputs, path/type-safe mappings, a bounded rule AST, and a structured DAG compiler for condition/merge, parallel split/join, approval, outcome, and end behavior;
- an editable canvas and contextual screens, JavaScript syntax/UI-contract coverage, and a recorded headed-browser desktop/mobile journey; formal WCAG and multi-assistive-technology certification remain outside the local verification claim;
- SQLite migrations with a pre-migration strict-JSON integrity check, a single persisted scheduler, restart recovery, actor-scoped idempotent task starts, bounded attachment records, mutable generation-versioned fixture connections, explicit internal effect-ledger records, complete exact-action binding for both directly approval-required writes and directly guarding explicit Approval controls, approval expiry, exact provider-record reconciliation, and a read-only endpoint containing aggregate counts and reduced effect summaries;
- first-class evidence-domain records with source/span/reference/access validation, plus a run evidence endpoint and authorized, audited `POST` run export with recursive redaction, action receipts, a Markdown summary, and a canonical integrity hash;
- a versioned ten-case known-answer scenario catalog, scenario-definition pinning, experiment-scoped write isolation, deterministic path/final-state/effect/authorization invariant evaluation, paired comparison, and regression-case creation primitives;
- deterministic planner proposals with explicit review/apply, stale-revision rejection, and an allowlist of at most 100 update/add/remove-node, add/remove-edge, field-binding, approval-insertion, and same-implementation replacement operations;
- permission-filtered template finding and agent-version impact analysis exposed by local API routes;
- tested domain services for reusable block expansion, bounded team planning with a matched-budget baseline, and paired future-version selection.
- five persistent demonstration workflows for payment disputes, employee access governance, production incident changes, vendor-risk onboarding, and insurance-claim adjudication. Each published demo has 14 nodes and 16 edges, a required typed input contract, parallel checks, a policy branch, an exact approval-bound local action record, and a final receipt. Their deterministic fixture manifests and default inputs are release-pinned and hash-verified; they do not represent live external integrations.

Some capabilities above are intentionally domain-only. `agent_sdk.py` scaffolding, reusable block expansion, TeamRecipe planning, and paired release selection do not yet have complete persistence, authorization, HTTP, or interface workflows. The detailed P0/P1/P2 sections below remain the broader product completion standard; the local reference status and its verified boundaries are recorded separately in `docs/IMPLEMENTATION_STATUS.md`.

Production OIDC, persistent secret management, distributed workers/failover, real Jira/CSR/OCI/email connectors, and production artifact storage remain open integration gates.

Local completion language remains bounded: attachment checks are not malware scanning, connection tests are not external contract tests, reminder `sent` means local-capture delivery only, and SHA-256 export hashes are not identity-backed digital signatures.

## P0 — complete governed local core

### P0.1 Domain records and migration discipline

1. Add a schema-version table and ordered, repeatable SQLite migrations. Existing local databases must upgrade without losing templates, runs, decisions, tickets, or audit history.
2. Replace broad JSON-only persistence where correctness depends on database constraints. Add explicit records and uniqueness rules for template submissions/publications, node attempts, approval requests/decisions, outbox commands, notification deliveries, prepared actions, effect ledger entries, artifacts, and run-event cursors.
3. Add workspace ownership to every scoped record and enforce it in repository/service helpers. Seed at least two workspaces for isolation tests.
4. Store UTC timestamps, stable IDs, content hashes, schema versions, and correlation IDs. Keep secrets out of workflow JSON, event payloads, logs, and exports.

**Exit criteria**

- A fresh database initializes once; a second startup is idempotent.
- A copy of the current fixture database migrates and retains its observable records.
- Duplicate publication, decision, command, event, and action identities are rejected by both server logic and database constraints where practical.
- Direct cross-workspace requests for records, evidence, exports, connections, and event cursors fail.

**Current local checkpoint:** ordered migrations plus explicit effect, attachment, actor-scoped task-request, connection, and local reminder-outbox records are implemented. API and persisted JSON use strict RFC 8259 handling: duplicate keys, non-finite numbers, and invalid Unicode fail, and startup checks legacy JSON before applying schema DDL. Attachment/start transactions are atomic and duplicate starts can return the original run. Multi-workspace ownership, normalized decision/attempt records, a general database-to-worker command outbox, and monotonic reconnect cursors remain open; the local reference must not claim those broader exit criteria yet.

### P0.2 Executable contract and graph compiler

1. Define a versioned business-contract representation shared by validation, publication, execution, simulation, comparison, role preview, and export.
2. Implement the bounded graph language: one Start and End; Agent; Manual start; Condition with a required default and explicit merge; Parallel split with matching Join; Approval; Outcome; and an optional bounded Delay.
3. Add a constrained typed-rule and mapping system. Support required/optional fields, nullability, enums, arrays, and object fields; reject unsupported schema constructs.
4. Reject cycles, duplicate IDs, unreachable required work, dangling edges, branch crossings, mismatched split/join pairs, invalid ports, missing defaults, unavailable agent versions, invalid connections, path-invalid mappings, approval bypasses, and unresolved blocking assumptions.
5. Resolve defaults and pin graph, agent, policy, schema, and interpreter versions at publication. Keep semantic hashes independent of node positions while retaining the published layout.

**Exit criteria**

- Independent valid fixtures compile to a deterministic plan.
- Seeded invalid graphs fail through direct HTTP/API tests with a node or field-specific error.
- Parallel branches really overlap within the configured local limit; joins wait for the correct branches.
- A condition skips unselected branches and its merge cannot deadlock on them.
- Publishing a new version cannot change an active or completed older run.

**Current local checkpoint:** template input schemas and built-in agent input/output schemas are persisted and migrated. New publications embed the exact agent version and complete executable manifest for every node. Existing published records are hash-verified and left byte-for-byte unchanged; the earlier schema-8 migration created separately hashed compatibility snapshots where older publications needed safe execution metadata, and schema 9 adds pinned, hash-verified demonstration fixture manifests and exact action-field contracts. Compatibility snapshots remain bound to their source version and source hash, retain replacement history, and audit the change. Mapping validation rejects undeclared target/source paths, non-upstream sources, values unavailable on every path, and incompatible supported-schema types. The mapping interface lists nested compatible fields. The schema language remains the explicit Axiom subset rather than general JSON Schema.

### P0.3 Registry, designer, and release lifecycle

1. Complete agent version records with input/output/configuration schemas, side-effect class, retry/reconcile capability, fixture tests, owner, lifecycle, and where-used results.
2. Complete canvas authoring for drag and keyboard insertion, edge insertion, sequential and parallel targets, repeated agent instances, typed mappings, dependency-aware removal, duplication, undo/redo, zoom, fit, and explicit auto-layout.
3. Complete contextual configuration for execution mode, executor roles, approval requirement, approver roles, connection, timeout, retries, and test data.
4. Provide revision-aware autosave states: Saving, Saved, Failed/Offline, and Conflict. Never overwrite a stale draft.
5. Keep template release review separate from runtime action approval. Bind publication to the exact submitted hash and enforce author/reviewer separation.

**Exit criteria**

- Create, configure, test, version, and deprecate an agent; deleting a referenced version is refused.
- Build and reload sequential and parallel graphs without losing layout or configuration.
- Both insertion targets appear after a node is added, and placeholders never execute.
- Stale writes conflict; submitted snapshots freeze; self-publication and altered-snapshot publication fail.
- Published versions remain immutable and archived versions remain readable by historical runs.

**Current local checkpoint:** templates can be duplicated, archived/restored, and hash-exported/imported through server-authorized interface controls; archive blocks new fixture starts, draft simulations, and rehearsal experiments but retains release history and existing runs. The interface disables the same operations and explains that restore is required. Custom agents can be deleted only when unused, while built-ins and draft/release/run references are preserved. Full agent-package version creation/testing, explicit auto-layout, dependency-aware removal UX, autosave/offline state, and reusable-block insertion remain open.

### P0.4 Human control, prepared actions, and effect safety

1. Keep manual execution and approval as independent gates. Recheck the current actor, dependency state, and connection permission when each command is applied.
2. Add prepare → approve → commit for protected writes. Store an immutable prepared payload before approval and commit exactly that payload.
3. Calculate a stable action fingerprint from workspace, run/node/action generation, canonical payload, method, destination/resource, and connection identity. Calculate a separate approval-envelope hash from the action fingerprint, policy version, evidence snapshot, reviewer scope, and expiry.
4. Add the local effect ledger states `prepared`, `dispatched`, `acknowledged`, `unknown`, `reconciled`, and `compensated` where supported. Reject operation-key reuse with a different fingerprint.
5. Keep unknown writes in `needs_attention` until reconciliation. Never turn an unknown write into a blind retry.
6. Make approval expiry, duplicate decisions, competing decisions, stale gate IDs, revocation, cancellation, and retry commands deterministic and auditable.

**Exit criteria**

- An eligible executor can start the allowed phase, but cannot bypass a separate action approval.
- Wrong-role, revoked, stale, duplicate, and altered-payload commands create no unauthorized effect.
- A pending decision survives refresh and process restart.
- A fixture write committed before a lost acknowledgement reconciles to one ticket after restart/retry.
- The same experiment against an adapter without idempotency or reconciliation refuses automatic retry.

**Current local checkpoint:** administrator-only local connection test/revoke/restore is persisted, audited, and generation-versioned. The generation is part of prepared action identity and authority is rechecked before decision and dispatch. Complete multi-action packets, self-gated approvals, expiry/restart, lost acknowledgement, provider fingerprint/payload mismatch, cancellation with unknown effects, and revocation races have focused tests. The local ledger has no general compensation state/contract, and no real destination's idempotency has been established.

### P0.5 Reliable local operations and complete core interface

1. Make database-to-scheduler commands durable through the SQLite outbox and idempotent local receivers. Distinguish command accepted, scheduler applied, and terminal result.
2. Add monotonic run-event cursors and reconnect/resynchronization behavior. The browser may display progress; it must not schedule it.
3. Finish Studio, Registry, Runs, Decision Inbox/My Work, Rehearsal, Connections, and Administration with consistent empty, loading, error, denied, disconnected, and conflict states.
4. Add an accessible ordered/table workflow view, keyboard authoring, visible focus, dialog focus handling, non-color status labels, and reduced-motion behavior.
5. Keep reminder recipients policy-derived, rate-limited, deduplicated, and locally captured. A GET link must never decide an approval.
6. Add redacted JSON and Markdown run exports with source IDs and an export schema version.

**Exit criteria**

- A crash after an API database commit but before scheduler handling recovers without a lost or duplicate command.
- Disconnect/reconnect returns missed events once and exposes stale state while reconnecting.
- Every visible button works or gives an actionable disabled reason.
- The complete create → design → review → publish → task → manual action/approval → completion journey works through real HTTP requests.
- Core flows pass the real-browser and accessibility checks listed under Final verification.

**Current local checkpoint:** task start accepts bounded UTF-8 JSON/text/CSV attachments and an optional actor-scoped idempotency key. Reminder recipients are policy-derived and persisted with delivery key, queued/sent local-capture transitions, connection generation, and review deep link; no external message is sent. The effects route exposes aggregate counts and reduced effect summaries, not protected payloads or complete internal ledger records. Run export is an authorized and audited `POST`; it is schema-versioned, recursively redacted, includes Markdown, and carries a canonical SHA-256 integrity hash. A general durable command outbox, monotonic event cursor, full ordered/table keyboard-authoring view, external delivery, production scanning/storage, and identity-backed signing remain open.

## P1 — intelligent construction, evidence, rehearsal, and recovery

### P1.1 Typed outcome compiler

1. Expand proposals to the complete allowlist: add/remove draft node, update allowed configuration, bind field, add/remove permitted edge, insert approval, create a structured parallel branch, and replace an eligible capability version.
2. Link proposal operations to requirements and surface blocking/non-blocking assumptions, affected policies, and suggested scenarios.
3. Validate model output exactly like manual changes. Permit one bounded correction attempt, then return concrete unresolved errors.
4. Keep provider state explicit: deterministic local planner, configured provider, or unavailable. Recheck revision and authorization after any network wait.

**Current local checkpoint:** the primitive operation allowlist is implemented as `update_node`, `add_node`, `remove_node`, `add_edge`, `remove_edge`, `bind_field`, `insert_approval`, and `replace_agent`, with a 100-operation bound. Approval removal and effect-class/implementation expansion are denied, and apply uses ordinary revision plus graph/schema/mapping validation. A higher-level one-operation structured-parallel transformation, requirement links, policy-impact explanation, suggested scenarios, and bounded correction are not complete.

**Exit criteria**

- Malformed, stale, unauthorized, unsupported, or unknown-reference proposals fail server validation.
- An accepted proposal uses the normal edit transaction, remains editable and undoable, and records requirement links.
- The planner cannot create credentials, grant roles, publish, suppress audit, or execute work.
- The full manual product remains usable when no model is configured.

### P1.2 Evidence graph and decision packets

1. Add first-class SourceSnapshot, EvidenceItem, Claim, Transformation, DecisionPacket, and ActionReceipt records.
2. Record source/version/hash, field path or excerpt span, observed time, access label, producer version, transformation links, and supporting/conflicting evidence.
3. Add the Evidence Lens to mappings, outputs, conditions, recommendations, and approvals. Derive explanations from recorded artifacts and events.
4. Enforce evidence access inheritance and redacted export rules. Treat canonical export hashes as integrity checks only; production signing requires signer identity, key lifecycle, trust and revocation policy.

**Exit criteria**

- Missing, stale, contradictory, and unsupported evidence remains visible.
- Claim references and excerpt bounds are validated; deterministic IDs, dates, and amounts are checked without a model.
- Cross-workspace or unauthorized evidence/export access fails.
- Decision packets show the exact action, applicable rule, evidence, uncertainty, expiry, and what approval unlocks.

### P1.3 Scenario laboratory and semantic comparison

1. Version scenarios with initial fixture state, contract/policy/adapter/model pins, injected events, simulated decisions, expected final state, and invariant assertions.
2. Add all required cases: happy path, missing input, dependency timeout, approval rejection, approval expiry, revoked role, duplicate callback, conflicting evidence, accepted write with lost acknowledgement, and malicious instructions in external content.
3. Keep inspect history, replay recorded outputs, and sandbox re-execution as separate commands.
4. Compare candidate and active versions on paired cases. Store actual paths, attempted effects, final state, latency/cost observations, and deterministic invariant results.

**Exit criteria**

- A suite compares expected with observed final state; a completed run is not automatically a passing case.
- Rehearsal cannot reach live-write credentials or create fixture records outside its isolated store.
- A cheaper candidate that violates permission or duplicates an action fails its release gate.
- A failed case can be saved as a reusable regression linked to the motivating change.

**Current local checkpoint:** each experiment stores the exact versioned scenario definition and fingerprint beside its run set. Simulation writes target an experiment-scoped ephemeral identity instead of fixture connections. Evaluation uses those pins to check final state, required event path, attempted-effect bounds, duplicate operation keys, graph-derived authorization, and absence of ticket/outbox writes; a completed result is fingerprinted and returned without reevaluating against a changed catalog. Archived templates cannot start an experiment. Paired release experiments and promotion remain domain-only work.

### P1.4 Recovery workbench

1. Add typed repair proposals limited to safe retry, reconciliation, approved fallback, new-draft mapping/configuration correction, or human investigation.
2. Bind a proposal to graph revision, run state, action IDs, and payload fingerprint. Revalidate it immediately before application.
3. Show completed work, pending work, known external effects, uncertain results, and available adapter-specific actions.
4. Require affected regression scenarios to pass before a template repair is submitted for release.

**Exit criteria**

- A stale repair cannot apply.
- Unknown writes require reconciliation before retry.
- Completed siblings and upstream outputs remain intact during an eligible failed-node retry.
- Malicious instructions in evidence cannot expand tools, permissions, or secret access.

## P2 — bounded teams, reuse, and controlled improvement

### P2.1 Bounded specialist teams

1. Add TeamRecipe records for roles, allowed tools/data scopes, input/output schemas, delegation rules, maximum turns, budgets, and stopping conditions.
2. Use deterministic coordination and one designated commit actor. Give each consequential internal action its own persisted reservation/checkpoint.
3. Compare each enabled team with a matched-budget single-agent baseline on held-out cases.

**Exit criteria**

- Turn, time, token, and cost limits stop work.
- A team cannot recruit an unapproved tool or broaden access.
- Retrying team work cannot repeat an already committed action.
- Baseline, outcome, latency, and cost results are reported without a fabricated composite score.

### P2.2 Reusable insertion blocks and template finding

1. Add versioned blocks with explicit input/output boundaries. Insertion expands fresh node instances and records source block/version provenance.
2. Add deterministic, permission-filtered Find a template for task creation; an optional model may rerank only the already authorized set.

**Exit criteria**

- Inserted nodes have fresh IDs and changing a source block cannot mutate an existing draft insertion or published release.
- Template finding returns only published templates the current user may start, explains the match, and requires ordinary selection/input validation.

### P2.3 Impact analysis, release experiments, and environment promotion

1. Show templates affected by an agent-version change.
2. Add paired held-out experiments for workflow, agent, model, prompt, connector, and team-recipe changes.
3. Add reviewed environment promotion by rebinding approved connection references without mutating the released contract.

**Exit criteria**

- A seeded regression is visible and blocks promotion.
- Deterministic policy failures cannot be overruled by a model judge.
- Promotion changes future starts only; active runs retain all pins.
- Connection rebinding changes the action fingerprint and requires a fresh applicable approval.

## Production integration gates

These gates remain incomplete until the corresponding real environment is available and tested. Local fixtures must remain available regardless.

| Gate | Required evidence before it may be called complete |
| --- | --- |
| Corporate identity | OIDC issuer/audience validation, directory mapping, real user lifecycle, revocation/delegation tests, and production refusal of development sessions. |
| Distributed execution | A chosen durable production runtime, reliable database-to-runtime delivery, worker restart/failover tests, version-compatible replay, and measured load behavior. The local SQLite scheduler remains the only local authority until this gate is deliberately implemented. |
| Jira and CSR | Approved service contracts, authenticated sandbox connections, contract tests, idempotency/reconciliation behavior, egress controls, and observed receipts. |
| OCI | Confirmed target OCI service, official SDK authentication appropriate to that service, server-side secret/principal setup, tenancy permission tests, and audited sandbox calls. |
| Production notifications | Approved delivery provider, verified sender/recipient policy, bounce/failure handling, rate limits, deduplication, and authenticated deep-link testing. |
| Production artifact storage and scanning | Authorized object store, scoped access, retention/deletion policy, malware and content scanning behavior, backup/restore, and fail-closed production configuration. Local MIME/size/UTF-8/JSON checks do not close this gate. |
| Identity-backed export signing | Approved signing format, protected key or workload identity, signer metadata, verification procedure, rotation/revocation policy, and negative tamper tests. Current SHA-256 manifest/package hashes provide integrity checking only. |

Passing local tests does not close these gates and does not make the application production-ready.

## Verification commands

Run from the repository root unless the command starts by changing directory.

### Required on every implementation checkpoint

```bash
cd app
python3 -m unittest discover -s tests -v
node --check public/app.js
node --check public/icons.js
```

The Python discovery command must include every new domain, HTTP, restart, security, scenario, and release-gate test added during P0/P1/P2.

### View contract and preview

```bash
cd app
python3 scripts/capture_preview.py --output ../preview
node tests/test_ui_contract.js ../preview/preview_data.json
```

This verifies view-function contracts only. It does not count as browser, layout, pointer, responsive, or accessibility verification.

### Local smoke check

```bash
cd app
python3 server.py --port 8765
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8765/api/health
```

Use a temporary database for destructive or failure-injection tests. Use a retained database for explicit migration and restart tests.

### Real-browser verification

On 2026-09-25 a headed-Chrome journey against the retained localhost database verified the payment-dispute demonstration's 14-node/16-edge graph, required typed sample input, complete action-record approval payload, administrator-to-reviewer switch, approval, and terminal result. The run completed 13 of 14 nodes with the unused condition branch correctly skipped and created the isolated local record `DSP-SIM-1C6A98`. The earlier 2026-09-24 clean-database journey verified task-template search, role switching, an exact prepared-action approval, a completed 7/7 fixture run, reduced effect-summary/evidence inspection, a 10/10 required rehearsal suite, desktop rendering, and the 390x844 breakpoint; that journey's browser logs contained no warnings or errors. Exact evidence is in `research/QA_NOTES.md`.

Before a production release, expand that local journey into a repeatable cross-browser/assistive-technology harness covering:

- 1440 × 900 and 1280px desktop: Studio, inspector, Registry, Runs, Decision Inbox, Rehearsal, Connections, error/empty/conflict states;
- 390px viewport: Tasks and My Work/Decision flows;
- keyboard-only creation, insertion, selection, configuration, review, task start, decision, evidence inspection, and recovery;
- focus visibility and restoration, dialog trapping/close, non-color statuses, accessible names, zoom/fit, reduced motion, and unclipped content;
- a real fixture run, process restart while waiting, eligible approval, evidence inspection, lost-acknowledgement recovery, and one retained ticket.

No phase may be marked verified from the Node view-contract test alone. The local reference combines that contract test with the recorded live journey; the broader production matrix remains a separate gate.

## Final completion definition

The local product is complete only when:

1. every required P0, P1, and P2 exit criterion above passes;
2. every applicable acceptance row in `docs/Axiom_Codex_Master_Prompt.md` lines 585–609 has recorded test evidence;
3. the Supplier onboarding and CSR-to-Demo-Jira fixture journeys both work end to end, and a second unrelated process demonstrates reuse;
4. real-browser, keyboard, accessibility, restart, failure-injection, privacy, and workspace-isolation checks pass;
5. measured 50-node editing/rendering and modest concurrent-run results are recorded with machine and environment details, without an unsupported capacity or SLA claim;
6. README, implementation status, architecture decisions, graph/state semantics, agent SDK guide, permissions rules, operations notes, dependency/license inventory, demo script, and known limitations match the code;
7. every production-only dependency is still labeled as an open integration gate unless its real contract and environment have been tested.

Shared executable sub-workflows, arbitrary graph loops, authenticated schedules/webhooks, collaborative editing, request-changes loops, and unspecified additional connectors remain later work unless the scope is deliberately expanded. Their absence does not justify an enabled placeholder or a claim that they are implemented.
