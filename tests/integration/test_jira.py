"""Integration tests for jira.py."""
import asyncio
import hashlib
import hmac
import json
from http import HTTPStatus

import aiohttp

# pylint: disable-next=import-error
import pytest

from extensions.eda.plugins.event_source.jira import main as jira_source

args = {
    "host": "127.0.0.1",
    "port": 18765,
    "path": "/webhook",
    "secret": "webhook-secret",
}
url = f'http://{args["host"]}:{args["port"]}{args["path"]}'
payload = json.dumps({
    "webhookEvent": "jira:issue_created",
    "issue": {"key": "OPS-1", "fields": {"summary": "Test issue"}},
})
body = payload.encode("utf-8")
signature = "sha256=" + hmac.new(
    args["secret"].encode("utf-8"),
    msg=body,
    digestmod=hashlib.sha256,
).hexdigest()
headers = {"X-Hub-Signature": signature, "Content-Type": "application/json"}


async def run_webhook() -> None:
    """Start webhook."""
    await jira_source(asyncio.Queue(), args)


async def wait_for_server() -> None:
    """Wait until the webhook server accepts connections."""
    for _ in range(50):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{args["host"]}:{args["port"]}/webhook',
                    data=b"{}",
                ):
                    return
        except aiohttp.ClientConnectorError:
            await asyncio.sleep(0.05)
    raise RuntimeError("Webhook server did not start in time")


@pytest.mark.asyncio
async def test_with_incorrect_path():
    """Posting to an incorrect path should return HTTP 404."""
    async def do_request():
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                f'http://{args["host"]}:{args["port"]}/something',
                data=body,
            ) as resp:
                plugin_task.cancel()
                assert resp.status == HTTPStatus.NOT_FOUND

    plugin_task = asyncio.create_task(run_webhook())
    await wait_for_server()
    request_task = asyncio.create_task(do_request())
    await asyncio.gather(plugin_task, request_task)


@pytest.mark.asyncio
async def test_event_body_valid_json():
    """Posting valid JSON with a valid signature should return HTTP 200."""
    async def do_request():
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, data=body) as resp:
                plugin_task.cancel()
                text = await resp.text()
                assert resp.status == HTTPStatus.OK
                assert text == "{}"

    plugin_task = asyncio.create_task(run_webhook())
    await wait_for_server()
    request_task = asyncio.create_task(do_request())
    await asyncio.gather(plugin_task, request_task)


@pytest.mark.asyncio
async def test_event_body_with_invalid_json():
    """Posting invalid JSON should return HTTP 400."""
    invalid_body = b"this is no valid json"
    invalid_signature = "sha256=" + hmac.new(
        args["secret"].encode("utf-8"),
        msg=invalid_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    async def do_request():
        async with aiohttp.ClientSession(
            headers={"X-Hub-Signature": invalid_signature},
        ) as session:
            async with session.post(url, data=invalid_body) as resp:
                plugin_task.cancel()
                assert resp.status == HTTPStatus.BAD_REQUEST
                assert resp.reason == "Invalid JSON payload"

    plugin_task = asyncio.create_task(run_webhook())
    await wait_for_server()
    request_task = asyncio.create_task(do_request())
    await asyncio.gather(plugin_task, request_task)


@pytest.mark.asyncio
async def test_without_signature_header():
    """Posting without a signature should return HTTP 401."""
    async def do_request():
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body) as resp:
                plugin_task.cancel()
                assert resp.status == HTTPStatus.UNAUTHORIZED
                assert resp.reason == "X-Hub-Signature header is missing"

    plugin_task = asyncio.create_task(run_webhook())
    await wait_for_server()
    request_task = asyncio.create_task(do_request())
    await asyncio.gather(plugin_task, request_task)
