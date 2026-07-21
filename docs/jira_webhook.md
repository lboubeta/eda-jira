# Event-source plugin jira_webhook

The `jira_webhook` event-source plugin receives webhook events from Jira Cloud or Jira Data Center. Admin webhooks can be secured with an HMAC shared secret (`X-Hub-Signature` header). OAuth 2.0 app webhooks can be secured with Bearer token authentication.

## Run tox locally to check linting

```bash
pip install tox
tox
```

## Run unit/integration tests

Install test dependencies:

```bash
pip install -r test_requirements.txt
```

Run unit tests:

```bash
pytest tests/unit/
```

Run integration tests:

```bash
pytest tests/integration/
```

## Test jira_webhook locally with ansible-rulebook

### Python requirements

- Python >= 3.9
- pip
- ansible-core
- ansible-rulebook

```bash
pip install ansible ansible-runner ansible-rulebook
```

### Local test steps

1. Create `rulebooks/vars.yml`:

```yaml
jira_webhook_secret: <your-test-secret>
```

2. Start the rulebook:

```bash
ansible-rulebook \
  --rulebook rulebooks/jira_webhook_event_example_rule.yml \
  -e rulebooks/vars.yml \
  -i inventory.yml \
  -S extensions/eda/plugins/event_source/
```

3. Send a test webhook:

```bash
BODY='{"webhookEvent":"jira:issue_created","issue":{"key":"OPS-1","fields":{"priority":{"name":"High"}}}}'
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "<your-test-secret>" | sed 's/^.* //')
curl -X POST \
  --header "Content-Type: application/json" \
  --header "X-Hub-Signature: sha256=$SIGNATURE" \
  --data "$BODY" \
  http://localhost:6009/webhook
```

## Jira webhook setup

1. In Jira, go to **Settings** > **System** > **Webhooks** (Cloud: **Settings** > **System** > **Advanced** > **Webhooks**).
2. Create a webhook pointing to your EDA endpoint, for example `https://eda.example.com/webhook`.
3. Configure the events you want (for example `jira:issue_created`, `jira:issue_updated`).
4. Optionally add a secret for HMAC signature verification and pass the same value to the `secret` plugin option.
