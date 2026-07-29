# Part 3 — Multi-Agent Flow in Langflow

A three-agent customer support system built in Langflow. The system performs
dynamic routing: not every agent runs for every message, and not every tool is
triggered for every request.

Built and tested on Langflow 1.11.0.

---

## Contents

| File | Description |
|---|---|
| `flow_export.json` | Complete flow export, importable into any Langflow instance |
| `http_post_run.json` | Unedited response from running the flow over HTTP POST |
| `Jeen_part3_langflow_demo.mov` | Demo video: flow walkthrough, conversation, trace, HTTP POST run |

---

## Architecture

```
Chat Input
    │
    ▼
ORCHESTRATOR AGENT ──────────────────► Chat Output
    │  tools: [Analysis Agent, Response Agent]
    │
    ├──────────────┐
    ▼              ▼
ANALYSIS       RESPONSE
 AGENT          AGENT
    │              │
    ▼              ▼
SQL Database   Gmail Send Email
   (tool)          (custom tool)
```

The Analysis Agent and the Response Agent are exposed to the Orchestrator **as
tools**, using Langflow's Tool Mode. This is the design decision that makes the
system genuinely multi-agent rather than a fixed pipeline: the Orchestrator reads
each message and decides which sub-agents to invoke, or none at all.

---

## Agent roles

### Orchestrator Agent

Receives every incoming message. Classifies intent, then activates only the
components that intent requires. It never answers data questions itself, because
it has no access to ticket data.

Every reply opens with a routing line, so the decision is visible in the
Playground, in the trace, and in the HTTP response:

```
ROUTE: <intent> | AGENTS: <names, or "none"> | REASON: <short justification>
```

### Analysis Agent

Retrieves and interprets support ticket data through the SQL Database tool. It
does not speak to the end user; its output is an internal brief consumed by the
Response Agent.

Constrained to `SELECT` statements only. Every brief reports classification,
query executed, findings, missing information, urgency and a recommended action.
When a query returns nothing it states `NO MATCHING RECORDS` explicitly rather
than widening the query or inventing a plausible record.

### Response Agent

Composes the user-facing reply and performs outbound actions through the Gmail
tool. Every factual claim must come from the analysis brief. Where the brief
reports no records or a database error, the reply says so plainly rather than
filling the gap.

---

## Tools

### SQL Database

Langflow's built-in SQL Database component, connected to a PostgreSQL instance
holding the `support_requests` table specified in the assignment.

Connected to the Analysis Agent only. The Response Agent has no database access.

### Gmail Send Email — custom component

A custom Langflow component that sends email over SMTP. The assignment permits
custom tools, and this route was chosen after the bundled Gmail component proved
to depend on a third-party integration service.

The component returns structured data describing the outcome rather than raising
on failure:

```json
{"status": "sent",   "to": "...", "subject": "...", "sent": true}
{"status": "failed", "error": "...",                "sent": false}
```

This matters for the error-handling requirement: when a send fails, the calling
agent receives a description of the failure and can tell the user that no message
was delivered, instead of the flow crashing or the agent claiming success.

Connected to the Response Agent only.

---

## Dynamic routing

The Orchestrator activates only what each request needs. Demonstrated behaviour:

| Message | Agents invoked | Tools fired |
|---|---|---|
| `hi` | none | none |
| `how many open tickets do we have?` | Analysis, Response | SQL |
| `send an email to <address> summarizing all open tickets` | Analysis, Response | SQL, Gmail |
| `what is the status of the ticket for Rachel Green?` | Analysis, Response | SQL |
| `can you check on that thing for me?` | none | none |
| `what is the weather in Tel Aviv?` | none | none |

A greeting never touches the database. An ambiguous request produces one
clarifying question and no tool calls. An out-of-scope request produces a fixed
response and a handoff.

---

## Error handling

| Case | Behaviour |
|---|---|
| Data not found in the database | Analysis Agent reports `NO MATCHING RECORDS`; the reply states no ticket was found and suggests what to check. No record is invented |
| Unclear request | Routed as unclear. One specific clarifying question, no agents and no tools |
| Out of scope | Fixed response and handoff. No tools |
| Missing information | Named explicitly in the analysis brief and surfaced to the user |
| Email sending failure | The custom tool returns `status: failed` with the underlying error. The agent reports that no message was delivered and never claims success |
| Tool or database error | Reported plainly. The agent does not answer from guesswork |

---

## Credentials

No API keys, connection strings or passwords appear anywhere in the flow. All
credentials are stored as Langflow **Global Variables** and referenced by name:

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini model access for all three agents |
| `POSTGRES_URL_DB` | PostgreSQL connection string for the SQL tool |
| `GMAIL_ADDRESS` | Sender address for the Gmail tool |
| `GMAIL_APP_PASSWORD` | Google App Password for SMTP authentication |

`flow_export.json` contains these variable **names** and none of their values.
Anyone importing the flow supplies their own.

---

## Running the flow

### Import

Langflow → **New Flow** → **Import** → select `flow_export.json`.

Then create the four Global Variables listed above under **Settings → Global
Variables**, and create the database table:

```sql
CREATE TABLE support_requests (
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(255),
    category VARCHAR(100),
    priority VARCHAR(50),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO support_requests
(customer_name, email, category, priority, status)
VALUES
('John Smith', 'john@example.com', 'Login Issue', 'High', 'Open'),
('Sarah Cohen', 'sarah@example.com', 'Billing', 'Medium', 'In Progress'),
('David Levi', 'david@example.com', 'Technical Support', 'Low', 'Closed'),
('Emma Johnson', 'emma@example.com', 'Account Access', 'High', 'Open'),
('Michael Brown', 'michael@example.com', 'Subscription', 'Medium', 'Open');
```

### Playground

Open the flow and click **Playground**.

### HTTP POST

```bash
curl --request POST \
  --url "http://localhost:7861/api/v1/run/<FLOW_ID>?stream=false" \
  --header 'Content-Type: application/json' \
  --header "x-api-key: <LANGFLOW_API_KEY>" \
  --data '{
    "output_type": "chat",
    "input_type": "chat",
    "input_value": "how many open tickets do we have?"
  }'
```

`http_post_run.json` is the unedited response from this command. It contains the
routing decision, the agent steps with tool input and tool output, and the final
answer.

---

## Notes

**Model.** All three agents run on a Gemini Flash-tier model. Model selection is
set per agent and can be changed after import.

**Agent briefs in the output.** The Analysis Agent's internal brief is visible in
the Playground output before the routing line. This is intentional: it makes the
information flow between agents observable, which is what the trace walkthrough
in the video shows in more structured form.

**Rate limits.** The demo runs on a free-tier Gemini quota. Under throttling,
individual requests can take considerably longer than normal. This affects
latency only, not behaviour.
