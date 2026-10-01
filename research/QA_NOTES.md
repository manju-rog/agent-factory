# Axiom reference application: verification record

## Current Axiom 2.2 release update

- Checkpoint: Axiom 2.2.0, SQLite schema 13, built-in deterministic-agent contract 1.3.0.
- Schema 13 adds durable one-time, hourly, daily, and weekly workflow schedules with IANA timezone recurrence, exact published release pins, optimistic revisions and definition generations, restart recovery, coalesced missed occurrences, overlap protection, idempotent automatic/manual starts, role-controlled lifecycle actions, audit records, and generated-run provenance.
- Scheduling reuses the ordinary trusted run-creation path. A schedule can start work but cannot approve a later manual stage or consequential prepared action. The local server must be running; no result establishes distributed scheduling, high availability, clock coordination across workers, load capacity, or exactly-once external delivery.
- The focused scheduling gate passed **16/16 tests**, including recurrence and DST, restart, immutable pinning after a newer publication or template archive, overlap/missed-run handling, edit-generation isolation, exact lost-response replay, protected-input preservation, pause/resume/run-now/archive, stale-revision rejection, roles, idempotency, and real loopback HTTP boundaries.
- The full Axiom 2.2 discovery gate passed **338/338 tests in 70.056 seconds** on 2026-10-01. The Axiom 2.1 322-test result remains a separate historical baseline.
- JavaScript syntax, Python compilation, JSON validation, and the available Node VM interface contract passed. Browser verification is recorded separately below and does not constitute broad accessibility or cross-browser certification.

Current scheduling commands include:

```bash
# From app
python3 -m unittest -v tests.test_scheduling
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
node --check public/app.js
node tests/test_ui_contract.js ../preview/preview_data.json
```

## Axiom 2.2 scheduling browser review — 2026-10-01

A headed Chrome pass against the real persistent localhost application completed the primary scheduling journey:

- `/api/health` reported `status: ready`, application version `2.2.0`, and schema version `13`.
- The administrator created **Browser verification schedule** for **Service request orchestration**, every day at `13:19` in `Asia/Kolkata`. The Schedules table showed its active state, next local/UTC-derived occurrence, and pinned workflow version 1.
- Pause and resume changed the persisted state and available action in place. **Run now** created exactly one linked workflow run, `run_fd3bcea45380`.
- The run inspector showed **Manually started from a schedule**, the source schedule ID/name, and pinned workflow version 1. Normal execution reached the existing human approval and waited there; the scheduled trigger did not bypass the reviewer decision or prepared-action boundary.
- **View schedules** returned to the originating schedule and retained its linked last-run record. The schedule was left safely paused so the browser check will not trigger unattended work.
- The complete scheduling page was visually inspected in both light and night modes. Buttons, metrics, table, status, provenance, and actions rendered without clipping at the available desktop viewport.

This pass used local fixture execution and created no external effect. It does not establish mobile/cross-browser coverage, formal accessibility conformance, distributed scheduling, high availability, or a live provider result.

## Historical Axiom 2.0 release update

- Checkpoint: Axiom 2.0.0, SQLite schema 11, built-in deterministic-agent contract 1.3.0.
- Schema 11 adds the governed outbound-connection gateway, version/generation-bound connection health, bounded Slack/Jira Cloud/Confluence Cloud/webhook presets, and external capability integration with Goal Agent preparation and approval.
- The integration contract checks cover strict records and operation schemas, secret-reference redaction, provider destination pinning, DNS/address policy, exact prepared-call verification, response projection, rate admission, retry classification, OpenAPI inspection primitives, MCP protocol contracts, and Goal Agent capability adaptation. Controlled transports and records do not establish a live provider connection.
- The final Axiom 2.0 discovery gate passed **287/287 tests in 34.162 seconds** on 2026-09-25. It used isolated temporary databases and real loopback HTTP servers, including the controlled external-gateway boundary tests. The Axiom 1.9 235-test result below remains a separate historical baseline.
- No Slack workspace, Jira/Confluence site, webhook receiver, remote MCP server, or arbitrary API tenant was authenticated. No check establishes OAuth consent/refresh, live provider permissions, external write reconciliation, automatic external retry, inbound webhooks, production authentication/tenant isolation, or distributed operation.
- A fresh headed-browser pass against `http://127.0.0.1:8765` verified the Axiom 2.0 Connections workspace, OpenAPI inspection boundary, persisted theme, workflow-creation dialog, and agent-step action menu. The Axiom 1.9 journeys below remain separate regression evidence; neither pass establishes a live external connection.

## Axiom 2.0 headed-browser review — 2026-09-25

The live local server and persistent schema-11 workspace completed the following browser checks:

- `/api/health` reported `status: ready`, application version `2.0.0`, and schema version `11` (browser evidence `@828`).
- Connections rendered three explicitly local fixtures plus six provider types: Slack, Jira Cloud, Confluence Cloud, REST / OpenAPI, Outbound Webhook, and MCP server. The interface labeled REST / OpenAPI as requiring developer-reviewed import and MCP as requiring client integration; it did not present either as active.
- The REST / OpenAPI dialog accepted one bounded, fully inlined OpenAPI 3.1 JSON document. A deliberately incomplete first document failed visibly. A valid read contract then produced one hash-bound, unclassified candidate and stated that no connection, capability, credential, or executable operation had been created (browser evidence `@817`).
- Night mode changed the control to **Switch to day mode** with `aria-pressed=true`, then remained active after navigating from Connections to Workflow studio (`@848`, `@857`).
- **New** opened the workflow-creation dialog with editable **Template name** and **Business purpose** fields and a **Create blank template** action (`@863`). The dialog was closed without adding test data.
- The agent-node action surface exposed configure, rename, add-connected, duplicate, connect, input mapping, agent-contract inspection, reusable-agent editing, and removal (`@875`). The node itself exposes the same surface through right-click or `Shift+F10`; the headed pass opened it through the visible equivalent action button to avoid mutating the stored workflow.
- A final cache-busted Connections tab (`@883`) loaded with no browser console warning/error summary, retained the persisted night preference, and rendered all provider headings from fresh server state.

This pass made no outbound provider request and configured no external credentials. Live OAuth, provider permissions, external delivery, reconciliation, retries, tenant isolation, broader accessibility, and cross-browser behavior remain integration or release-environment work.

Current release commands include:

```bash
# From app
python3 -m unittest discover -s tests -v
python3 -m unittest -v tests.test_integrations tests.test_agent_factory
python3 -m py_compile integrations.py agent_factory.py server.py
node --check public/app.js
node tests/test_ui_contract.js ../preview/preview_data.json
node tests/test_ui_contract.js ../output_v2/preview_data.json
```

## Historical Axiom 1.9 environment and limits

- Date: 2026-09-25.
- Checkpoint: Axiom 1.9.0, SQLite schema 10, built-in deterministic-agent contract 1.3.0.
- Python discovery ran against isolated temporary SQLite databases. HTTP tests launched the real loopback server in subprocesses rather than mocking endpoint responses.
- The recorded 2026-09-24/25 headed-Chrome sessions used the real local application. Historical payment-dispute and workflow-builder regression evidence is separated below from the current Agent Factory browser review.
- Semantic accessibility output and focusable control names were inspected during the browser work. A full automated WCAG audit, screen-reader matrix, cross-browser matrix, and production security assessment were not performed.

## Historical Axiom 1.9 verification status

The final Axiom 1.9 Python discovery gate passed **235/235 tests in 29.065 seconds**. The focused Agent Factory gate passed **65/65 tests**: 29 generic engine tests, 15 fixture/decision tests, 1 schema migration test, 16 durable runtime/workflow-bridge tests, and 4 HTTP-boundary tests. The 65 are included in the 235; they are not an additional total. The supplied factory source checkpoint's historical 113-test result remains a separate checkpoint and is not part of either current count.

Focused Agent Factory runtime, fixture, migration, workflow-bridge, and HTTP gates have been exercised against isolated temporary SQLite databases and real loopback HTTP. Node syntax passed for `public/app.js`, `public/icons.js`, and `public/theme.js`. Python `compileall` and repository JSON validation passed. `factory/Verification.md` records their scope without treating controlled model doubles or scripted fixture decisions as live-model validation.

Covered Agent Factory behavior includes strict capability/specification schemas; context projection and attributable observations; structured decision validation; observation-dependent plans; clarification and resume; turn/tool/write/time/model-token/cost limits; exact adaptive prepared actions; trusted fixture outcome validators; restart; immutable version pins; stale provider-response rejection; provider waiting outside the persistence lock; and parent/child workflow propagation. The same gate also retains regression coverage for the prior workflow compiler, release, evidence, effect, rehearsal, connection, and recovery boundaries.

The retained deterministic-workflow baseline includes five persistent published workflows: payment disputes, employee access governance, production incident changes, vendor-risk onboarding, and insurance-claim adjudication. Their prior verification is regression evidence, but this file does not restate that historical count as the final Axiom 1.9 total.

The passing suite includes scalar/array/nested/additional-property schema assignability; declared built-in input/output contracts and path/type-safe mappings; embedded release agent manifests; hash-verified source-bound compatibility snapshots that do not rewrite published releases; strict request and persisted JSON handling; complete multi-action and self-gated approval packets; provider-record mismatch recovery; mutable connection test/revoke/restore authority and generation invalidation; bounded task attachments and actor-scoped idempotent starts; the full bounded planner-operation allowlist; template duplicate/archive/restore/hash export/import and archive gating for task/rehearsal starts; scenario pin integrity, including rejection of missing or malformed pins before accepting a cached completed evaluation; experiment destination isolation; unused-agent deletion guards; local reminder delivery receipts; recursive audited-POST run-export redaction with a canonical manifest hash; and runtime recovery.

Coverage scope matters: the SDK, block insertion, TeamRecipe planning, and paired release selection are domain services rather than complete HTTP/interface workflows. The local exact-action envelope uses generation-versioned fixture connection/policy identities in one local workspace; connection `test` checks only the local fixture state. Attachment validation checks allowed type, bounds, UTF-8 and JSON syntax, not malware or semantic content safety. The public effects route exposes aggregate counts and reduced records, not protected payloads or the complete internal ledger. Run export is an authorized, audited `POST`. Export SHA-256 values detect canonical-content changes but are not HMACs or public-key signatures. No test result establishes corporate OIDC, tenant isolation, live external connectors, distributed workers, production secrets, OCI behavior, production storage/scanning, external notification delivery, or signer identity.

`app.js`, `icons.js`, `theme.js`, and the view-contract harness have current syntax/contract coverage. Both regenerated preview captures passed the UI contract; each rendered **28 routes, 72 workflow runs, 7 inspectors, 2 mapping dialogs, 18 evidence dialogs, 1 effects dialog, and 18 repair dialogs**. Their preview data contains **13 Agent Factory scenarios and 13 corresponding factory runs**, including **7 controlled variations**. The factory smoke exercises specification creation/save shape, valid stop-rule objects, controlled behavior comparison, complete prepared-action fields, completion/outcome states, paused deadlines, and polling-driven comparison refresh. These are HTML-producing functions and delegated handlers in a Node VM; they do not establish browser rendering, pointer/drag behavior, assistive-technology behavior, or a cross-browser result.

The same Node UI-contract run also passed the workflow-builder and persistent-theme checks: the empty-canvas call to action, bounded node creation and connected placement, connection-free node duplication, role-aware context-menu actions, reviewer-to-administrator quick switching, and saved light/night preference. These are interface contracts running in a document stub; pointer placement, reload persistence, and responsive visibility were separately exercised in headed Chrome.

Commands:

```bash
# From app
python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest -v tests.test_agent_factory tests.test_factory_fixtures tests.test_factory_migration tests.test_factory_runtime tests.test_factory_http
python3 -m py_compile server.py domain.py workflow.py scenarios.py agent_factory.py factory_fixtures.py
node --check public/app.js
node --check public/icons.js
node --check public/theme.js
node --check tests/test_ui_contract.js
node tests/test_ui_contract.js ../preview/preview_data.json
node tests/test_ui_contract.js ../output_v2/preview_data.json
```

The recorded static gate also ran Python `compileall` and validated repository JSON successfully.

## Agent Factory merged-release review

- The factory catalog distinguishes administrator-authored drafts from reviewer-activated versions. A draft does not appear in the workflow palette or become runnable merely because it saved successfully.
- The editor preserves mission, instructions, permitted context, capability allowlist, strict input/result contracts, required evidence, supported stop rules, policy references, evaluation cases, and all resource limits, including model tokens and estimated cost.
- Bundled service, invoice, and access variations are visibly labeled scripted fixtures. Configured-model mode exposes missing provider configuration and does not fall back.
- The run inspector exposes actual action/observation order, scoped clarification, persisted exact-action target/adapter/version/operation/payload/policy/evidence/source-version fields, and completion plus trusted outcome validation as satisfied, contradicted, or unknown.
- Behavior preview compares persisted ordered traces for controlled same-agent cases and refreshes when polling advances a run. It remains fixture-only evidence, not a stochastic model-quality evaluation.
- The regenerated preview exposes 13 factory scenarios/runs: six primary service, invoice, and access demonstrations plus seven controlled missing-evidence, conflict, denial, unavailability, duplicate-operation, and changed-business-condition variations.
- Goal Agent workflow nodes pin the approved specification version, distinguish start permission from a discovered write approval, and link to their durable child session.
- No current check establishes live-provider quality, external business integration, production identity/tenancy, distributed load/failover, or full accessibility. These remain release-environment gates.

## Static review findings

- First CSS review found several small functional text colors below the 4.5:1 contrast target: `#758093` on white (3.99:1), `#8a93a1` on white (3.10:1), `#9aa3b0` on white (2.55:1), and `#8b9782` on `#fbfcf9` (2.98:1). The frontend owner added darker functional text overrides, larger labels, and a reduced-motion preference rule. A full computed-style contrast or accessibility audit has not been performed.
- Review found and the owners corrected a named manual-step planning mismatch, incorrect UI assumptions about administrator execution rights, missing cancellation permissions, retry-limit mismatch, audit-record key mismatch, hardcoded provider labels, frozen-candidate editing, and missing advertised support for the accepted-write timeout scenario.
- Later focused review added server-enforced template duplication/archive/restore/hash import/export, archive gates for new task and experiment starts, unused-agent deletion guards, the eight-operation planner allowlist, generation-versioned fixture connection authority, bounded attachment ingestion, idempotent task starts, and redacted hash-sealed run exports. Run export uses an audited `POST`; none of its hashes is described as an identity-backed signature.
- Schema-10 migration review preserves schema-9 records and original published workflow release snapshots/hashes while adding adaptive specifications and sessions. Compatibility execution snapshots remain separately hashed and bound to their source version/hash. Strict JSON checks reject duplicate keys, non-finite numbers, and unpaired surrogates before request mutation or legacy-database migration.
- Experiment review pins the scenario definition and fingerprint used by every run, gives simulated writes an experiment-scoped ephemeral identity, rejects missing, malformed, or changed pins before accepting even a cached completed result, and evaluates required paths, final state, attempted-effect bounds, graph authorization, duplicate operation keys, and absence of fixture ticket/outbox records.
- Literal icon references resolve to declared icons. Inline JavaScript event attributes were removed so the error-recovery control works with the server's restrictive script policy.
- The domain modules deliberately fail closed for unsupported schema/rule/graph/manifest/governance inputs. Server integration is present for compilation, evidence export, scenarios, effects, template finding, and agent impact; other P2 services remain domain-only.

## Historical workflow demo browser review — 2026-09-25

The headed-Chrome journey against the live local server completed the following:

- Selected the payment-dispute workflow from the six-template selector.
- Verified the complete 14-step/16-connection graph.
- Opened the run flow and verified its required typed input form and payment-specific sample values.
- Reached approval and inspected the full prepared payload and the `payment-dispute-case` action destination.
- Approved the exact action and observed completion with 13 successful nodes and one intentionally skipped condition branch.
- Confirmed the isolated local result used a `DSP-SIM` action-record identifier.

## Historical workflow-builder browser review — 2026-09-25

The headed-Chrome follow-up against the live localhost application completed the following:

- Opened an empty workflow and confirmed that the central **Add your first step** control opened the agent palette.
- Created **Workflow Builder Quickstart**, added two nodes, connected them with one edge, saved the draft, and confirmed that the saved two-node/one-edge graph remained available.
- Opened the step menu by right-clicking and exercised its visible configuration actions, including rename, duplicate, and confirmed removal. The duplicate was a separate draft placement rather than an implicit copy of existing connections.
- Switched to the reviewer development account, confirmed the read-only banner, and used its explicit quick-switch control to return to the administrator editing account.
- Enabled night mode, reloaded localhost, and confirmed that the night preference persisted.
- Resized the headed browser to 800 pixels wide and confirmed that the **Save draft** control remained visible and usable.

This journey proves the local builder interaction and persisted local theme preference exercised above. It does not establish collaborative multi-user editing, production identity, external connector execution, or cross-browser visual equivalence.

## Historical browser review — 2026-09-24

The final 2026-09-24 headed-Chrome journey completed the following against the real server at `127.0.0.1:8877` and a new temporary SQLite database:

- Opened the published workflow's task-start flow and verified that the form was generated from the published typed input contract.
- Started the published fixture workflow and observed it pause at the explicit Approval control while the downstream ticket action was already prepared.
- Switched from the administrator fixture identity to the reviewer through the visible account selector.
- Opened the decision dialog and verified the exact destination, canonical payload, action fingerprint, and approval-envelope hash before approval.
- Approved the exact action and observed the same run complete all 7/7 nodes with one local ticket.
- Inspected the reduced effect response and confirmed exactly one acknowledged effect whose action and approval hashes matched the decision.
- Inspected the matching evidence, then generated the authorized export with `POST` and confirmed its `run.exported` audit entry.
- Switched back to administrator and successfully tested the local ticket connection.
- Returned to Rehearsal Lab as administrator, ran the required suite, and observed 10 actual simulations with 10/10 assertions passing.
- Archived the template and confirmed that Run workflow and all ten individual rehearsal buttons were disabled, then restored it and confirmed that Run workflow was re-enabled.
- Inspected the desktop journey. The earlier same-date pass inspected the 390x844 layout, where mobile navigation, account selector, hero, scenario cards, and controls remained visible without clipping.
- Queried browser logs after the journey; there were no warning or error entries.

These historical browser journeys remain useful workflow regressions. Broader keyboard-only traversal, automated contrast/ARIA tooling, multiple screen readers/browsers, sustained performance testing, and production integration security testing remain separate release-environment work unless later recorded above.

## Historical Axiom 1.9 Agent Factory browser review — 2026-09-25

The headed browser used the live server at `127.0.0.1:8765` and the persistent local schema-10 workspace. It completed or inspected the following current-release journeys:

- Created **Browser QA Investigator** as a custom specification, saved its draft, activated version 1 through the separate reviewer identity, and confirmed that the approved Goal Agent became available for workflow placement.
- Created and saved **Goal Agent Browser Verification**, placed the pinned Goal Agent in its graph, and inspected the node menu. Right-click and **Shift+F10** exposed the same nine role-aware actions, including configure, rename, add-connected, duplicate, connect, mapping, contract inspection/editing, and removal. The Save control remained available at an 800-pixel viewport.
- Switched to night mode, reloaded the application, and confirmed that the browser-local choice persisted. A final fresh headed session loaded the Agent Factory with no console warnings or errors after the embedded favicon removed the browser's automatic `/favicon.ico` 404.
- Confirmed that a custom agent with neither a scripted fixture nor a configured model has both provider choices and **Run this case** disabled, with a visible explanation. No scripted fallback was presented as AI.
- Ran the same Service Investigator through materially different evidence. An existing linked issue completed after `service.lookup`; a new request followed `service.lookup → service.search_runbook → service.create_ticket`; missing request identity paused for `input.requestId`, resumed with the supplied value, and completed from the new observation.
- Reviewed and approved the new-request action through the separate reviewer path. The persisted public run record binds `service.create_ticket` version `1.0.0`, the local fixture adapter target, stable operation key, payload hash, policy reference, evidence references, source-result versions, exact arguments, and action fingerprint `87b72337…`. It records one acknowledged local effect and receipt `LOCAL-04654001D4`, with `externalWrite: false`.
- The completed run displayed satisfied kernel completion checks and satisfied trusted business outcome validation from `fixture-outcome-validator.v1`. The behavior preview showed different ordered traces and identified them as fixture-only evidence rather than model-quality evaluation.

The final browser-tool pass could not use its native primitive to select another HTML `<select>` option, and polling invalidated some event references. The already persisted action, HTTP view, automated exact-action checks, and preview contract supplied the remaining record-level verification; they are not substituted for a second browser click-through. Full WCAG certification, broad keyboard-only traversal, screen-reader coverage, and a browser matrix remain outside the local machine gate.
