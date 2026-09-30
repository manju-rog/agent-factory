# Agent factory source verification and merge gate

Source-checkpoint verification date: 2026-09-25.

> **Host status:** the original factory extension was integrated into the Axiom
> 1.9 schema-10 host. Its 113-test source result and the Axiom 1.9 235-test host
> result below are historical. Axiom 2.0/schema 11 adds external capabilities;
> its release-wide discovery gate passed **287/287 tests in 34.162 seconds**.
> Do not carry either historical count forward as the 2.0 result.

## What is being verified

The source extension adds a generic, registry-driven agent engine, editable agent specifications, a model-provider adapter, and reusable Goal Agent placements inside published workflows. It is a local reference application. Business-system adapters use explicit local fixtures. In the merged host, approved adaptive writes must use the existing durable SQLite effect ledger rather than a second, weaker effect store.

The bundled service, invoice and access scenarios use a **scripted fixture decision provider, not an LLM**. Model-mode tests use declared test doubles, including actual loopback HTTP through the application's chat-completion adapter. They verify transport and enforcement, not live-model reasoning quality.

## Axiom 2.0 external-capability addendum

The schema-11 host can compile reviewed operations from ready Slack, Jira Cloud, Confluence Cloud, and outbound-webhook connections into stable per-connection Goal Agent capabilities. The shared runtime did not gain provider-specific planning branches. An external read is still selected through the specification allowlist, and an external write still becomes an exact prepared action whose approved stored request is dispatched only after authority and relevant source state are rechecked.

Integration contract checks exercise strict connection/operation schemas, public secret-reference redaction, native-provider origin pinning, DNS/address boundaries, exact prepared-plan verification, response projection, stale generation handling, and Goal Agent adapter registration. They use controlled records/transports and establish enforcement only. No live provider credential, tenant, permission, delivery, OAuth lifecycle, automatic retry, or external reconciliation was verified. OpenAPI now has an inspect-only HTTP/UI flow whose candidates remain non-executable; MCP remains a module-level/developer primitive. Neither is an activated connection.

## Historical Axiom 1.9 host factory gate

The focused current-host command below is the authoritative factory gate. It passed **65/65 tests** and covers the generic engine, fixture adapters and decisions, schema-9-to-10 migration, durable runtime and workflow bridge, and HTTP boundaries.

| Current-host focused suite | Passed |
| --- | ---: |
| Generic Agent Factory engine | 29 |
| Factory fixtures and decisions | 15 |
| Schema-9-to-10 factory migration | 1 |
| Durable runtime and workflow bridge | 16 |
| Factory HTTP boundaries | 4 |
| **Focused total** | **65** |

Primary coverage includes strict capability contracts, adaptive observations, context boundaries, budgets, provider errors, exact approvals, previously unknown registered tools, three business domains, observation-dependent paths, clarification, fail-closed outcome validators, restart/replay, immutable pins, parent/child gates, cancellation, simulation, stale provider responses, payload tampering, controlled provider transport, draft/publish roles, approved-only palette registration, stale revisions, and custom agents executed as pinned workflow children.

## Verified source checkpoint

**All 113 Python tests passed** in the supplied factory checkpoint's final unified run (7.637 seconds). Both checkpoint frontend JavaScript files passed Node syntax checks, and its expanded VM contract check passed. These counts include 65 tests from that checkpoint's older host and must not be added wholesale to the current host's test count.

| Suite | Passed | Primary coverage |
| --- | ---: | --- |
| Generic agent engine | 23 | Novel registry tools, observed-result adaptation, scoped context and provenance, schemas, references, exact approvals, deadlines, budgets, error observations and completion checks. |
| Factory fixture adapters and decisions | 11 | Twelve local tools, six cases across three domains, observation-dependent paths, clarification, custom-agent rejection in scripted mode and truthful simulation results. |
| Factory runtime and workflow bridge | 10 | Frozen definitions, restart/replay, tampering, parent gates and cancellation, simulation, stale in-flight responses and actual generation transport. |
| Factory HTTP boundaries | 4 | Author roles, schema/allowlist limits, revision conflicts, unavailable provider, exact approval once, and custom specification through published parent/child execution. |
| Existing application and context-binding regression | 65 | All previous compiler, runtime and HTTP tests remain passing. |

## What the checks establish

- **A generic capability boundary.** Engine tests inject previously unknown `observatory.*` tools and a new agent specification. The engine runs them without adding domain branches. The same agent changes its next action when the preceding measurement changes; a failed read becomes an observation for a subsequent clarification. This proves the generic engine mechanism. The shipped application exposes twelve trusted local adapters; adding a production adapter remains developer work.
- **Actual observation changes the path.** The service investigator observes an existing ticket and finishes without proposing a write. For a different request, the same specification observes that no ticket exists, reads a runbook, then prepares a new ticket. Finance and access fixtures exercise two further pairs of observation-dependent paths. Scenario labels alone do not determine the decision.
- **Creation reaches workflow execution.** A real HTTP test creates a custom specification, verifies its registry alias, places it in a newly published workflow, and runs its durable child through actual chat-completion HTTP transport against a scripted model double. The child returns the observed ticket to its parent, preserves its pinned specification version, inherits the contributor initiator, and excludes an undeclared private task field from the provider request.
- **Agent generation is a reviewable proposal.** A controlled HTTP provider returns a specification through the actual generation endpoint. The result is compiled and returned for review without saving it or registering it automatically.
- **Authority is checked before execution.** Tests reject undeclared tools and fields, unsupported schema rules, invented observation references, resource-binding overrides, missing or wrong action hashes, and excessive budgets. Context projection includes only the declared task paths. Every write needs approval of its exact tool and arguments. Deadline checks include time spent waiting for approval.
- **The model receives attributable observations.** Each observed call maps to its actual tool, resolved arguments and success/failure status. Two tools with identically shaped outputs remain distinguishable. Unselected input and unrelated full-history data are excluded; the complete model request, including provenance metadata, must fit the byte budget.
- **Workflow and action approval remain separate.** Authorizing a workflow placement and satisfying its manual executor gate do not approve a child write. A parent review must submit the hash that was displayed; missing or stale hashes are rejected. The UI confirmation retains action A's hash even if the selected node has since advanced to action B, and refuses submission after switching to a different parent run.
- **Persistence and concurrency preserve decisions.** Restart after approval resumes the same prepared action. Replaying it retains one local effect under the original operation key. Mutated payloads do not reach the adapter. Published agent/tool snapshots remain frozen. A delayed provider request does not hold the workflow-store lock, and stopping its session discards the late response. Parent cancellation stops pending child work.
- **Simulation has no captured effect.** In the merged contract, parent simulation inserts no adaptive row in the host `effects` ledger and reports the observed write as simulated. Fixture mode captures one acknowledged local effect under a stable operation identity. Neither mode contacts an external business system.

## Historical source UI contract checks

The JavaScript check executes the real view functions and selected delegated-handler logic in a Node VM against actual captured server data. It retains the previous workflow, context-binding, evidence and release-preview checks, and adds all saved factory specifications, captured agent sessions, action-review dialogs, clarification forms and a new blank specification.

The passing capture contains eleven workflow runs, nine factory runs and four templates. Coverage includes:

- 32 route/role views, 44 workflow run/role views, and 16 node inspectors.
- 12 factory specification/role views and 36 factory session/role views.
- 16 factory action dialogs, four clarification views, and a new blank draft with no tool permissions.
- Eleven evidence dialogs, eleven recovery dialogs, and two prepared workflow approval dialogs, including the real Goal Agent child action.
- Two bound context inspectors/design previews, six stale-preview checks, two stale-approval payload checks, captured validation/diff responses, and offline-write rejection.

The stale-review check uses a deliberately constructed parent shell around a real recorded pending action to exercise a state change between opening and confirming a dialog. It checks the emitted action hash and run binding. It does not simulate browser clicks or claim DOM interaction coverage.

## Historical Axiom 1.9 host interface checks

The merged interface has syntax and Node VM coverage for the Agent Factory route, specification editing and save payload, valid stop-rule objects, explicit draft/activation lifecycle, fixture/model disclosure, behavior comparison, prepared-action records, completion/outcome states, paused deadlines, and polling-driven comparison refresh. The approval card and dialog render the persisted tool version, authoritative action target and adapter binding, operation key, payload hash, authorization and policy references, evidence references, source-result versions, exact arguments, and action fingerprint rather than claiming fields that are hidden.

These checks preserve the newer workflow builder, context menus, dark theme, responsive layout rules, and Goal Agent inspector bridge. They are not a substitute for a live browser, keyboard, screen-reader, drag-and-drop, or computed-style audit.

Both regenerated preview captures passed the Node VM UI contract. Each run rendered **28 routes, 72 workflow runs, 7 inspectors, 2 mapping dialogs, 18 evidence dialogs, 1 effects dialog, and 18 repair dialogs**. The regenerated preview data contains **13 Agent Factory scenarios and 13 corresponding factory runs**, including **7 controlled variation cases** beyond the six primary paired demonstrations. Node syntax checks passed for `public/app.js`, `public/icons.js`, and `public/theme.js`. Python `compileall` and repository JSON validation also passed.

The complete Axiom 1.9 merged Python discovery gate passed **235/235 tests in 29.065 seconds**. This total includes the 65 focused Axiom 1.9 host tests above; it is separate from the historical 113-test source checkpoint and is not the Axiom 2.0 total.

## Reproduce

From the current repository's `app` directory, the merge gate is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest -v tests.test_agent_factory tests.test_factory_fixtures tests.test_factory_migration tests.test_factory_runtime tests.test_factory_http
python3 -m unittest -v tests.test_integrations tests.test_agent_factory
python3 -W error::ResourceWarning -m unittest discover -s tests -v
node --check public/app.js
node --check public/icons.js
node --check public/theme.js
node tests/test_ui_contract.js ../preview/preview_data.json
node tests/test_ui_contract.js ../output_v2/preview_data.json
```

The focused command, syntax checks, and interface contracts are narrower than
the complete repository and browser gates. The recorded release also passed
Python `compileall` and JSON validation.

HTTP tests use isolated temporary databases and actual loopback servers. They do not modify an existing application database. The model transport tests send requests only to their controlled loopback handlers and do not use an external provider.

## Review findings corrected in the source checkpoint

Implementation owners corrected metadata/compiler mismatches, dotted capability identifiers, provider construction and fixture labeling, executable-action resource revalidation, approval deadline enforcement, stale parent approval binding, frozen compilation reuse, attributable provider observations, and simulation capture wording. The merged frontend distinguishes configured-model availability from scripted fixtures; enforces draft versus reviewer-activated lifecycle; identifies exact persisted target, adapter, operation, payload, policy, evidence and source-version fields; and separates kernel completion checks from trusted business-outcome validation.

## Limits of these results

No live LLM was called. These tests do not establish that a model will choose the best business action, reliably resist every prompt injection, or achieve a real-world goal. The bundled fixture domains now have trusted validators that compare recorded observations and fail closed. For a custom or live domain without such a validator, output-schema and evidence checks still do **not** certify business-outcome correctness.

No external Slack, Jira, Confluence, finance, directory, email, webhook receiver, MCP server, or arbitrary API tenant was used. Axiom 2.0 includes bounded outbound adapter code, but controlled transport tests do not establish provider authority or delivery. Local idempotency proves one local database effect; it does not establish exactly-once execution across a remote service boundary. Live adapters still need tenant identity, resource authorization, freshness checks, destination-specific reconciliation, sandbox integration tests, and production secret/OAuth lifecycle management.

Current headed-browser evidence is recorded separately in `research/QA_NOTES.md`. It covers custom specification activation and workflow placement, observation-dependent and clarification paths, the persisted exact-action approval/receipt, provider-unavailable controls, theme persistence, context menus, and responsive Save access. Syntax, VM, and this focused browser journey still do not establish screen-reader behavior, broad cross-browser behavior, or accessibility conformance.

The application remains a single-process local reference with development account switching. These results do not establish production SSO, tenant isolation, distributed-worker correctness or enterprise readiness.
