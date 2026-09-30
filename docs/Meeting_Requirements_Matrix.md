# Meeting requirements and implementation traceability

Source: the user-supplied timestamped transcript Pasted markdown(3).md, checked against visible screens in video1875684916.mp4. Requirements are paraphrased; timestamps refer to the supplied transcript. Product choices and assumptions are labeled separately. This is traceability for the implementation specification, not a record of completed software.

## Confirmed baseline and proposed implementation

| ID | Transcript range | Requirement or discussion | Implementation in the Codex prompt |
| --- | --- | --- | --- |
| R01 | 00:00–00:48 | Configure agent name, type, and agent-specific settings; Jira creation is an example. | Guided configuration over registered implementation manifests and schemas; agent defaults separate from node overrides. |
| R02 | 00:49–01:21 | Show an Agent ID after creation. | Stable visible Agent ID in creation result, catalog, and detail. |
| R03 | 01:34–01:55 | Edit, modify, and delete agents. | CRUD for unreferenced drafts; versioning and deprecation preserve published/historical references. This restriction is a proposed integrity rule. |
| R04 | 01:56–02:21 | Workflow template list with Template ID. | Searchable template library, stable IDs, lifecycle, draft and published versions. |
| R05 | 02:50–03:42 | List/select available agents; scrolling/search/filtering can vary. | Searchable left palette and click-to-add alternative. Exact dropdown presentation is flexible. |
| R06 | 03:43–04:16 | Current Mermaid view is not draggable; administrators need an editable playground. | React Flow-based editor integrated with the existing app; diagrams in documentation do not substitute for this UI. |
| R07 | 03:43–04:16 | Zoom in/out and draggable screen. | Canvas pan, zoom, fit, selection, moving nodes, auto-layout, keyboard outline. |
| R08 | 04:17–05:12 | Start with an empty dotted Step 1 and drag an agent into it. | Explicit empty state/insertion target; dropping creates one configured node instance. |
| R09 | 05:13–06:21 | Once a step is filled, two new boxes appear automatically. | Both Next step and Add parallel agent targets appear after insertion; placeholders are not executable nodes. |
| R10 | 06:22–07:08 | Sequential next step and parallel agents; same agent can be used again. Parallel implementation may come later. | Separate instance IDs; explicit split/join semantics. Full parallel execution is included in the proposed complete product scope. |
| R11 | 07:09–08:20 | Selecting an agent opens the right pane with that instance's configuration. | Contextual inspector with schemas, mappings, connection, access, reliability, and test fields. |
| R12 | 07:09–08:20 | Template naming/configuration also needs an editor. | Template metadata inspector/top bar with persisted name and revision-aware autosave. Exact placement is a proposed design choice. |
| R13 | 08:21–08:58 | Blocks group agents for rapid reuse; speaker explicitly defers this enhancement. | Next release insertion blocks expand fresh instances with pinned source provenance. Live shared sub-workflows remain later work. |
| R14 | 08:59–09:43; 15:47–18:24 | Compare Flowable and n8n against custom requirements. | Source-backed architecture comparison; a final recommended engine is distinct from what was agreed in the meeting. |
| R15 | 09:44–10:28 | New Task popup/form selects a template, submits, and creates a task. | Published-template selector, schema form/uploads, server start command, and persisted task. |
| R16 | 10:29–11:44 | Runtime workflow resembles the designed workflow and shows the current stage. | Same canvas layout with immutable version pins and actual server events. |
| R17 | 10:29–11:44 | Users can run/execute actions on a stage. | Manual-start execution mode and eligible Execute action, independently gated by dependencies and approval. |
| R18 | 10:29–11:44 | Completed nodes green; pending manual approval visually distinct; only the right user approves. | Consistent labeled statuses plus server-enforced approval eligibility. Color is supplementary for accessibility. |
| R19 | 10:29–11:44 | Right-side option to email that approval is needed. | Reminder preview and authorized delivery command; local SMTP capture in demo, delivery status and audit. |
| R20 | 11:45–12:47 | Per-agent role dropdown, such as admin or contributor. | Allowed executor roles and explicit manual versus automated execution identity; server checks actual actor/delegation. |
| R21 | 11:45–12:47 | Per-agent Approval needed Yes/No. | Independent pre-execution approval policy compiled into a visible gate. Before-execution timing is a proposed default, not confirmed in transcript. |
| R22 | 11:45–12:47 | Additional design screens to be shared later. | Record them as unavailable; do not claim the supplied recording contains those future designs. |
| R23 | 12:48–13:37 | Example is CSR then Jira; future Jira/Confluence-related agents may be added. | Meeting-faithful CSR to Jira fixture template and SDK extension model. Real CSR/Confluence service contracts remain unspecified. |
| R24 | 13:38–14:29 | Developers create agents; admins arrange/configure the process with their help. | Separate code-level implementation registration, catalog configuration, and template composition. |
| R25 | 13:38–14:29 | Templates can remain draft, be tested/reviewed, then become active. | Immutable reviewed snapshot, testing, author/reviewer separation by default, and published active version. |
| R26 | 14:30–15:46 | Application is principally automation; AI may recommend templates during New Task. | Complete core without LLM; permission-filtered template finder with optional model reranking. Workflow generation is a separate proposed extension. |
| R27 | 16:54–18:24 | Need customizable configuration and customer roles, including certificate-related use cases. | Workspace policy model, external identity mapping, and capability adapters; no bank-specific role names in domain logic. |
| R28 | 18:25–20:10 | Discuss API integrations and reaching an approval screen, possibly via popup/headless browser. | First-class authenticated approval screen/deep link; browser automation is not required by the confirmed business need. |
| R29 | 19:20–20:10 | OCI keys raised; capability and Oracle acceptance are uncertain. | OCI SDK/authentication boundary and secret references, unconfigured until service/identity details are supplied. Corrects OCA in earlier summary. |
| R30 | 20:11–21:55 | Build an enterprise product in-house; avoid paid products; speaker explicitly says not to use n8n. | Custom product with selected self-hosted open-source foundations, no n8n dependency or mandatory enterprise subscription. Infrastructure still has operating costs. |

## Additional product ideas and their status

| Proposal | Why it helps | Scope |
| --- | --- | --- |
| Design, Simulate, Run on one canvas | Preserves the user's mental model across authoring and operation. | Required product enhancement. |
| Typed input/output mapping | Prevents configuration mistakes and makes agent reuse practical. | Required product enhancement. |
| Read-only role preview | Shows whether a workflow is actually operable by its intended people before publication. | Required product enhancement. |
| Runtime allowed-actions contract | Supplies Execute, Approve/Reject, Reminder, or an explanation from actual policy/state. | Required product enhancement. |
| Side-effect-isolated simulation | Demonstrates failure paths without sending real writes. | Required product enhancement. |
| Semantic version comparison | Makes release review concrete and keeps historical runs understandable. | Required product enhancement. |
| Durable execution and outbox reconciliation | Prevents lost tasks/decisions after process or delivery failures. | Required runtime foundation. |
| Safe failed-node recovery | Preserves completed work and handles uncertain external writes honestly. | Required runtime foundation with bounded v1 behavior. |
| Redacted evidence export | Makes a run's inputs, versions, decisions, and outcomes inspectable. | Required product enhancement. |
| Change-impact analysis | Shows which templates will be affected by an agent upgrade. | Proposed later roadmap. |
| Saved scenario comparison | Supplies repeatable release evidence across workflow changes. | Proposed later roadmap. |
| Environment promotion | Reuses immutable approved releases with controlled connection rebinding. | Proposed later roadmap. |

## Explicit assumptions and limits

The meeting did not choose React Flow, Temporal, NestJS, PostgreSQL, or a complete schema. These are recommendations with a repository-first exception. Flowable OSS remains a legitimate alternative for an existing Java/BPMN environment. The meeting's remarks about n8n pricing or tools' agent capabilities are discussion statements, not independently verified universal facts; the blueprint uses current official sources for the technical comparison.

The transcript does not settle approval timing, split/join behavior on failure, lifecycle race arbitration, retry safety, actual CSR API, OCI service, deployment scale, or retention policy. The prompt provides explicit reversible implementation defaults and bounded semantics instead of pretending the meeting specified them.

No live Jira, OCI, email, or customer connection has been configured or contacted as part of preparing this pack. The interactive concept uses sample data. The implementation prompt requires real local persistence and fixture services before any demonstration is called end-to-end.

## Recording review method

The video contains 32,897 frames at 25 fps. A full decode and scene-change pass with a 0.012 difference threshold selected 554 frames. Rapid edits separated by no more than 1.5 seconds were clustered; the final state of each cluster produced 156 keyframes, all reviewed in ten contact sheets. An earlier 30-second sampling pass and selected full-resolution frames supplemented that coverage. Very small pointer/text changes below the threshold may not produce a keyframe; requirements come from the full supplied transcript as well as visible evidence.

Useful visual checkpoints include the Agent ID creation at roughly 01:17–01:27, template ID at 02:10, initial dotted target at 05:01, two new targets at 06:33–06:54, right-pane layout at 07:51–08:13, New Task template selector at 10:34, and green/yellow runtime styling at 11:35–12:20. The n8n demonstration begins around 18:26 and its pricing page is visible around 20:30. These identify what was on screen, not proof of implementation or license entitlement.
