"""Security and contract tests for provider-neutral external integrations."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_factory
import integrations


PUBLIC_IP = "93.184.216.34"


def public_resolver(_hostname, _port):
    return [PUBLIC_IP]


AUTH = {
    "slack": {"mode": "bearer", "secretRefs": {"token": "env:SLACK_BOT_TOKEN"}, "scopes": ["channels:history", "chat:write"]},
    "jira-cloud": {"mode": "basic", "secretRefs": {"username": "env:JIRA_USER", "password": "env:JIRA_API_TOKEN"}, "scopes": ["read:jira-user", "read:jira-work", "write:jira-work"]},
    "confluence-cloud": {"mode": "basic", "secretRefs": {"username": "env:CONF_USER", "password": "env:CONF_API_TOKEN"}, "scopes": ["read:space:confluence", "read:page:confluence", "write:page:confluence"]},
    "generic-rest": {"mode": "none", "secretRefs": {}, "scopes": []},
    "webhook": {"mode": "none", "secretRefs": {}, "scopes": []},
    "mcp": {"mode": "none", "secretRefs": {}, "scopes": []},
}
BASE = {
    "slack": "https://slack.com/api/",
    "jira-cloud": "https://acme.atlassian.net/rest/api/3/",
    "confluence-cloud": "https://acme.atlassian.net/wiki/api/v2/",
    "generic-rest": "https://api.example.com/v1/",
    "webhook": "https://hooks.example.com/axiom/",
    "mcp": "https://mcp.example.com/v1/",
}


def connection(provider="slack", ready=True):
    record = integrations.connection_template(
        provider,
        connection_id=f"{provider}-primary",
        name=f"{provider} primary",
        base_urls=[BASE[provider]],
        auth=AUTH[provider],
    )
    if ready:
        record["status"] = "ready"
    return integrations.normalize_connection_spec(record)


class ProviderCatalogTests(unittest.TestCase):
    def test_catalog_has_expected_descriptor_only_providers(self):
        records = integrations.provider_descriptors()
        self.assertEqual(
            {"slack", "jira-cloud", "confluence-cloud", "generic-rest", "webhook", "mcp"},
            {item["id"] for item in records},
        )
        self.assertTrue(all(item["configurationState"] == "descriptor-only" for item in records))
        self.assertTrue(all("category" in item and "docsUrl" in item and "setupFields" in item for item in records))
        self.assertTrue(all(item["secretRefSchemes"] == ["env"] for item in records))
        health = {item["id"]: item["healthOperationId"] for item in records}
        self.assertEqual("slack.auth.test", health["slack"])
        self.assertEqual("jira.users.myself", health["jira-cloud"])
        self.assertEqual("confluence.spaces.health", health["confluence-cloud"])
        self.assertEqual("mcp.catalog.list_tools", health["mcp"])
        self.assertIsNone(health["generic-rest"])
        self.assertIsNone(health["webhook"])
        text = json.dumps(records)
        self.assertNotIn('"secretRefs": {', text)
        self.assertNotIn("SLACK_BOT_TOKEN", text)

    def test_every_descriptor_builds_a_strict_draft(self):
        for provider in AUTH:
            with self.subTest(provider=provider):
                record = connection(provider, ready=False)
                self.assertEqual("draft", record["status"])
                self.assertGreaterEqual(len(record["operations"]), 1)

    def test_provider_descriptors_are_defensive_copies(self):
        first = integrations.provider_descriptors()
        first[0]["name"] = "changed"
        self.assertNotEqual("changed", integrations.provider_descriptors()[0]["name"])


class SecretAndPublicStateTests(unittest.TestCase):
    def test_inline_secret_values_and_unknown_auth_fields_are_rejected(self):
        record = connection(ready=False)
        record["auth"]["secretRefs"]["token"] = "synthetic-inline-secret"
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.normalize_connection_spec(record)
        self.assertEqual("SECRET_REFERENCE", denied.exception.code)

        record = connection(ready=False)
        record["auth"]["token"] = "synthetic-inline-secret"
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.normalize_connection_spec(record)
        self.assertEqual("CONNECTION_SCHEMA", denied.exception.code)

    def test_secret_reference_schemes_are_narrow(self):
        for reference in ("env:SLACK_TOKEN", "secret://tenant/slack#token", "vault://prod/slack/token", "keychain://axiom/slack"):
            record = connection(ready=False)
            record["auth"]["secretRefs"]["token"] = reference
            self.assertEqual(reference, integrations.normalize_connection_spec(record)["auth"]["secretRefs"]["token"])
        for reference in ("env://TOKEN", "env:bad-name", "https://vault/token", "secret:", "token"):
            record = connection(ready=False)
            record["auth"]["secretRefs"]["token"] = reference
            with self.subTest(reference=reference), self.assertRaises(integrations.IntegrationError):
                integrations.normalize_connection_spec(record)

    def test_public_connection_omits_secret_paths_and_values(self):
        public = integrations.public_connection(connection())
        encoded = json.dumps(public)
        self.assertNotIn("secretRefs", encoded)
        self.assertNotIn("SLACK_BOT_TOKEN", encoded)
        self.assertTrue(public["auth"]["credentialReferencesConfigured"])
        self.assertEqual(1, public["auth"]["credentialSlotCount"])

    def test_credential_reference_change_changes_exact_plan_hash(self):
        first = connection()
        prepared = integrations.prepare_call(
            first, "slack.conversations.history", {"channel": "C123", "limit": 10}, "adaptive:session:call_1"
        )
        second = copy.deepcopy(first)
        second["auth"]["secretRefs"]["token"] = "env:SLACK_ROTATED_TOKEN"
        with self.assertRaises(integrations.IntegrationError) as stale:
            integrations.verify_prepared_call(second, prepared)
        self.assertEqual("PREPARED_CALL_CHANGED", stale.exception.code)


class NetworkPolicyTests(unittest.TestCase):
    def test_public_connections_require_https_and_deny_private_hosts(self):
        for url in (
            "http://api.example.com/v1/", "https://localhost/v1/", "https://127.0.0.1/v1/",
            "https://169.254.169.254/latest/", "https://metadata.google.internal/",
            "https://user:pass@example.com/v1/",
        ):
            record = connection("generic-rest", ready=False)
            record["baseUrls"] = [url]
            with self.subTest(url=url), self.assertRaises(integrations.IntegrationError) as denied:
                integrations.normalize_connection_spec(record)
            self.assertEqual("DESTINATION_DENIED", denied.exception.code)

    def test_target_must_remain_under_exact_origin_and_path_prefix(self):
        allowed = ["https://api.example.com/v1/"]
        self.assertEqual((PUBLIC_IP,), integrations.validate_outbound_url(
            "https://api.example.com/v1/resources/1", allowed, resolver=public_resolver
        ))
        for target in (
            "https://evil.example/v1/resources/1",
            "https://api.example.com/v2/resources/1",
            "https://api.example.com.evil.test/v1/resources/1",
        ):
            with self.subTest(target=target), self.assertRaises(integrations.IntegrationError) as denied:
                integrations.validate_outbound_url(target, allowed, resolver=public_resolver)
            self.assertEqual("DESTINATION_DENIED", denied.exception.code)

    def test_native_provider_credentials_are_pinned_to_official_api_origins(self):
        for provider in ("slack", "jira-cloud", "confluence-cloud"):
            record = connection(provider)
            record["baseUrls"] = ["https://credential-capture.example/api/"]
            with self.subTest(provider=provider), self.assertRaises(integrations.IntegrationError) as denied:
                integrations.normalize_connection_spec(record)
            self.assertEqual("DESTINATION_DENIED", denied.exception.code)

    def test_atlassian_oauth_uses_the_cloud_gateway_for_the_selected_product(self):
        record = connection("jira-cloud")
        record["auth"] = {
            "mode": "oauth2", "secretRefs": {"credential": "env:JIRA_OAUTH_TOKEN"},
            "scopes": record["auth"]["scopes"],
        }
        record["baseUrls"] = [
            "https://api.atlassian.com/ex/jira/11111111-2222-3333-4444-555555555555/rest/api/3/"
        ]
        normalized = integrations.normalize_connection_spec(record)
        self.assertEqual(record["baseUrls"], normalized["baseUrls"])

        record["baseUrls"] = ["https://acme.atlassian.net/rest/api/3/"]
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.normalize_connection_spec(record)
        self.assertEqual("DESTINATION_DENIED", denied.exception.code)

    def test_dns_rebinding_to_private_address_is_denied(self):
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.validate_outbound_url(
                "https://api.example.com/v1/resources/1", ["https://api.example.com/v1/"],
                resolver=lambda _host, _port: ["10.0.0.8"],
            )
        self.assertEqual("DESTINATION_DENIED", denied.exception.code)

    def test_private_network_needs_explicit_policy(self):
        record = connection("mcp", ready=False)
        record["allowPrivateNetwork"] = True
        record["baseUrls"] = ["http://127.0.0.1:8080/mcp/"]
        normalised = integrations.normalize_connection_spec(record)
        addresses = integrations.validate_outbound_url(
            "http://127.0.0.1:8080/mcp/", normalised["baseUrls"],
            allow_private_network=True, resolver=lambda _host, _port: ["127.0.0.1"],
        )
        self.assertEqual(("127.0.0.1",), addresses)


class OperationAndPreparationTests(unittest.TestCase):
    def test_unknown_fields_and_unapproved_writes_are_rejected(self):
        record = connection()
        record["surprise"] = True
        with self.assertRaises(integrations.IntegrationError):
            integrations.normalize_connection_spec(record)

        record = connection()
        write = next(item for item in record["operations"] if item["effect"] == "write")
        write["approvalRequired"] = False
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.normalize_connection_spec(record)
        self.assertEqual("APPROVAL_POLICY", denied.exception.code)

    def test_model_cannot_supply_undeclared_arguments_or_destination(self):
        record = connection("jira-cloud")
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.prepare_call(
                record, "jira.issues.get",
                {"issueKey": "AX-1", "url": "https://evil.example/"}, "adaptive:s1:c1",
            )
        self.assertEqual("SCHEMA_VALUE", denied.exception.code)

    def test_path_values_are_percent_encoded_and_url_stays_allowlisted(self):
        record = connection("jira-cloud")
        prepared = integrations.prepare_call(
            record, "jira.issues.get", {"issueKey": "../admin?x=1"}, "adaptive:s1:c1"
        )
        self.assertIn("..%2Fadmin%3Fx%3D1", prepared.target_url)
        integrations.validate_outbound_url(prepared.target_url, record["baseUrls"], resolver=public_resolver)

    def test_exact_dot_segments_cannot_change_the_reviewed_endpoint(self):
        record = connection("jira-cloud")
        for issue_key in (".", ".."):
            with self.subTest(issue_key=issue_key):
                with self.assertRaises(integrations.IntegrationError) as denied:
                    integrations.prepare_call(
                        record, "jira.issues.get", {"issueKey": issue_key}, "adaptive:s1:c1"
                    )
                self.assertEqual("SCHEMA_VALUE", denied.exception.code)

    def test_prepared_state_has_exact_identity_and_no_credentials(self):
        record = connection()
        prepared = integrations.prepare_call(
            record, "slack.chat.post_message", {"channel": "C123", "text": "Reviewed update"},
            "adaptive:session:call_2",
        )
        public = prepared.public_dict()
        self.assertTrue(public["approvalRequired"])
        self.assertEqual(record["generation"], public["connectionIdentity"]["generation"])
        self.assertEqual("adaptive:session:call_2", public["operationKey"])
        self.assertNotIn("SLACK_BOT_TOKEN", json.dumps(public))
        self.assertNotIn("secretRefs", json.dumps(public))
        self.assertNotIn("authBindingHash", public)

    def test_connection_generation_change_invalidates_prepared_call(self):
        record = connection()
        prepared = integrations.prepare_call(
            record, "slack.conversations.history", {"channel": "C123", "limit": 10}, "adaptive:s1:c1"
        )
        record["generation"] += 1
        with self.assertRaises(integrations.IntegrationError) as stale:
            integrations.verify_prepared_call(record, prepared)
        self.assertEqual("CONNECTION_CHANGED", stale.exception.code)

    def test_tampered_prepared_dispatch_fields_cannot_reuse_an_old_plan_hash(self):
        record = connection()
        prepared = integrations.prepare_call(
            record,
            "slack.chat.post_message",
            {"channel": "C123", "text": "Approved text"},
            "adaptive:session:call_0001",
        )
        mutations = (
            replace(prepared, target_url="https://slack.com/api/admin.users.remove"),
            replace(prepared, method="DELETE"),
            replace(prepared, headers={**prepared.headers, "X-Unreviewed": "true"}),
            replace(prepared, body={"channel": "C999", "text": "Changed text"}),
            replace(prepared, timeout_ms=prepared.timeout_ms + 1),
        )
        for mutated in mutations:
            changed_field = next(
                field for field in prepared.__dataclass_fields__
                if getattr(prepared, field) != getattr(mutated, field)
            )
            with self.subTest(field=changed_field):
                with self.assertRaises(integrations.IntegrationError) as caught:
                    integrations.verify_prepared_call(record, mutated)
                self.assertEqual("PREPARED_CALL_CHANGED", caught.exception.code)

    def test_draft_and_revoked_connections_cannot_prepare(self):
        for status in ("draft", "revoked", "disabled", "error"):
            record = connection(ready=False)
            record["status"] = status
            with self.subTest(status=status), self.assertRaises(integrations.IntegrationError) as denied:
                integrations.prepare_call(
                    record, "slack.conversations.history", {"channel": "C123", "limit": 10}, "adaptive:s1:c1"
                )
            self.assertEqual("CONNECTION_NOT_READY", denied.exception.code)

    def test_native_health_operations_need_no_fabricated_business_input(self):
        for provider, operation_id in (
            ("slack", "slack.auth.test"),
            ("jira-cloud", "jira.users.myself"),
            ("confluence-cloud", "confluence.spaces.health"),
            ("mcp", "mcp.catalog.list_tools"),
        ):
            with self.subTest(provider=provider):
                prepared = integrations.prepare_call(connection(provider), operation_id, {}, f"health:{provider}:1")
                self.assertEqual(operation_id, prepared.operation_id)

    def test_capability_projection_compiles_in_shared_agent_kernel(self):
        contracts = integrations.capability_contracts(connection())
        read_id = next(item["id"] for item in contracts if item["adapterBinding"]["operation"] == "slack.conversations.history")
        spec = {
            "id": "slack_observer", "version": 1, "name": "Slack Observer",
            "mission": "Read permitted messages and return a summary.", "instructions": "Use only registered reads.",
            "inputSchema": {"type": "object", "properties": {"channel": {"type": "string", "minLength": 1, "maxLength": 100}}, "required": ["channel"], "additionalProperties": False},
            "outputSchema": {"type": "object", "properties": {"summary": {"type": "string", "maxLength": 2000}}, "required": ["summary"], "additionalProperties": False},
            "contextFields": ["input.channel"], "allowedTools": [read_id],
            "requiredEvidenceTools": [read_id], "limits": {}, "stopRules": {},
            "policyRefs": ["external-integrations.v1"], "evaluationCases": [],
        }
        compiled = agent_factory.compile_agent(spec, contracts)
        self.assertEqual(read_id, compiled["tools"][0]["id"])
        self.assertEqual("slack.conversations.history", compiled["tools"][0]["adapterBinding"]["operation"])

    def test_two_connections_project_noncolliding_capability_ids(self):
        first = connection()
        second = copy.deepcopy(first)
        second["id"] = "slack-secondary"
        first_contracts = integrations.capability_contracts(first)
        second_contracts = integrations.capability_contracts(second)
        first_ids = {item["id"] for item in first_contracts}
        second_ids = {item["id"] for item in second_contracts}
        self.assertFalse(first_ids & second_ids)
        self.assertTrue(all(len(ident) <= 150 for ident in first_ids | second_ids))
        self.assertEqual(
            {item["adapterBinding"]["operation"] for item in first_contracts},
            {item["adapterBinding"]["operation"] for item in second_contracts},
        )


class RetryRateAndReconciliationTests(unittest.TestCase):
    def test_reads_retry_with_bounded_backoff(self):
        advice = integrations.retry_advice(
            connection(), "slack.conversations.history", attempt=1, status_code=429
        )
        self.assertTrue(advice.retry)
        self.assertEqual(250, advice.delay_ms)
        self.assertFalse(advice.reconcile_first)

    def test_non_idempotent_write_never_blindly_retries(self):
        advice = integrations.retry_advice(
            connection(), "slack.chat.post_message", attempt=1, network_error=True, outcome_unknown=True
        )
        self.assertFalse(advice.retry)
        self.assertTrue(advice.reconcile_first)
        self.assertEqual("write_requires_reconciliation", advice.reason)

    def test_manual_reconciliation_directive_is_explicit(self):
        directive = integrations.reconciliation_directive(
            connection(), "slack.chat.post_message", "adaptive:s1:c2"
        )
        self.assertEqual("manual", directive["mode"])
        self.assertFalse(directive["automatic"])
        self.assertTrue(directive["retryPermittedOnlyAfterNotFound"])

    def test_rate_limiter_enforces_window_and_concurrency_without_sleeping(self):
        clock = [10.0]
        limiter = integrations.InMemoryRateLimiter(clock=lambda: clock[0])
        policy = {"maxRequests": 2, "windowSeconds": 10, "maxConcurrent": 1}
        first = limiter.acquire("connection-1", policy)
        with self.assertRaises(integrations.IntegrationError) as concurrent:
            limiter.acquire("connection-1", policy)
        self.assertEqual("RATE_LIMITED", concurrent.exception.code)
        first.release()
        second = limiter.acquire("connection-1", policy)
        second.release()
        with self.assertRaises(integrations.IntegrationError) as window:
            limiter.acquire("connection-1", policy)
        self.assertGreater(window.exception.details["retryAfterMs"], 0)
        clock[0] = 21.0
        limiter.acquire("connection-1", policy).release()


class FakeSecrets:
    def __init__(self, values=None, failure=None):
        self.values = values or {"env:SLACK_BOT_TOKEN": "synthetic-resolved-only-at-dispatch"}
        self.failure = failure

    def resolve(self, reference):
        if self.failure:
            raise RuntimeError(self.failure)
        return self.values[reference]


class FakeExecutor:
    def __init__(self, response):
        self.response = response
        self.request = None

    def send(self, request):
        self.request = request
        return self.response


class AdapterBoundaryTests(unittest.TestCase):
    def history_plan(self):
        record = connection()
        prepared = integrations.prepare_call(
            record, "slack.conversations.history", {"channel": "C123", "limit": 1}, "adaptive:s1:c1"
        )
        return record, prepared

    def test_http_adapter_resolves_secret_only_for_ephemeral_request(self):
        record, prepared = self.history_plan()
        payload = {"ok": True, "messages": [], "has_more": False, "response_metadata": {"next_cursor": ""}}
        executor = FakeExecutor(integrations.TransportResponse(
            200, {"content-type": "application/json"}, json.dumps(payload).encode(), prepared.target_url
        ))
        adapter = integrations.StrictHttpAdapter(executor)
        result = adapter.execute(
            record, prepared, secret_resolver=FakeSecrets(), network_resolver=public_resolver
        )
        self.assertEqual("acknowledged", result.status)
        self.assertIn("synthetic-resolved-only-at-dispatch", executor.request.headers["Authorization"])
        self.assertNotIn("synthetic-resolved-only-at-dispatch", repr(executor.request))
        self.assertFalse(executor.request.follow_redirects)
        self.assertEqual((PUBLIC_IP,), executor.request.approved_addresses)

    def test_redirects_and_oversized_responses_are_rejected(self):
        record, prepared = self.history_plan()
        for response, code in (
            (integrations.TransportResponse(302, {"location": "https://evil.example"}, b"", prepared.target_url), "REDIRECT_DENIED"),
            (integrations.TransportResponse(200, {}, b"x" * (prepared.max_response_bytes + 1), prepared.target_url), "RESPONSE_TOO_LARGE"),
        ):
            adapter = integrations.StrictHttpAdapter(FakeExecutor(response))
            with self.subTest(code=code), self.assertRaises(integrations.IntegrationError) as denied:
                adapter.execute(record, prepared, secret_resolver=FakeSecrets(), network_resolver=public_resolver)
            self.assertEqual(code, denied.exception.code)

    def test_secret_resolver_failure_is_sanitized(self):
        record, prepared = self.history_plan()
        executor = FakeExecutor(integrations.TransportResponse(200, {}, b"{}", prepared.target_url))
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.StrictHttpAdapter(executor).execute(
                record, prepared,
                secret_resolver=FakeSecrets(failure="vault path prod/super-secret failed"),
                network_resolver=public_resolver,
            )
        self.assertEqual("SECRET_UNAVAILABLE", denied.exception.code)
        self.assertNotIn("super-secret", denied.exception.message)

    def test_adapter_registry_is_trusted_and_transport_scoped(self):
        record, _ = self.history_plan()
        registry = integrations.AdapterRegistry()
        executor = FakeExecutor(integrations.TransportResponse(200, {}, b"{}", ""))
        adapter = integrations.StrictHttpAdapter(executor)
        registry.register(adapter)
        self.assertIs(adapter, registry.resolve(record))
        with self.assertRaises(integrations.IntegrationError) as duplicate:
            registry.register(integrations.StrictHttpAdapter(executor))
        self.assertEqual("ADAPTER_CONTRACT", duplicate.exception.code)

    def test_invalid_provider_output_is_not_accepted_as_success(self):
        record, prepared = self.history_plan()
        response = integrations.TransportResponse(200, {}, json.dumps({"ok": True, "messages": {}}).encode(), prepared.target_url)
        with self.assertRaises(integrations.IntegrationError) as invalid:
            integrations.StrictHttpAdapter(FakeExecutor(response)).execute(
                record, prepared, secret_resolver=FakeSecrets(), network_resolver=public_resolver
            )
        self.assertEqual("PROVIDER_RESPONSE", invalid.exception.code)

    def test_slack_native_envelope_is_projected_and_logical_error_fails(self):
        record, prepared = self.history_plan()
        native = {
            "ok": True,
            "messages": [{"user": "U123", "text": "hello", "ts": "1710000000.001"}],
            "has_more": False,
            "response_metadata": {"next_cursor": "next"},
        }
        adapter = integrations.StrictHttpAdapter(FakeExecutor(integrations.TransportResponse(
            200, {}, json.dumps(native).encode(), prepared.target_url
        )))
        result = adapter.execute(record, prepared, secret_resolver=FakeSecrets(), network_resolver=public_resolver)
        self.assertEqual("1710000000.001", result.output["messages"][0]["id"])
        self.assertEqual("U123", result.output["messages"][0]["authorId"])
        self.assertTrue(result.output["hasMore"])

        failed = integrations.StrictHttpAdapter(FakeExecutor(integrations.TransportResponse(
            200, {}, json.dumps({"ok": False, "error": "missing_scope"}).encode(), prepared.target_url
        )))
        with self.assertRaises(integrations.IntegrationError) as denied:
            failed.execute(record, prepared, secret_resolver=FakeSecrets(), network_resolver=public_resolver)
        self.assertEqual("PROVIDER_RESPONSE", denied.exception.code)
        self.assertEqual("missing_scope", denied.exception.details["providerCode"])

    def test_jira_native_paths_request_projection_and_response_projection(self):
        record = connection("jira-cloud")
        search = integrations.prepare_call(
            record, "jira.issues.search", {"jql": "project = AX", "maxResults": 10}, "adaptive:j1:c1"
        )
        self.assertIn("/rest/api/3/search/jql?", search.target_url)
        native_search = {
            "issues": [{"key": "AX-1", "fields": {"summary": "Broken", "status": {"name": "Open"}}}],
            "total": 1,
        }
        secrets = FakeSecrets({"env:JIRA_USER": "admin@example.com", "env:JIRA_API_TOKEN": "token"})
        result = integrations.StrictHttpAdapter(FakeExecutor(integrations.TransportResponse(
            200, {}, json.dumps(native_search).encode(), search.target_url
        ))).execute(record, search, secret_resolver=secrets, network_resolver=public_resolver)
        self.assertEqual({"key": "AX-1", "summary": "Broken", "status": "Open"}, result.output["issues"][0])

        create = integrations.prepare_call(
            record, "jira.issues.create",
            {"projectKey": "AX", "issueType": "Task", "summary": "Investigate", "description": "Exact details"},
            "adaptive:j1:c2",
        )
        self.assertEqual("AX", create.body["fields"]["project"]["key"])
        self.assertEqual("Task", create.body["fields"]["issuetype"]["name"])
        self.assertEqual("doc", create.body["fields"]["description"]["type"])
        self.assertEqual("Exact details", create.body["fields"]["description"]["content"][0]["content"][0]["text"])

    def test_confluence_v2_native_request_and_page_projection(self):
        record = connection("confluence-cloud")
        health = integrations.prepare_call(record, "confluence.spaces.health", {}, "adaptive:c1:h1")
        self.assertTrue(health.target_url.endswith("spaces?limit=1"))
        create = integrations.prepare_call(
            record, "confluence.pages.create",
            {"spaceId": "10", "title": "Runbook", "body": "<p>Safe</p>"}, "adaptive:c1:c1",
        )
        self.assertEqual({"representation": "storage", "value": "<p>Safe</p>"}, create.body["body"])
        self.assertEqual("current", create.body["status"])
        read = integrations.prepare_call(record, "confluence.pages.get", {"pageId": "42"}, "adaptive:c1:c2")
        native = {
            "id": "42", "title": "Runbook", "version": {"number": 7},
            "_links": {"base": "https://acme.atlassian.net/wiki", "webui": "/spaces/OPS/pages/42"},
        }
        secrets = FakeSecrets({"env:CONF_USER": "admin@example.com", "env:CONF_API_TOKEN": "token"})
        result = integrations.StrictHttpAdapter(FakeExecutor(integrations.TransportResponse(
            200, {}, json.dumps(native).encode(), read.target_url
        ))).execute(record, read, secret_resolver=secrets, network_resolver=public_resolver)
        self.assertEqual(7, result.output["version"])
        self.assertEqual("https://acme.atlassian.net/wiki/spaces/OPS/pages/42", result.output["url"])


class FakeMcpClient:
    def __init__(self):
        self.call = None

    def list_tools(self, **kwargs):
        self.call = kwargs
        return {"tools": [{"name": "crm.accounts.lookup", "description": "Read an account"}]}

    def call_tool(self, **kwargs):
        raise AssertionError("tools/list must use the MCP protocol method, not tools/call")


class McpBoundaryTests(unittest.TestCase):
    def test_mcp_calls_only_registered_operation(self):
        record = connection("mcp")
        prepared = integrations.prepare_call(record, "mcp.catalog.list_tools", {}, "adaptive:m1:c1")
        client = FakeMcpClient()
        result = integrations.StrictMcpAdapter(client).execute(
            record, prepared, secret_resolver=FakeSecrets({}), network_resolver=public_resolver
        )
        self.assertNotIn("tool_name", client.call)
        self.assertEqual("acknowledged", result.status)
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.prepare_call(record, "mcp.unregistered.execute", {}, "adaptive:m1:c2")
        self.assertEqual("OPERATION_NOT_FOUND", denied.exception.code)


def openapi_document():
    widget = {
        "type": "object",
        "properties": {"id": {"type": "string", "minLength": 1, "maxLength": 100}, "name": {"type": "string", "maxLength": 500}},
        "required": ["id", "name"],
        "additionalProperties": False,
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "Widget API", "version": "2026-09"},
        "servers": [{"url": "https://api.example.com/v1/"}],
        "components": {"securitySchemes": {"ApiToken": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}},
        "security": [{"ApiToken": []}],
        "paths": {
            "/widgets/{widgetId}": {
                "get": {
                    "operationId": "getWidget", "description": "Read one widget.",
                    "parameters": [
                        {"name": "widgetId", "in": "path", "required": True, "schema": {"type": "string", "minLength": 1, "maxLength": 100}},
                        {"name": "expand", "in": "query", "schema": {"type": "boolean"}},
                    ],
                    "responses": {"200": {"description": "Widget", "content": {"application/json": {"schema": widget}}}},
                }
            },
            "/widgets": {
                "post": {
                    "operationId": "createWidget", "description": "Create one widget.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 500}},
                        "required": ["name"], "additionalProperties": False,
                    }}}},
                    "responses": {"201": {"description": "Created", "content": {"application/json": {"schema": widget}}}},
                }
            },
        },
    }


class OpenApiInspectorTests(unittest.TestCase):
    def test_inspection_produces_unclassified_non_executable_candidates(self):
        report = integrations.inspect_openapi(openapi_document())
        self.assertEqual("review_required", report["status"])
        self.assertEqual("https://api.example.com/v1/", report["serverBaseUrl"])
        self.assertEqual(2, len(report["candidates"]))
        create = next(item for item in report["candidates"] if item["sourceOperationId"] == "createWidget")
        self.assertEqual("unclassified", create["reviewState"])
        self.assertNotIn("effect", create)
        self.assertNotIn("approvalRequired", create)
        self.assertIn("effect", create["requiredReviewFields"])

    def test_trusted_review_is_required_before_operation_activation(self):
        candidate = integrations.inspect_openapi(openapi_document())["candidates"][0]
        operation = integrations.activate_openapi_candidate(candidate, {
            "effect": "read", "requiredScopes": ["widgets.read"], "approvalRequired": False,
            "idempotency": {"classification": "read_only", "retry": "safe", "reconciliation": "not_applicable"},
            "maxResponseBytes": 100_000,
        })
        self.assertEqual("read", operation["effect"])
        self.assertEqual("rest.getWidget", operation["id"])
        self.assertEqual("identity.v1", operation["binding"]["codec"])

        create = integrations.inspect_openapi(openapi_document())["candidates"][1]
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.activate_openapi_candidate(create, {
                "effect": "write", "requiredScopes": ["widgets.write"], "approvalRequired": False,
                "idempotency": {"classification": "non_idempotent", "retry": "reconcile_before_retry", "reconciliation": "manual", "operationKey": "host-ledger-only"},
                "maxResponseBytes": 100_000,
            })
        self.assertEqual("APPROVAL_POLICY", denied.exception.code)

    def test_candidate_mutation_is_detected(self):
        candidate = integrations.inspect_openapi(openapi_document())["candidates"][0]
        candidate["method"] = "DELETE"
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.activate_openapi_candidate(candidate, {
                "effect": "read", "requiredScopes": [], "approvalRequired": False,
                "idempotency": {"classification": "read_only", "retry": "safe", "reconciliation": "not_applicable"},
                "maxResponseBytes": 100_000,
            })
        self.assertEqual("OPENAPI_CANDIDATE_CHANGED", denied.exception.code)

    def test_remote_refs_http_servers_and_duplicate_operation_ids_are_refused(self):
        referenced = openapi_document()
        referenced["paths"]["/widgets/{widgetId}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": "https://evil.example/schema.json"}
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.inspect_openapi(referenced)
        self.assertEqual("OPENAPI_REF_UNSUPPORTED", denied.exception.code)

        insecure = openapi_document()
        insecure["servers"] = [{"url": "http://api.example.com/v1/"}]
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.inspect_openapi(insecure)
        self.assertEqual("DESTINATION_DENIED", denied.exception.code)

        duplicate = openapi_document()
        duplicate["paths"]["/widgets"]["post"]["operationId"] = "getWidget"
        with self.assertRaises(integrations.IntegrationError) as denied:
            integrations.inspect_openapi(duplicate)
        self.assertEqual("OPENAPI_OPERATION", denied.exception.code)


if __name__ == "__main__":
    unittest.main()
