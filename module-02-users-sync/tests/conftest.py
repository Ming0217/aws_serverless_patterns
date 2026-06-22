"""Shared pytest fixtures for the M2 Users Service tests.

The handlers are plain files (no package), and each binds its boto3 resource /
fetches JWKS at IMPORT time. So the fixtures here set the environment + mocks
FIRST, then load the module fresh by file path — guaranteeing the module-level
setup runs against the mock, not real AWS / the network.
"""

import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

MODULE_DIR = Path(__file__).resolve().parents[1]
USERS_PATH = MODULE_DIR / "src" / "api" / "users.py"
AUTHORIZER_PATH = MODULE_DIR / "src" / "authorizer" / "authorizer.py"

TABLE_NAME = "users-test"


def _load(path, name):
    """Import a standalone .py file as a module by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def users(monkeypatch):
    """The users handler bound to a fresh, empty, mocked DynamoDB table."""
    # Dummy AWS env so boto3/moto never reach real AWS.
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("USERS_TABLE", TABLE_NAME)

    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "userid", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "userid", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # Import AFTER the mock + table exist so module-level `table` binds to it.
        yield _load(USERS_PATH, "users_under_test")


@pytest.fixture
def authorizer(monkeypatch):
    """The authorizer handler with env set and the JWKS fetch stubbed out."""
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_test")
    monkeypatch.setenv("APP_CLIENT_ID", "testclient")
    monkeypatch.setenv("ADMIN_GROUP_NAME", "apiAdmins")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    fake_jwks = json.dumps({"keys": [{"kid": "k1"}]}).encode()

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return fake_jwks

    # Stub the module-level JWKS HTTP fetch so import needs no network.
    monkeypatch.setattr("urllib.request.urlopen", lambda url: _FakeResp())
    return _load(AUTHORIZER_PATH, "authorizer_under_test")


def api_event(method, resource, path_params=None, body=None, is_admin=False):
    """Build a minimal API Gateway proxy event with authorizer context."""
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": path_params,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {"isAdmin": "true" if is_admin else "false"}
        },
    }


@pytest.fixture
def event():
    """Factory fixture returning api_event(...) — avoids importing conftest."""
    return api_event
