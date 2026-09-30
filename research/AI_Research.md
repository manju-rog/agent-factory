# Research foundations for an ambitious workflow product

Research checked 24 September 2026. The proposals below are product synthesis, not claims that these papers already implement this product or that the combination is unique. Their value must be demonstrated on business outcomes. A compelling ambition is: **a person describes an outcome; the platform constructs a reviewable process, rehearses it, runs it within authority, and explains every consequential result.**

The important object is an executable business contract. It contains the desired outcome, input schemas, allowed capabilities, approval requirements, stopping conditions, and evidence obligations. A visual graph becomes one view of that contract. A document, a task inbox, a scenario comparison, and an execution history become other views of the same underlying state. This connects useful AI to a product people can operate.

## 1. Compile intent into a constrained, typed plan

**Finding.** PICARD constrains generation through incremental parsing and demonstrates improved validity in text-to-SQL. It does not establish that syntactically valid output satisfies a business goal. LLMCompiler separates planning, dependency-aware dispatch, and execution; its experiments support parallel tool orchestration for suitable workloads. [PICARD](https://arxiv.org/pdf/2109.05093), [LLMCompiler](https://arxiv.org/html/2312.04511).

**Proposed feature — Outcome Designer.** The user writes “Resolve new support requests, create engineering work when needed, and require a lead to approve customer-facing changes.” AI proposes a contract and a graph, highlighting unresolved assumptions beside affected steps. “Approve customer-facing changes” must become an explicit constraint, not an instruction buried in a prompt.

**Implementation.** Define a versioned intermediate representation with node IDs, schemas, typed data references, capabilities, side-effect classes, timeouts, branches, and approval bindings. The model emits structured proposals; an ordinary compiler rejects unsupported nodes and invalid references. Use a restricted type system whose assignability rules can actually be implemented. Check nullability, unreachable nodes, join semantics, bounded loops, and whether every path to a protected write passes its approval gate. Show compiler errors directly on the canvas. Natural-language edits produce patches against the same representation, with semantic diffs before application.

**Measurable test.** Maintain independently written valid and invalid workflow fixtures. All seeded structural and approval-bypass defects must be rejected. Measure accepted-plan task success separately from compilation success. Compare creation time and correction count against manual construction.

**Limits.** A compiler cannot prove arbitrary business intent. Approval dominance is tractable over the restricted control model; claims of general workflow verification require stronger semantics and dedicated verification work.

## 2. Use specialist teams only when they earn their cost

**Finding.** AutoGen demonstrates programmable collaboration between agents, tools, and humans. MAST analyzes multi-agent failures including system design problems, misalignment, and verification weaknesses. Neither establishes that adding agents universally improves results. [AutoGen](https://arxiv.org/abs/2308.08155), [MAST](https://arxiv.org/abs/2503.13657).

**Proposed feature — Adaptive Specialist Step.** One business step can expose a small team: a classifier identifies the issue, a researcher gathers evidence, and a reviewer checks the proposed response. The interface shows responsibilities and deliverables rather than an endless chat transcript.

**Implementation.** Start with a single executor as the baseline. Team recipes specify eligible agents, input views, output schemas, maximum turns, token/cost budgets, and termination conditions. A deterministic coordinator routes work and enforces limits. Specialists receive only relevant evidence. A reviewer produces structured objections with evidence references; it cannot silently expand tools or change permissions. Reserve each consequential action against a unique action ID so two specialists cannot independently commit the same change. Allow dynamic specialist selection only from the recipe's approved set.

**Measurable test.** Compare one agent, a fixed team, and adaptive selection on identical held-out scenarios at matched budgets. Measure valid outcomes, contradictions, duplicate actions, latency, and cost per successful case. Ship a team recipe only when its measured advantage warrants the operational cost.

**Limits.** Several agents can repeat the same error. Diversity of role names does not establish independent evidence. Agent coordination belongs inside bounded nodes; it must not replace the durable workflow scheduler.

## 3. Make evidence a first-class runtime object

**Finding.** W3C PROV provides a model for entities, activities, agents, and their derivation relationships. RARR investigates retrieving evidence and revising generated text to improve attribution. Provenance and attribution support inspection; neither guarantees truth. [W3C PROV-DM](https://www.w3.org/TR/prov-dm/Overview.html), [RARR](https://arxiv.org/abs/2210.08726).

**Proposed feature — Evidence Lens.** Click a field, recommendation, or approval and see its source records, exact supporting excerpts, transformations, timestamps, and reviewer decision. Conflicting sources remain visible. “Why was this ticket escalated?” resolves to the relevant policy, request facts, and evaluated condition.

**Implementation.** Give source snapshots, artifacts, claims, and transformations stable IDs. Store claim-to-evidence links with content hashes, source versions, field paths or excerpt spans, and access labels. Record model and prompt versions alongside generated artifacts. Separate direct extraction, deterministic calculation, model inference, and human assertion. A claim validator checks that cited references exist and actually support the claimed statement; deterministic checks handle amounts, IDs, and dates. Preserve a concise decision summary rather than exposing private model reasoning. Render provenance from recorded events, not a retrospectively invented explanation.

**Measurable test.** Seed missing, stale, contradictory, and irrelevant evidence. Measure supported-claim precision and evidence coverage against human annotations. Test whether reviewers can identify the correct source and resolve a conflict faster than from raw logs.

**Limits.** Content hashes detect content changes, not deception. Source access can expire. Retention and permissions apply to evidence copies and derived artifacts as well as original records.

## 4. Rehearse business outcomes in a scenario laboratory

**Finding.** ToolEmu explores finding agent risks with an LM-emulated environment. Tau-bench evaluates tool agents using policy-sensitive tasks, final database states, and consistency across repeated trials. These support testing behavior and outcomes beyond fluent text. [ToolEmu](https://arxiv.org/abs/2309.15817), [Tau-bench](https://arxiv.org/abs/2406.12045).

**Proposed feature — Scenario Laboratory.** Fork a saved case: “The API times out after accepting the write,” “The approver changes,” or “The attachment contains conflicting facts.” Compare baseline and candidate workflows as final state differences: what was created, sent, withheld, or escalated, and which invariant failed.

**Implementation.** Build deterministic connector fixtures first. A scenario pins initial records, workflow version, policy version, adapter behavior, inputs, and expected outcomes. Branches change specified assumptions. Inject timeouts, duplicate webhooks, late approvals, partial responses, and contradictory records. Generated scenarios extend coverage after review; they do not replace fixtures with known answers. An optional model-emulated connector is visibly labeled approximate. Every laboratory run uses a write-isolated execution mode. Record actual side effects attempted, not only the agent's account of its actions.

**Measurable test.** Assert final state, permitted transition sequences, prohibited effects, and repeated-trial reliability. Include a case that succeeds once but fails intermittently. Report the proportion of scenario groups whose every repeated run succeeds, alongside ordinary per-run success.

**Limits.** This is controlled scenario analysis, not causal proof about an organization. Model-emulated APIs can be unrealistic. Replaying pinned outputs differs from re-executing a stochastic model; the UI must distinguish them.

## 5. Repair failures through bounded, reviewable proposals

**Finding.** AgentDojo demonstrates the importance of evaluating agents against instructions injected into untrusted tool data. It supplies an extensible test environment; it is not a proof that any single defense eliminates prompt injection. [AgentDojo](https://arxiv.org/abs/2406.13352).

**Proposed feature — Repair Branch.** When a run fails, AI drafts a scoped repair: retry a read, correct a mapping, select an approved fallback, or ask a person. The user sees what changed, which evidence justified it, and which completed actions must not repeat.

**Implementation.** Capture failure category, input schema, attempted action, side-effect status, and adapter response. A repair planner emits one of a small set of typed repair operations. Recompile the patch, evaluate policy, and rehearse affected scenarios before approval. Treat all retrieved text and tool responses as data; they cannot grant capabilities. Bind approval to the patch, workflow version, run state, and affected action IDs. Changed arguments invalidate the approval. An unknown external write result enters reconciliation; it is never automatically treated as a safe retry. Template fixes create a new version rather than mutating history.

**Measurable test.** Inject malicious instructions into ordinary tool responses and repair evidence. Assert no authority expansion, secret disclosure, or unauthorized side effect. Test uncertain-write recovery against a connector that commits before returning a timeout.

**Limits.** Repair is a proposal system with bounded execution rights. “Self-healing” is an unsuitable promise when a failure leaves real-world effects uncertain. Exactly-once effects require cooperation from the destination or explicit reconciliation.

## 6. Turn human oversight into a usable control surface

**Finding.** Cedar supports policy validation against a schema; validation and authorization are distinct operations. This supports making access decisions explicit and testable rather than relying on interface visibility or agent instructions. [Cedar policy validation](https://docs.cedarpolicy.com/policies/validation.html).

**Proposed feature — Decision Desk.** A reviewer sees the requested action, exact changes, evidence, applicable policy, current authority, and consequences of waiting. The desk allows approval, rejection, requesting evidence, or returning a structured correction. Reviewers can preview a role's permitted actions before a template is released.

**Implementation.** Evaluate principal, action, resource, and context on the server at execution time. Bind an approval to an immutable action payload and expiry. Recheck current permissions when consuming it. Separate author, publisher, operator, and approver privileges where configured. Track review readiness using observable conditions—missing evidence, violated rules, schema errors, unknown side-effect state—rather than a model's self-reported confidence percentage. Route cases by policy and ownership; allow an accountable human override only where policy explicitly permits it and preserve its reason.

**Measurable test.** Cover revoked access, stale approval, modified payload, wrong tenant, reassigned reviewer, and expired delegation. Conduct usability tasks measuring decision accuracy and time, including whether reviewers notice a changed recipient or amount.

**Limits.** A policy engine enforces the policy it receives; incorrect policies remain incorrect. Human approval without sufficient context can become a rubber stamp.

## 7. Improve workflows through controlled release experiments

**Finding.** The reliability and failure-analysis work above implies an engineering requirement: evaluate repeatable outcomes and failure classes before promoting a change. This is a synthesis, not a new result demonstrated by those papers.

**Proposed feature — Release Laboratory.** A proposed prompt, model, agent recipe, connector, or workflow change competes against the active version on the same cases. The release page explains which business outcomes improved, which regressed, and what evidence supports promotion.

**Implementation.** Keep immutable evaluation sets with a held-out partition and domain-owner labels. Version datasets, evaluators, prompts, models, policies, and workflow definitions. Run paired scenarios and report sample sizes and uncertainty, avoiding rankings on tiny differences. Gate deterministic invariants independently of model-judged quality. Offer read-only shadow execution before a limited rollout, then explicit promotion and rollback of future runs. Existing runs retain their original versions unless deliberately migrated through a separately reviewed procedure.

**Measurable test.** Include a candidate that looks cheaper but loses important cases, and one that overfits the development set. Verify rejection. Track successful business outcomes, unnecessary human reviews, latency, cost, and prohibited effects separately; do not hide tradeoffs in one opaque score.

**Limits.** Historical cases may miss tomorrow's inputs. Improvement suggestions need continuing monitoring and owner review. No automated optimizer should rewrite production policy or grant itself broader authority.

## What should feel exceptional in the demonstration

Show one coherent incident-resolution story. An operator describes the desired outcome; a validated graph appears with one unresolved assumption. They resolve it, inspect the evidence contract, and test a timeout-after-write scenario. The laboratory catches a duplicate-action risk. AI proposes a narrow repair, which survives the repeated tests. A reviewer approves the precise change. A subsequent run pauses for a real decision, explains what it needs, then resumes with an auditable result.

The impact comes from continuity: the requirement, graph, scenario, evidence, approval, and executed action are connected objects. The canvas should make those relationships immediately navigable. This is a stronger and more defensible product thesis than a larger catalog of disconnected AI buttons.
