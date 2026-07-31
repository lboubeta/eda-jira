"""Plugin polls Jira for issues matching a JQL query and sends them to EDA."""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

# pylint: disable-next=import-error
import aiohttp

DOCUMENTATION = r"""
---
name: jira_jql.py
description:
  - Event source plugin that polls Jira for issues matching a JQL query
    and sends matching issues to Ansible EDA rulebooks.
options:
  jira_url:
    description:
      - Base URL of the Jira instance (for example https://example.atlassian.net).
    required: true
  jira_user:
    description:
      - Username or email for Jira API authentication.
  jira_token:
    description:
      - API token or personal access token for Jira API authentication.
    required: true
  jql:
    description:
      - JQL query used to find issues to send as events.
    required: true
  delay:
    description:
      - Delay between polling requests in seconds.
    default: 60
  proxy:
    description:
      - Proxy URL through which to access Jira.
    default: none
  fields:
    description:
      - Comma-separated list of issue fields to return from the search API.
    default: "summary,status,priority,assignee,project,issuetype,updated"
"""

EXAMPLES = r"""
- name: Poll Jira for newly created bugs
  hosts: all
  sources:
    - redhat_iberia.eda.jira_jql:
        jira_url: "https://example.atlassian.net"
        jira_user: "automation@example.com"
        jira_token: "{{ jira_api_token }}"
        jql: 'project = OPS AND issuetype = Bug AND status = "To Do"'
        delay: 60

  rules:
    - name: Auto-assign critical bugs
      condition: event.fields.priority.name == "Highest"
      action:
        run_job_template:
          name: "Assign critical bug"
          organization: "Default"
"""

logger = logging.getLogger(__name__)


def _initialize_logger_config() -> None:
    logging.basicConfig(
        format="[%(asctime)s] - %(pathname)s: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %I:%M:%S",
    )


def _build_auth_headers(jira_user: str | None, jira_token: str) -> dict[str, str]:
    if jira_user:
        credentials = base64.b64encode(
            f"{jira_user}:{jira_token}".encode(),
        ).decode("ascii")
        return {"Authorization": f"Basic {credentials}"}

    return {"Authorization": f"Bearer {jira_token}"}


def _issue_event_key(issue: dict[str, Any]) -> str:
    issue_key = issue.get("key", "")
    updated = issue.get("fields", {}).get("updated", "")
    return f"{issue_key}:{updated}"


async def search_issues(
    jira_url: str,
    headers: dict[str, str],
    jql: str,
    fields: str,
    proxy: str,
) -> list[dict[str, Any]]:
    """Search Jira for issues matching the configured JQL query.

    Parameters
    ----------
    jira_url : str
        Base URL of the Jira instance.
    headers : dict[str, str]
        Authentication headers for the Jira API.
    jql : str
        JQL query used to find issues.
    fields : str
        Comma-separated list of issue fields to return.
    proxy : str
        Optional proxy URL.

    Returns
    -------
    list[dict[str, Any]]
        Matching Jira issues.

    """
    timeout = aiohttp.ClientTimeout(total=30)
    url = f"{jira_url.rstrip('/')}/rest/api/3/search/jql"
    body = {
        "jql": jql,
        "fields": [field.strip() for field in fields.split(",") if field.strip()],
        "maxResults": 50,
    }

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.post(url=url, json=body, proxy=proxy or None) as resp:
            resp.raise_for_status()
            payload = await resp.json()
            return payload.get("issues", [])


async def main(queue: asyncio.Queue, args: dict[str, Any]) -> None:
    """Poll Jira and enqueue matching issues as events.

    Parameters
    ----------
    queue : asyncio.Queue
        Event queue.
    args : dict[str, Any]
        Plugin configuration arguments.

    Raises
    ------
    ValueError
        If required configuration arguments are missing.

    """
    _initialize_logger_config()

    jira_url = args.get("jira_url")
    jira_user = args.get("jira_user")
    jira_token = args.get("jira_token")
    jql = args.get("jql")
    delay = int(args.get("delay", 60))
    proxy = args.get("proxy", "")
    fields = args.get(
        "fields",
        "summary,status,priority,assignee,project,issuetype,updated",
    )

    if not jira_url:
        msg = "jira_url is missing as an argument"
        logger.error(msg)
        raise ValueError(msg)
    if not jira_token:
        msg = "jira_token is missing as an argument"
        logger.error(msg)
        raise ValueError(msg)
    if not jql:
        msg = "jql is missing as an argument"
        logger.error(msg)
        raise ValueError(msg)

    headers = _build_auth_headers(jira_user, jira_token)
    seen_issues: set[str] = set()

    try:
        while True:
            issues = await search_issues(
                jira_url,
                headers,
                jql,
                fields,
                proxy,
            )
            new_events = 0
            for issue in issues:
                event_key = _issue_event_key(issue)
                if event_key in seen_issues:
                    logger.info("Issue %s already sent to EDA", issue.get("key"))
                    continue

                await queue.put(issue)
                seen_issues.add(event_key)
                new_events += 1
                logger.info("Sent issue %s to EDA queue", issue.get("key"))

            logger.info(
                "Poll done: found %d issue(s), sent %d new event(s); "
                "next poll in %ds",
                len(issues),
                new_events,
                delay,
            )
            await asyncio.sleep(delay)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.exception("Jira polling task timed out or was cancelled")
