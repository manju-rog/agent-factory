# Axiom: the complete beginner's guide

This guide is for someone who has never used Axiom, workflow software, automation tools, or AI agents.

It explains what Axiom is, why it exists, how its parts work together, how to use the local application, what the examples demonstrate, how external services fit in, and what is not yet a production feature.

---

## 1. Axiom in one minute

Axiom helps an organization turn a business process into a visible, controlled workflow.

A workflow is simply a series of steps. For example:

1. Receive a customer request.
2. Find the customer record.
3. Investigate the problem.
4. Ask a person to approve an important action.
5. Create a work item.
6. Save the result and evidence.

Some steps always follow the same instructions. Other steps need to adapt to what they discover. Axiom supports both:

- **Fixed steps** perform a known operation in a known way.
- **Goal Agent steps** receive a goal and choose the next permitted action from the evidence they find.

Axiom does not give an AI unlimited access. Every agent receives a limited job description, a limited set of tools, limited context, a required result shape, and explicit stopping or approval rules.

The current workspace is **Axiom 2.0**, a runnable local reference application. It is suitable for learning, demonstrations, development, and controlled testing. It is not a finished multi-tenant production deployment.

---

## 2. The problem Axiom solves

Ordinary automation works well when every case follows the same path.

For example:

> When a form is submitted, copy its fields into a ticket.

That process is predictable. A fixed workflow is a good fit.

Real business work is often less predictable:

- A ticket may already exist.
- Required information may be missing.
- Two records may disagree.
- A policy may require extra review.
- A service may be unavailable.
- A proposed action may be safe in one case but sensitive in another.

Building a separate workflow branch for every possibility becomes difficult to maintain. Axiom therefore allows a workflow to include a Goal Agent whose purpose stays stable while its procedure changes according to the current case.

The important idea is:

> Keep the goal, permissions, limits, and expected result stable. Let the agent adjust the permitted steps after it sees real evidence.

This gives people flexibility without removing human control or business rules.

---

## 3. A simple mental model

Imagine a well-run company office.

| Axiom concept | Office equivalent |
| --- | --- |
| Workflow | The company process map |
| Step or node | One job on that map |
| Fixed Action | A checklist with exact instructions |
| Goal Agent | A trained employee with a clear assignment |
| Capability | A tool the employee is allowed to use |
| Context | The case files the employee is allowed to read |
| Connection | The secure doorway to another business system |
| Agent specification | The employee's written job instructions |
| Session | The work record for one case |
| Prepared action | A completed form waiting for approval |
| Approval | Permission for that exact form and action |
| Evidence | The records showing why a decision was made |
| Receipt | Proof of what actually happened |
| Release | An approved, locked version of the process |
| Rehearsal | A safe practice run |

The Goal Agent is not the owner of the whole company. It cannot add its own permissions, invent a new tool, remove a required approval, or claim that an external action succeeded without a result.

---

## 4. The most important building blocks

### 4.1 Workflow

A workflow is a connected map of work.

It answers questions such as:

- What starts the process?
- Which steps must happen?
- Which steps can happen at the same time?
- When is a human decision required?
- Which result allows the next step to begin?
- What counts as completion?

A workflow can contain fixed actions, Goal Agents, conditions, approvals, joins, manual work, and final outcomes.

### 4.2 Step or node

Each box on the workflow canvas is a step. A connection between two boxes means that information or control moves from one step to another.

Common step purposes include:

- Receive input.
- Read a record.
- Analyze a case.
- Wait for a person.
- Choose a route.
- Prepare or perform an action.
- Combine parallel results.
- Record an outcome.

### 4.3 Capability

A capability is one approved operation that an agent can request.

Examples:

- Read a customer record.
- Search existing service issues.
- Retrieve a Confluence page.
- Read Slack channel history.
- Search Jira issues.
- Prepare a Jira issue.
- Prepare a Slack message.
- Send a reviewed JSON webhook.

A capability has a stable name, a version, a description, expected input, expected output, its read/write effect, and the authority required to use it.

An agent cannot use a capability merely because it knows the capability exists. The capability must be registered, allowed by the agent specification, and allowed for the person and connection involved.

### 4.4 Connection

A connection is the governed path from Axiom to another service.

The connection says:

- Which provider is involved.
- Which exact destination is allowed.
- Which authentication method is used.
- Which operations are allowed.
- Which scopes are required.
- Whether an operation reads or writes.
- How large and how long a response may be.
- Which connection version and generation are current.

A connection does not automatically give every agent access. It only makes reviewed capabilities available for later selection.

### 4.5 Agent specification

An agent specification is the stable job description for a Goal Agent.

It includes:

- **Mission:** the outcome the agent should achieve.
- **Operating instructions:** how it should behave while pursuing the mission.
- **Permitted context:** the information it may receive at the start.
- **Capabilities:** the exact tools it may request.
- **Input contract:** the information a run must provide.
- **Result contract:** the exact structure the agent must return.
- **Evidence requirements:** what must support the result.
- **Stop and escalation rules:** when to ask, pause, escalate, or fail.
- **Policies:** the business rules that apply.
- **Budgets:** limits for time, turns, tool calls, writes, model tokens, and estimated cost.
- **Evaluation cases:** example situations used to check behavior.

Saving a specification creates a draft. It does not authorize the agent. A separate reviewer must activate the exact saved version.

### 4.6 Agent session

A session is the durable work record for one agent handling one case.

It contains:

- Starting input and permitted context.
- Every operational decision.
- Every capability request.
- Every actual observation.
- Clarification questions and answers.
- Prepared actions and approval state.
- Provider and model metadata when available.
- Resource usage.
- Final result or stopping reason.

The durable history is larger than the information sent to a model for one decision. The server projects only the administrator-selected `input.*` paths and carries accumulated observations within the configured context and resource limits. Choosing what is relevant remains an agent-design and engineering responsibility; Axiom does not guarantee that every useful fact is automatically selected.

### 4.7 Prepared action

A prepared action is an exact proposed write that has not yet been dispatched.

It includes details such as:

- Destination.
- Operation and version.
- Exact arguments or body.
- Evidence references.
- Policy reference.
- Connection version and generation.
- Stable operation identity.
- Content and plan hashes.

Approval applies to this exact prepared action. If an important field changes, the old approval is no longer enough.

---

## 5. Fixed Actions and Goal Agents

These two kinds of work are intentionally different.

### Fixed Action

Use a Fixed Action when the procedure is already known.

Example:

> Read customer number `C-1042` from the approved customer directory.

The step has one known operation and predictable input/output.

### Goal Agent

Use a Goal Agent when the required procedure depends on discoveries made during the case.

Example mission:

> Investigate this onboarding problem and return either the existing linked issue, a supported resolution, a clarification request, or a prepared work item.

The same agent may behave differently:

| What it discovers | What it does next |
| --- | --- |
| A linked issue already exists | Returns the existing issue instead of creating a duplicate |
| No issue exists | Searches guidance and prepares a new work item |
| The request identifier is missing | Asks for that one missing fact and pauses |
| A required service is unavailable | Returns a useful partial result and explains the gap |
| A proposed write is sensitive | Prepares the exact action and waits for approval |

The agent is adaptive, but its authority is not.

---

## 6. How a Goal Agent thinks and acts

A Goal Agent follows a repeated operational loop.

1. **Observe:** Read the mission, relevant permitted context, previous observations, open questions, constraints, and remaining budget.
2. **Choose:** Propose one structured next decision.
3. **Validate:** Axiom checks that the decision names a real allowed capability and uses valid arguments.
4. **Act:** Axiom performs an allowed read or prepares a reviewed write.
5. **Record:** Store the actual result, error, or human answer.
6. **Adjust:** Let the next decision use the new observation.
7. **Finish or pause:** Return a valid result, request information, wait for approval, or stop with a visible reason.

The model does not submit shell commands or arbitrary program code through this loop. It must choose from registered capabilities.

### Example: service investigation

Suppose the input is:

```json
{
  "requestId": "REQ-1042",
  "summary": "New employee cannot access the onboarding portal"
}
```

Possible run A:

1. The agent calls `service.lookup`.
2. The result contains an already linked issue.
3. The agent returns that issue with its evidence.
4. No new ticket is created.

Possible run B:

1. The same agent calls `service.lookup`.
2. No linked issue exists.
3. It calls `service.search_runbook`.
4. The runbook evidence does not resolve the problem.
5. It prepares `service.create_ticket`.
6. Axiom pauses for exact approval.
7. After approval, Axiom executes the stored action and records the receipt.

Possible run C:

1. The input does not contain `requestId`.
2. The agent requests only that missing value.
3. The session pauses without inventing it.
4. A person supplies the value.
5. The same durable session resumes.

These are different procedures produced by one saved agent specification.

---

## 7. The complete Axiom lifecycle

The full journey is:

1. A developer registers safe executable capabilities.
2. An administrator configures any required connection.
3. An administrator creates a Goal Agent specification.
4. A reviewer activates one exact specification version.
5. An administrator places that Goal Agent into a workflow.
6. The workflow draft is reviewed and published.
7. A user starts a run with valid input.
8. Fixed steps and Goal Agents perform their work.
9. The run may request missing information or exact approval.
10. Schema-validated typed results flow to downstream steps. A custom domain's independent business-outcome status may still be `unknown` until a trusted validator exists.
11. The run stores evidence, effects, receipts, and the final outcome.

Published definitions are pinned. Publishing a newer agent or workflow version does not silently change a run that already started.

---

## 8. Who does what

The local application includes seeded development identities so different responsibilities can be demonstrated.

| Role | Typical responsibility |
| --- | --- |
| Administrator | Builds workflows, drafts agents, configures connections, and manages the workspace |
| Reviewer | Activates reviewed agent versions, reviews releases, and makes eligible approval decisions |
| Operator | Runs permitted operational work and handles assigned manual steps |
| Contributor | Supplies permitted information and participates in limited work |

These identities are local demonstration accounts. They are not corporate sign-in, single sign-on, or tenant isolation.

The important separation is that the person who drafts an agent does not automatically authorize it for use.

---

## 9. Tour of the application

### Agent Factory

Use Agent Factory to create, review, compare, and inspect Goal Agents.

It contains:

- Agent catalog.
- Specification editor.
- Capability and context selection.
- Result and evidence requirements.
- Resource limits.
- Draft and activation lifecycle.
- Behavior previews.
- Run/session inspector.

### Workflow Studio

Use Workflow Studio to create and connect business-process steps.

It supports:

- Blank workflows.
- Reusable steps and approved Goal Agents.
- Positioned node insertion.
- Connections between nodes.
- Input mappings.
- Conditions and joins.
- Human stages and approvals.
- Validation, rehearsal, review, publication, and runs.

### Capability Registry

This shows registered executable capabilities and reusable agent implementations.

It is not an app store that accepts arbitrary code from a browser. Executable code still needs developer delivery and review.

### Runs

Runs shows active and completed workflow executions.

Open a run to inspect:

- Current step state.
- Waiting or blocked reasons.
- Evidence.
- Decisions.
- Prepared actions.
- Effects and receipts.
- Final outcome.

### Review Inbox

Review Inbox collects work that requires a permitted human decision, such as an exact prepared write.

### Rehearsal Lab

Rehearsal Lab runs controlled cases without treating them as real business effects.

Use it to test normal cases, missing information, service failures, conflicting evidence, duplicates, approval problems, and changed business state.

### Connections

Connections is where an administrator configures bounded access to external systems.

### Audit Trail

Audit Trail records important administrative and operational events. It helps answer who did what, when, and against which version.

### Day and night mode

The sun/moon control changes the interface theme. The choice is stored in the current browser. It does not alter workflow data.

---

## 10. Start the local application

### Requirements

- Python 3.10 or newer.
- A web browser.
- No required paid workflow platform.
- No required JavaScript package installation.

### Start it

Open a terminal in the source folder, then run:

```bash
cd app
python3 server.py --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

`127.0.0.1` means the application is available only on the local computer unless the server is deliberately deployed differently.

### Stop it

Return to the terminal and press `Ctrl+C`.

### Where data is stored

The default local database is:

```text
app/.runtime/axiom.sqlite3
```

Restarting the server with the same database retains local workflows, releases, runs, decisions, connections, and fixture records.

Do not delete that database unless you intentionally want to remove the local state.

---

## 11. A ten-minute first tour

1. Open Axiom in the browser.
2. Use the development account selector to choose the administrator.
3. Open **Workflow Studio**.
4. Look at the existing service-request workflow.
5. Select a node to see its configuration.
6. Open a node's ellipsis menu. The same menu is available through right-click or `Shift+F10`.
7. Open **Agent Factory** and inspect a bundled agent.
8. Open its behavior preview to compare different evidence paths.
9. Open **Rehearsal Lab** and inspect a controlled scenario.
10. Open **Connections** and review which providers are setup-capable and which still require development work.
11. Switch to night mode.
12. Return to Studio and confirm that the theme remains active.

At this point, the reader has seen the design, agent, testing, connection, and operational parts of the product without changing important data.

---

## 12. Create a workflow from scratch

### Step 1: create the draft

1. Open **Workflow Studio** as the administrator.
2. Select **New**.
3. Enter a clear name.
4. Enter the business purpose.
5. Select **Create blank template**.

The new draft opens with the step palette so the first step can be selected immediately.

### Step 2: add the first step

Choose a reusable step from the palette. Give it a business-friendly name and configure its required fields.

### Step 3: add more steps

Use any of these paths:

- Select **Add step**.
- Use **Add connected step** on an existing node.
- Right-click an empty area and add a step at that position.
- Use the visible node action button on a touch device.

### Step 4: connect steps

Use the input and output connection controls or **Connect from this step**.

A connection should express a real dependency. Do not connect boxes merely to make the diagram look complete.

### Step 5: map data

Input mapping tells a step where its values come from.

Example:

```text
Workflow input: customerId
        ↓
Customer lookup input: id
        ↓
Customer lookup output: accountOwner
        ↓
Goal Agent context: owner
```

Axiom checks that a mapped source exists, is available on every required path, and has a compatible data type.

### Step 6: validate

Select **Validate before release**. Fix every reported structural, mapping, schema, or policy problem.

### Step 7: save and rehearse

Save the draft and run safe rehearsal cases. A successful attractive diagram is not enough; test behavior and final state.

### Step 8: review and publish

Submit the draft for review. The reviewer inspects the changes and publishes an immutable release.

### Useful editing controls

- Right-click or `Shift+F10`: open step actions.
- Arrow keys: move through a menu.
- `Home` and `End`: jump within a menu.
- `Escape`: close the menu.
- `Ctrl/Cmd+S`: save.
- `Ctrl/Cmd+D`: duplicate the selected step.
- Undo and Redo: reverse or restore draft changes.

Removing a step asks for confirmation. Duplicating a step creates a separate placement and does not silently copy its existing connections.

---

## 13. Create a Goal Agent

### Example goal

Suppose the organization wants an agent that investigates supplier onboarding problems.

### Mission

```text
Determine why this supplier cannot complete onboarding and return either a supported resolution, a missing-information request, or a prepared escalation.
```

### Permitted context

```text
input.supplierId
input.onboardingRequestId
input.requestSummary
input.requesterDepartment
```

Context paths must be exact `input.*` paths exposed by the agent's input contract. Do not select all workflow data simply because it is available.

One compatible input contract is:

```json
{
  "type": "object",
  "properties": {
    "supplierId": {"type": "string", "minLength": 1, "maxLength": 100},
    "onboardingRequestId": {"type": "string", "minLength": 1, "maxLength": 100},
    "requestSummary": {"type": "string", "minLength": 1, "maxLength": 2000},
    "requesterDepartment": {"type": "string", "minLength": 1, "maxLength": 200}
  },
  "required": ["onboardingRequestId", "requestSummary"],
  "additionalProperties": false
}
```

`supplierId` is deliberately optional here so the agent can request it when the case genuinely lacks it.

### Allowed capabilities

```text
supplier.read
onboarding.status.read
policy.search
case.search
case.prepare_create
```

These names illustrate what a production supplier integration might provide. They are not bundled capability IDs. In the editor, select only capability IDs that actually appear in the current Capability Registry. A new executable capability requires reviewed developer integration.

### Result

A result contract is a JSON Schema—the agreed rules for the returned information—not an example answer. A simple contract might be:

```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["resolved", "needs_information", "prepared_escalation", "blocked"]
    },
    "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
    "evidenceIds": {
      "type": "array",
      "items": {"type": "string", "minLength": 1, "maxLength": 200},
      "maxItems": 50
    },
    "caseId": {"type": "string", "minLength": 1, "maxLength": 200}
  },
  "required": ["status", "summary", "evidenceIds"],
  "additionalProperties": false
}
```

### Boundaries

Examples:

- Ask for `supplierId` when it is missing.
- Do not create another case when an open matching case exists.
- Require approval before creating a new external case.
- Stop after the tool or time budget is exhausted.
- Return a partial result when the policy service is unavailable.

### Limits

Set sensible limits for:

- Decision turns.
- Tool calls.
- Write attempts.
- Elapsed time.
- Model tokens.
- Estimated cost.

Limits protect the organization from stuck or unexpectedly expensive sessions.

### Save and activate

1. Save the agent as an administrator.
2. Confirm that it remains a draft.
3. Switch to the reviewer development identity.
4. Inspect the exact version.
5. Activate it.
6. Return to Studio and place the approved Goal Agent from the palette.

Later edits create another version. They do not rewrite existing published workflows or active sessions.

---

## 14. How approvals work

There are two different kinds of approval.

### Approval to start a step

This permits a workflow stage to begin.

### Approval of a discovered action

This permits one exact action that the agent discovered later.

These approvals are not interchangeable.

Example:

1. A person approves starting an investigation.
2. The investigation discovers that a privileged entitlement is required.
3. The agent prepares an access-grant request.
4. Axiom asks for a new approval covering the exact account, entitlement, duration, evidence, and destination.

The first approval is not blanket permission for the second action.

### What happens if something changes

Before dispatch, Axiom rechecks important authority and source information.

If the connection was revoked, the source record changed, the payload changed, or the action fingerprint no longer matches, the old approval is rejected and a new decision is required.

---

## 15. External connections

Axiom 2.0 includes reviewed presets for:

| Provider | Example uses | Current local status |
| --- | --- | --- |
| Slack | Read bounded channel history; prepare reviewed messages | Setup-capable; no workspace credentials included |
| Jira Cloud | Search/read issues; prepare reviewed issue writes | Setup-capable; no Jira tenant credentials included |
| Confluence Cloud | Check space access; read/list pages; prepare reviewed page creation | Setup-capable; no Confluence tenant credentials included |
| Outbound Webhook | Send reviewed JSON to one exact receiver | Setup-capable; no receiver included |
| REST / OpenAPI | Inspect a strict OpenAPI 3.1 contract | Inspection only; activation requires developer review |
| MCP server | Future reviewed discovery and invocation of MCP tools | Protocol contract exists; runtime client setup is not implemented |

### Safe connection setup

1. Open **Connections** as the administrator.
2. Choose a setup-capable provider.
3. Enter a clear connection name.
4. Select only the operations needed.
5. Enter the exact approved base URL.
6. Choose the authentication method.
7. Reference credentials through server environment variables.
8. Save the connection as a draft.
9. Run its safe health check when available.
10. Activate it only after the current check succeeds.

### Credential example

Set a value in the same terminal that will start the Axiom server:

```bash
export COMPANY_SLACK_TOKEN="replace-with-the-real-secret"
python3 server.py --port 8765
```

In the connection form, reference it as:

```text
env:COMPANY_SLACK_TOKEN
```

If the server is already running, stop it and restart it from the terminal containing that exported variable. Exporting a variable in another terminal does not add it to an existing server process.

The secret value stays in the server process. Public connection responses do not return the value or the environment-variable name.

For a production deployment, use an approved secret manager rather than relying only on process environment variables.

### Connection states

- **Draft:** saved but not authorized for agent use.
- **Ready:** health and authority requirements passed and the connection was activated.
- **Revoked or disabled:** new use is blocked.
- **Error:** a configuration or health problem needs attention.

Restoring a revoked connection returns it to a draft-like review path. It must be checked and activated again instead of silently regaining authority.

### Read operations

An explicitly registered read can be tested or invoked within its allowed destination, arguments, scopes, size, and time limits.

### Write operations

External writes are not directly invoked from the browser connection screen. A Goal Agent prepares the exact write, Axiom stores it, a permitted person reviews it, and Axiom dispatches that same stored action after approval.

### OpenAPI inspection

The OpenAPI screen safely inspects one fully inlined OpenAPI 3.1 JSON document.

It can show candidate operations and a canonical document hash. It does not:

- Fetch remote references.
- Save credentials.
- Decide whether an operation is a read or write.
- Decide required scopes or approval policy.
- Create an active connection.
- Make a candidate executable.

A developer must review, classify, test, and register the final contract.

### Why Axiom cannot promise “every API automatically”

APIs differ in authentication, permissions, rate limits, data meaning, retry safety, and failure behavior. Automatically executing an unknown API would create serious security and reliability risks.

Axiom therefore provides a reusable integration boundary, but new executable tools still require review and validation.

---

## 16. What happens when an external write is uncertain

Sometimes a remote service may accept a request but fail before returning a clear response.

In that situation, blindly retrying can create a duplicate.

Axiom distinguishes:

- **Known failure:** the request was not accepted.
- **Known success:** a valid receipt confirms completion.
- **Unknown outcome:** Axiom cannot prove whether the remote service committed the action.

For an unknown external outcome, the current runtime stops. It does not blindly retry or claim success. A provider-specific reconciliation check or a human investigation is required.

The local ticket fixture includes a controlled lost-acknowledgement recovery demonstration. That local demonstration does not mean every external provider already has reconciliation support.

---

## 17. Evidence, results, and audit history

A valid JSON result only proves that the answer has the expected shape. It does not prove that the answer is true.

Axiom therefore separates:

- **Observed fact:** directly returned by a trusted capability.
- **Inference:** a conclusion drawn from observations.
- **Unresolved question:** something the available evidence did not establish.
- **Effect:** an attempted or completed change.
- **Receipt:** confirmation from the executing system.

Supported local domains have outcome validators that compare final results with trusted local observations and receipts.

Custom domains remain unverified until a developer supplies an appropriate outcome validator.

Run exports are authorized and audited. They redact secret-looking fields and include integrity hashes. A hash can reveal later modification, but it is not a person's digital signature.

---

## 18. Versions and why they matter

Business processes change over time. Axiom keeps versions so old and new work do not become mixed.

### Example

1. Access Agent version 1 allows standard employee access.
2. A reviewer activates version 1.
3. Workflow release 5 pins Access Agent version 1.
4. An administrator drafts version 2 with a new policy.
5. A run already using release 5 stays on version 1.
6. A later workflow release may explicitly adopt version 2.

The same idea applies to workflow releases, capability contracts, connection generations, scenario definitions, and prepared actions.

Canvas position and display labels do not define data flow. Stable identifiers and exact bindings do.

---

## 19. Rehearsal and behavior preview

Before publishing an agent or workflow, test more than the happy path.

Useful variations include:

- Normal case.
- Missing evidence.
- Conflicting records.
- Existing duplicate.
- Denied capability.
- Unavailable service.
- Changed business state.
- Approval rejection or expiry.
- Lost acknowledgement.
- Malicious or misleading retrieved content.

Behavior Preview compares how one agent version acts across controlled variations.

Look for:

- Different action sequences caused by different evidence.
- Unnecessary tool calls.
- Duplicate effects.
- Clear clarification requests.
- Correct approval pauses.
- Useful partial results.
- Evidence supporting completion.
- Time and cost differences.

The bundled previews use scripted fixtures. They verify the runtime and interface, not the planning quality of a live language model.

---

## 20. The included demonstration workflows

The local database begins with the original service-request workflow and five complex demonstrations.

### 20.1 Payment dispute investigation

What it demonstrates:

- Typed dispute input.
- Identity and settlement checks in parallel.
- Conditional routing for higher-value cases.
- Review of the complete proposed action.
- One simulated dispute record and receipt.

Possible real application:

> Help a payments team gather the right evidence and route complex disputes consistently.

### 20.2 Employee access governance

What it demonstrates:

- Employment and manager checks.
- Conflict and license checks.
- Extra review for privileged access.
- Time-bounded access action.

Possible real application:

> Coordinate joiner, mover, and leaver access while preserving security approvals.

### 20.3 Production incident and change control

What it demonstrates:

- Telemetry and customer-impact evidence.
- Severe-incident routing.
- Review of a bounded mitigation.
- A simulated change record.

Possible real application:

> Help an operations team investigate incidents and control risky mitigations.

### 20.4 Vendor risk and procurement onboarding

What it demonstrates:

- Security and corporate evidence checks.
- Enhanced review for material contracts.
- A simulated procurement record.

Possible real application:

> Coordinate procurement, security, legal, and business ownership before onboarding a supplier.

### 20.5 Insurance claim adjudication

What it demonstrates:

- Coverage and fraud evidence.
- Higher-value routing.
- Adjuster review.
- A simulated adjudication record.

Possible real application:

> Gather and compare claim evidence while reserving important decisions for authorized people.

Each complex demonstration has 14 steps and 16 connections. The data and effects are deterministic local fixtures. They do not contact real payment, identity, monitoring, procurement, insurance, or cloud systems.

---

## 21. More practical applications

Axiom's shared runtime can support many domains when the required capabilities and validators exist.

### Customer and employee support

- Triage requests.
- Search known issues.
- Reuse existing work items.
- Ask for missing facts.
- Prepare escalations.

### Finance operations

- Compare invoices, purchase orders, and receipts.
- Detect duplicates.
- Route policy exceptions.
- Prepare reviewed case records.

### Document review

- Retrieve permitted documents.
- Extract required facts.
- Compare clauses with policy.
- Identify missing or conflicting evidence.
- Route uncertain cases to a person.

### Account and vendor onboarding

- Check required documents.
- Verify ownership.
- Detect missing approvals.
- Coordinate several departments.
- Prepare a bounded onboarding action.

### IT and security operations

- Investigate incidents.
- Check asset and account state.
- Apply different procedures for standard and privileged access.
- Require approval for consequential changes.

### Team communication

- Read permitted Slack context.
- Retrieve Confluence knowledge.
- Search or prepare Jira work.
- Prepare a reviewed notification.

Real use requires real provider credentials, tested contracts, least-privilege scopes, reliable outcome validation, and production operations.

---

## 22. Simulation, fixture, model, and production labels

These labels must not be confused.

| Label | Meaning |
| --- | --- |
| Local fixture | Deterministic local data or behavior used for repeatable tests |
| Scripted fixture | Predefined agent decisions sent through the real validation and persistence loop |
| Simulation | A run designed not to create real external effects |
| Recorded preview | An explorable snapshot; it does not run or save work |
| Configured model | A real model endpoint supplied through server settings |
| External connection | A configured outbound provider boundary with server credentials |
| Production | A fully operated deployment with real identity, tenancy, secrets, monitoring, retention, scaling, and provider validation |

The words “fixture sent” or “local ticket created” do not mean that an external email, Slack message, or Jira issue was delivered.

---

## 23. Optional configured AI model

The workflow-edit proposal helper defaults to a deterministic local planner. Bundled Agent Factory examples use a labeled scripted provider. Neither should be described as real AI.

Configured-model mode uses these server environment variables:

```text
AXIOM_MODEL_ENDPOINT
AXIOM_MODEL_NAME
AXIOM_MODEL_API_KEY
AXIOM_MODEL_INPUT_COST_MICROS_PER_MILLION
AXIOM_MODEL_OUTPUT_COST_MICROS_PER_MILLION
```

The endpoint and model name are required for model mode. The key and pricing values depend on the provider.

If the provider is missing or incompatible, Axiom shows an error. It does not silently replace the model with a scripted fixture and call that AI.

A configured endpoint still needs evaluation for quality, privacy, retention, price, availability, and resistance to unsafe retrieved content.

---

## 24. Common run states

| State | Meaning | What a person should do |
| --- | --- | --- |
| Running | Work is progressing | Monitor if needed |
| Waiting for information | A required fact is missing | Supply the requested permitted value |
| Waiting for approval | An exact action needs review | Inspect destination, payload, evidence, and policy |
| Completed | The configured session checks finished; independent business-outcome validation may still be unknown | Review the result, evidence, receipt, and outcome-validation status |
| Failed | A known error prevented completion | Inspect the error and retry only when safe |
| Budget exhausted | A configured limit was reached | Review whether the task or limit should change |
| Cancelled | An authorized person or parent stopped the work | Decide whether a new run is appropriate |
| Unknown external outcome | A remote write may or may not have committed | Reconcile with the destination before any retry |

A useful blocked state is better than invented success.

---

## 25. Common beginner questions

### Is a Goal Agent a chatbot?

No. It is a governed worker inside a business process. It has a defined mission, typed input and result, limited tools, limits, evidence requirements, and stopping rules.

### Do I need an AI model to use Axiom?

No model is needed to explore workflows, use deterministic local execution, run bundled scripted demonstrations, rehearse cases, inspect approvals, or review evidence. Executing a newly created custom adaptive Goal Agent does require a configured compatible model because custom agents do not receive a hidden scripted fallback. A real model is also required for AI-assisted specification proposals.

### Does an agent see the whole database?

No. It receives selected starting context and may use specifically authorized retrieval capabilities.

### Can an agent invent a tool?

No. Unknown capability identifiers and invalid arguments are rejected.

### Can an agent remove an approval?

No. The model cannot change its authority, mission, required approvals, or business policy.

### Can I add any API by pasting its OpenAPI file?

You can inspect a supported OpenAPI 3.1 document. Inspection does not make its operations executable. A developer must review and register the final contract.

### Does Axiom automatically retry every failed write?

No. Reads and writes have different risks. An uncertain write stops rather than risking a duplicate.

### Are Slack, Jira, and Confluence already connected?

The presets and gateway are implemented, but this local workspace contains no live tenant credentials. An administrator must configure and validate each real connection.

### Does “approved” mean every later action is approved?

No. Approval binds one exact action or one defined stage. Changed actions require another decision.

### Does a valid result prove the business outcome?

No. It proves the data shape. Trusted evidence or a domain outcome validator is needed to establish business success.

### Can a newer agent version change a running case?

No. The run stays pinned to the version it started with.

### Is this production-ready?

No. It is a substantial local reference implementation with verified boundaries. Production identity, tenancy, secret management, distributed execution, monitoring, retention, live-provider testing, and other operating controls remain required.

### Is Axiom already proven better than n8n?

No objective superiority claim has been established. Axiom's intended distinction is governed adaptive Goal Agents, exact-action approval, evidence-linked execution, behavior rehearsal, explicit uncertainty, and version locking. A fair comparison still needs representative customer tasks, reliability measurements, integration breadth, operating cost, and usability studies.

---

## 26. Current safety protections

The implemented local gateway and runtime include protections such as:

- Strict request and result schemas.
- Capability allowlists.
- Selected-context boundaries.
- Server-side credential resolution.
- Native-provider destination and path pinning.
- DNS and private-address checks.
- Redirect refusal.
- Response time and size bounds.
- Connection version and generation checks.
- Stale-result rejection.
- Exact prepared-action approval.
- Source and authority rechecks before dispatch.
- Stable operation identities.
- Explicit unknown-outcome handling.
- Metadata-only integration audits.
- Secret and raw-content redaction in exported evidence.
- Durable local sessions and workflow state.

These controls reduce risk. They do not replace production security review, provider sandbox testing, threat modeling, monitoring, incident response, or compliance work.

---

## 27. What is implemented and what still needs work

### Implemented in the local reference

- Visual workflow creation and editing.
- Reusable registered steps.
- Adaptive Goal Agent specifications and sessions.
- Draft, review, activation, publication, and version pinning.
- Strict capabilities, context, inputs, results, limits, and policies.
- Clarification and resume.
- Exact-action preparation and approval.
- Local evidence, effects, receipts, and audit history.
- Controlled behavior previews and rehearsal cases.
- Five complex demonstration workflows.
- Slack, Jira Cloud, Confluence Cloud, and outbound-webhook presets.
- Safe external health/read execution when configured.
- OpenAPI 3.1 inspect-only interface.
- Night mode and accessible menu alternatives.
- Durable SQLite persistence.

### Integration or production work still required

- Live Slack, Jira, Confluence, and webhook tenant validation.
- Full OAuth consent, callback, refresh, rotation, and revocation lifecycle.
- Generic OpenAPI contract promotion and activation.
- A configured remote MCP client and reviewed tool import.
- Inbound provider webhooks.
- Automatic external retry scheduling.
- Provider-specific reconciliation for uncertain writes.
- Corporate sign-in and directory lifecycle.
- Tenant isolation.
- Managed production secrets.
- Distributed workers, queues, failover, and load testing.
- Production observability and alerting.
- Retention and deletion operations.
- Production artifact storage and malware scanning.
- Live-model quality and adversarial evaluations.
- Complete accessibility and cross-browser certification.

---

## 28. A practical daily operating pattern

### Administrator

1. Reviews capability and connection health.
2. Creates or edits workflow and agent drafts.
3. Runs controlled rehearsals.
4. Submits changes for review.
5. Investigates capability gaps without silently widening access.

### Reviewer

1. Inspects the exact proposed version or action.
2. Checks permissions, evidence, destination, payload, policy, and freshness.
3. Approves or rejects within the permitted role.
4. Records a useful decision reason.

### Operator

1. Starts a permitted run.
2. Watches waiting and failed states.
3. Supplies requested information when authorized.
4. Performs assigned manual work.
5. Confirms the final result and receipt.

### Developer or platform owner

1. Implements and tests capability adapters.
2. Defines strict schemas and effects.
3. Implements idempotency or reconciliation behavior for each provider.
4. Adds trusted outcome validators.
5. Operates identity, secrets, monitoring, retention, scaling, and recovery.

---

## 29. How to judge whether Axiom is helping

Do not judge success only by attractive explanations or the number of tool calls.

Measure:

- Verified completed cases.
- Cases correctly paused for missing information.
- Duplicate effects avoided.
- Forbidden actions rejected.
- Approval quality.
- Useful escalations and partial outcomes.
- Time per completed case.
- Model and provider cost per completed case.
- Unnecessary tool calls.
- Repeated-run reliability.
- Final business state.

Keep deterministic runtime testing separate from live-model quality evaluation.

---

## 30. Troubleshooting

### The application does not open

Confirm that the server terminal shows the local Axiom address and that the browser uses the same port.

```text
http://127.0.0.1:8765
```

### I cannot edit a workflow

Check the selected development role. Reviewer, operator, and contributor roles can be read-only for draft editing. Switch to the administrator only when that matches the intended task.

### I cannot place a Goal Agent

Confirm that:

1. The specification was saved successfully.
2. A separate reviewer activated that exact version.
3. The workflow is an editable draft.
4. The required capability contracts still exist.

### A connection will not activate

Check:

1. The exact base URL.
2. Required credential references.
3. Whether the referenced environment variables exist in the server process.
4. Selected operations and scopes.
5. The latest health result.
6. Whether the connection must return to draft after restoration.

### A write is waiting

Open Review Inbox or the run inspector. Review the exact action rather than approving from the summary alone.

### A run asks for information

Supply only the requested fact if you are authorized. The run should resume from the existing session rather than beginning an unrelated new case.

### A run shows an unknown external outcome

Do not immediately retry. Check the destination system using an approved reconciliation procedure or escalate to a person who can confirm whether the action exists.

### A configured model will not run

Check the model endpoint, model name, server-side key, endpoint transport rules, and provider response compatibility. Axiom will not silently substitute the scripted provider.

---

## 31. Suggested demonstration scripts

### Five-minute overview

1. Open Workflow Studio and show one complete demonstration graph.
2. Open Agent Factory and compare two paths from the same Service Investigator.
3. Point out that one path reuses an existing issue while another prepares a new action.
4. Open the prepared-action view and show the exact destination, payload, evidence, and approval boundary.
5. Finish in Connections and explain the difference between setup-capable, inspect-only, and integration-required providers.

Main lesson:

> Axiom combines a stable workflow with adaptable work while keeping consequential actions reviewable.

### Fifteen-minute beginner demonstration

1. Complete the five-minute overview.
2. Show the missing-information Service Investigator case and resume it with the requested value.
3. Open Behavior Preview and compare normal, missing, duplicate, denied, and unavailable-service cases.
4. Run one safe rehearsal and inspect its final state and evidence.
5. Switch to night mode and return to Studio.
6. Open a node action menu and show configure, rename, add-connected, duplicate, map, inspect, edit, and remove options without changing the saved workflow.

Main lesson:

> Good adaptation includes asking, pausing, reusing existing work, and returning a partial result—not only taking more actions.

### Thirty-minute technical demonstration

Choose the path before starting:

- **Offline path:** use a bundled fixture-backed Goal Agent and its controlled variations. No model is required.
- **Custom-agent path:** configure and validate a compatible model first. A newly created custom agent cannot execute through the scripted fixture provider.

1. Create a blank workflow draft.
2. Add, configure, connect, and map two or more steps.
3. For the offline path, inspect a bundled fixture-backed Goal Agent. For the custom path, create a specification with limited context, capabilities, result, evidence, stop rules, and budgets.
4. On the custom path, save the specification as a draft, switch to the reviewer, and activate that exact version.
5. Place the selected approved Goal Agent into the workflow.
6. Validate the workflow and compare at least two bundled fixture variations or two configured-model cases, according to the chosen path.
7. Inspect an exact prepared action and explain why its approval cannot authorize a changed payload.
8. Inspect a valid OpenAPI 3.1 document and show that the candidate remains unclassified and non-executable.
9. Review the audit trail, evidence, receipt, and version pins.
10. End with the production-work checklist so the demonstration is not mistaken for a live deployment.

Main lesson:

> The model may choose a method, but the application owns authority, persistence, validation, approval, and evidence.

---

## 32. Glossary

**Action:** A step with a known operation.

**Adapter:** Trusted code that translates a registered capability into a provider request and validates the response.

**Agent:** A goal-directed worker operating through the shared runtime.

**Approval:** A permitted person's decision about an exact stage or prepared action.

**Capability:** One registered operation an agent may be allowed to request.

**Connection:** A versioned, scoped boundary to an external or local service.

**Context:** Information selected for an agent to use.

**Contract:** The exact expected shape and meaning of input, output, or an operation.

**Draft:** An editable definition that is not yet published or activated.

**Effect:** A change attempted against a destination.

**Evidence:** A record supporting a fact, inference, decision, or result.

**Fixture:** Controlled local data or behavior used for repeatable demonstration and tests.

**Goal Agent:** An adaptive workflow step with a stable mission and bounded authority.

**Idempotency:** A provider-specific way to prevent the same logical operation from creating duplicates.

**Join:** A point that waits for required parallel paths before continuing.

**Observation:** The actual result of a capability, human answer, or system event.

**Outcome validator:** Trusted code that checks whether the final business condition was established.

**Prepared action:** An exact stored proposed write awaiting approval or dispatch.

**Receipt:** Evidence returned after an action is accepted or completed.

**Reconciliation:** Checking a destination to learn whether an uncertain operation actually committed.

**Release:** An immutable published workflow version.

**Result schema:** Rules describing the shape of an agent's final answer.

**Session:** Durable history for one agent working on one case.

**Simulation:** Execution designed not to produce real external effects.

**Tool:** A plain-language synonym for capability.

**Workflow:** The versioned map of stages, dependencies, decisions, and outcomes.

---

## 33. Beginner checklist

Before building:

- [ ] I can state the business outcome in one sentence.
- [ ] I know which steps are fixed and which genuinely require adaptation.
- [ ] I know what information the process may read.
- [ ] I know which external changes are consequential.
- [ ] I know who may approve those changes.

Before activating an agent:

- [ ] Its mission is specific.
- [ ] Its capabilities are minimal and relevant.
- [ ] Its starting context is limited.
- [ ] Its result contract is clear.
- [ ] Missing-information behavior is defined.
- [ ] Stop and escalation rules are defined.
- [ ] Time, tool, write, token, and cost limits are set.
- [ ] Controlled evaluation cases have been run.

Before publishing a workflow:

- [ ] Mappings are valid.
- [ ] Condition paths and joins are correct.
- [ ] Human responsibilities are explicit.
- [ ] Exact-action approvals are in the right place.
- [ ] Normal and failure rehearsals pass.
- [ ] The release diff was reviewed.

Before using a live connection:

- [ ] The destination is exact and approved.
- [ ] Credentials are server-side and least privilege.
- [ ] Required scopes match selected operations.
- [ ] Health/read checks pass against the intended tenant.
- [ ] Write idempotency and reconciliation behavior are understood.
- [ ] Outcome validation is meaningful.
- [ ] Monitoring, retention, and incident ownership are assigned.

---

## 34. Where to read next

- [Start and verification overview](START_HERE.md)
- [External integration guide](docs/EXTERNAL_INTEGRATIONS.md)
- [Application README](app/README.md)
- [Shared application contract](app/CONTRACT.md)
- [Agent Factory contract](app/FACTORY_CONTRACT.md)
- [Current feature matrix](app/feature_status.json)
- [Verification record](research/QA_NOTES.md)
- [Agent Factory verification](factory/Verification.md)

---

## Final summary

Axiom combines a visible business workflow with adaptive but constrained Goal Agents.

The workflow controls commitments, dependencies, roles, and required approvals. The agent chooses its next permitted action according to actual evidence. Capabilities define what can be done. Connections define where it may be done. Prepared actions make important writes reviewable. Versions keep old work stable. Evidence and receipts show what really happened. Rehearsals expose unsafe or unreliable behavior before publication.

That combination is the central idea:

> Flexible problem-solving inside explicit business boundaries.
