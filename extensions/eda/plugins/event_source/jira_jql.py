"""Plugin polls Jira for issues matching a JQL query and sends them to EDA."""
from __future__ import annotations

import asyncio
import base64
import json
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
  - Matches every issue/request type returned by the JQL (bugs, stories,
    service requests, and so on). Do not filter by issuetype in JQL unless
    you intentionally want a subset.
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
      - JQL query used to find issues to send as events. Omit issuetype
        filters to include every request type (including JSM service requests).
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
        The enhanced search endpoint returns only ids by default; always
        request the fields your rules need.
    default: "summary,status,priority,assignee,project,issuetype,updated,created"
"""

EXAMPLES = r"""
- name: Poll Jira for every issue/request in a project
  hosts: all
  sources:
    - redhat_iberia.eda.jira_jql:
        jira_url: "https://example.atlassian.net"
        jira_user: "automation@example.com"
        jira_token: "{{ jira_api_token }}"
        jql: 'project = OPS ORDER BY updated DESC'
        delay: 60

  rules:
    - name: Log every matching issue
      condition: true
      action:
        debug:
          msg: "Jira {{ event.key }} ({{ event.fields.issuetype.name }}): {{ event.fields.summary }}"
"""

logger = logging.getLogger(__name__)

DEFAULT_FIELDS = (
    "summary,status,priority,assignee,project,issuetype,updated,created"
)


def _initialize_logger_config() -> None:
    logging.basicConfig(
        format="[%(asctime)s] - %(pathname)s: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %I:%M:%S",
    )


def _build_auth_headers(jira_user: str | None, jira_token: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if jira_user:
        credentials = base64.b64encode(
            f"{jira_user}:{jira_token}".encode(),
        ).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"
        return headers

    headers["Authorization"] = f"Bearer {jira_token}"
    return headers


def _issue_event_key(issue: dict[str, Any]) -> str:
    issue_key = issue.get("key", "")
    fields = issue.get("fields") or {}
    updated = fields.get("updated", "")
    return f"{issue_key}:{updated}"


def _normalize_issue_event(issue: dict[str, Any]) -> dict[str, Any]:
    """Expose key and fields at the top level for rulebook conditions."""
    fields = issue.get("fields") or {}
    return {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "self": issue.get("self"),
        "fields": fields,
        "issue": issue,
    }


async def search_issues(
    jira_url: str,
    headers: dict[str, str],
    jql: str,
    fields: str,
    proxy: str,
) -> list[dict[str, Any]]:
    """Search Jira for issues matching the configured JQL query.

    Uses the enhanced JQL search GET API, which matches the curl form that
    returns issues reliably on Jira Cloud (including JSM service requests).

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
    field_list = [field.strip() for field in fields.split(",") if field.strip()]
    # Always ask for key so rulebooks can match even if other fields are sparse.
    if "key" not in field_list:
        field_list.insert(0, "key")

    params: dict[str, Any] = {
        "jql": jql,
        "maxResults": 50,
        "fields": ",".join(field_list),
    }

    logger.info("Jira search GET %s jql=%r fields=%s", url, jql, params["fields"])

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url=url, params=params, proxy=proxy or None) as resp:
            body_text = await resp.text()
            if resp.status >= 400:
                logger.error(
                    "Jira search failed: HTTP %s — %s",
                    resp.status,
                    body_text[:500],
                )
                resp.raise_for_status()

            try:
                payload = json.loads(body_text)
            except json.JSONDecodeError:
                logger.exception(
                    "Jira search returned non-JSON body: %s",
                    body_text[:500],
                )
                raise

            issues = payload.get("issues") or []
            if not issues:
                logger.warning(
                    "Jira search returned 0 issues (HTTP %s, isLast=%s, "
                    "response keys=%s). Check JQL, token permissions, and that "
                    "the query is not filtered to a missing issuetype.",
                    resp.status,
                    payload.get("isLast"),
                    sorted(payload.keys()),
                )
            else:
                keys = [issue.get("key") for issue in issues]
                logger.info("Jira search returned %d issue(s): %s", len(issues), keys)

            return issues


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
    fields = args.get("fields", DEFAULT_FIELDS)

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

    logger.info(
        "Starting jira_jql poller url=%s user=%s delay=%ss jql=%r",
        jira_url,
        jira_user or "(bearer)",
        delay,
        jql,
    )

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

                event = _normalize_issue_event(issue)
                await queue.put(event)
                seen_issues.add(event_key)
                new_events += 1
                fields_data = event.get("fields") or {}
                issue_type = (fields_data.get("issuetype") or {}).get("name", "?")
                summary = fields_data.get("summary", "")
                logger.info(
                    "Sent issue %s type=%s summary=%r to EDA queue",
                    event.get("key"),
                    issue_type,
                    summary,
                )

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
