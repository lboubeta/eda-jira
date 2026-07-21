# Jira + Red Hat Event Driven Ansible

This collection contains Event-Driven Ansible source plugins for Jira:

- `jira_webhook` — receive webhook events from Jira Cloud or Jira Data Center
- `jira_jql` — poll Jira for issues matching a JQL query

## Webhook events (`jira_webhook`)

The `jira_webhook` plugin listens for HTTP POST requests from Jira webhooks and forwards the JSON payload to your rulebook.

### Requirements

- Jira Cloud or Jira Data Center with webhooks configured
- Ansible Automation Platform with an EDA Controller instance (or local `ansible-rulebook` for testing)
- A publicly reachable HTTPS endpoint, or use AAP Event Streams for managed webhook delivery

### Authentication

- **Admin webhooks**: configure a shared `secret` in Jira and pass the same value to the plugin. Jira signs payloads with HMAC-SHA256 in the `X-Hub-Signature` header.
- **OAuth 2.0 app webhooks**: configure a `token` and verify incoming `Authorization: Bearer` headers.

### Example rulebook

```yaml
---
- name: Listen for Jira webhook events
  hosts: all
  sources:
    - jira.event_driven_ansible.jira_webhook:
        host: 0.0.0.0
        port: 5000
        path: /webhook
        secret: '{{ jira_webhook_secret }}'

  rules:
    - name: High priority issue created
      condition: >
        event.payload.webhookEvent == "jira:issue_created" and
        event.payload.issue.fields.priority.name == "High"
      action:
        run_job_template:
          name: "Triage high priority issue"
          organization: "Default"
```

## JQL polling (`jira_jql`)

The `jira_jql` plugin polls Jira on a configurable interval and sends matching issues to your rulebook. This is useful when webhooks are not available or when you need to backfill events.

### Requirements

- Jira Cloud or Jira Data Center
- Jira API token with permission to run the configured JQL query
- Ansible Automation Platform with an EDA Controller instance

### Example rulebook

```yaml
---
- name: Poll Jira for open bugs
  hosts: all
  sources:
    - jira.event_driven_ansible.jira_jql:
        jira_url: "https://example.atlassian.net"
        jira_user: "automation@example.com"
        jira_token: '{{ jira_api_token }}'
        jql: 'project = OPS AND issuetype = Bug AND status = "To Do"'
        delay: 60

  rules:
    - name: Auto-assign highest priority bugs
      condition: event.fields.priority.name == "Highest"
      action:
        run_job_template:
          name: "Assign critical bug"
          organization: "Default"
```

## Decision environment

Install this collection in a custom decision environment on the EDA Controller. For webhook-based integrations, you can also use AAP Event Streams with the built-in `eda.builtin.webhook` source if you prefer managed webhook infrastructure.

See the [Event-Driven Ansible decision environments guide](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.5/html/using_automation_decisions/eda-decision-environments) for setup details.

## Local testing

See [docs/jira_webhook.md](docs/jira_webhook.md) for local `ansible-rulebook` testing instructions.

## Licensing

Licensed under the Apache License 2.0.
