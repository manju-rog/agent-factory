# How Axiom's Agentic, Domain-Agnostic Intelligence Works

This guide explains, in plain language, how Axiom uses connected workflow nodes, results from earlier steps, and Goal Agents that change their approach when the facts change.

It describes the behavior implemented in the current local Axiom application.

## The answer in one minute

Axiom has two cooperating layers:

1. **The workflow is the visible map.** Its connected nodes decide what must happen first, what may run next, where fixed branches go, where people must approve work, and when separate branches join.
2. **A Goal Agent is an adaptive worker inside one node.** It receives a stable goal, selected information, approved capabilities, an expected result, and safety limits. It chooses one permitted action, observes the real result, and then chooses again.

The workflow graph does not secretly redraw itself during a run. The Goal Agent changes its **method inside its node**. Its typed result can then cause a visible Condition node to choose one of the workflow's already designed branches.

```text
Earlier workflow nodes
        │
        │ selected and validated results
        ▼
   Goal Agent node
        │
        ├─ observe the current facts
        ├─ choose one allowed capability
        ├─ see the actual result
        ├─ change the next action when needed
        └─ return a typed result
        │
        ▼
Later workflow nodes or a visible Condition branch
```

The shortest useful description is:

> Connections control when information can move. Contracts control what information may move. The Goal Agent uses that information and new observations to choose its next permitted action.

## “Agentic” and “domain-agnostic” mean different things

The two words are easy to confuse.

- **Agentic** means the system can pursue a goal by choosing its next action after seeing what happened.
- **Domain-agnostic** means the same execution engine is not hardcoded only for support, invoices, access, or one other business area.

A support investigator and an invoice reviewer can use the same Goal Agent runtime. They behave differently because they have different missions, input contracts, allowed capabilities, policies, and result contracts.

The runtime does not contain a special planning branch such as “if this is an invoice, always do these five steps.” Developers register trusted capabilities. Administrators define bounded Goal Agents. The shared runtime performs the same observe → choose → validate → act → observe loop for all of them.

## The six pieces to understand

| Axiom term | Simple meaning | Everyday comparison |
| --- | --- | --- |
| Workflow | The complete business process | A road map |
| Node or step | One unit of work | One stop on the map |
| Connection | A dependency between two steps | “Finish this before going there” |
| Input mapping | A declared way to copy or rename information | Filling selected boxes on a form |
| Capability | One trusted operation the agent may use | A tool in an approved toolbox |
| Goal Agent | A bounded worker that chooses its next allowed tool from the evidence | A trained specialist with a clear job and limited access |

Two more terms become important later:

- **Observation:** the recorded result or error returned by a capability.
- **Contract:** the agreed shape of an input or result, including which fields are required.

## What a connection between nodes really does

Consider this simple workflow:

```text
Request Intake ─────► Service Investigator ─────► Send Outcome
```

The first connection means the Service Investigator depends on Request Intake. The second means Send Outcome depends on the Service Investigator.

A connection has three effects.

### 1. It controls order

A normal node does not start until all its incoming dependencies succeed.

If a node has two incoming connections, both parent nodes normally have to succeed before it becomes ready. This prevents a later step from running with only half of the required work.

A Join node is a special case. It waits until all incoming branches are finished, accepting a branch that was deliberately skipped by a Condition as well as a branch that succeeded. At least one incoming branch must have succeeded.

The published workflow is a one-way graph: it has one starting point, one final point, and no cycles. Repeated adaptive decisions happen inside a Goal Agent session rather than by drawing a workflow connection back to an earlier node.

### 2. It makes earlier results available for input resolution

At runtime, Axiom begins building a node's input from:

- the workflow's starting input; and
- object results returned by the node's directly connected parents.

When several direct parents return the same top-level field name, their objects are merged in stable edge order and a later value can replace an earlier one. Important fields should therefore use explicit mappings and distinct names instead of depending on an accidental collision.

An explicit input mapping can then copy or rename a field from:

- the workflow input, such as `input.requestId`; or
- a valid upstream node result, such as `nodes.intake.output.summary`.

For example:

```json
{
  "requestId": "nodes.intake.output.requestId",
  "requestSummary": "nodes.intake.output.summary"
}
```

This means:

- put `intake.output.requestId` into the new node's `requestId` field; and
- put `intake.output.summary` into its `requestSummary` field.

Axiom checks mappings before publication:

- The source node must really be upstream.
- The source field must be declared by the source node's result contract.
- The destination field must be declared by the receiving node's input contract.
- The two field types must be compatible.
- The source must be available on every possible path to that receiving node, unless the design provides another safe source.
- A mapping cannot contain executable code or an arbitrary expression.

### 3. It can change the facts seen by the next Goal Agent

If an earlier node returns a different value, the next Goal Agent begins with different facts.

That can produce a different action sequence. The intelligence is not based mainly on the previous node's display name. It is based on:

```text
stable mission
  + permitted starting facts
  + allowed capabilities
  + actual capability observations
  + policies and limits
```

For example, a node named “Check Account” might return `accountStatus: "active"` in one run and `accountStatus: "suspended"` in another. The next agent can respond differently because the value changed, not simply because it followed a node named “Check Account.”

## Exactly what a Goal Agent receives

A connection does not give a Goal Agent the whole database, all prior workflow history, every conversation, or every secret.

There are several boundaries:

1. The Goal Agent node has a pinned **input contract**. Before its child session starts, Axiom keeps only top-level input fields declared by that contract.
2. Its specification lists exact permitted context paths such as `input.requestId` or `input.summary`.
3. Only those selected paths become the Goal Agent's starting model context.
4. The Goal Agent sees only the capabilities included in its approved allowlist.
5. Observations produced by those capabilities are added as attributable facts, within the configured context budget.

This is why the administrator's design matters. Axiom enforces the selected boundaries, but it does not magically know which company data is relevant or safe. The designer must choose the input contract, context paths, mappings, capabilities, and policies deliberately.

### Mission, placement objective, and previous-node facts

These three inputs have different jobs:

- The reusable **mission** says what the Goal Agent is responsible for.
- A workflow placement may add a **case-specific objective**, such as “Investigate onboarding failures for the enterprise support route.” Axiom pins this objective with the published placement.
- Previous nodes provide **case facts**, such as the request ID, customer tier, or diagnostic summary.

The previous node does not silently rewrite the mission or invent the case-specific objective. It supplies validated data; the approved Goal Agent definition and workflow placement supply the purpose.

### A simple privacy example

```text
Employee Request
  output:
    employeeId
    requestedRole
    managerApproval
    salary
    medicalNote
        │
        │ Goal Agent contract and context allow only:
        │ employeeId, requestedRole, managerApproval
        ▼
Access Coordinator Goal Agent
```

The access agent can make decisions using the three permitted fields. It should not receive unrelated salary or medical information merely because those values exist elsewhere.

## How the Goal Agent works, one turn at a time

A Goal Agent session repeats a small operational loop.

```text
Observe
   ↓
Choose one next decision
   ↓
Axiom validates it
   ↓
Execute a read, ask a question, or prepare a write
   ↓
Record the real result
   ↓
Observe again and adjust
```

### Step 1: Observe

For each decision, the configured model receives a bounded request containing:

- the mission;
- operating instructions;
- permitted starting input;
- observations recorded so far;
- the identity and arguments of the capability that produced each observation;
- answers supplied after any earlier clarification;
- allowed capability contracts;
- the required result contract;
- applicable policies and stop rules; and
- remaining time, decision, tool, write, token, and cost budgets.

The complete durable session history is stored by Axiom, but the model request is a controlled projection of that state. It is not unrestricted access to everything Axiom knows.

### Step 2: Choose one decision

The model may propose only one of three structured decisions:

1. **Call** one allowed capability with structured arguments.
2. **Ask** for specific missing input that the agent is permitted to request.
3. **Finish** with a result that matches the required contract and cites real evidence.

Conceptually:

```json
{
  "kind": "call",
  "toolId": "service.lookup",
  "arguments": {
    "requestId": {
      "$ref": "input.requestId"
    }
  },
  "reason": "Check whether this request already has a linked issue."
}
```

The short reason is an operational explanation. Axiom does not require or display private chain-of-thought.

### Step 3: Validate

Axiom, not the model, checks the decision.

It rejects:

- unknown decision types;
- extra or malformed fields;
- invented capability IDs;
- capabilities outside the approved allowlist;
- invalid argument shapes;
- references to data that does not exist;
- attempts to override trusted destinations or recipients;
- actions outside the budget; and
- final results that do not match the result contract or lack required evidence.

The model proposes. Trusted application code decides whether the proposal is allowed.

### Step 4: Act

For an allowed read, Axiom calls the registered capability adapter.

For a write, such as creating a Jira issue or posting a message, Axiom first stores the exact proposed action. It does not let the model perform an unrestricted external operation.

### Step 5: Record the observation

The real capability result becomes a new observation. A failure also becomes a visible observation when it is safe to continue.

The record identifies:

- which capability was called;
- which arguments were actually used;
- whether it succeeded or failed; and
- the result or bounded error.

The agent cannot honestly say a capability succeeded before this observation exists.

### Step 6: Choose again

The next model decision includes the new observation. This is the point where behavior becomes genuinely adaptive.

The next action may be different because:

- an existing record was found;
- no record was found;
- the result contradicted an earlier assumption;
- a required fact was missing;
- the capability was denied;
- a service was unavailable;
- business state changed; or
- the remaining budget became too small.

## What changes dynamically and what stays fixed

The safest way to understand Axiom is to separate method from authority.

| Can change during a case | Stays fixed for that published run |
| --- | --- |
| Which allowed capability the agent calls next | The agent's mission |
| The order of allowed capability calls | The pinned agent version |
| Unbound arguments for an allowed capability call | Trusted destinations, recipients, and resource bindings |
| Whether the agent asks for missing information | The allowed capability list |
| The evidence gathered | Input and result contracts |
| The operational explanation for the next step | Context boundaries |
| Whether the agent finishes, returns a partial result, pauses, or escalates | Required approvals |
| The typed result values | Policies and resource limits |
| Which already-designed Condition branch runs after the result | The published workflow graph |

The Goal Agent may change its procedure. It may not:

- add a new capability;
- grant itself access;
- read unselected data;
- remove a required approval;
- change its mission;
- increase its own budget;
- redraw the published workflow;
- execute model-generated code or shell commands;
- call an invented or arbitrary URL;
- treat retrieved text as permission; or
- declare an external action successful without a recorded result.

It also does not learn across unrelated runs or rewrite its own published instructions after a success. Improvements become a reviewed new version rather than an invisible self-modification.

## A complete example: one agent, four different paths

Suppose an administrator creates one reusable **Service Investigator** Goal Agent.

Its mission is:

> Resolve or safely route an onboarding problem using permitted evidence, avoiding duplicate work.

Its allowed capabilities are:

- look up an existing linked issue;
- read permitted diagnostics;
- search approved guidance; and
- prepare a new work item.

Its required result contains:

- a disposition;
- a summary;
- an optional existing or prepared issue identifier; and
- evidence references.

The workflow contains only one Service Investigator node:

```text
Request Intake
      │ maps requestId, accountId, summary
      ▼
Service Investigator Goal Agent
      │ typed result
      ▼
Condition
  ├─ resolved or existing issue ─► Communicate Outcome
  └─ specialist needed          ─► Human Review
```

### Case A: an issue already exists

1. The agent calls the issue lookup capability.
2. The capability returns `ISSUE-482`.
3. The agent finishes with that issue and cites the lookup observation.
4. It does not search more systems or create a duplicate.

```text
lookup issue → existing issue found → finish
```

### Case B: no issue exists

1. The same agent calls the same lookup capability.
2. The result says no linked issue exists.
3. The agent reads permitted diagnostics.
4. It searches approved guidance.
5. The evidence does not solve the problem.
6. It prepares an exact new work item.
7. Axiom pauses for human approval.
8. After approval, Axiom dispatches the stored action and records the receipt.
9. The agent uses that real receipt in its final result.

```text
lookup issue
   → none found
   → read diagnostics
   → search guidance
   → prepare issue
   → approval
   → execute stored action
   → observe receipt
   → finish
```

### Case C: the request ID is missing

For this path, the agent design treats `requestId` as a permitted but optional starting field. If a field is required by the node's input contract or an explicit mapping and is absent, Axiom rejects the input before the Goal Agent starts instead of asking the model to repair an invalid contract.

1. The agent sees that the allowed `input.requestId` field has no value.
2. It asks one focused question.
3. The child session pauses and the parent workflow node shows **waiting for input**.
4. A person supplies only the requested field.
5. The same durable session resumes with its earlier observations intact.

```text
missing requestId → ask → pause → answer supplied → resume
```

The answer can fill a missing permitted field. It cannot secretly replace a value that was already bound to the session.

### Case D: Jira or another required service is unavailable

1. The agent calls an allowed capability.
2. The adapter records a bounded service-unavailable error.
3. A trusted stop rule decides whether the session may continue, must return a partial result, must escalate, or must stop.
4. The agent does not invent a successful ticket.

```text
capability call → unavailable observation → configured boundary action
```

These four paths use one saved agent version. The mission and authority remain the same. The capability sequence changes because the evidence changes.

## How one Goal Agent can use a previous Goal Agent's result

Goal Agents can be connected like other workflow nodes.

```text
Service Investigator Goal Agent
            │
            │ typed result
            ▼
Communicate Outcome Goal Agent
```

Suppose the first agent returns:

```json
{
  "disposition": "existing_issue",
  "issueId": "ISSUE-482",
  "summary": "A known onboarding defect already covers this request."
}
```

The second agent can receive selected fields through its input contract and mapping. It might prepare a message that links to the existing issue.

On another run, the first agent may return:

```json
{
  "disposition": "needs_specialist",
  "summary": "Identity evidence conflicts and needs human review."
}
```

The same second agent can now choose a different permitted action, such as preparing an internal escalation instead of a customer resolution.

What matters is not “the previous agent was Service Investigator.” What matters is:

- the previous node completed successfully;
- its result matched its pinned contract;
- the receiving node was connected appropriately;
- selected fields were available to the receiving contract; and
- the receiving agent's own mission and capabilities allowed the next action.

This makes agents reusable. A Goal Agent does not need a hardcoded rule for every possible predecessor name.

## Two different kinds of branching

Axiom supports two kinds of changing path, and they should not be confused.

### 1. A Goal Agent changes its internal action path

This happens inside one node:

```text
Goal Agent
  ├─ lookup → finish
  ├─ lookup → diagnostics → prepare action
  └─ ask → resume → lookup
```

These internal actions appear in the Goal Agent session inspector. They do not add new boxes or lines to the workflow canvas.

### 2. A Condition changes the visible workflow path

This happens between nodes:

```text
Goal Agent result
       ▼
Condition
  ├─ match   ─► Specialist Review ─┐
  └─ default ─► Ordinary Handling ─┤
                                   ▼
                                  Join
```

The Condition evaluates a rule defined in the published workflow. It selects one visible branch and marks the other branch as skipped until the paired Join.

The model does not invent these workflow branches during the run. Administrators can inspect them before publication.

## Parallel work and joins

A workflow may also deliberately start independent branches in parallel.

```text
                 ┌─► Check Identity ────┐
Request ─► Split ┤                      ├─► Join ─► Review
                 └─► Check Entitlement ─┘
```

Both checks can produce evidence independently. The Join waits until the required incoming branches are finished. The later Review step then receives the joined workflow state according to its input contract and mappings.

Parallel workflow branches are designed on the canvas. They are different from a Goal Agent making several sequential decisions inside one child session.

“Parallel” means the branches become independently eligible. The local reference scheduler does not promise that their machine instructions execute at exactly the same instant.

## The parent workflow and child Goal Agent session

When a published workflow reaches a Goal Agent node:

1. The parent workflow resolves and validates the node input.
2. Axiom loads the Goal Agent definition pinned into that workflow release.
3. Axiom creates one durable child session for that node.
4. The parent node waits while the child session works.
5. The child may be running, waiting for input, waiting for exact-action approval, completed, stopped, or failed.
6. When the child completes, Axiom validates its output against the Goal Agent node's pinned result contract.
7. The validated typed result becomes the parent node's output.
8. Downstream workflow nodes may then start.

If the application restarts, the durable records allow the same parent run and child session to continue. Axiom does not intentionally create a fresh child each time the scheduler checks the node.

Failure and pause states are not hidden:

- **waiting for input** pauses the parent at that node;
- **waiting for approval** exposes the exact prepared action;
- **failed or stopped** causes the workflow node to fail visibly; and
- **completed** passes the typed result downstream.

## Why approval is separate from intelligence

A Goal Agent may discover that a write is useful, but discovery is not permission to execute it.

For a consequential action, Axiom stores a prepared action containing items such as:

- the capability and version;
- the exact destination or adapter binding;
- the exact arguments;
- the policy and authorization requirements;
- evidence references;
- relevant source-result versions;
- a stable operation identity; and
- a fingerprint of the complete action.

A permitted reviewer approves or rejects that exact prepared action.

```text
Agent proposes exact write
          ↓
Axiom freezes destination + arguments + evidence + identity
          ↓
Human reviews that exact packet
          ↓
Approved: execute the stored packet
Rejected: stop that action
```

If the payload, destination, policy, connection generation, or relevant business state changes, the old approval is not silently reused.

There are also separate kinds of approval:

- approval to publish a workflow;
- approval to start a node or task; and
- approval for an exact write discovered inside a Goal Agent session.

One does not automatically grant the others.

## What happens when information or tools fail

Dynamic behavior does not mean “keep trying anything until something works.” It means adapt within declared boundaries.

| Situation | Safe behavior |
| --- | --- |
| A permitted input is missing | Ask for that exact field and pause |
| An existing record is found | Reuse it instead of creating a duplicate |
| A capability is not allowed | Reject the decision |
| A registered service is unavailable | Record the error and follow the configured stop rule |
| Evidence conflicts | Gather another permitted fact, return uncertainty, or escalate |
| A budget is exhausted | Stop visibly |
| A model result arrives too late for the session revision | Ignore the stale completion |
| A read fails safely | Record the failure so a later decision may adapt |
| A write may have happened but no receipt returned | Stop and require reconciliation; do not blindly repeat it |
| Business state changes after preparation | Invalidate the old action and require a new decision |

This is one reason Axiom records observations and effects separately. A confident explanation is not proof that an external change happened.

## What is genuinely intelligent here

With a configured compatible model, the intelligence lies in choosing a useful next action from:

- a stable goal;
- bounded facts;
- real observations;
- explicit tool descriptions;
- business constraints; and
- the remaining budget.

The model can recognize that:

- an existing issue makes creation unnecessary;
- a missing receipt blocks invoice reconciliation;
- a privileged role requires escalation;
- contradictory diagnostics need another permitted check; or
- a service outage means only a partial result is currently supportable.

Trusted application code supplies the guardrails:

- strict decision shapes;
- capability allowlists;
- input and output validation;
- context boundaries;
- approval enforcement;
- idempotency and operation identity;
- durable state;
- version pinning;
- budget enforcement; and
- evidence records.

Neither part is enough by itself. A model without boundaries is unsafe. Fixed workflow code without adaptive decisions becomes brittle when real cases differ.

## Scripted demonstrations versus real model decisions

The local Axiom application contains scripted fixture providers for repeatable demonstrations.

A scripted fixture can prove that the runtime correctly handles:

- different action sequences;
- observations;
- clarification;
- exact approvals;
- persistence;
- budgets; and
- parent/child workflow behavior.

It is **not AI**, and it does not prove that a live model will make good business decisions.

A newly created custom Goal Agent needs a compatible model provider configured on the server. If the provider is absent or incompatible, Axiom shows an error. It does not silently run a script and label the result as AI.

Live-model quality must be evaluated separately with representative cases, repeated trials, outcome evidence, cost, latency, and forbidden-action testing.

## Why the architecture is domain-agnostic

The same runtime can support very different tasks:

| Goal Agent | Starting facts | Example capabilities | Possible adaptive change |
| --- | --- | --- | --- |
| Service Investigator | request and account IDs | issue lookup, diagnostics, runbook search | Reuse an issue or prepare a new one |
| Invoice Reviewer | invoice, order, and supplier IDs | read invoice, read receipt, read policy | Finish normally or request exception review |
| Access Coordinator | employee, role, approval | read entitlement, read risk, prepare grant | Prepare standard access or escalate privileged access |
| Vendor Reviewer | supplier and contract facts | registry lookup, security review, policy check | Continue onboarding or request missing evidence |

The runtime does not need a new planning loop for each row. What changes is the reviewed configuration and trusted capability registry.

New combinations can be built from existing capabilities. A completely new external operation still requires a developer to implement and validate a capability adapter. The model cannot create its own production integration.

## Version pinning keeps dynamic behavior controlled

Dynamic does not mean definitions change while a case is running.

When an agent version and workflow version are published, Axiom freezes the relevant definitions. A running case keeps:

- the exact workflow graph;
- the exact Goal Agent specification;
- the exact capability contracts;
- the exact input and result contracts; and
- the selected provider mode.

If an administrator later publishes a better agent version, existing runs stay on the version with which they started. A new workflow placement or release is needed to adopt the new version.

This prevents a long-running case from silently changing rules halfway through.

## How to inspect all of this in the interface

Use these areas:

### Workflow Studio

See:

- node connections and dependencies;
- input mappings;
- Conditions and their fixed branches;
- Parallel Split and Join nodes;
- manual or approval stages; and
- the exact approved Goal Agent version placed in the graph.

### Agent Factory

See or define:

- the mission;
- operating instructions;
- input and result contracts;
- permitted context;
- allowed capabilities;
- required evidence;
- stop rules;
- policies;
- evaluation cases; and
- budgets.

### Goal Agent run inspector

See the real sequence:

```text
model decision
  → prepared capability action
  → actual observation
  → changed next decision
  → question, approval, or typed result
```

This is the best place to understand why two cases followed different internal paths.

### Runs

See the parent workflow node states, child Goal Agent link, downstream results, failures, waits, and final workflow status.

### Review Inbox

See the exact action a person is being asked to approve. Approval should show the protected payload and identity, not only a vague sentence.

### Rehearsal Lab and behavior previews

Compare how the same saved agent or workflow behaves when:

- evidence is missing;
- a duplicate exists;
- a service times out;
- approval is rejected;
- information conflicts; or
- an external instruction is malicious.

## A beginner's design checklist

Before adding a Goal Agent node, answer these questions:

1. What stable outcome should this agent achieve?
2. What exact result must it return?
3. Which workflow input and prior node fields does it really need?
4. Which of those fields may enter the model context?
5. Which registered capabilities may it use?
6. Which capability results count as required evidence?
7. Which actions change another system?
8. What exact approval is required for those actions?
9. What should happen when evidence is missing, conflicting, denied, stale, or unavailable?
10. What time, tool, write, token, and cost limits are reasonable?
11. Which visible Condition should route the workflow after the agent returns?
12. What trusted check would show whether the business outcome really succeeded?

If these answers are unclear, adding more AI will not make the process clear.

## Common misunderstandings

### “Does every connection give the next agent all previous data?”

No. Connections establish dependencies and make direct parent results candidates for input resolution. Contracts, mappings, and permitted context paths determine what a Goal Agent can actually receive and what reaches the model.

### “Does the agent behave differently only because the previous node has a different name?”

No. It responds to selected values, observations, mission, capabilities, policies, and limits. Display names are not the intelligence.

### “Can the agent create a new workflow branch while running?”

No. It can change its internal permitted capability sequence. Visible workflow branches are created and reviewed in Workflow Studio.

### “Can a previous agent tell the next one to ignore its rules?”

No. Earlier outputs and retrieved documents are data, not higher-priority authority. Axiom validates every proposed action against the receiving agent's pinned rules.

### “Does valid JSON prove the business task succeeded?”

No. It proves the result has the expected shape. Evidence checks and trusted domain outcome validators are needed to establish business success. For custom domains without such a validator, outcome verification may remain unknown.

### “Is a scripted demo the same as model intelligence?”

No. A scripted fixture proves deterministic runtime behavior. A configured model is required for real model-chosen decisions.

## The complete mental model

Think of Axiom as a railway system with a bounded specialist working at one station.

- The **workflow graph** is the railway map.
- A **connection** says which station must be reached before another can operate.
- An **input mapping** chooses which labeled package is handed forward.
- A **contract** checks the package shape.
- A **Goal Agent** is the specialist who can choose among approved tools at its station.
- A **capability observation** is what the specialist learns after using a tool.
- A **Condition** is a visible switch in the railway track.
- A **Join** waits for the required tracks to come back together.
- An **approval** is a human key for one exact consequential action.
- A **receipt** is evidence that an attempted external action returned a result.
- **Version pinning** prevents the map and rules from changing during the journey.

The specialist may change how it works after every observation. It cannot move the tracks, take an unapproved tool, open every package, or declare that a delivery happened without a receipt.

That is Axiom's central idea:

> Keep business structure and authority stable, while allowing the procedure inside a Goal Agent to adapt to the actual case.

## Related implementation documents

- [Axiom beginner guide](AXIOM_BEGINNER_GUIDE.md)
- [Agent Factory contract](app/FACTORY_CONTRACT.md)
- [Application contract](app/CONTRACT.md)
- [Agent Factory paradigm](factory/Agent_Factory_Paradigm.md)
- [External integrations](docs/EXTERNAL_INTEGRATIONS.md)
