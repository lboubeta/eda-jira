
"""Jira Event Source Plugin for Ansible EDA (redhat_iberia.eda.jira).

This plugin listens for incoming HTTP webhook events from Jira Cloud
or Jira Data Center.
"""
import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from typing import Any

# pylint: disable-next=import-error
from aiohttp import web

DOCUMENTATION = r"""
---
name: jira.py
description:
  - Event source plugin for receiving webhook events from Jira.
    The payload must be a valid JSON object as sent by Jira webhooks.
options:
  host:
    description:
      - The hostname to listen to.
    default: "0.0.0.0"
  port:
    description:
      - The TCP port to listen to.
    required: true
  path:
    description:
      - The HTTP path to accept webhook POST requests on.
    default: "/webhook"
  token:
    description:
      - Optional Bearer authentication token for OAuth 2.0 app webhooks.
  secret:
    description:
      - Optional shared secret for HMAC verification of admin webhooks.
        Jira sends the signature in the X-Hub-Signature header.
"""

EXAMPLES = r"""
- name: Watch for Jira webhook events
  hosts: localhost
  sources:
    - redhat_iberia.eda.jira:
        host: 0.0.0.0
        port: 5000
        path: /webhook
        secret: "{{ jira_webhook_secret }}"

  rules:
    - name: High priority bug created
      condition: >
        event.payload.webhookEvent == "jira:issue_created" and
        event.payload.issue.fields.priority.name == "High"
      action:
        run_job_template:
          name: "Triage high priority bug"
          organization: "Default"
"""

logger = logging.getLogger(__name__)
routes = web.RouteTableDef()


def _initialize_logger_config() -> None:
    logging.basicConfig(
        format="[%(asctime)s] - %(pathname)s: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %I:%M:%S",
    )


def _verify_hmac_signature(body: bytes, secret: str, signature_header: str) -> None:
    """Verify the Jira X-Hub-Signature HMAC header.

    Parameters
    ----------
    body : bytes
        Raw request body.
    secret : str
        Shared webhook secret configured in Jira.
    signature_header : str
        Value of the X-Hub-Signature header.

    Raises
    ------
    HTTPUnauthorized
        If the signature is missing or invalid.

    """
    if not signature_header:
        msg = "X-Hub-Signature header is missing"
        logger.error(msg)
        raise web.HTTPUnauthorized(reason=msg) from None

    hash_object = hmac.new(
        secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    )
    calculated_signature = f"sha256={hash_object.hexdigest()}"

    if not hmac.compare_digest(calculated_signature, signature_header):
        msg = "Invalid webhook signature"
        logger.error(msg)
        raise web.HTTPUnauthorized(reason=msg) from None


def _parse_auth_header(scheme: str, token: str, configured_token: str) -> None:
    """Check authorization type and token.

    Parameters
    ----------
    scheme : str
        Authorization schema from request header.
    token : str
        Token string retrieved from request header.
    configured_token : str
        Token string retrieved from args.

    Raises
    ------
    HTTPUnauthorized
        If the authorization type is not allowed or token is invalid.

    """
    if scheme != "Bearer":
        msg = f"Authorization type {scheme} is not allowed"
        logger.error(msg)
        raise web.HTTPUnauthorized(reason=msg) from None
    if token != configured_token:
        msg = "Invalid authorization token"
        logger.error(msg)
        raise web.HTTPUnauthorized(reason=msg) from None


@web.middleware
async def check_auth(request: web.Request, handler: Callable) -> web.StreamResponse:
    """Check Bearer authorization header.

    Parameters
    ----------
    request : web.Request
        Received request.
    handler : Callable
        Request handler.

    Returns
    -------
    web.StreamResponse
        Response from the request handler.

    Raises
    ------
    HTTPUnauthorized
        If the authorization header is missing or invalid.

    """
    try:
        scheme, token = request.headers["Authorization"].strip().split(" ", 1)
        _parse_auth_header(scheme, token, request.app["token"])
    except KeyError:
        msg = "Authorization header is missing or not correct"
        logger.exception(msg)
        raise web.HTTPUnauthorized(reason=msg) from None
    except ValueError:
        msg = "Invalid authorization header"
        logger.exception(msg)
        raise web.HTTPUnauthorized(reason=msg) from None
    return await handler(request)


def _set_app_attributes(args: dict[str, Any]) -> dict[str, Any]:
    if "host" not in args:
        msg = "Host is missing as an argument"
        logger.error(msg)
        raise ValueError(msg)

    if "port" not in args:
        msg = "Port is missing as an argument"
        logger.error(msg)
        raise ValueError(msg)

    return {
        "host": args.get("host"),
        "port": args.get("port"),
        "path": args.get("path", "/webhook"),
        "token": args.get("token"),
        "secret": args.get("secret"),
    }


def _create_event_handler(app: web.Application) -> Callable:
    async def handle_event(request: web.Request) -> web.Response:
        """Handle received Jira webhook event and put it on the queue.

        Parameters
        ----------
        request : web.Request
            Received request.

        Returns
        -------
        web.Response
            Empty JSON response.

        Raises
        ------
        HTTPBadRequest
            If the payload cannot be parsed as JSON.

        """
        logger.info("Received Jira webhook event")
        body = await request.read()

        if app.get("secret"):
            _verify_hmac_signature(
                body,
                app["secret"],
                request.headers.get("X-Hub-Signature", ""),
            )

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.exception("Failed to parse JSON payload")
            raise web.HTTPBadRequest(reason="Invalid JSON payload") from None

        headers = dict(request.headers)
        headers.pop("Authorization", None)
        data = {
            "payload": payload,
            "meta": {"headers": headers},
        }
        logger.info("Put Jira event on queue")
        await app["queue"].put(data)
        return web.json_response({})

    return handle_event


async def main(queue: asyncio.Queue, args: dict[str, Any]) -> None:
    """Entrypoint from ansible-rulebook cli.

    Parameters
    ----------
    queue : asyncio.Queue
        Event queue.
    args : dict[str, Any]
        Plugin configuration arguments.

    """
    _initialize_logger_config()
    logger.info("Starting jira webhook source...")

    app_attrs = _set_app_attributes(args)
    middlewares = []
    if app_attrs.get("token"):
        middlewares.append(check_auth)

    if not app_attrs.get("token") and not app_attrs.get("secret"):
        logger.warning(
            "Neither token nor secret configured; webhook endpoint is unsecured",
        )

    app = web.Application(middlewares=middlewares)
    app["queue"] = queue
    if app_attrs.get("token"):
        app["token"] = app_attrs["token"]
    if app_attrs.get("secret"):
        app["secret"] = app_attrs["secret"]

    handler = _create_event_handler(app)
    app.router.add_post(app_attrs["path"], handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        app_attrs["host"],
        app_attrs["port"],
    )
    await site.start()
    logger.info(
        "jira source is running on %s:%s%s",
        app_attrs["host"],
        app_attrs["port"],
        app_attrs["path"],
    )

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("jira source plugin stopped")
    finally:
        await runner.cleanup()
