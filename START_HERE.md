# Axiom delivery and verification

New to workflow software or AI agents? Start with [Axiom: the complete beginner's guide](AXIOM_BEGINNER_GUIDE.md). It explains the product from first principles, walks through realistic examples, and clearly separates local demonstrations, configured integrations, and remaining production work.

This delivery contains Axiom 2.2.0, an original runnable local application with SQLite schema 13, an explorable snapshot of its interface, a complete production implementation prompt, primary-source research, and meeting traceability. This release includes the governed external-connection gateway, stateful Simulation Lab, adaptive Agent Factory, reusable Goal Agent workflow nodes, and durable version-pinned workflow scheduling. It is not a production deployment.

## Start the application

Extract `Axiom_Source.zip`, open its `app` directory, and run:

```bash
python3 server.py --port 8765
```

Open http://127.0.0.1:8765 in a browser. Python 3.10 or newer is required. No package installation or paid workflow platform is required. The default database is `app/.runtime/axiom.sqlite3`. Restarting with that database retains local templates, runs, decisions, and fixture tickets.

The development account selector deliberately exposes seeded roles so the review and execution journey can be tested. It is not corporate authentication.

## Build a workflow from scratch

Use the administrator development account, choose **New** in Studio, and name the workflow. Axiom creates an empty draft and immediately opens the reusable-agent palette so the first step can be placed without another setup screen. Choose an existing capability, configure it in the inspector, and save the draft. The palette, blank-canvas action, and canvas menu also expose the supported path for registering a reusable agent backed by an existing local implementation; its shared name and description can later be edited from the Agent Registry or a node's action menu. This does not upload or install arbitrary code.

Right-click a node for configure, rename, add-connected, duplicate, connect, mapping, agent inspection/editing, and confirmed removal actions. Right-click a connection to inspect or remove it, or right-click empty canvas space to add at that position, register an agent, fit the graph, undo, or redo. The visible ellipsis button supports pointer and touch use. Keyboard users can open the same menus with the Context Menu key or **Shift+F10**, move through them with the arrow, Home, and End keys, close them with Escape, save with **Ctrl/Cmd+S**, and duplicate the selected step with **Ctrl/Cmd+D**. Actions that change a draft remain role- and lifecycle-gated.

The header button switches between day and night mode and remembers that preference in the current browser. If a reviewer or another read-only development role opens Studio, the banner offers a direct switch back to the seeded editing account; unsaved work still requires confirmation before the saved draft is reloaded. These conveniences are local demonstration UX, not production identity or user-preference storage.

## Create an adaptive Goal Agent

Open **Agent Factory** as the administrator. Define the stable mission and operating instructions, permitted input paths, allowed capability contracts, typed input and result schemas, required evidence, stop/escalation rules, policy references, evaluation cases, and time/tool/model/cost limits. Saving creates a validated draft; it does not make that draft available to workflows.

Switch to the separate reviewer development account and activate the exact saved version. Only an approved version appears as a reusable **Goal Agent** in the workflow palette. A placement pins that specification version and its capability contracts, so later drafts cannot change an already published workflow or active child session.

The run inspector records the real decision → action → observation order, scoped clarification requests, exact prepared writes, approvals, evidence, resource usage when the provider reports it, typed results, and trusted outcome-validation status. Bundled service, invoice, and access variations use a prominently labeled scripted fixture provider for repeatable offline demonstrations. They do not call an AI model or prove model quality. Configured-model execution uses the server-side provider settings described in `app/README.md`; missing or incompatible configuration produces a visible error and never silently substitutes a fixture.

## Connect Slack, Jira, Confluence, or a webhook

Open **Connections** as the administrator and select a bounded provider preset. Choose only the reviewed operations the connection needs, supply the exact approved provider base URL, and reference each credential as `env:VARIABLE_NAME`. Set those environment variables in the server process; public responses never return their names or values. Slack and Atlassian presets include a safe read-only health operation. A ready connection's reviewed operations become stable Agent Factory capabilities, but an external write still requires a saved Goal Agent plan and exact-action approval.

The gateway enforces strict schemas, native-provider destination pinning, DNS/address checks, redirect refusal, response size/time limits, generation/version pinning, and stale-result rejection. A new connection remains a draft until its server-side credentials exist, its registered diagnostic passes when available, and an administrator activates it. The Generic REST card can inspect a fully inlined OpenAPI 3.1 JSON document, but every returned candidate remains unclassified and non-executable. No live Slack or Atlassian tenant and no webhook receiver was authenticated during recorded verification. OAuth consent/callback/refresh, browser activation of generic OpenAPI contracts, a configured MCP host client, automatic retry, provider-specific external reconciliation, and inbound webhook receipt remain integration work. See `app/README.md` and `docs/EXTERNAL_INTEGRATIONS.md` before supplying credentials.

## Demonstration workflows

The local database starts with six published workflows: the original CSR resolution workflow and five complex demonstrations designed for realistic presentations:

- **Payment dispute investigation** traces a disputed payment, compares identity and settlement evidence in parallel, routes higher-value cases, requires review of the complete action, and creates one simulated dispute record.
- **Employee access governance** checks employee, manager, conflict, and license facts, routes privileged access for added review, and creates one time-bound simulated access record.
- **Production incident and change control** combines telemetry and customer impact, routes severe incidents, reviews a bounded mitigation, and creates one simulated change record.
- **Vendor risk and procurement onboarding** checks security and corporate evidence, routes material contracts for enhanced review, and creates one simulated procurement record.
- **Insurance claim adjudication** compares coverage and fraud evidence, routes higher-value claims, requires adjuster review, and creates one simulated claim record.

Each demonstration is a published 14-step, 16-connection workflow with typed required input, parallel checks, both condition routes, exact full-action approval, a local simulated record, and a final receipt. These use deterministic local fixture data so the same demo can be repeated reliably. They do not connect to external payment, identity, monitoring, procurement, insurance, Jira, or cloud systems.

## Schedule a workflow

Open **Schedules** to select an active published workflow and run its exact current release once, hourly, daily, or weekly. Enter a local start date/time and IANA timezone, review the JSON input, then create the schedule. The schedule can be paused, resumed, edited, run immediately, or archived according to the visible role policy. Generated runs link back to their schedule, and schedules show their last and next run.

Schedules persist through restart and do not silently move to a newly published workflow version. The local worker prevents overlapping runs from the same schedule and coalesces missed times after downtime into one catch-up start. The server must be running for dispatch; this is not a distributed or high-availability scheduler. See [the complete scheduling guide](docs/SCHEDULING.md).

The seed process is safe to run again: it adds a missing built-in workflow ID without replacing a workflow already stored under that ID. Each published demonstration release pins and hashes its fixture manifest and defaults so later runs can verify the exact data contract used by that release.

## What the delivery means

| Area | Implemented local behavior | Remaining production work |
| --- | --- | --- |
| Designer | Create blank templates with an immediately opened step palette, place/connect/duplicate/configure nodes through canvas and keyboard menus, keep Save available on responsive layouts, use nested type-compatible mappings, undo/redo, revision-aware saving, structured validation/compilation, persistent browser day/night mode, and template duplicate/archive/restore/hash export/import. | Persisted editor insertion for reusable blocks, collaborative editing, explicit auto-layout, server-backed user preferences, and formal assistive-technology/WCAG certification. |
| Agent registry | Create reusable built-in aliases, edit metadata, deprecate while preserving history, delete only unused custom registrations, refuse built-in/referenced deletion; tested SDK and impact API. | Dynamic package registration, arbitrary approved adapters, connector evaluation catalog, and production secret-backed connections. |
| Agent Factory | Author versioned Goal Agent specifications; constrain context, capabilities, schemas, policies and budgets; require separate reviewer activation; run durable adaptive sessions; request scoped clarification; inspect action/observation history; approve exact prepared actions; compare controlled behavior variations; and place approved pinned versions into workflows. | Live-model planning/evaluation, production capability adapters and credentials, authoritative validators for custom domains, tenant isolation, retention/observability, distributed execution, load/failover evidence, and formal accessibility certification. |
| AI proposals | Review-before-apply proposals, assumptions, stale-revision rejection, and at most 100 allowlisted node/config, edge, field-binding, approval-insertion, and same-implementation replacement operations. | Live provider compatibility/quality, requirement compiler, retrieval, grounded claim evaluation, requirement links, and broader language coverage. |
| Execution | SQLite-persisted local scheduler; one-time/hourly/daily/weekly version-pinned schedules; structured branch/join/outcome handling; ordered migrations, effect ledger, bounded local attachments, and actor-scoped idempotent task starts. | Distributed workers, production queues/streams, load/failover testing, tenant isolation, and production artifact storage/scanning. |
| Human control | Separate manual execution and approval, eligible local roles, expiry, complete exact-action packets, and generation-bound fixture authority rechecked before decision and dispatch. | Corporate OIDC/directory grants, production delegation/revocation, tenant-scoped external identities, and external notification delivery. |
| Evidence | Adapter records, events, decisions, hashes, receipts, access-filtered evidence, and recursively redacted hash-sealed run export with Markdown summary. | Persistent external source snapshots, retention/deletion, tenant authorization, production provenance storage, and identity-backed export signing. |
| Rehearsal | Versioned ten-case known-answer catalog, isolated required-suite execution, deterministic invariants, paired comparison and regression-case domain primitives. | Scenario authoring/persistence UI, repeated stochastic/model trials, team evaluations, and release-promotion workflow. |
| Recovery | Lost-write fixture, stable operation identity, explicit unknown/reconciled states, exact operation/fingerprint/payload provider matching, and eligible retry. | Destination-specific live idempotency/reconciliation contracts, compensation/cancel contracts, and controlled repair workflow. |
| Integrations | Governed connection catalog and workspace; bounded Slack, Jira Cloud, Confluence Cloud, and outbound-webhook presets; server-side `env:` references; safe health/read calls; stable capability compilation; generation/version pinning; exact approved Goal Agent writes; and explicit unknown remote outcomes. | Live tenant/receiver verification, production secret manager, complete OAuth lifecycle, generic OpenAPI activation, MCP host client, inbound webhooks, automatic retry scheduling, provider-specific reconciliation, real CSR/OCI/finance/directory contracts, and production auth/tenant isolation. |
| Advanced product | Tested domain services for reusable block expansion, permission-filtered template finding, change-impact analysis, bounded TeamRecipe planning, paired release safety, and active-run pin preservation. Template finding has a task-start interface; impact has a local route. | Persistence/API/UI/runtime for blocks and teams, saved release experiments, controlled repair branches, and reviewed environment promotion. |

The complete target is specified in `Axiom_Codex_Master_Prompt.md`. A documented feature is not counted as implemented merely because it appears in that prompt.

## Integrity and lifecycle boundaries

- This checkpoint is Axiom 2.2.0 with SQLite schema 13 and built-in deterministic-agent contract 1.3.0.
- Schema 10 added durable Goal Agent specifications, immutable published versions, adaptive sessions, and parent/child workflow bindings. Schema 11 added the governed external-connection gateway and its health records. Schema 12 added the stateful Simulation Lab. Schema 13 adds durable workflow schedules. Migrations preserve earlier application records and do not rewrite prior published workflow releases or their hashes. Earlier compatibility snapshots remain separately hashed and bound to their source version/hash.
- A Goal Agent draft is configuration, not executable authority. Reviewer activation creates the approved version and workflow alias; runs pin the exact specification, tool contracts, and result contract they started with.
- API and stored JSON use strict RFC 8259 handling. Duplicate object keys, non-finite numbers, and unpaired Unicode surrogates are rejected; startup checks legacy JSON before applying schema changes.
- Archiving keeps releases, history, and existing runs readable, but blocks new fixture runs, draft simulations, and rehearsal experiments until the template is restored. Both server rules and visible controls enforce this boundary.
- The run-effects route returns aggregate counts and reduced effect summaries, not protected payloads or complete internal ledger records. Run export is an authorized, audited `POST` with recursive redaction and a canonical integrity hash.
- Every experiment pins the versioned scenario definition and fingerprint used by its runs. Simulated writes use an experiment-scoped ephemeral destination, and evaluation checks the pinned final state and event path, attempted-effect bounds, graph-derived authorization, duplicate operation keys, and absence of fixture writes. Even a completed experiment must pass pinned-scenario presence and shape checks before its cached result is accepted.

## Verification evidence

The accompanying tests exercise domain services, real local records, strict integration contracts, and HTTP requests. The Axiom 2.2 discovery gate passed **338/338 tests in 70.056 seconds** on 2026-10-01, including 16 focused scheduling tests. The prior Axiom 2.1 **322/322**, Axiom 2.0 **287/287**, Axiom 1.9 **235/235**, and supplied factory source checkpoint's historical 113-test results remain separate dated baselines. Commands and current evidence are recorded in `research/QA_NOTES.md` and `factory/Verification.md`.

Node syntax passed for `app.js`, `icons.js`, and `theme.js`; Python `compileall` and JSON validation passed. Both preview captures passed the UI contract with **32 route, 72 run, 7 inspector, 2 mapping-dialog, 18 evidence-dialog, 1 effects-dialog, and 18 repair-dialog renders** apiece. Important covered behaviors include:

- Restart with in-flight work and finish the same logical run.
- Lose the response after a local ticket is created, restart, reconcile, and retain one ticket after retry.
- Reject a wrong-role decision and deduplicate repeated approvals.
- Keep existing runs on their immutable version after another version is published.
- Reject stale draft/proposal updates and preserve frozen release candidates.
- Keep simulation from inserting local ticket records.
- Fail a malformed run without stalling an unrelated healthy run.
- Keep the scheduler progressing while a model request waits outside the database lock.
- Preserve a scheduled workflow's exact release pin across later publication and restart; coalesce missed times, prevent overlap, and deduplicate automatic and manual starts.
- Reject unsupported schemas/rules and malformed structured graphs before publication.
- Bind both directly approval-required writes and directly guarding explicit Approval controls to the exact downstream prepared action, and reject stale approval references or operation-key reuse with different action data.
- Keep contradictory evidence visible and prevent access-filtered exports from leaking hidden references.
- Preserve source blocks/templates and active-run pins while evaluating reusable insertions and future releases.
- Validate task input and nested mappings against explicit template and built-in agent schemas; reject undeclared, path-invalid, or type-incompatible mappings.
- Deduplicate identical actor-scoped task starts, ingest bounded JSON/text/CSV attachments once, and fail malformed or changed-key requests atomically.
- Test/revoke/restore local connection authority with audited generation changes; block stale approvals and new dispatch while retaining exact reconciliation for an already accepted write.
- Require complete multi-action approval packets and preserve self-gated approval idempotency across restart.
- Duplicate/archive/restore templates, verify hash-checked import/export, and delete only unused custom agents.
- Redact secret-looking fields and raw external content in run exports and expose a canonical integrity hash without claiming an identity-backed signature.
- Publish all five demonstration workflows with pinned, hash-verified fixture manifests and retain existing stored workflows when a missing seed is backfilled.
- Retain regression coverage for every case in the five deterministic demonstration suites, including the invariant that simulations create no external or unauthorized writes.
- Reject unregistered or unauthorized adaptive capabilities, over-budget sessions, invalid structured decisions, stale model responses, changed prepared actions, and context outside declared paths.
- Preserve durable Goal Agent sessions across restart, keep model calls outside the persistence lock, and bridge a pinned child result or pause state back to its parent workflow.
- Exercise the same saved fixture agent against different evidence so its ordered capability path changes, while clearly separating scripted runtime verification from live-model evaluation.

Current and historical headed-browser evidence is maintained in `research/QA_NOTES.md`. The current Agent Factory journey covers custom activation and workflow placement, three observation-dependent service paths, separate exact-action review, truthful unavailable-provider controls, theme persistence, keyboard/context menus, and responsive Save access. Full accessibility and cross-browser certification remain separate work.

A separate headed-browser builder check created and saved **Workflow Builder Quickstart**, placed two reusable-agent steps with one connection, and confirmed that the saved graph remained available. It then exercised the right-click step actions for rename, duplicate, and confirmed removal; the reviewer read-only banner's editing-account switch; night-mode persistence after reload; and visible Save access at an 800-pixel browser width. This verifies the recorded local builder journey, not collaborative editing, production identity, complete keyboard/accessibility conformance, or cross-browser visual equivalence.

## Explorable preview

`Axiom_Studio_Preview.html` embeds six templates and 18 workflow runs produced by the local runtime, including a completed realistic simulation for each of the five complex demonstrations and the full required ten-case Payment dispute suite. Its Agent Factory capture adds **13 controlled scenarios and 13 corresponding factory runs**: six primary paired demonstrations and **7 controlled variations**. Navigation, selection, graph positioning, and inspection are local. It does not run workflows, publish changes, send messages, call a model, or save server state. Start the application for those supported local operations.

Regenerate it from the source:

```bash
python3 scripts/capture_preview.py --output ../preview
```

## Research and meeting coverage

The two research briefs distinguish existing platform features from proposed advantages. The architecture links planning, evidence, approvals, testing, and recovery with explicit evaluation hypotheses. It makes no unsupported claim of market superiority or transferred research-paper performance.

The meeting matrix has 30 timestamped requirements. Video review used a full scene-change scan and inspection of 156 clustered keyframes, supplemented by sampled and selected full-resolution frames. It did not individually inspect all 32,897 frames. The supplied transcript remains the primary record of spoken requirements.
