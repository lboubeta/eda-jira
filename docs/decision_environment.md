# Decision environment for jira.event_driven_ansible

This directory contains Ansible Builder definitions for a custom Event-Driven Ansible decision environment that includes the `jira.event_driven_ansible` collection.

## Prerequisites

- Podman or Docker
- [ansible-builder](https://ansible.readthedocs.io/projects/builder/) 3.x

```bash
pip install ansible-builder
```

For the AAP image (`execution-environment.yml`), you need access to the Red Hat `de-minimal` base image from `registry.redhat.io`.

For the open source image (`execution-environment-oss.yml`), no Red Hat subscription is required.

## Build the image

From the repository root:

```bash
# AAP / de-minimal base image
./decision-environment/build.sh jira-eda-de:latest

# Open source base image (quay.io/ansible/ansible-rulebook)
DEFINITION=decision-environment/execution-environment-oss.yml \
  ./decision-environment/build.sh jira-eda-de-oss:latest
```

Or run ansible-builder directly:

```bash
ansible-builder build \
  -f decision-environment/execution-environment.yml \
  -c . \
  -t jira-eda-de:latest
```

## Use the image in Ansible Automation Platform

1. Push the built image to a container registry accessible by your EDA Controller.
2. In AAP, go to **Automation Decisions** > **Decision Environments**.
3. Create a decision environment pointing to your image tag.
4. Create or update a rulebook activation to use that decision environment.

Example rulebook activation source:

```yaml
sources:
  - jira.event_driven_ansible.jira_webhook:
      host: 0.0.0.0
      port: 5000
      path: /webhook
      secret: '{{ jira_webhook_secret }}'
```

## Test locally with ansible-rulebook

```bash
podman run --rm -it \
  -v "$(pwd)/inventory.yml:/tmp/inventory.yml:Z" \
  -v "$(pwd)/rulebooks:/tmp/rulebooks:Z" \
  jira-eda-de:latest \
  ansible-rulebook \
    --rulebook /tmp/rulebooks/jira_webhook_event_example_rule.yml \
    -i /tmp/inventory.yml \
    -e jira_webhook_secret=test-secret
```

## Files

| File | Purpose |
|------|---------|
| `execution-environment.yml` | AAP definition using `de-minimal-rhel9` |
| `execution-environment-oss.yml` | OSS definition using `quay.io/ansible/ansible-rulebook` |
| `requirements.txt` | Python dependencies (`aiohttp`) |
| `requirements.yml` | Galaxy collection requirements |
| `build.sh` | Helper script to build the image |

## Customizing the base image

Update the `images.base_image.name` value in the definition file for your AAP version, for example:

```yaml
images:
  base_image:
    name: registry.redhat.io/ansible-automation-platform-26/de-minimal-rhel9:latest
```
