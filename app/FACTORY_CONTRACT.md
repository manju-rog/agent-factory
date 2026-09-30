# Agent Factory implementation contract

`agent_factory.py` is the domain-independent execution kernel. A configured model chooses one action per turn using the agent's mission, permitted inputs, trusted tool contracts, and observations from completed calls. The module performs no business-tool effects and stores no sessions. The host owns persistence, authentication, authorization, adapter execution, and idempotency. Demonstration tools and their explicitly scripted provider live separately in `factory_fixtures.py`.

## Definition and tool contracts

The canonical `AgentSpec` fields are:

| Field | Meaning |
|---|---|
| `id`, `version`, `name` | Stable identifier, positive integer version, display name. Version defaults to 1. |
| `mission`, `instructions` | Business goal and bounded instructions; instructions default to empty text. |
| `inputSchema`, `outputSchema` | Contracts for initial input and final output. Input must be an object. |
| `contextFields` | Exact permitted paths such as `input.requestId`; no overlapping parent/child selections. |
| `allowedTools` | Explicit registered tool IDs. Dotted namespaces are supported. |
| `requiredEvidenceTools` | Optional tool IDs whose successful observations must be cited before completion. |
| `stopRules` | Reviewed boundary choices for missing/denied capabilities, unavailable services, conflicting evidence, exhausted budgets, and changed business state. Supported outcomes are `stop`, `request_information`, `return_partial`, and `escalate`. |
| `policyRefs` | Stable identifiers for applicable reviewed policies. Policy content and enforcement remain host responsibilities. |
| `evaluationCases` | Bounded controlled cases used for preview/evaluation; they do not modify a published agent automatically. |
| `limits` | Resource limits; omitted values use defaults below. |

Unknown spec fields are rejected. Agent IDs and schema property names use letters, digits, underscores, and hyphens. Tool IDs may additionally contain separating dots.

Each trusted tool registry entry contains `id`, `version`, business `description`, `effect` (`read` or `write`), `inputSchema`, and `outputSchema`. Production registries also describe semantic fields, authorization scope, adapter/version binding, examples, verification status, and retry/idempotency/reconciliation behavior. The bundled catalog fills these fields but labels every adapter `local-only` and `fixture-verified`; that is not external integration verification. Optional `boundArguments` fixes argument sources, for example:

```json
{"requestId":"input.requestId"}
```

The model omits that argument or supplies exactly `{"$ref":"input.requestId"}`. The kernel inserts its resolved value and checks the binding again immediately before execution. The host must ensure that the underlying input resource is authorized; a binding alone does not authorize access.

Schemas support explicit single `type` values: object, array, string, integer, number, boolean, or null. Supported constraints are `properties`, `required`, `additionalProperties:false`, `items`, `enum`, length/item/numeric bounds, and string `format:"email"`. `title` and `description` are allowed. Objects are closed even when `additionalProperties` is omitted. Unknown schema keywords, unions, schema references, regular-expression constraints, and schemas deeper than ten levels are rejected rather than silently ignored. Values must be finite UTF-8 JSON.

## Public API

All functions below except the provider's network request operate on in-memory JSON-compatible values. Mutation operations return copied state.

| Function | Behavior |
|---|---|
| `compile_agent(spec, tools, policy=None)` | Validate and freeze the spec plus selected tool contracts; return `{kernelVersion,spec,tools,agentHash}`. Host policy may lower budget ceilings. |
| `propose_agent(brief, tools, provider, policy=None)` | Ask an actual provider to generate a spec, compile it, and return an unsaved proposal marked `requiresReview:true`. |
| `create_state(compiled, task_input)` | Validate initial input, retain only selected context, and create a serializable ready session. |
| `model_messages(compiled, state)` | Build the next bounded model request without contacting a provider. |
| `apply_decision(compiled, state, decision, provider_label=..., provider_metadata=None)` | Validate one JSON decision and bounded provider usage metadata, then return the next state; execute no tool. |
| `advance(compiled, state, provider)` | Make one `provider.complete(messages,response_schema)` call and apply its decision; convert `AgentError` into a visible failed/stopped state. |
| `approve_action(compiled,state,approved,actor_id,expected_action_hash)` | Record an explicit decision for the exact pending write. Host authorizes the actor. |
| `executable_action(compiled,state)` | Recheck authority, deadline, payload, and approval **before** host adapter execution. |
| `record_tool_result(compiled,state,result)` | Validate a real adapter result, store its observation, and return to ready. |
| `record_tool_error(compiled,state,code,message,retryable=False)` | Record a sanitized read failure for adaptation; stop uncertain writes for reconciliation. |
| `supply_input(compiled,state,answers)` | Accept answers keyed by requested exact input paths. |

Other direct calls raise `AgentError(code,message,details=None)`. The host can call `model_messages`, perform provider I/O outside its transaction, then apply the response after checking the session revision. The compiled snapshot and complete session must be persisted together.

## Decisions, references, and observations

An example call:

```json
{"kind":"call","toolId":"service.lookup","arguments":{"requestId":{"$ref":"input.requestId"}},"reason":"Check whether this request already has a linked issue."}
```

A clarification request:

```json
{"kind":"ask","question":"Which application is affected?","fields":["input.application"]}
```

`input.application` must already be a permitted context field. Supply it with `{"input.application":"Customer portal"}`; partial answers leave the session waiting for remaining fields.

A finish decision, assuming the declared output schema requires `issueId`:

```json
{"kind":"finish","output":{"issueId":{"$ref":"facts.call_0001.existingTicket"}},"evidence":["facts.call_0001.existingTicket"]}
```

References address projected input or actual observations under `facts.call_0001.field`. There is no `.result` wrapper, wildcard, expression evaluation, array-index syntax, or access to arbitrary workflow history. Argument and output values may contain nested exact `$ref` objects or literal JSON. Evidence references must exist and be unique. Optional `reason` is a short operational justification, not a request for hidden reasoning.

The state contains `input`, `facts`, separate `factSources` metadata, ordered `events`, `counters`, `pendingAction`, `approval`, `output`, and clarification fields. Statuses are `ready`, `awaiting_tool`, `awaiting_approval`, `awaiting_input`, `completed`, `stopped`, and `failed`.

Model requests include `observationSources`, keyed by call ID, with each observed call's tool ID, success/failure status, and exact resolved arguments from the matching frozen action. Results remain in `observations`; full event history and unselected private inputs are excluded. This distinguishes identical-looking outputs from different tools or resource queries. Provenance metadata counts toward the complete request byte limit.

## Effects and limits

Every write pauses at `awaiting_approval`. Its action hash binds session, compiled definition, call ID, tool, effect, and resolved arguments. Approval is checked against that hash. Hashes provide consistency checks within the trusted host; they are not signatures. The host must call `executable_action` before the effect and use durable operation records to prevent duplicate effects.

Failed reads become observed `{error:{code,message,retryable}}` values so the next model turn can adapt. An uncertain write returns `WRITE_NEEDS_RECONCILIATION`; it is never blindly retried by the kernel. Invalid model decisions fail visibly instead of executing partially.

| Budget | Default | Hard ceiling |
|---|---:|---:|
| `maxTurns` | 12 | 32 |
| `maxToolCalls` | 8 | 24 |
| `maxWriteCalls` | 2 | 8 |
| `maxContextBytes` | 32,000 | 128,000 |
| `maxOutputBytes` | 16,000 | 64,000 |
| `maxModelTokens` | 64,000 | 1,000,000 |
| `maxEstimatedCostMicros` | 5,000,000 | 100,000,000 |
| `timeoutSeconds` | 900 | 3,600 |

The context check includes the complete model request and tool contracts. The deadline covers human waiting time and is rechecked before approval and execution. Token and estimated-cost limits are enforced only from trusted provider usage metadata. If provider pricing is not configured, the session marks cost as unknown instead of fabricating a monetary value.

## Provider and completion meaning

`ChatCompletionProvider.from_environment()` reads `AXIOM_MODEL_ENDPOINT`, `AXIOM_MODEL_NAME`, and optional `AXIOM_MODEL_API_KEY`. Optional server-side `AXIOM_MODEL_INPUT_COST_MICROS_PER_MILLION` and `AXIOM_MODEL_OUTPUT_COST_MICROS_PER_MILLION` rates enable cost estimates. The endpoint must be HTTPS or loopback HTTP; redirects are disabled. It uses a chat-completions-compatible JSON response request, captures bounded provider/model/response/token metadata, then applies local decision validation. No model is silently substituted when configuration is missing. `response_schema` is a provider-interface hint; this adapter requests JSON-object output rather than claiming provider-enforced schema compliance.

Kernel completion validates output shape, existing evidence references, and any required evidence-tool observations. `completionCheck.businessOutcomeVerified` initially remains `false`: these checks do not establish factual entailment or prove the business goal was met. The bundled service, invoice, and access demonstrations separately run `factory_fixtures.validate_outcome`, which compares the final result with trusted fixture observations and receipts. Custom domains remain visibly `unknown` until a developer registers an authoritative validator.
