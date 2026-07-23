"""Unit tests for jira.py."""
# pylint: disable-next=import-error
import hashlib
import hmac

import pytest
from aiohttp import web

from extensions.eda.plugins.event_source.jira import (
    _parse_auth_header,
    _set_app_attributes,
    _verify_hmac_signature,
)

args = {
    "host": "127.0.0.1",
    "port": 1234,
    "token": "thisisnotanactualtoken",
    "secret": "webhook-secret",
}


def test_parse_token_with_incorrect_token():
    with pytest.raises(web.HTTPUnauthorized, match="Invalid authorization token"):
        _parse_auth_header("Bearer", "thisisnotanactualtoken!", args["token"])


def test_parse_token_invalid_auth_type():
    with pytest.raises(web.HTTPUnauthorized, match="Authorization type Token is not allowed"):
        _parse_auth_header("Token", "thisisnotanactualtoken!", args["token"])


def test_set_app_attributes():
    app_attrs = _set_app_attributes(args)
    assert app_attrs["host"] == "127.0.0.1"
    assert app_attrs["port"] == 1234
    assert app_attrs["token"] == "thisisnotanactualtoken"
    assert app_attrs["secret"] == "webhook-secret"
    assert app_attrs["path"] == "/webhook"


def test_set_app_attributes_without_port():
    with pytest.raises(ValueError, match="Port is missing as an argument"):
        _set_app_attributes({
            "host": "127.0.0.1",
            "token": "thisisnotanactualtoken",
        })


def test_set_app_attributes_without_host():
    with pytest.raises(ValueError, match="Host is missing as an argument"):
        _set_app_attributes({
            "port": "1234",
            "token": "thisisnotanactualtoken",
        })


def test_verify_hmac_signature_valid():
    body = b'{"webhookEvent":"jira:issue_created"}'
    signature = "sha256=" + hmac.new(
        args["secret"].encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    _verify_hmac_signature(body, args["secret"], signature)


def test_verify_hmac_signature_invalid():
    body = b'{"webhookEvent":"jira:issue_created"}'
    with pytest.raises(web.HTTPUnauthorized, match="Invalid webhook signature"):
        _verify_hmac_signature(body, args["secret"], "sha256=invalid")
