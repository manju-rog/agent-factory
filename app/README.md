# Axiom

Axiom 2.0.0 is a runnable local workflow application using SQLite schema 11. It combines an original workflow authoring interface with an adaptive Agent Factory, reusable version-pinned Goal Agent nodes, typed graph proposals, structured validation, role-controlled execution, persisted runs and write effects, bounded task attachments, a governed external-connection gateway, an approval inbox, evidence inspection, and isolated rehearsals. It remains a local reference application rather than a production deployment.

## Run

Use Python 3.10 or newer. The reference application uses Python's standard library and does not require a package install.

```bash
python3 server.py --port 8765
```

Open [Axiom locally](http://127.0.0.1:8765). The server binds to localhost. Its SQLite database persists local work; the exact database argument and defaults are documented by `python3 server.py --help`.

The account control is explicitly a development account switch. It is intended to demonstrate different permissions using seeded local identities. It is not production authentication. Do not expose this server to a public network.

## Build a workflow from scratch

1. Use the administrator development account, open Studio, choose **New**, and enter a name and purpose. The new empty draft is selected and its reusable-agent palette opens automatically.
2. Choose the first capability. Use **Add step** for another independent placement, or right-click a node and choose **Add connected step** to place and connect the next capability in one operation. Configure the selected step in the inspector and use **Save draft**; Save remains present on tablet and mobile layouts.
3. Right-click a node to configure, rename, add after, duplicate without copying its connections, connect from it, map inputs, inspect or edit its reusable agent, or remove it after confirmation. Right-click a connection to inspect or remove it. Right-click empty canvas space to add at that point, register an agent, fit, undo, or redo.
4. The node ellipsis opens the same menu without a right-click. The Context Menu key or **Shift+F10** opens node, connection, and canvas menus from the keyboard; Arrow keys, Home, End, and Escape navigate or close them. **Ctrl/Cmd+S** saves, **Ctrl/Cmd+D** duplicates the selected node, and **Ctrl/Cmd+Z** undoes.
5. An administrator can register a reusable agent from the step palette, the empty-canvas menu, or **Agent registry → New agent**. Edit its shared display name and description from its Registry contract view or **Edit reusable agent details** on a workflow node. Registrations wrap an existing local implementation; arbitrary code upload is intentionally outside this application.

Use the moon/sun button in the header to switch between day and night mode. The choice persists in that browser through `localStorage`; it does not alter workflow data or create a server-side user preference. A read-only reviewer, operator, or contributor sees a banner that can switch directly to the seeded administrator editing account. That shortcut uses the same local development-session API as the account selector and asks before discarding unsaved draft changes; it is not production authentication.

## Build and reuse a Goal Agent

1. Open **Agent Factory** as the administrator and create a specification with a stable mission, operating instructions, permitted context paths, selected capabilities, typed input/result contracts, evidence requirements, stop rules, policies, evaluation cases, and resource limits.
2. Save the specification. It remains a draft and cannot be placed or run merely because it validated.
3. Switch to the reviewer development account and activate that exact version. Self-publication is refused. The approved version is registered as a Goal Agent palette entry.
4. Place the Goal Agent in a workflow. Its specification version and capability contracts are pinned; replacing the node is an explicit upgrade rather than a silent adoption of a later draft.
5. Run a labeled scripted variation or a configured-model case. The inspector exposes the action/observation timeline, scoped questions, exact prepared-action target and arguments, policy and authorization scope, evidence/source versions, approval fingerprint, resource usage when known, typed result, and outcome validation.

The bundled service, invoice, and access variations use deterministic scripted decisions through the same runtime validation and persistence loop. They are fixtures, not AI. They establish runtime behavior but not live-model planning quality or external delivery.

## Connect an external service

Open **Connections** as the administrator. The Axiom 2.0 catalog exposes bounded presets for Slack, Jira Cloud, Confluence Cloud, and an outbound JSON webhook. For each connection:

1. Select only the reviewed read/write operations needed for that connection. Axiom derives their declared scopes and does not accept executable operation definitions from the browser.
2. Enter the exact approved API base URL. Native provider credentials are pinned to Slack's API origin or the corresponding Atlassian Cloud product path; redirects and destination changes are rejected.
3. Reference credentials as `env:VARIABLE_NAME`, then set those variables in the server process before startup. The connection record stores only the reference, and public responses expose only configuration/availability booleans—not the variable name or secret value.
4. Create the connection as a draft or explicitly ready. Where the preset has a registered health operation, use **Test** to perform that safe read. Direct **Invoke** requests are restricted to explicitly registered reads.
5. Add a ready connection's capability to a reviewed Goal Agent specification. External writes cannot be invoked directly: the runtime stores the exact request, pauses for the exact-action approval, rechecks relevant source observations and the connection generation, and dispatches that stored request only after approval.

These paths can execute outbound requests when an administrator supplies valid server-side credentials and a reachable approved destination. The Connections screen also offers an inspect-only OpenAPI 3.1 JSON flow; its candidates are not executable and cannot create a connection. No live Slack workspace, Jira/Confluence site, or webhook receiver was used in the recorded verification. OAuth consent/callback/refresh, generic OpenAPI activation, a configured MCP host client, automatic external retries, provider-specific external reconciliation, and inbound webhook receipt are not implemented. An uncertain remote write stops for manual/provider-specific reconciliation rather than being retried blindly. See `../docs/EXTERNAL_INTEGRATIONS.md` for the provider and security contract.

## Try the complete journey

1. Open Studio. Select the seeded CSR workflow or follow the from-scratch builder above. Drag and configure steps, connect ports or use the right-click menus, then save the draft. Templates can be duplicated, archived/restored, and exported/imported as hash-checked packages. The agent registry supports reusable configured agents, metadata editing, deprecation, deletion only when unused, and preservation of every draft/release/run reference.
2. Ask the local planner for a concrete change such as “Make CSR manual for a contributor” or “Add approval before ticket creation.” Inspect assumptions, operations, and validation before applying. The server accepts only bounded `update_node`, `add_node`, `remove_node`, `add_edge`, `remove_edge`, `bind_field`, `insert_approval`, and same-implementation `replace_agent` operations.
3. Run a rehearsal case or the required ten-case suite and inspect the recorded node states, invariants, effects, and evidence. Simulation is labeled and does not create fixture tickets.
4. Submit a draft for review. Change to the reviewer development account, inspect the release diff, and publish.
5. Start a fixture task by selecting the published template. Enter JSON input or load a JSON file, and optionally attach up to five bounded UTF-8 JSON, text, or CSV files. The browser supplies an idempotency key so a repeated identical start returns the same run instead of ingesting the files twice. Use the relevant development account to execute a manual node or decide an approval.
6. Inspect the completed local ticket, effect ledger, evidence receipt, and redacted hash-sealed run export. Try a lost-acknowledgement scenario, reconcile the retained write, and recover the eligible failed step.
7. Open Connections as an administrator to configure a bounded external preset or test, revoke, and restore an existing authority. Authority changes increment the connection generation; prepared actions recheck it before approval and dispatch.
8. Restart the server with the same database and inspect the retained templates, runs, decisions, attachments, connections, and fixture tickets. Environment credential values are intentionally not stored in SQLite and must still be present in the server process.

The exact supported endpoints and data shapes are in CONTRACT.md. Tests and the supplied verification report state which behaviors have been exercised.

## Included demonstration workflows

The database begins with six published workflows: the original CSR resolution workflow plus five presentation-ready demonstrations.

1. **Payment dispute investigation** — checks identity and payment settlement evidence, routes higher-value disputes, and creates one governed local dispute record.
2. **Employee access governance** — checks employment, manager intent, role conflicts, and license exposure, then creates one time-bound local access record.
3. **Production incident and change control** — combines telemetry and customer impact, reviews a bounded mitigation, and creates one local change record.
4. **Vendor risk and procurement onboarding** — checks security and corporate evidence, applies enhanced review to material contracts, and creates one local procurement record.
5. **Insurance claim adjudication** — checks coverage and fraud evidence, routes higher-value claims, and creates one local adjudication record.

Each demonstration has 14 steps and 16 connections. It validates typed required input, runs checks in parallel, tests both condition routes, requires approval of the complete action record, creates a simulated local record, and produces a receipt. The stored release pins and hashes its fixture manifest and defaults. If a built-in seed ID is missing at startup, Axiom restores it without replacing a workflow that already exists under that ID.

These demonstrations use deterministic local fixtures. They look and behave like realistic governed workflows, but they do not contact external payment, identity, monitoring, procurement, insurance, Jira, or cloud services.

## Implemented local boundaries

- `domain.py` provides the constrained schema validator, conservative schema-assignability checks, deterministic rule AST, canonical hashes, and semantic/layout separation. Within its documented subset, assignability checks scalar/array bounds, finite enums/constants, nested required and optional properties, and closed or typed additional properties. It is not general JSON Schema.
- `workflow.py` validates and compiles the bounded structured DAG. Published snapshots pin compiler/interpreter versions and the compiled plan; the local runtime handles condition selection, skipped branches, joins, outcomes, manual gates, and approvals.
- `evidence.py` validates source snapshots, excerpt bounds, transformations, claims and conflicts, decision packets, receipts, access inheritance, and redacted access-filtered export. The run evidence endpoint builds a local evidence graph from recorded run data.
- SQLite stores ordered migration markers, actor-scoped idempotent task-start records, bounded attachment records, mutable connection records, and a write-effect ledger. Write nodes are prepared before dispatch, retain operation identity, reject changed fingerprints or connection generations, and reconcile an exact matching local ticket before retry.
- Template input schemas and built-in agent input/output schemas drive server-side task validation and mapping validation. Mappings must reference a declared compatible field that is available on every path; the mapping dialog exposes the same nested, type-compatible choices.
- Local task attachments are limited to five UTF-8 JSON, text, or CSV files, 256 KiB each and 512 KiB total. Public run/evidence views expose metadata and SHA-256 only. This is bounded local ingestion, not malware scanning or production object storage.
- Run exports are authorized, audited, schema-versioned, recursively redact secret-looking fields and raw `externalContent`, and include a canonical SHA-256 `manifestHash`. That hash detects modification; it is not an identity-backed digital signature.
- Local fixture connection records expose allowed operations, status, principal reference, and generation. Schema-11 external records additionally pin provider, exact base URL, authentication mode, server-side credential references, scopes, reviewed operation contracts, time/size/rate/retry settings, and authority generation. Public views omit credential references and values. Administrator create/test/read-invoke/revoke/restore paths are audited; generation or contract changes invalidate stale work. Only a successful call against the intended tenant can establish current reachability.
- `integrations.py` supplies strict Slack, Jira Cloud, Confluence Cloud, webhook, generic REST/OpenAPI, and MCP contracts; exact call preparation; credential injection at dispatch; native-provider origin pinning; DNS/address and redirect controls; response validation; and stable capability compilation. The server currently enables browser setup only for Slack, Jira Cloud, Confluence Cloud, and outbound webhooks. Generic OpenAPI activation and remote MCP execution remain developer-review-required.
- `scenarios.py` defines the complete ten-case known-answer catalog, deterministic invariant evaluation, paired comparison, and regression-case records. The server exposes the catalog and can run the core or required simulation suite. Completed experiments validate that their pinned scenarios are present and well formed before returning a cached evaluation.
- `governance.py` supplies deterministic reusable-block expansion, template finding, agent impact analysis, bounded team planning, and paired release selection. Template finding and impact analysis have local API routes; blocks, team planning, and release selection are domain services only.
- `agent_sdk.py` supplies a provider-neutral manifest, validated execution wrapper, restricted named connector operations, and safe scaffolding. It is not yet a dynamic package-install or server registration system.

Protected writes use prepare → approve → dispatch. A write with `approvalRequired`, or a directly preceding explicit Approval control, prepares the downstream action before review and binds the decision to its immutable payload, destination, operation generation, action fingerprint, connection generation, evidence snapshot, policy, reviewer scope, and expiry. Any material change requires a new approval. A revoked connection blocks a new dispatch. Local fixtures retain their tested reconciliation path; uncertain external writes remain stopped because provider-specific reconciliation is not implemented.

## AI provider

The workflow-edit proposal planner defaults to the deterministic and clearly labeled `local-planner`. Agent Factory fixture variations use the separately labeled `scripted-fixture` provider. Neither is presented as AI.

Configured-model Goal Agent execution and optional AI specification proposals use the server-side chat-completion adapter with these environment variables:

```text
AXIOM_MODEL_ENDPOINT
AXIOM_MODEL_NAME
AXIOM_MODEL_API_KEY
AXIOM_MODEL_INPUT_COST_MICROS_PER_MILLION
AXIOM_MODEL_OUTPUT_COST_MICROS_PER_MILLION
```

`AXIOM_MODEL_ENDPOINT` and `AXIOM_MODEL_NAME` are required for model mode; the key and pricing rates are optional. The endpoint must satisfy the adapter's HTTPS or loopback-HTTP boundary. Credentials remain server-side. An absent, incompatible, or failing provider produces a visible error; the runtime never silently falls back to scripted decisions.

Use an approved endpoint and verify its compatibility, model behavior, pricing metadata, retention, and availability with your actual service. Controlled loopback transport tests and local fixtures do not establish live-model planning quality, prompt-injection resistance, privacy compliance, or production authorization.

## Source layout

| Path | Purpose |
| --- | --- |
| server.py | HTTP API, SQLite persistence/migrations, scheduler, fixtures, prepared effects, and local policies. |
| domain.py | Constrained schemas, rules, canonical hashes, and semantic/layout separation. |
| workflow.py | Structured graph validation and deterministic compilation. |
| evidence.py | Evidence graph records, validation, access filtering, and redaction. |
| scenarios.py | Versioned known-answer scenarios, invariant evaluation, and paired comparison. |
| agent_sdk.py | Capability manifests, validated execution boundary, restricted connectors, and scaffolding. |
| agent_factory.py | Shared adaptive decision loop, strict specifications and capability contracts, context projection, budgets, prepared actions, clarification, provider adapter, and completion checks. |
| integrations.py | External connection contracts, reviewed provider presets, exact request preparation, egress checks, strict adapters, OpenAPI inspection primitives, and MCP protocol interfaces. |
| factory_fixtures.py | Labeled local service, invoice, access, and artifact capabilities, deterministic decisions, controlled variations, and domain-owned outcome validators. |
| governance.py | Blocks, template finding, impact analysis, bounded teams, and release decisions. |
| public/index.html | Application entry. |
| public/styles.css | Original application design system and responsive layout. |
| public/app.js | Studio and operational UI interactions. |
| public/icons.js | Self-contained interface icon definitions. |
| tests | Domain, compiler, evidence, SDK, governance, scenario, runtime, ledger, and HTTP checks. |
| CONTRACT.md | Shared API and domain contract. |

Run tests from the application directory:

```bash
python3 -m unittest discover -s tests -v
```

The Axiom 2.0 discovery gate passed **287/287 tests in 34.162 seconds** on 2026-09-25. The completed Axiom 1.9 gate and historical 113-test factory source checkpoint remain separate dated baselines. Current commands and evidence are maintained in `../research/QA_NOTES.md`; focused adaptive-runtime evidence is in `../factory/Verification.md`.

To regenerate the offline interface preview from recorded fixture runs:

```bash
python3 scripts/capture_preview.py --output ../preview
```

The optional view-template contract check requires Node, which is not needed to run the application:

```bash
node --check public/app.js
node --check public/icons.js
node --check public/theme.js
node tests/test_ui_contract.js ../preview/preview_data.json
node tests/test_ui_contract.js ../output_v2/preview_data.json
```

Node syntax passed for all three application scripts. Both regenerated preview captures passed the view contract; each produced **28 route, 72 run, 7 inspector, 2 mapping-dialog, 18 evidence-dialog, 1 effects-dialog, and 18 repair-dialog renders**. Python `compileall` and repository JSON validation also passed. The preview data includes **13 factory scenarios and 13 factory runs**, including **7 controlled variations**.

The view-contract check executes view functions with document stubs. Headed-browser evidence is maintained separately in `../research/QA_NOTES.md`; the recorded Axiom 1.9 Agent Factory journey covers custom activation and placement, adaptive and clarification paths, separate exact-action review, provider-unavailable controls, theme persistence, menus, and responsive Save access. Record a separate Axiom 2.0 Connections browser check rather than treating that earlier journey as external-provider evidence. Neither the focused journey nor the Node VM checks certify broad browser compatibility or accessibility.

The same-date headed-browser builder journey created and saved **Workflow Builder Quickstart**, retained its two-step/one-connection graph, exercised right-click rename/duplicate/confirmed removal, used the reviewer banner to return to the editing account, confirmed night mode after reload, and kept **Save draft** visible at an 800-pixel viewport. This is verification of the local reference workflow, not collaborative authoring, production identity, or a cross-browser/accessibility certification.

## Product boundary

This reference supports local fixture execution, adaptive Goal Agent child sessions, a bounded structured DAG, and governed outbound calls under one SQLite-backed scheduler. It is not a multi-tenant or distributed production service. Reminder `deliveryStatus: sent` means delivered to the persisted local capture outbox and named local role recipients; no email or external notification is sent. Slack, Jira Cloud, Confluence Cloud, and webhook presets require administrator-supplied server credentials and live sandbox validation; none was verified against a tenant for this release. OAuth lifecycle, MCP hosting, generic OpenAPI activation, inbound webhooks, automatic external retries, external reconciliation, real CSR/OCI/finance/directory services, live-model evaluations, corporate OIDC/directory grants, tenant isolation, managed secret storage, production mail, distributed workers/failover, observability and load validation, production object storage and malware scanning, retention operations, identity-backed export signing, and operational deployment remain integration gates. TeamRecipe planning exists as a validated domain service, not a model-driven runtime or user-facing orchestration workflow.

The source is supplied for continued development with no embedded paid workflow platform. The application has no required third-party JavaScript dependency or remote asset. Python and any optional service you configure retain their own terms.
