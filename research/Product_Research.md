# Product research: an original workflow operating system

Research checked 24 September 2026. This is a bounded review of official documentation and source licenses, not a hands-on benchmark or an exhaustive market survey. Proposed advantages below are hypotheses to validate, not claims of market leadership.

## What the competitive baseline actually is

| Product / edition boundary | Verified capabilities | Consequence for this product |
|---|---|---|
| **n8n** | Current documentation lists natural-language workflow building, assistant-based editing/testing, templates, MCP access, execution inspection, evaluations, and OpenTelemetry. Specific agent tools can pause for human approval with the proposed parameters. [Documentation index](https://docs.n8n.io/llms.txt), [tool approvals](https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools.md). | A canvas plus an AI sidebar plus approval buttons is established functionality. Compete on the complete business task and the reliability of its contracts. |
| **n8n self-hosted Community** | The edition comparison excludes projects, workflow/credential sharing, SSO, environments, external secrets, and Git version control from Community. Queue mode and ordinary logging are included. Registered Community adds selected free features; paid editions unlock other capabilities. [Edition comparison](https://docs.n8n.io/deploy/host-n8n/community-edition-features.md). | The meeting's no-paid-product constraint cannot be satisfied by assuming free n8n includes all enterprise collaboration. Recheck exact editions before adoption. |
| **LangGraph** | Persistent interrupts support human review and resumption. Checkpoint replay and forks explore previous states; downstream model and API calls execute again. [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel). | Replay alone is not novel and is not a harmless visual rewind. Distinguish event inspection, sandbox replay, and live re-execution. |
| **LangSmith** | Offline datasets and experiments compare changes; online evaluations inspect production interactions. Human, code, model-judge, and pairwise evaluators are supported. Production failures can become regression cases. [Evaluation](https://docs.langchain.com/langsmith/evaluation). | “AI quality dashboard” is table stakes. Surface business-specific quality evidence at the publish decision and at the affected step. |
| **Dify** | Human Input nodes collect editable forms, route user decisions, and handle timeout paths. Applications can be exposed as MCP servers. [Human Input](https://docs.dify.ai/en/self-host/use-dify/nodes/human-input), [MCP publishing](https://docs.dify.ai/en/cloud/use-dify/publish/publish-mcp). | An approval form or MCP logo is not differentiation. Approval comprehension, eligibility, expiry, and binding to the exact proposed action matter. |
| **Flowable engines versus complete platform** | Open-source Java BPMN, CMMN, and DMN engines support human and automated processing. Flowable distinguishes these engines from its full low-code Case Platform, including fine-grained permissions, runtime monitoring, and visual debugging. [Open-source and platform distinction](https://www.flowable.com/open-source). | Business process semantics and human work are mature capabilities. Original UX can simplify their use, but do not mistake the free engine for the entire commercial product. |

## License facts that change the architecture

- The inspected n8n repository license applies Sustainable Use terms to most code, limits use to internal business or personal/noncommercial purposes, and treats `.ee` code separately under its Enterprise license. This is not unrestricted permission to redistribute or embed its editor into a commercial product. The latest deployment agreement and exact release must be checked separately. [n8n source license](https://github.com/n8n-io/n8n/blob/master/LICENSE.md).
- Dify's current main-branch license is modified Apache 2.0. It requires commercial authorization for operating a multi-tenant environment, defines a tenant as a workspace, and restricts changing frontend logos/copyright notices. Older descriptions limited to competing SaaS products are insufficient. [Dify source license](https://github.com/langgenius/dify/blob/main/LICENSE).
- LangGraph's inspected repository uses MIT. This does not grant rights to separate LangSmith services or enterprise offerings. [LangGraph license](https://github.com/langchain-ai/langgraph/blob/main/LICENSE).
- Flowable's cited open-source page identifies its engines as Apache 2.0. Do not extend that statement to every Flowable-branded product.

**Architecture implication:** own the product model, designer, task experience, agent registry, policy enforcement, and AI assistance. Use independently reviewed permissive infrastructure dependencies where useful. “From scratch” should mean an original product and owned behavior, not reinvention of databases, authentication cryptography, or browser rendering. Keep model inference and infrastructure costs explicit even when there is no enterprise workflow license.

## Four differentiated product hypotheses

These are proposed combinations, not inventions claimed absent from every competitor. Targets are provisional acceptance goals, not achieved results.

### 1. An executable specification instead of a disposable AI draft

The user describes a business outcome. AI produces a structured change: steps, typed bindings, role rules, failure paths, effect classifications, and tests. A deterministic compiler checks that structure. The interface highlights exactly what changed and links each generated rule to the supplied requirement. Unresolved decisions remain visible; a model cannot silently invent approval roles or credentials.

**Build:** versioned workflow intermediate representation, JSON Schema contracts, static checks, editable AI patch, requirement-to-node links. Start with API, transform, condition, human task, and bounded agent nodes.

**Measure:** median time to a valid five-step workflow; first-run success on held-out tasks; unsupported assumption rate. Initial goal: 40% faster authoring than the manual version without worsening correctness.

### 2. A rehearsal laboratory for business consequences

Place two template versions beside the same historical cases. Explain which cases change route, which proposed writes differ, and how approval load changes. Inject timeouts, missing fields, duplicate callbacks, and unavailable approvers. Display observed outcomes separately from estimates.

**Build:** recorded fixtures, isolated credentials, mock effect adapters, branch coverage, deterministic data rules, explicit model rerun policy. Never claim a simulation predicts every external system response.

**Measure:** escaped regression rate, scenario coverage, unexpected external writes during rehearsal. Initial goal: zero external writes in sandbox tests and detection of every seeded policy violation.

### 3. Approvals that let a person understand the decision

An approver sees a compact evidence packet: requested change, relevant source fields, policy clause, exact outgoing action, alternatives, and deadline. An execution preview shows what approval unlocks. A task belongs to a business case even when several workflows participate.

**Build:** action fingerprint binding approval to actor, payload, template version, and expiry; current server-side eligibility checks; atomic decision transitions; separate execution and approval permissions. AI summarizes evidence with source references and labels uncertainty.

**Measure:** reviewer comprehension, median decision time, corrections after approval, unauthorized transition attempts. Initial goal: at least 90% correct answers to “what will happen next?” in usability testing.

### 4. Recovery with an explicit side-effect ledger

When a branch fails, show what already changed outside the product, what is known, and what requires reconciliation. AI suggests a repair patch and matching regression case. The operator chooses among retry, compensate, reconcile, or fork a new run, depending on adapter capabilities.

**Build:** append-only execution events, idempotency keys, adapter capability declarations, saved outputs, immutable run-version binding, reconciliation state. Never promise universal exactly-once external effects or universal undo.

**Measure:** time to diagnose seeded failures; duplicate side-effect rate; successful recovery under worker crashes. Initial goal: a 50% reduction in diagnosis time versus raw logs, with zero duplicates in the tested idempotent adapters.

## UI principles for a genuinely complex product

1. **Stable spatial memory:** keep node positions across Design, Rehearse, and Run. A mode changes permitted actions and overlays, not the user's map.
2. **Three coordinated views:** canvas for topology, table for bulk configuration, timeline for causality. Selecting a step synchronizes all three.
3. **Business detail before technical detail:** a collapsed node shows action, owner, wait condition, and effect. Expand for schemas, policies, retries, and traces.
4. **Semantic zoom:** overview shows grouped stages; working zoom shows steps; detail shows ports and mappings. Never fit hundreds of unreadable nodes merely to claim scale.
5. **Local explanations:** selecting a blocked step answers “why waiting, who can act, what changes next?” The relevant inspector sits beside the selected work.
6. **AI as an inspectable editor:** show proposed additions, removals, assumptions, and tests. Accept patches individually; retain undo. Avoid presenting unverifiable private model reasoning as evidence.
7. **Operational visual hierarchy:** neutral surfaces, precise typography, restrained status color, strong selection, and readable edge labels. Motion explains state transitions and respects reduced-motion settings.
8. **Accessible authoring:** keyboard insertion and connection, searchable node library, visible focus, text status labels, and a table alternative to dragging.

The standout demonstration should complete one difficult case: generate a typed workflow, catch an unsafe route, rehearse failure, publish an approved version, obtain a comprehensible human decision, and recover after a worker restart. Every visual claim should correspond to stored state or a clearly marked simulation.
