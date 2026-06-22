"""Unit tests for the Lambda authorizer's logic.

We don't exercise real RS256 verification (that needs signed tokens + keys);
instead we stub `_verify` to return canned claims and test the authorization
decisions: principal, isAdmin flag, the IAM policy, and the 401 path.
"""

import pytest

METHOD_ARN = "arn:aws:execute-api:us-east-1:123456789012:abc123/Prod/GET/users"


def test_allow_policy_scoped_to_api_stage(authorizer):
    policy = authorizer._allow_policy(METHOD_ARN)
    stmt = policy["Statement"][0]
    assert stmt["Effect"] == "Allow"
    assert stmt["Action"] == "execute-api:Invoke"
    # all methods + paths of THIS api/stage, not just the called method
    assert stmt["Resource"].endswith("abc123/Prod/*/*")


def test_handler_flags_admin_when_in_group(authorizer, monkeypatch):
    monkeypatch.setattr(
        authorizer, "_verify",
        lambda token: {"sub": "u1", "email": "a@x.com", "cognito:groups": ["apiAdmins"]},
    )
    resp = authorizer.lambda_handler(
        {"authorizationToken": "Bearer t", "methodArn": METHOD_ARN}, None
    )
    assert resp["principalId"] == "u1"
    assert resp["context"]["isAdmin"] is True
    assert resp["context"]["email"] == "a@x.com"
    assert resp["policyDocument"]["Statement"][0]["Effect"] == "Allow"


def test_handler_non_admin_when_not_in_group(authorizer, monkeypatch):
    monkeypatch.setattr(
        authorizer, "_verify",
        lambda token: {"sub": "u2", "email": "b@x.com", "cognito:groups": ["users"]},
    )
    resp = authorizer.lambda_handler(
        {"authorizationToken": "t", "methodArn": METHOD_ARN}, None
    )
    assert resp["context"]["isAdmin"] is False


def test_handler_no_groups_claim_is_non_admin(authorizer, monkeypatch):
    monkeypatch.setattr(authorizer, "_verify", lambda token: {"sub": "u3"})
    resp = authorizer.lambda_handler(
        {"authorizationToken": "t", "methodArn": METHOD_ARN}, None
    )
    assert resp["context"]["isAdmin"] is False


def test_handler_raises_unauthorized_on_bad_token(authorizer, monkeypatch):
    def _boom(token):
        raise ValueError("bad signature")

    monkeypatch.setattr(authorizer, "_verify", _boom)
    with pytest.raises(Exception, match="Unauthorized"):
        authorizer.lambda_handler(
            {"authorizationToken": "t", "methodArn": METHOD_ARN}, None
        )
