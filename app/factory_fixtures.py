"""Local demonstration capabilities for the adaptive agent factory.

Nothing in this module connects to an enterprise service. The fixture provider
is a deliberately scripted test double, not an AI model. Its domain branches
live here so that the factory runtime and its configured-model provider remain
independent of these demonstrations. The server owns authorization, approvals,
idempotency and persistence; write-result helpers only construct local records.
"""
from __future__ import annotations

import copy
import hashlib
import json


class FixtureToolError(ValueError):
    """Bounded adapter failure used only by the controlled demonstration."""

    def __init__(self, code, message, *, condition=None, retryable=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.condition = condition
        self.retryable = retryable


def _argument(args, name):
    if not isinstance(args, dict) or name not in args:
        raise FixtureToolError(
            "FIXTURE_ARGUMENT_INVALID",
            "The local fixture call is missing its declared " + name + " argument.",
        )
    return args[name]


def _object(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def _text(description=""):
    result = {"type": "string"}
    if description:
        result["description"] = description
    return result


_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_NUM = {"type": "number"}
_CAPTURE = {"recordId": _STR, "status": _STR, "capturedLocally": _BOOL,
            "externalWrite": _BOOL, "fixture": _BOOL}


def _tool(identifier, description, effect, inputs, outputs):
    domain = identifier.split(".", 1)[0]

    def example_value(schema):
        if "enum" in schema:
            return copy.deepcopy(schema["enum"][0])
        return {"string": "example", "number": 1.0, "integer": 1,
                "boolean": True, "array": [], "object": {}}.get(schema.get("type"))

    example_input = {name: example_value(schema) for name, schema in inputs.items()}
    retry_contract = (
        {"classification": "safe-read", "retry": "bounded-by-session-policy",
         "reconciliation": "not-required"}
        if effect == "read" else
        {"classification": "idempotent-local-capture", "operationKey": "required",
         "retry": "only-after-ledger-check", "reconciliation": "read-local-effect-receipt"}
    )
    return {
        "id": identifier,
        "version": "1.0.0",
        "description": description,
        "effect": effect,
        "inputSchema": _object(inputs),
        "outputSchema": _object(outputs),
        "semanticFields": {
            name: schema.get("description", "Declared " + name + " value.")
            for name, schema in inputs.items()
        },
        "authorization": {
            "scope": "fixture:" + domain,
            "principal": "bounded-agent-session",
            "credentials": "none",
        },
        "adapterBinding": {
            "adapterId": "local-fixture." + domain,
            "adapterVersion": "1.0.0",
            "operation": identifier,
            "transport": "in-process",
        },
        "idempotency": retry_contract,
        "examples": [{"label": "Contract-shape example", "input": example_input}],
        "verification": {
            "status": "fixture-verified",
            "environment": "local-only",
            "externalIntegration": False,
        },
    }


_TOOLS = [
    _tool("service.lookup", "Read a local service request fixture and any existing linked ticket.", "read",
          {"requestId": _text("The service request identifier from the agent input.")},
          {"requestId": _STR, "service": _STR, "summary": _STR,
           "existingTicket": _text("Empty string means no existing ticket was found."),
           "severity": _STR, "fixture": _BOOL}),
    _tool("service.search_runbook", "Search the local fixture runbook for the observed service and symptom.", "read",
          {"service": _STR, "symptom": _STR},
          {"matched": _BOOL, "articleId": _STR, "recommendedAction": _STR, "fixture": _BOOL}),
    _tool("service.create_ticket", "Prepare a local work-item capture; this does not create a real Jira ticket.", "write",
          {"requestId": _STR, "service": _STR, "summary": _STR,
           "priority": _STR, "runbookReference": _STR}, _CAPTURE),
    _tool("finance.inspect_invoice", "Read a local invoice fixture, including the observed purchase-order variance.", "read",
          {"invoiceId": _STR},
          {"invoiceId": _STR, "supplier": _STR, "amount": _NUM, "currency": _STR,
           "purchaseOrder": _STR, "variancePercent": _NUM,
           "supplierApproved": _BOOL, "fixture": _BOOL}),
    _tool("finance.lookup_policy", "Read the fixture invoice policy for a currency. This is demonstration policy only.", "read",
          {"currency": _STR},
          {"policyId": _STR, "currency": _STR, "maxVariancePercent": _NUM,
           "maxAmountWithoutException": _NUM, "fixture": _BOOL}),
    _tool("finance.record_decision", "Capture a local invoice recommendation. No payment or financial-system update occurs.", "write",
          {"invoiceId": _STR, "decision": {"type": "string", "enum": ["ready_for_review", "hold"]},
           "reason": _STR, "policyId": _STR}, _CAPTURE),
    _tool("finance.request_review", "Capture a local exception-review request. This does not contact a reviewer or financial service.", "write",
          {"invoiceId": _STR, "reason": _STR, "policyId": _STR}, _CAPTURE),
    _tool("access.inspect_request", "Read a local access request fixture; this tool cannot change entitlements.", "read",
          {"requestId": _STR},
          {"requestId": _STR, "userId": _STR, "resource": _STR,
           "requestedRole": _STR, "fixture": _BOOL}),
    _tool("access.lookup_entitlements", "Read local fixture facts about a requested entitlement and its risk.", "read",
          {"userId": _STR, "resource": _STR, "requestedRole": _STR},
          {"currentRole": _STR, "risk": _STR, "managerApprovalOnFile": _BOOL,
           "roleAvailable": _BOOL, "fixture": _BOOL}),
    _tool("access.record_grant", "Capture a proposed entitlement grant locally. This never grants real access.", "write",
          {"requestId": _STR, "userId": _STR, "resource": _STR,
           "role": _STR, "reason": _STR}, _CAPTURE),
    _tool("access.request_review", "Capture a local privileged-access review request. No access is granted and no reviewer is contacted.", "write",
          {"requestId": _STR, "userId": _STR, "resource": _STR,
           "role": _STR, "reason": _STR}, _CAPTURE),
    _tool("artifact.write_report", "Capture a general report locally from explicit source references; it performs no external delivery.", "write",
          {"title": _STR, "body": _STR,
           "sourceReferences": {"type": "array", "items": _STR}}, _CAPTURE),
]

# A model may choose which permitted operation to perform, but may not silently
# change the primary request/invoice scope supplied by the workflow placement.
for _registered_tool in _TOOLS:
    if _registered_tool["id"].startswith(("service.", "access.")) and "requestId" in _registered_tool["inputSchema"]["properties"]:
        _registered_tool["boundArguments"] = {"requestId": "input.requestId"}
    elif _registered_tool["id"].startswith("finance.") and "invoiceId" in _registered_tool["inputSchema"]["properties"]:
        _registered_tool["boundArguments"] = {"invoiceId": "input.invoiceId"}


_SERVICE = {
    "SR-EXISTING": {"requestId": "SR-EXISTING", "service": "Customer portal",
                    "summary": "Customers encounter intermittent login timeouts.",
                    "existingTicket": "LOCAL-INC-208", "severity": "high", "fixture": True},
    "SR-NEW": {"requestId": "SR-NEW", "service": "Customer portal",
               "summary": "Customers encounter intermittent login timeouts.",
               "existingTicket": "", "severity": "high", "fixture": True},
    "SR-SERVICE-UNAVAILABLE": {"requestId": "SR-SERVICE-UNAVAILABLE", "service": "Customer portal",
                               "summary": "Controlled unavailable dependency during timeout diagnosis.",
                               "existingTicket": "", "severity": "high", "fixture": True},
}
_INVOICES = {
    "INV-MATCHED": {"invoiceId": "INV-MATCHED", "supplier": "Example Office Supply",
                    "amount": 820.0, "currency": "USD", "purchaseOrder": "PO-410",
                    "variancePercent": 0.0, "supplierApproved": True, "fixture": True},
    "INV-EXCEPTION": {"invoiceId": "INV-EXCEPTION", "supplier": "Example Office Supply",
                      "amount": 1040.0, "currency": "USD", "purchaseOrder": "PO-410",
                      "variancePercent": 26.83, "supplierApproved": True, "fixture": True},
    "INV-CONFLICTING": {"invoiceId": "INV-CONFLICTING", "supplier": "Example Office Supply",
                        "amount": 820.0, "currency": "USD-CONFLICTING", "purchaseOrder": "PO-410",
                        "variancePercent": 0.0, "supplierApproved": True, "fixture": True},
    "INV-CHANGED": {"invoiceId": "INV-CHANGED", "supplier": "Example Office Supply",
                    "amount": 820.0, "currency": "USD-CHANGED", "purchaseOrder": "PO-410",
                    "variancePercent": 0.0, "supplierApproved": True, "fixture": True},
}
_ACCESS = {
    "AR-STANDARD": {"requestId": "AR-STANDARD", "userId": "fixture-user-14",
                    "resource": "Analytics workspace", "requestedRole": "viewer", "fixture": True},
    "AR-PRIVILEGED": {"requestId": "AR-PRIVILEGED", "userId": "fixture-user-14",
                      "resource": "Analytics workspace", "requestedRole": "administrator", "fixture": True},
    "AR-DENIED": {"requestId": "AR-DENIED", "userId": "fixture-user-14",
                  "resource": "Restricted workspace", "requestedRole": "viewer", "fixture": True},
    "AR-UNAVAILABLE": {"requestId": "AR-UNAVAILABLE", "userId": "fixture-user-14",
                       "resource": "Analytics workspace", "requestedRole": "auditor", "fixture": True},
}


def tool_catalog():
    """Return independent tool-contract copies for runtime registration."""
    return copy.deepcopy(_TOOLS)


def execute_read(tool_id, args):
    """Execute a pure fixture read; missing records fail instead of inventing facts."""
    if tool_id == "service.lookup":
        result = _SERVICE.get(_argument(args, "requestId"))
    elif tool_id == "service.search_runbook":
        service = _argument(args, "service")
        symptom = _argument(args, "symptom")
        if not isinstance(service, str) or not isinstance(symptom, str):
            raise FixtureToolError("FIXTURE_ARGUMENT_INVALID", "Runbook fixture arguments must be text.")
        if "controlled unavailable" in symptom.lower():
            raise FixtureToolError(
                "SERVICE_UNAVAILABLE", "The controlled runbook service is unavailable for this demonstration.",
                condition="unavailableService", retryable=True,
            )
        matched = service == "Customer portal" and "timeout" in symptom.lower()
        result = {"matched": matched, "articleId": "KB-LOGIN-07" if matched else "",
                  "recommendedAction": "Investigate the identity-provider connection pool." if matched else "No matching local runbook.",
                  "fixture": True}
    elif tool_id == "finance.inspect_invoice":
        result = _INVOICES.get(_argument(args, "invoiceId"))
    elif tool_id == "finance.lookup_policy":
        currency = _argument(args, "currency")
        if currency == "USD-CONFLICTING":
            raise FixtureToolError(
                "CONFLICTING_RECORDS", "Two controlled policy records disagree for this invoice currency.",
                condition="conflictingEvidence",
            )
        if currency == "USD-CHANGED":
            raise FixtureToolError(
                "BUSINESS_STATE_CHANGED", "The controlled policy version changed during the review.",
                condition="changedBusinessState",
            )
        result = ({"policyId": "FIXTURE-INVOICE-1", "currency": "USD",
                   "maxVariancePercent": 2.0, "maxAmountWithoutException": 5000.0,
                   "fixture": True} if currency == "USD" else None)
    elif tool_id == "access.inspect_request":
        result = _ACCESS.get(_argument(args, "requestId"))
    elif tool_id == "access.lookup_entitlements":
        user_id = _argument(args, "userId")
        resource = _argument(args, "resource")
        requested_role = _argument(args, "requestedRole")
        if resource == "Restricted workspace":
            raise FixtureToolError(
                "CAPABILITY_DENIED", "The controlled fixture principal cannot inspect this restricted entitlement.",
                condition="deniedCapability",
            )
        if user_id != "fixture-user-14" or resource != "Analytics workspace":
            result = None
        else:
            known = requested_role in {"viewer", "administrator"}
            result = {"currentRole": "none", "risk": "privileged" if requested_role == "administrator" else "standard",
                      "managerApprovalOnFile": requested_role == "viewer",
                      "roleAvailable": known, "fixture": True}
    else:
        raise ValueError("This is not a registered fixture read tool: " + str(tool_id))
    if result is None:
        raise ValueError("No local fixture record matches the supplied identifier.")
    return copy.deepcopy(result)


def prepare_write_result(tool_id, args, operation_key):
    """Construct an output after server authorization; never persist or send it.

    Stable identity allows the owning server's idempotency ledger to demonstrate
    replay without extra records. This function itself makes no exactly-once
    claim: transaction and duplicate protection are the server's responsibility.
    """
    allowed = {item["id"] for item in _TOOLS if item["effect"] == "write"}
    if tool_id not in allowed:
        raise ValueError("This is not a registered fixture write tool: " + str(tool_id))
    material = json.dumps([tool_id, operation_key], separators=(",", ":"), ensure_ascii=False)
    suffix = hashlib.sha256(material.encode()).hexdigest()[:10].upper()
    status = {"service.create_ticket": "work_item_captured",
              "finance.record_decision": "recommendation_captured",
              "finance.request_review": "exception_review_captured",
              "access.record_grant": "grant_proposal_captured",
              "access.request_review": "privileged_review_captured",
              "artifact.write_report": "report_captured"}[tool_id]
    return {"recordId": "LOCAL-" + suffix, "status": status,
            "capturedLocally": True, "externalWrite": False, "fixture": True}


_RESULT_SCHEMA = _object({"outcome": _STR, "summary": _STR, "recordId": _STR})


def _spec(identifier, name, mission, instructions, input_name, tool_ids):
    return {"id": identifier, "version": 1, "name": name, "mission": mission,
            "instructions": instructions, "inputSchema": _object({input_name: _STR}),
            "outputSchema": copy.deepcopy(_RESULT_SCHEMA),
            "contextFields": ["input." + input_name], "allowedTools": tool_ids,
            "requiredEvidenceTools": [tool_ids[0]],
            "stopRules": {
                "missingCapability": "return_partial",
                "deniedCapability": "escalate",
                "unavailableService": "return_partial",
                "conflictingEvidence": "escalate",
                "budgetExhausted": "stop",
                "changedBusinessState": "escalate",
            },
            "policyRefs": ["fixture-policy:" + identifier],
            "evaluationCases": [],
            "limits": {"maxTurns": 12, "maxToolCalls": 8, "maxWriteCalls": 2,
                       "maxContextBytes": 32000, "maxOutputBytes": 16000, "timeoutSeconds": 900}}


_SPECS = [
    _spec("service-investigator", "Service Investigator",
          "Investigate a service request and establish the appropriate work-item outcome without creating duplicates.",
          "Use observed request and runbook facts. Reuse an existing linked ticket when present. "
          "When a new work item is warranted, prepare its precise request and cite the relevant runbook. "
          "Every adapter here is a local fixture. A captured work item is not a real Jira ticket.",
          "requestId", ["service.lookup", "service.search_runbook", "service.create_ticket", "artifact.write_report"]),
    _spec("invoice-reviewer", "Invoice Reviewer",
          "Compare an invoice to the available invoice policy and prepare an appropriate recommendation or exception review.",
          "Obtain both invoice and applicable policy facts. Identify exceptions from variance, amount, supplier approval or missing purchase order. "
          "Make an ordinary recommendation only when the observed policy permits it; otherwise prepare an exception review. "
          "The tools capture local records only. Never claim an invoice has been paid or financially approved.",
          "invoiceId", ["finance.inspect_invoice", "finance.lookup_policy", "finance.record_decision", "finance.request_review", "artifact.write_report"]),
    _spec("access-coordinator", "Access Coordinator",
          "Assess a requested entitlement and prepare a justified access proposal or specialist review without granting real access.",
          "Read the request and entitlement facts. Avoid a duplicate proposal when access already exists. "
          "A standard available role with manager approval can receive a grant proposal. Privileged access or missing approval requires review. "
          "If the role is unavailable, report that capability gap. The tools never modify actual entitlements.",
          "requestId", ["access.inspect_request", "access.lookup_entitlements", "access.record_grant", "access.request_review", "artifact.write_report"]),
]


def agent_specs():
    """Reusable configurations; no runtime implementation is generated per agent."""
    specs = copy.deepcopy(_SPECS)
    scenarios_by_spec = {}
    for scenario in demo_scenarios():
        scenarios_by_spec.setdefault(scenario["specId"], []).append({
            "id": scenario["id"],
            "description": scenario["description"],
            "input": copy.deepcopy(scenario["input"]),
            "expectedState": {
                "inspectableAdaptivePath": True,
                "variationKind": scenario.get("variationKind", "observation-dependent-path"),
                **copy.deepcopy(scenario.get("expectedState", {})),
            },
        })
    for spec in specs:
        spec["evaluationCases"] = scenarios_by_spec.get(spec["id"], [])
    return specs


_SCENARIOS = [
    {"id": "service-existing", "name": "Service · linked issue exists", "specId": "service-investigator",
     "input": {"requestId": "SR-EXISTING"},
     "variationKind": "observation-dependent-path", "expectedState": {"status": "completed"},
     "description": "The observed linked issue allows completion without creating another work item."},
    {"id": "service-new", "name": "Service · new investigation", "specId": "service-investigator",
     "input": {"requestId": "SR-NEW"},
     "variationKind": "observation-dependent-path", "expectedState": {"status": "completed"},
     "description": "No linked issue is observed, so the agent retrieves a runbook and prepares a local work item."},
    {"id": "invoice-matched", "name": "Invoice · within policy", "specId": "invoice-reviewer",
     "input": {"invoiceId": "INV-MATCHED"},
     "variationKind": "observation-dependent-path", "expectedState": {"status": "completed"},
     "description": "Invoice and policy observations support an ordinary recommendation; no payment occurs."},
    {"id": "invoice-exception", "name": "Invoice · variance exception", "specId": "invoice-reviewer",
     "input": {"invoiceId": "INV-EXCEPTION"},
     "variationKind": "observation-dependent-path", "expectedState": {"status": "completed"},
     "description": "The observed variance exceeds policy, changing the selected tool to exception review."},
    {"id": "access-standard", "name": "Access · standard role", "specId": "access-coordinator",
     "input": {"requestId": "AR-STANDARD"},
     "variationKind": "observation-dependent-path", "expectedState": {"status": "completed"},
     "description": "Observed standard risk and manager approval support a local grant proposal; no real access is granted."},
    {"id": "access-privileged", "name": "Access · privileged role", "specId": "access-coordinator",
     "input": {"requestId": "AR-PRIVILEGED"},
     "variationKind": "observation-dependent-path", "expectedState": {"status": "completed"},
     "description": "Observed privileged risk changes the selected tool to a review request."},
]

_VARIATIONS = [
    {"id": "service-missing-evidence", "name": "Controlled · missing evidence and clarification",
     "specId": "service-investigator", "input": {"requestId": ""},
     "resumeAnswers": {"input.requestId": "SR-EXISTING"},
     "variationKind": "missing-evidence", "expectedState": {"status": "completed", "clarificationCount": 1},
     "description": "The required request identity is absent, so the agent asks one scoped question and resumes from the supplied answer."},
    {"id": "invoice-conflicting-records", "name": "Controlled · conflicting policy records",
     "specId": "invoice-reviewer", "input": {"invoiceId": "INV-CONFLICTING"},
     "variationKind": "conflicting-records",
     "expectedState": {"status": "stopped", "boundaryCondition": "conflictingEvidence"},
     "description": "The policy adapter reports contradictory controlled records, so the configured boundary escalates instead of inventing a disposition."},
    {"id": "access-denied-capability", "name": "Controlled · denied entitlement capability",
     "specId": "access-coordinator", "input": {"requestId": "AR-DENIED"},
     "variationKind": "denied-capability",
     "expectedState": {"status": "stopped", "boundaryCondition": "deniedCapability"},
     "description": "The fixture principal is denied the restricted entitlement read, producing an explicit escalation with no write."},
    {"id": "service-unavailable", "name": "Controlled · runbook service unavailable",
     "specId": "service-investigator", "input": {"requestId": "SR-SERVICE-UNAVAILABLE"},
     "variationKind": "unavailable-service",
     "expectedState": {"status": "completed", "outcome": "service_unavailable"},
     "description": "The request lookup succeeds, the runbook adapter returns a controlled unavailable-service observation, and the agent returns a cited partial result."},
    {"id": "access-unavailable-capability", "name": "Controlled · requested role unavailable",
     "specId": "access-coordinator", "input": {"requestId": "AR-UNAVAILABLE"},
     "variationKind": "unavailable-capability", "expectedState": {"status": "completed", "outcome": "capability_gap"},
     "description": "The entitlement lookup succeeds but reports that the requested role is unavailable, yielding a useful capability-gap result."},
    {"id": "service-duplicate-operation", "name": "Controlled · duplicate operation replay",
     "specId": "service-investigator", "input": {"requestId": "SR-NEW"},
     "duplicateWriteReplay": True,
     "variationKind": "duplicate-operation",
     "expectedState": {"status": "completed", "uniqueLocalEffects": 1, "writeAttempts": 2},
     "description": "The harness repeats the same stable local operation identity and verifies that both attempts resolve to one deterministic receipt."},
    {"id": "invoice-changed-business-condition", "name": "Controlled · policy changed during review",
     "specId": "invoice-reviewer", "input": {"invoiceId": "INV-CHANGED"},
     "variationKind": "changed-business-condition",
     "expectedState": {"status": "stopped", "boundaryCondition": "changedBusinessState"},
     "description": "The policy adapter reports a changed controlled business version, so the configured boundary escalates before any recommendation write."},
]


def scenarios():
    """Return the original six paired paths used by the stable recorded preview."""
    return copy.deepcopy(_SCENARIOS)


def behavior_variations():
    """Return controlled adverse cases for the scripted Behaviour Preview."""
    return copy.deepcopy(_VARIATIONS)


def demo_scenarios():
    """Return paired normal paths plus every labeled controlled variation."""
    return copy.deepcopy(_SCENARIOS + _VARIATIONS)


def _observed(state, tool_id):
    for event in reversed(state.get("events", [])):
        if event.get("type") == "tool.observed" and event.get("toolId") == tool_id:
            call_id = event.get("callId")
            if call_id in state.get("facts", {}):
                return call_id, state["facts"][call_id]
    return None, None


def _failed(state, tool_id):
    for event in reversed(state.get("events", [])):
        if event.get("type") != "tool.failed" or event.get("toolId") != tool_id:
            continue
        call_id = event.get("callId")
        fact = state.get("facts", {}).get(call_id, {})
        error = fact.get("error") if isinstance(fact, dict) else None
        if isinstance(call_id, str) and isinstance(error, dict):
            return call_id, error
    return None, None


def _ref(call_id, field):
    return {"$ref": "facts." + call_id + "." + field}


def _call(tool_id, arguments, reason):
    return {"kind": "call", "toolId": tool_id, "arguments": arguments, "reason": reason}


def _finish(outcome, summary, record_id, evidence):
    return {"kind": "finish", "output": {"outcome": outcome, "summary": summary, "recordId": record_id},
            "evidence": evidence, "reason": "Conclude using the recorded observations; local captures do not establish external effects."}


def fixture_decision(compiled, state, scenario=None):
    """Scripted demonstration decisions driven by observed outputs.

    The optional scenario identifier is deliberately ignored. It must not choose
    the path. This test double supports only the three bundled spec IDs; custom
    agents require the configured-model path or a separately supplied test
    provider. Never use its success rate as a claim about model intelligence.
    """
    spec_id = compiled["spec"]["id"]
    if spec_id == "service-investigator":
        return _service_decision(state)
    if spec_id == "invoice-reviewer":
        return _invoice_decision(state)
    if spec_id == "access-coordinator":
        return _access_decision(state)
    raise ValueError("The scripted fixture provider supports only the bundled demonstration agents. Configure a model for custom agents.")


def _service_decision(state):
    if not state.get("input", {}).get("requestId"):
        return {"kind": "ask", "question": "Which service request should I investigate?", "fields": ["input.requestId"],
                "reason": "A request identifier is needed before retrieving scoped service facts."}
    request_call, request = _observed(state, "service.lookup")
    if request is None:
        return _call("service.lookup", {"requestId": {"$ref": "input.requestId"}}, "Inspect the request before selecting the next action.")
    if request.get("existingTicket"):
        return _finish("existing_work_item", "The local request fixture already links a work item; no duplicate capture is needed.",
                       _ref(request_call, "existingTicket"), ["facts." + request_call + ".existingTicket", "facts." + request_call + ".summary"])
    runbook_call, runbook = _observed(state, "service.search_runbook")
    failed_runbook_call, failed_runbook = _failed(state, "service.search_runbook")
    if failed_runbook is not None:
        return _finish(
            "service_unavailable",
            "The request was observed, but the controlled runbook service is unavailable. No work item was prepared.",
            "",
            ["facts." + request_call + ".requestId", "facts." + failed_runbook_call + ".error.code"],
        )
    if runbook is None:
        return _call("service.search_runbook", {"service": _ref(request_call, "service"), "symptom": _ref(request_call, "summary")},
                     "The observed request has no linked work item; retrieve relevant diagnostics before preparing one.")
    write_call, write = _observed(state, "service.create_ticket")
    if write is None:
        return _call("service.create_ticket", {"requestId": {"$ref": "input.requestId"}, "service": _ref(request_call, "service"),
                     "summary": _ref(request_call, "summary"), "priority": _ref(request_call, "severity"),
                     "runbookReference": _ref(runbook_call, "articleId")},
                     "Prepare a new local work item from the observed request and runbook. Review the exact payload before capture.")
    captured = bool(write.get("capturedLocally"))
    return _finish("work_item_captured" if captured else "work_item_simulated",
                   "A work item was captured locally with its runbook reference. No external Jira ticket was created." if captured else
                   "A work-item action was simulated with its runbook reference. No local record was captured and no external Jira ticket was created.",
                   _ref(write_call, "recordId"), ["facts." + request_call + ".requestId", "facts." + runbook_call + ".articleId", "facts." + write_call + ".recordId"])


def _invoice_decision(state):
    if not state.get("input", {}).get("invoiceId"):
        return {"kind": "ask", "question": "Which invoice should I review?", "fields": ["input.invoiceId"],
                "reason": "An invoice identifier is needed before retrieving invoice facts."}
    invoice_call, invoice = _observed(state, "finance.inspect_invoice")
    if invoice is None:
        return _call("finance.inspect_invoice", {"invoiceId": {"$ref": "input.invoiceId"}}, "Inspect invoice facts before selecting its disposition.")
    policy_call, policy = _observed(state, "finance.lookup_policy")
    if policy is None:
        return _call("finance.lookup_policy", {"currency": _ref(invoice_call, "currency")}, "Retrieve the policy applicable to the observed invoice currency.")
    exceptions = []
    variance = invoice.get("variancePercent", 0)
    variance_limit = policy.get("maxVariancePercent", 0)
    if variance > variance_limit:
        exceptions.append("Observed variance of " + str(variance) + "% exceeds " + str(variance_limit) + "% policy limit.")
    if invoice.get("amount", 0) > policy.get("maxAmountWithoutException", 0):
        exceptions.append("Observed amount exceeds the policy ceiling.")
    if not invoice.get("supplierApproved"):
        exceptions.append("Supplier approval is absent.")
    if not invoice.get("purchaseOrder"):
        exceptions.append("Purchase-order evidence is missing.")
    tool_id = "finance.request_review" if exceptions else "finance.record_decision"
    write_call, write = _observed(state, tool_id)
    if write is None:
        args = {"invoiceId": {"$ref": "input.invoiceId"}, "policyId": _ref(policy_call, "policyId"),
                "reason": " ".join(exceptions) if exceptions else "The observed invoice matches the supplied fixture policy; recommend ordinary review."}
        if not exceptions:
            args["decision"] = "ready_for_review"
        return _call(tool_id, args, "Observed exceptions require specialist review." if exceptions else "Observed facts support an ordinary recommendation.")
    captured = bool(write.get("capturedLocally"))
    outcome = ("exception_review" if exceptions else "recommendation") + ("_captured" if captured else "_simulated")
    summary = ("An invoice exception review" if exceptions else "An ordinary invoice recommendation") + (
        " was captured locally; no payment occurred." if captured else
        " was simulated. No local record was captured and no payment occurred.")
    return _finish(outcome, summary,
                   _ref(write_call, "recordId"), ["facts." + invoice_call + ".variancePercent", "facts." + policy_call + ".maxVariancePercent", "facts." + write_call + ".recordId"])


def _access_decision(state):
    if not state.get("input", {}).get("requestId"):
        return {"kind": "ask", "question": "Which access request should I assess?", "fields": ["input.requestId"],
                "reason": "A request identifier is needed before retrieving entitlement facts."}
    request_call, request = _observed(state, "access.inspect_request")
    if request is None:
        return _call("access.inspect_request", {"requestId": {"$ref": "input.requestId"}}, "Inspect the requested entitlement first.")
    entitlement_call, entitlement = _observed(state, "access.lookup_entitlements")
    if entitlement is None:
        return _call("access.lookup_entitlements", {"userId": _ref(request_call, "userId"), "resource": _ref(request_call, "resource"),
                     "requestedRole": _ref(request_call, "requestedRole")}, "Check existing access, role availability and approval evidence.")
    if not entitlement.get("roleAvailable"):
        return _finish("capability_gap", "The observed role is unavailable. No grant can be prepared.", "",
                       ["facts." + entitlement_call + ".roleAvailable", "facts." + request_call + ".requestedRole"])
    if entitlement.get("currentRole") == request.get("requestedRole"):
        return _finish("already_present", "The observed entitlement already matches the request; no duplicate proposal is needed.", "",
                       ["facts." + entitlement_call + ".currentRole", "facts." + request_call + ".requestedRole"])
    review = entitlement.get("risk") == "privileged" or not entitlement.get("managerApprovalOnFile")
    tool_id = "access.request_review" if review else "access.record_grant"
    write_call, write = _observed(state, tool_id)
    if write is None:
        reason = "Privileged access or missing approval requires specialist review." if review else "The observed role is standard and manager approval is present."
        return _call(tool_id, {"requestId": {"$ref": "input.requestId"}, "userId": _ref(request_call, "userId"),
                     "resource": _ref(request_call, "resource"), "role": _ref(request_call, "requestedRole"), "reason": reason}, reason)
    captured = bool(write.get("capturedLocally"))
    outcome = ("review" if review else "grant_proposal") + ("_captured" if captured else "_simulated")
    summary = ("A privileged-access review request" if review else "A grant proposal") + (
        " was captured locally; no access was granted." if captured else
        " was simulated. No local record was captured and no access was granted.")
    return _finish(outcome, summary,
                   _ref(write_call, "recordId"), ["facts." + request_call + ".requestId", "facts." + entitlement_call + ".risk", "facts." + entitlement_call + ".managerApprovalOnFile", "facts." + write_call + ".recordId"])


def validate_outcome(spec_id, state):
    """Validate supported fixture outcomes from trusted observations.

    This deliberately lives beside the demonstration domain adapters rather
    than in the generic planning kernel. Unknown/custom domains remain visibly
    unverified until a developer registers an authoritative validator.
    """
    base = {"validatorId": "fixture-outcome-validator.v1", "agentId": spec_id,
            "businessOutcomeVerified": False, "status": "unknown", "checks": []}
    if not isinstance(state, dict) or state.get("status") != "completed" or not isinstance(state.get("output"), dict):
        return {**base, "reason": "A completed typed result is required before outcome validation."}

    output = state["output"]
    def observed(tool_id):
        call_id, value = _observed(state, tool_id)
        return call_id, value if isinstance(value, dict) else None

    checks = []
    def check(identifier, satisfied, evidence, statement):
        checks.append({"id": identifier, "status": "satisfied" if satisfied else "contradicted",
                       "kind": "trusted-fixture-comparison", "statement": statement,
                       "evidence": evidence})

    if spec_id == "service-investigator":
        request_call, request = observed("service.lookup")
        if request is None:
            return {**base, "reason": "The authoritative service-request observation is unavailable."}
        if request.get("existingTicket"):
            check("reuse-existing", output.get("outcome") == "existing_work_item"
                  and output.get("recordId") == request["existingTicket"],
                  [f"facts.{request_call}.existingTicket"],
                  "The result reuses the linked work item instead of claiming a new one.")
            check("no-duplicate-write", observed("service.create_ticket")[1] is None,
                  [f"facts.{request_call}.existingTicket"],
                  "No local work-item capture was observed for an already-linked request.")
        else:
            failed_runbook_call, failed_runbook = _failed(state, "service.search_runbook")
            if failed_runbook is not None:
                check("unavailable-service-partial", output.get("outcome") == "service_unavailable",
                      [f"facts.{request_call}.requestId", f"facts.{failed_runbook_call}.error.code"],
                      "The partial result reports the observed unavailable runbook service.")
                check("unavailable-service-no-write", observed("service.create_ticket")[1] is None,
                      [f"facts.{failed_runbook_call}.error.code"],
                      "No work item is captured while required diagnostic evidence is unavailable.")
                verified = all(item["status"] == "satisfied" for item in checks)
                return {**base, "businessOutcomeVerified": verified,
                        "status": "satisfied" if verified else "contradicted", "checks": checks,
                        "reason": "All registered fixture comparisons passed." if verified else "One or more registered comparisons failed."}
            runbook_call, runbook = observed("service.search_runbook")
            write_call, write = observed("service.create_ticket")
            if runbook is None or write is None:
                return {**base, "reason": "Runbook or captured-action evidence is unavailable."}
            check("runbook-linked", bool(runbook.get("articleId")),
                  [f"facts.{runbook_call}.articleId"], "The work item is supported by a runbook observation.")
            check("receipt-matches", output.get("recordId") == write.get("recordId"),
                  [f"facts.{write_call}.recordId"], "The returned record identity matches the captured receipt.")
    elif spec_id == "invoice-reviewer":
        invoice_call, invoice = observed("finance.inspect_invoice")
        policy_call, policy = observed("finance.lookup_policy")
        if invoice is None or policy is None:
            return {**base, "reason": "Invoice or policy evidence is unavailable."}
        exceptional = (invoice.get("variancePercent", 0) > policy.get("maxVariancePercent", 0)
                       or invoice.get("amount", 0) > policy.get("maxAmountWithoutException", 0)
                       or not invoice.get("supplierApproved") or not invoice.get("purchaseOrder"))
        expected_tool = "finance.request_review" if exceptional else "finance.record_decision"
        write_call, write = observed(expected_tool)
        if write is None:
            return {**base, "reason": "The expected reviewed recommendation receipt is unavailable."}
        check("policy-route", ("exception" in output.get("outcome", "")) == exceptional,
              [f"facts.{invoice_call}.variancePercent", f"facts.{policy_call}.maxVariancePercent"],
              "The disposition matches the observed invoice-policy comparison.")
        check("receipt-matches", output.get("recordId") == write.get("recordId"),
              [f"facts.{write_call}.recordId"], "The returned record identity matches the captured receipt.")
    elif spec_id == "access-coordinator":
        request_call, request = observed("access.inspect_request")
        entitlement_call, entitlement = observed("access.lookup_entitlements")
        if request is None or entitlement is None:
            return {**base, "reason": "Access-request or entitlement evidence is unavailable."}
        if not entitlement.get("roleAvailable"):
            check("unavailable-role", output.get("outcome") == "capability_gap",
                  [f"facts.{entitlement_call}.roleAvailable"], "An unavailable role is reported without a grant proposal.")
        elif entitlement.get("currentRole") == request.get("requestedRole"):
            check("avoid-duplicate", output.get("outcome") == "already_present",
                  [f"facts.{entitlement_call}.currentRole", f"facts.{request_call}.requestedRole"],
                  "Existing matching access is reused without a duplicate proposal.")
        else:
            review = entitlement.get("risk") == "privileged" or not entitlement.get("managerApprovalOnFile")
            expected_tool = "access.request_review" if review else "access.record_grant"
            write_call, write = observed(expected_tool)
            if write is None:
                return {**base, "reason": "The expected access proposal receipt is unavailable."}
            check("risk-route", ("review" in output.get("outcome", "")) == review,
                  [f"facts.{entitlement_call}.risk", f"facts.{entitlement_call}.managerApprovalOnFile"],
                  "The proposed path matches the observed risk and approval state.")
            check("receipt-matches", output.get("recordId") == write.get("recordId"),
                  [f"facts.{write_call}.recordId"], "The returned record identity matches the captured receipt.")
    else:
        return {**base, "reason": "No trusted outcome validator is registered for this custom agent."}

    verified = bool(checks) and all(item["status"] == "satisfied" for item in checks)
    return {**base, "businessOutcomeVerified": verified,
            "status": "satisfied" if verified else "contradicted", "checks": checks,
            "reason": "All registered fixture comparisons passed." if verified else "One or more registered comparisons failed."}
