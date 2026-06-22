"""Integration tests against the DEPLOYED API.

These run only when both env vars are set, so normal `pytest` (unit) runs skip
them:

    API_BASE_URL  e.g. https://<id>.execute-api.us-east-1.amazonaws.com/Prod
    ID_TOKEN      a valid Cognito ID token (from initiate-auth)

Run:
    API_BASE_URL=... ID_TOKEN=... uv run pytest -m integration
"""

import os
import uuid

import pytest
import requests

API = os.environ.get("API_BASE_URL")
TOKEN = os.environ.get("ID_TOKEN")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (API and TOKEN),
        reason="set API_BASE_URL and ID_TOKEN to run integration tests",
    ),
]

AUTH = {"Authorization": TOKEN} if TOKEN else {}


def test_missing_token_is_401():
    assert requests.get(f"{API}/users", timeout=10).status_code == 401


def test_list_with_token_is_200():
    r = requests.get(f"{API}/users", headers=AUTH, timeout=10)
    assert r.status_code == 200
    assert "users" in r.json()


def test_create_then_get_roundtrip():
    uid = f"it-{uuid.uuid4()}"
    create = requests.post(
        f"{API}/users", headers=AUTH,
        json={"userid": uid, "name": "Integration Test"}, timeout=10,
    )
    assert create.status_code == 201

    got = requests.get(f"{API}/users/{uid}", headers=AUTH, timeout=10)
    assert got.status_code == 200
    assert got.json()["name"] == "Integration Test"
