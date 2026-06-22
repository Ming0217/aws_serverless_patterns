"""Unit tests for the Users mono-lambda handler (DynamoDB mocked via moto).

Fixtures `users` (the handler bound to a mocked table) and `event` (proxy-event
factory) come from tests/conftest.py and are injected automatically.
"""

import json


def _body(resp):
    return json.loads(resp["body"])


# ---- create ----------------------------------------------------------------
def test_create_generates_id_and_returns_201(users, event):
    resp = users.lambda_handler(
        event("POST", "/users", body={"name": "Ada", "email": "ada@x.com"}), None
    )
    assert resp["statusCode"] == 201
    body = _body(resp)
    assert body["name"] == "Ada"
    assert body["userid"]  # a UUID was generated


def test_create_with_explicit_id(users, event):
    resp = users.lambda_handler(
        event("POST", "/users", body={"userid": "u1", "name": "Ada"}), None
    )
    assert resp["statusCode"] == 201
    assert _body(resp)["userid"] == "u1"


def test_create_duplicate_returns_409(users, event):
    users.lambda_handler(event("POST", "/users", body={"userid": "u1"}), None)
    resp = users.lambda_handler(event("POST", "/users", body={"userid": "u1"}), None)
    assert resp["statusCode"] == 409


def test_invalid_json_body_returns_400(users, event):
    evt = event("POST", "/users")
    evt["body"] = "{not json"
    resp = users.lambda_handler(evt, None)
    assert resp["statusCode"] == 400


# ---- read ------------------------------------------------------------------
def test_get_missing_returns_404(users, event):
    resp = users.lambda_handler(
        event("GET", "/users/{userid}", path_params={"userid": "nope"}), None
    )
    assert resp["statusCode"] == 404


def test_get_returns_item(users, event):
    users.lambda_handler(event("POST", "/users", body={"userid": "u1", "name": "Ada"}), None)
    resp = users.lambda_handler(
        event("GET", "/users/{userid}", path_params={"userid": "u1"}), None
    )
    assert resp["statusCode"] == 200
    assert _body(resp)["name"] == "Ada"


def test_list_returns_all(users, event):
    users.lambda_handler(event("POST", "/users", body={"userid": "u1"}), None)
    users.lambda_handler(event("POST", "/users", body={"userid": "u2"}), None)
    resp = users.lambda_handler(event("GET", "/users"), None)
    assert resp["statusCode"] == 200
    ids = {u["userid"] for u in _body(resp)["users"]}
    assert ids == {"u1", "u2"}


# ---- update ----------------------------------------------------------------
def test_update_merges_fields(users, event):
    users.lambda_handler(
        event("POST", "/users", body={"userid": "u1", "name": "Ada", "email": "a@x.com"}),
        None,
    )
    resp = users.lambda_handler(
        event("PUT", "/users/{userid}", path_params={"userid": "u1"},
              body={"email": "ada@x.com"}),
        None,
    )
    assert resp["statusCode"] == 200
    body = _body(resp)
    assert body["email"] == "ada@x.com"
    assert body["name"] == "Ada"  # untouched field preserved


def test_update_missing_returns_404(users, event):
    resp = users.lambda_handler(
        event("PUT", "/users/{userid}", path_params={"userid": "nope"},
              body={"email": "x@y.com"}),
        None,
    )
    assert resp["statusCode"] == 404


def test_update_with_no_fields_returns_400(users, event):
    users.lambda_handler(event("POST", "/users", body={"userid": "u1"}), None)
    resp = users.lambda_handler(
        event("PUT", "/users/{userid}", path_params={"userid": "u1"}, body={}), None
    )
    assert resp["statusCode"] == 400


# ---- delete (admin only) ---------------------------------------------------
def test_delete_non_admin_returns_403(users, event):
    users.lambda_handler(event("POST", "/users", body={"userid": "u1"}), None)
    resp = users.lambda_handler(
        event("DELETE", "/users/{userid}", path_params={"userid": "u1"}, is_admin=False),
        None,
    )
    assert resp["statusCode"] == 403


def test_delete_as_admin_returns_204(users, event):
    users.lambda_handler(event("POST", "/users", body={"userid": "u1"}), None)
    resp = users.lambda_handler(
        event("DELETE", "/users/{userid}", path_params={"userid": "u1"}, is_admin=True),
        None,
    )
    assert resp["statusCode"] == 204
    get = users.lambda_handler(
        event("GET", "/users/{userid}", path_params={"userid": "u1"}), None
    )
    assert get["statusCode"] == 404  # confirm it's gone


def test_delete_missing_as_admin_returns_404(users, event):
    resp = users.lambda_handler(
        event("DELETE", "/users/{userid}", path_params={"userid": "nope"}, is_admin=True),
        None,
    )
    assert resp["statusCode"] == 404
