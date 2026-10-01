# Axiom Agent Factory

Axiom is a runnable local reference application for building governed business workflows with reusable, adaptive Goal Agents. It combines a visual workflow designer, typed node connections, exact-action approvals, durable agent sessions, behavior rehearsals, evidence tracking, and bounded external-service connections.

This repository contains Axiom 2.2.0 with SQLite schema 13. It is a local development and demonstration system, not a production deployment.

## Run locally

Python 3.10 or newer is required. No mandatory package installation is needed.

```bash
cd app && python3 server.py
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

The server is intended for loopback development use. Do not expose the reference server directly to the public internet.

## Atlas Checkout Simulation Lab

Open **Simulation Lab** for the flagship adaptive-agent demonstration. It creates a stateful, SQLite-persisted local world for the fictional Atlas Checkout service and offers seven controlled evidence profiles: `fresh-incident`, `existing-incident`, `missing-owner`, `confluence-unavailable`, `slack-rate-limit`, `jira-lost-ack`, and `changed-flag-version`.

The world, virtual clock, capability results, prepared actions, approvals, operation ledger, reconciliation, reset generations, and authoritative outcome checks are real local application behavior. Atlas Checkout and the provider-shaped Metrics, Service Catalog, Deployments, Jira, Confluence, Slack, and feature-flag systems are simulated in-process. Their receipts are explicitly marked simulated, and the sandbox enforces **no external network and zero external effects**.

Writes still pause for approval of the exact prepared action. A lost Jira acknowledgement is reconciled by stable operation identity instead of blindly retried. A reset is refused while a bound workflow, agent session, or unresolved effect is active; a successful reset advances the world generation while preserving prior-generation audit history.

See the [complete Simulation Lab guide](docs/SIMULATION_LAB.md) for the guided walkthrough, REST API, profile behavior, and safety boundaries.

## Schedule workflow runs

Open **Schedules** to run an exact published workflow version once, hourly, daily, or weekly. Schedules use IANA time zones, preserve daily and weekly wall-clock time across daylight-saving changes, survive server restarts, and prevent overlapping runs. Administrators can create, edit, pause, resume, run now, and archive schedules; operators can control eligible existing schedules. Every generated run records the schedule and pinned release that started it.

See the [workflow scheduling guide](docs/SCHEDULING.md) for the interface, API, recurrence, recovery, and safety behavior.

## Start here

- [Delivery, startup, verification, and feature status](START_HERE.md)
- [Complete beginner's guide](AXIOM_BEGINNER_GUIDE.md)
- [How Axiom's agentic intelligence works](AXIOM_AGENTIC_INTELLIGENCE_GUIDE.md)
- [Atlas Checkout Simulation Lab](docs/SIMULATION_LAB.md)
- [Workflow scheduling](docs/SCHEDULING.md)
- [Application documentation](app/README.md)
- [External integration guide](docs/EXTERNAL_INTEGRATIONS.md)
- [Agent Factory architecture](factory/Agent_Factory_Paradigm.md)
- [Verification report](factory/Verification.md)

## Important boundaries

- Bundled scripted fixtures demonstrate runtime behavior; they are not AI and do not prove live-model quality.
- The Atlas Checkout sandbox is stateful and realistic by design, but every provider is local and simulated. It neither authenticates to nor changes a live Slack, Jira, Confluence, observability, deployment, or feature-flag system.
- Slack, Jira Cloud, Confluence Cloud, and webhook support requires administrator-supplied credentials and live sandbox validation.
- Corporate authentication, tenant isolation, managed secrets, complete OAuth, distributed workers, provider-specific reconciliation, production monitoring, retention controls, load testing, and failover validation remain production integration work.
- Local runtime databases, browser-automation captures, caches, and environment files are intentionally excluded from version control.

## License

No open-source license file is currently included. Add an appropriate license before offering this repository for public reuse or redistribution.
