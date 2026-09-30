# Axiom implementation status

Current release: Axiom 2.0.0 / SQLite schema 11. This is the implementation status of the runnable local reference application, not a production-deployment claim. The Axiom 2.0 discovery gate passed **287/287 tests in 34.162 seconds** on 2026-09-25; Axiom 1.9 and the supplied 113-test factory checkpoint remain historical records.

## Implemented locally; focused verification where stated

- Original responsive Studio, Registry, Runs, Review Inbox, Rehearsal, Connections, and Audit views.
- Primary Agent Factory workspace with a saved-agent catalog, business-oriented mission/instruction/context/capability/result editor, advanced strict schemas, required evidence, stop rules, policy references, evaluation cases, time/tool/model/cost limits, explicit fixture/model labels, durable run inspector, behavior comparison, responsive layout, and night-mode styling.
- Draft → separate reviewer activation lifecycle for Goal Agent specifications. Drafts cannot be run or placed. Approved versions create immutable palette entries; placements and active sessions pin the exact specification and capability contracts.
- One adaptive registry-driven runtime for custom agents: observe, choose one structured call/question/finish decision, validate it, execute or prepare, record the actual result, and choose again. It supports scoped clarification/resume, budgets and deadlines, durable observations, stale-provider-result rejection, restart, and newly registered tools without a domain-specific planner branch.
- Configured chat-completion provider adapter and AI specification proposal endpoint. Provider calls occur outside the persistence lock; missing configuration is visible and never replaced by a scripted result. Suggested permissions remain unapproved until a person reviews and saves the draft.
- Labeled scripted Agent Factory demonstrations for service investigation, invoice review, and access coordination. Same-agent variation pairs produce different ordered capability traces from different evidence. These fixtures do not call AI or establish live-model quality.
- Exact adaptive prepared-action review showing the authoritative action target/adapter binding, tool version, operation identity, exact arguments and payload hash, authorization/policies, evidence/source versions, and action fingerprint. Goal Agent start authority remains separate from approval of a later discovered write.
- Goal Agent workflow bridge with durable parent/child state, explicit clarification/approval/failure/cancellation propagation, typed downstream results, immutable version pins, and direct session inspection.
- Kernel completion checks plus domain-owned trusted outcome validation reported as satisfied, contradicted, or unknown. Custom domains remain unknown until an authoritative validator is registered.
- From-scratch workflow building with an empty-canvas **Add your first step** path, searchable agent palette, positioned or automatically connected node placement, drag layout, edge creation/removal, draft undo/redo, and saved graph persistence. Step right-click and keyboard-accessible menus expose configuration, rename, connected-add, connection-free duplicate, connect, mapping, agent inspection/editing, and confirmed removal according to the active role and template state.
- Persistent day/night appearance with a header toggle, pre-paint preference restoration, and dark styling across Studio, graphs, palettes, menus, forms, dialogs, tables, run views, and responsive layouts. The selected preference is local to the browser and is not a server-side user setting.
- A visible read-only Studio banner explains why editing is unavailable and provides an explicit development-only quick switch from reviewer to the administrator editing account; it does not silently elevate a production identity.
- Five persistent, published demonstration workflows for payment disputes, employee access governance, production incident changes, vendor-risk onboarding, and insurance-claim adjudication. Each has 14 nodes and 16 edges, required typed inputs, parallel evidence gathering, condition-driven branches, exact complete-action approval, and isolated local action records and receipts. Their fixture manifests and defaults are pinned and hash-verified; startup safely backfills only missing stable IDs and does not overwrite an existing customized demo.
- Revision-aware draft lifecycle, validation, frozen review candidate, different-reviewer publication, immutable and hash-verified releases, separately hashed source-bound compatibility snapshots, embedded per-node agent manifests, permission-filtered task-template finding, independent duplication, archive/restore, and hash-checked template export/import. Archive blocks new run and rehearsal starts while preserving history and existing runs.
- Agent registration and metadata editing, deprecation that preserves historical execution, deletion only for unused custom registrations, and refusal to delete built-ins or anything referenced by a draft, release, or run.
- Strict RFC 8259 request/storage handling; constrained schemas/rules; semantic/layout hashes; typed template inputs and built-in outputs; conservative nested/bounded assignability; path-safe mappings; and a bounded compiler/runtime for conditions, merges, parallel splits, joins, approvals, outcomes, delays, and end nodes.
- SQLite migrations, durable run recovery, role-authorized actions, operation generations, effect ledger, reconciliation after a lost acknowledgement, and safe retry boundaries.
- Prepare → approve → dispatch for protected writes. Both a write's own approval gate and a directly guarding explicit Approval control bind the reviewer decision to the complete downstream packet: payload, destination, operation generation, connection generation, evidence/policy envelope, expiry, and fingerprints.
- Mutable local fixture connections with administrator-only test/revoke/restore, audited generation changes, authority checks before decision and dispatch, and safe reconciliation of an already accepted write after revocation.
- Governed external-connection catalog and responsive Connections workspace for bounded Slack, Jira Cloud, Confluence Cloud, and outbound-webhook presets. Records use server-side `env:` credential references, derived least-operation scopes, exact native-provider destinations, strict operation schemas, connection version/generation, and redacted public state. Administrators can create, safely health-test where a reviewed health read exists, invoke explicit reads, revoke, and restore; browser-supplied executable operations are refused.
- Provider-neutral outbound execution with DNS/address checks, private/metadata-address denial by default, TLS to the reviewed host, no redirects, size/time limits, bounded in-process rate admission, strict provider response projection, stale-authority result rejection, and metadata-only audit. A ready connection contributes stable capability IDs to Agent Factory without granting them automatically.
- External Goal Agent writes use the same prepare → exact approval → dispatch boundary. The persisted request pins connection version/generation, operation/version, destination, method, arguments, body, operation identity, evidence/source versions, and plan hash. Source reads are rechecked before commit. An unknown remote outcome stops without blind retry; no external reconciliation result is invented.
- Bounded OpenAPI 3.1 inspection/candidate compilation is exposed through an administrator-only, inspect-only HTTP/UI flow; every candidate remains non-executable and requires developer review. An MCP `tools/list` client contract exists as a module primitive. Generic OpenAPI activation and a configured MCP host client are intentionally absent.
- Bounded local task attachments: up to five UTF-8 JSON/text/CSV files, 256 KiB each and 512 KiB total, with atomic validation, hashes, metadata-only public views, and restart persistence. Optional actor-scoped task-start idempotency prevents duplicate runs and attachment ingestion.
- First-class evidence claims, conflicts, decisions, action receipts, access filtering, reduced public effect summaries, and authorized/audited `POST` run export with Markdown summary and a canonical SHA-256 integrity hash. This is hash-sealed, not identity-signed.
- Canonical ten-scenario rehearsal catalog with pinned definitions/fingerprints, experiment-scoped write isolation, known outcomes, path checks, authorization checks, and effect invariants. Completed experiments reject missing or malformed pinned scenarios before returning cached results. All five demo suites pass all 50 cases with zero external writes and zero unauthorized effects.
- Bounded planner operations for node/config updates, node and edge addition/removal, typed field binding, approval insertion, and same-implementation agent replacement; all candidates use normal revision, graph, schema, and authority validation.
- Tested agent manifest/execution/scaffolding contract plus deterministic template finding, change impact, reusable-block expansion, bounded team planning, and paired release evaluation.
- Local-only reminder delivery with policy-derived recipients, role checks, rate limiting, deduplication, delivery keys, queued/sent transitions, connection generation, review deep link, and initiator audit. No external message is sent.

## Verification record

The current Axiom 2.0 **287/287** verification record and commands are in `research/QA_NOTES.md`; the focused factory gate and its source-checkpoint distinction are in `factory/Verification.md`. The prior Axiom 1.9 **235/235** and supplied source-checkpoint **113/113** results remain separate historical baselines.

Node syntax passed for `app.js`, `icons.js`, and `theme.js`; Python `compileall` and JSON validation passed. Both regenerated previews passed the Node VM interface contract, each with **28 route, 72 run, 7 inspector, 2 mapping-dialog, 18 evidence-dialog, 1 effects-dialog, and 18 repair-dialog renders**. The preview contains **13 factory scenarios and 13 corresponding runs**, including **7 controlled variations**.

Coverage includes strict capability/specification and external-connection schemas; allowlists and context projection; observation-dependent paths; clarification; budget/deadline exhaustion; exact adaptive approval; local effect deduplication/reconciliation; restart; immutable version pins; stale concurrent responses; parent/child workflow behavior; configured-provider error handling; external destination/secret/plan boundaries; fixture outcome validators; JavaScript syntax; and Node VM interface contracts. Browser evidence in `research/QA_NOTES.md` must distinguish the earlier Agent Factory journey from any new Axiom 2.0 Connections check. Neither is accessibility or broad cross-browser certification.

No verification result establishes live-model planning quality, a live Slack or Atlassian tenant, webhook delivery, production authorization, tenant isolation, load/failover behavior, or complete accessibility. Record those results only after running them in the intended deployment environment.

## Implemented as domain services, not complete user workflows

- Reusable-block persistence/editor insertion.
- TeamRecipe persistence, user interface, and multi-agent runtime.
- Paired release experiment persistence and reviewed environment promotion.
- Dynamic installation/registration of generated agent packages.

These services are tested but remain intentionally labeled as domain-level capability.

## Production integration gates

- Corporate OIDC/directory lifecycle, delegation, and tenant/workspace isolation.
- Approved least-privilege live credentials and sandbox contract tests for Slack, Jira Cloud, Confluence Cloud, webhooks, CSR, OCI, finance, directory, email, model-provider, and other connectors. Local doubles and contract tests do not establish tenant access or external delivery.
- OAuth consent/callback/state/refresh/reauthorization, a production secret manager, generic OpenAPI activation and drift review, a configured MCP host client, signed inbound webhook ingestion, automatic external retry scheduling, and provider-specific reconciliation/operator tooling.
- Live-model quality, repeated-run reliability, prompt-injection/adversarial evaluation, provider privacy/retention review, pricing validation, and production outcome validators for each supported business domain.
- Production secret management, object storage, malware scanning, content policy, retention/deletion, backups, and operational deployment. Local type/size validation is not a security scan.
- Identity-backed export signing and key lifecycle. Current template and run hashes detect changed canonical content but do not prove who produced it.
- Distributed workers, durable production queues/streams, failover, observability, and measured load/capacity for both parent workflows and Goal Agent child sessions.
- Formal accessibility, cross-browser, security, privacy, and disaster-recovery certification in the target environment.

Local fixture and controlled integration-contract tests do not close these gates, and the application does not describe fixture records or controlled transports as live external results.
