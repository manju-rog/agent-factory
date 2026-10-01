# Workflow scheduling

Axiom schedules start the same published workflows that a person can start from the Runs page. A scheduled trigger does not create a second execution engine and does not bypass approvals, manual steps, capability limits, evidence capture, or effect reconciliation.

## What can be scheduled

A schedule uses an already published workflow and one of these patterns:

- **Once** — run at one local date and time, then mark the schedule complete.
- **Hourly** — run at the chosen minute every hour.
- **Daily** — run at the chosen local time every day.
- **Weekly** — run on the chosen weekday and local time every week.

The schedule also stores its task input, fixture scenario, IANA timezone, overlap policy, creator, and next due time. This local reference supports the safe `skip` overlap policy: if the schedule's previous run is still active when another occurrence becomes due, the new occurrence is recorded as skipped instead of creating two competing runs.

## Version safety

Creating or editing a schedule pins the workflow's exact published version and release hash. Publishing a newer workflow version does not silently change an existing schedule. To adopt a new version, edit the schedule and review the newly pinned version.

Each generated run records a schedule trigger containing the schedule ID, schedule name, definition generation, pinned release, and intended occurrence time. A material edit advances the definition generation. Stable identities bind that generation and exact occurrence, so an edited schedule cannot collide with a run created by an older definition.

## Timezones and restarts

The form stores a local wall-clock start plus an IANA timezone such as `Asia/Kolkata`, `Europe/London`, or `America/New_York`. The server calculates the next UTC occurrence from those values. Daily and weekly schedules remain tied to the selected local wall time when daylight-saving rules change.

Schedules live in SQLite and are evaluated by the durable local worker. Closing a browser tab has no effect. If the application was stopped while occurrences became due, it starts at most one coalesced run when it returns, advances to the next future occurrence, and records how many intervening occurrences were missed.

This is a single-process reference scheduler. Distributed leases, high availability, managed clock monitoring, and multi-region failover remain deployment responsibilities.

## Using the interface

1. Open **Schedules**, or choose **Schedule** from Workflow Studio or Runs.
2. Give the schedule a clear name and choose a published workflow.
3. Choose Once, Hourly, Daily, or Weekly.
4. Enter the local start time and confirm the timezone.
5. Review the workflow input JSON and create the schedule.
6. Use **Pause** to stop future triggers without losing history, **Resume** to calculate the next safe occurrence, **Run now** for an additional manual occurrence, or **Archive** to retire the schedule permanently.

If a workflow input contains a field whose name indicates a credential or secret, the API masks that value. An update must explicitly choose `inputMode: "preserve"` and omit `input`, or choose `inputMode: "replace"` and provide the complete replacement object. The editor uses preserve mode, keeps the protected input on the server, and never sends the mask back as data. The hidden input remains bound to its existing workflow; create a replacement schedule when both the workflow and protected input must change.

The Runs page remains the source of truth for execution. Open a generated run there to review its pinned graph, decisions, approvals, events, evidence, and effects.

## HTTP surface

The local API exposes:

- `GET /api/schedules`
- `POST /api/schedules`
- `GET /api/schedules/:id`
- `PUT /api/schedules/:id`
- `DELETE /api/schedules/:id`
- `POST /api/schedules/:id/pause`
- `POST /api/schedules/:id/resume`
- `POST /api/schedules/:id/run`

Create and update requests use a shape like:

```json
{
  "name": "Daily customer-resolution review",
  "templateId": "customer-resolution",
  "frequency": "daily",
  "localStart": "2026-10-02T09:30",
  "timezone": "Asia/Kolkata",
  "scenario": "happy",
  "input": {
    "requestId": "REQ-SCHEDULED-1",
    "customerId": "CUS-1042",
    "subject": "Review queued service requests",
    "amount": 12500
  },
  "overlapPolicy": "skip"
}
```

Updates, archive, pause, resume, and new run-now requests also send `expectedRevision` so stale controls cannot overwrite a newer change. Run-now additionally requires a client `idempotencyKey`. The browser keeps an unresolved key and its original revision in session storage across rerenders and reloads. Retrying the exact actor/key/request after a lost response returns the original run even though that committed request advanced the revision; changing the bound request or actor fails closed. A structured server rejection clears the pending browser request because the transaction did not commit. Mutation routes are protected by the same localhost session, CSRF, and role checks as other Axiom operations.
