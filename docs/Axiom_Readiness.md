# Axiom delivery and verification

> Historical checkpoint: this document records the Axiom 1.8.0 / SQLite schema 9 release. For the current Axiom 2.0.0 / schema 11 Agent Factory and external-gateway delivery, its 287-test release gate, and current browser evidence, use `START_HERE.md`, `docs/IMPLEMENTATION_STATUS.md`, and `research/QA_NOTES.md`.

This delivery contains an original runnable local application, an explorable snapshot of its actual interface, a complete production implementation prompt, primary-source research, and meeting traceability. It is not a production deployment.

## Start the application

Extract `Axiom_Source.zip`, open its `app` directory, and run:

```bash
python3 server.py --port 8765
```

Open http://127.0.0.1:8765 in a browser. Python 3.10 or newer is required. No package installation or paid workflow platform is required. The default database is `app/.runtime/axiom.sqlite3`. Restarting with that database retains local templates, runs, decisions, and fixture tickets.

The development account selector deliberately exposes seeded roles so the review and execution journey can be tested. It is not corporate authentication.

## What the delivery means

| Area | Implemented local behavior | Remaining production work |
| --- | --- | --- |
| Designer | Create blank templates and immediately choose a first step; place, configure, rename, duplicate, connect, map, and remove steps through visible controls and canvas/node/connection context menus; keyboard alternatives, undo/redo, responsive revision-aware saving, structured condition/parallel compilation, and template duplicate/archive/restore/hash export/import. Read-only seeded roles receive an explicit development-only path to the editing account. | Persisted editor insertion for reusable blocks, multi-user collaborative editing, production identity, explicit whole-graph auto-layout, and formal WCAG/assistive-technology certification. |
| Appearance | Persistent day/night mode across the workflow studio and supporting application surfaces, with an initial saved or system preference, updated browser theme color, and a local toggle whose explicit choice survives reload. | Organization-managed appearance policy, cross-device preference sync, and formal contrast/accessibility certification. |
| Agent registry | Create reusable agents, edit metadata, deprecate while preserving published references, delete only unused custom registrations, refuse deletion of built-ins/references; tested SDK and version-impact API. | Dynamic package installation/registration, arbitrary approved adapters, production secrets, and connector evaluation catalog. |
| AI proposals | Review-before-apply proposals, stale-revision rejection, and at most 100 allowlisted node/config, edge, field-binding, approval-insertion, and same-implementation replacement operations. | Live provider compatibility/quality, requirement compiler, retrieval, grounded claim evaluation, requirement links, and broader natural-language coverage. |
| Execution | SQLite-persisted scheduler; structured conditions, branches, joins and outcomes; pinned releases, migrations, effect ledger, bounded local attachments, and actor-scoped idempotent task starts. | Distributed workers, production queues/streams, measured load/failover, tenant isolation, and production artifact storage/scanning. |
| Human control | Separate manual execution and approval, expiry, complete exact-action packets, mutable generation-bound fixture authority, and authority checks before decision and dispatch. | Corporate OIDC/directory grants, production delegation/revocation, tenant-scoped external identities, and external notification delivery. |
| Evidence | Stored inputs, outputs, events, decisions, claims/conflicts, receipts, access-filtered graph, and recursively redacted hash-sealed run export with Markdown summary. | Persistent external source snapshots, tenant authorization, retention/deletion, production provenance storage, and identity-backed export signing. |
| Rehearsal | Canonical ten-case suite with known answers, actual simulations, deterministic invariants, paired comparison, and regression-case domain records. | Scenario-authoring persistence UI, stochastic/model trials, team evaluation runtime, and promotion workflow. |
| Demonstrations | Five persistent, complex domain workflows for payment disputes, employee access, production incident/change, vendor onboarding, and insurance claims. Each has 14 nodes and 16 edges, typed required inputs, parallel checks, two tested condition routes, full action-record approval, release-pinned/hash-verified fixtures and defaults, safe local simulation, and receipts. | Replace the deterministic local fixtures with reviewed, credentialed production integrations and organization-specific policies before real operational use. |
| Recovery | Lost-acknowledgement fixture, stable operation identity, unknown/reconciled effects, exact operation/fingerprint/payload provider matching, and eligible retry. | Destination-specific live idempotency, reconciliation, compensation, and cancel contracts; no universal exactly-once claim. |
| Integrations | Mutable local directory/ticket/outbox fixtures with allowed operations and generations; reminders resolve local role recipients and persist queued/sent capture receipts and review links. | Real CSR contract, Jira/OCI, production notifications and secret-backed connections. Local fixture testing does not establish external reachability. |
| Advanced product | Domain-tested reusable blocks, permission-filtered template finding, change impact, bounded TeamRecipe planning, paired release safety, and active-run pins. Template finding is wired into task start. | Persistence/API/UI/runtime for blocks and teams, saved release experiments, controlled repair branches, and reviewed promotion. |

The complete target is specified in `Axiom_Codex_Master_Prompt.md`. A documented feature is not counted as implemented merely because it appears in that prompt.

## Integrity and lifecycle boundaries

- This checkpoint is Axiom 1.8.0 with SQLite schema 9 and built-in agent contract 1.3.0.
- Published release records and their hashes stay unchanged. The earlier schema-8 migration created separately hashed compatibility snapshots when older releases needed safe execution metadata; schema 9 adds pinned demonstration fixtures and exact action-field contracts. Every compatibility snapshot stays bound to the source version and hash, and executable snapshots contain one pinned agent version and complete manifest per node.
- API and stored JSON use strict RFC 8259 handling. Duplicate object keys, non-finite numbers, and unpaired Unicode surrogates are rejected; startup checks legacy JSON before applying schema changes.
- Archiving keeps releases, history, and existing runs readable, but blocks new fixture runs, draft simulations, and rehearsal experiments until the template is restored. Both server rules and visible controls enforce this boundary.
- The run-effects route returns aggregate counts and reduced effect summaries, not protected payloads or complete internal ledger records. Run export is an authorized, audited `POST` with recursive redaction and a canonical integrity hash.
- Every experiment pins the versioned scenario definition and fingerprint used by its runs. Simulated writes use an experiment-scoped ephemeral destination, and evaluation checks the pinned final state and event path, attempted-effect bounds, graph-derived authorization, duplicate operation keys, and absence of fixture writes. Even a completed experiment must pass pinned-scenario presence and shape checks before its cached result is accepted.

## Verification evidence

The accompanying tests exercise domain services, real local records, and HTTP requests. The final 2026-09-25 discovery run passed all 170 Python tests. Python byte-compilation and JavaScript syntax checks passed. The Node VM contract harness also passed with 28 route renders, 72 run renders, 7 inspector renders, 2 mapping modals, 18 evidence modals, 1 effects modal, and 18 repair modals. Commands and browser evidence are in `research/QA_NOTES.md`.

- Restart with in-flight work and finish the same logical run.
- Lose the response after a local ticket is created, restart, reconcile, and retain one ticket after retry.
- Reject a wrong-role decision and deduplicate repeated approvals.
- Keep existing runs on their immutable version after another version is published.
- Reject stale draft/proposal updates and preserve frozen release candidates.
- Keep simulation from inserting local ticket records.
- Preserve all five named demonstration workflows across restart without overwriting local edits; verify every happy-path simulation and all five required ten-case suites at 50/50, with zero external writes and zero unauthorized effects.
- Fail a malformed run without stalling an unrelated healthy run.
- Keep the scheduler progressing while a model request waits outside the database lock.
- Reject undeclared, path-invalid, or type-incompatible mappings using template and built-in agent schemas.
- Deduplicate identical actor-scoped task starts and ingest bounded JSON/text/CSV attachments once; reject malformed or changed-key requests atomically.
- Revoke a prepared or approved local connection generation before dispatch without creating a ticket, while still reconciling an already accepted exact write once.
- Require a complete multi-action approval packet, preserve self-gated approval across restart, and refuse mismatched provider records as safe recovery.
- Duplicate/archive/restore templates, verify hash-checked template import/export, and refuse deletion of referenced agents.
- Redact secret-looking fields and raw external content in run exports and provide an integrity hash without claiming a digital signature.

The final headed-Chrome journeys on 2026-09-25 used the real server at `127.0.0.1:8765`. They verified the payment-dispute demonstration's 14-node/16-edge graph, required domain sample, complete action-record approval payload, and successful simulation with 13 of 14 nodes completed plus the correctly skipped branch. The resulting `DSP-SIM` record stayed isolated from the durable ticket fixture. They also created a blank workflow, opened its first-step picker, placed and configured nodes, exercised node and canvas context actions, saved the draft, reloaded it, and confirmed that an explicitly selected night theme persisted across reload. This is not a complete WCAG audit. The five demonstrations use deterministic local fixtures: they are realistic, repeatable simulations, not live payment, identity, incident, vendor, insurance, Jira, or OCI integrations. The theme is a local browser preference, and the editor remains a single-workspace reference implementation. No live model, corporate identity, production email, production artifact scanning, identity-backed export signature, distributed-runtime, or production-scale result is claimed.

## Explorable preview

`Axiom_Studio_Preview.html` embeds six templates and 18 recorded runs produced by the local runtime, including completed simulations for the five complex demonstration workflows. Navigation, selection, graph positioning, and inspection are local. It does not run workflows, publish changes, send messages, call a model, or save server state. Start the application for those supported local operations.

Regenerate it from the source:

```bash
python3 scripts/capture_preview.py --output ../preview
```

## Research and meeting coverage

The two research briefs distinguish existing platform features from proposed advantages. The architecture links planning, evidence, approvals, testing, and recovery with explicit evaluation hypotheses. It makes no unsupported claim of market superiority or transferred research-paper performance.

The meeting matrix has 30 timestamped requirements. Video review used a full scene-change scan and inspection of 156 clustered keyframes, supplemented by sampled and selected full-resolution frames. It did not individually inspect all 32,897 frames. The supplied transcript remains the primary record of spoken requirements.
