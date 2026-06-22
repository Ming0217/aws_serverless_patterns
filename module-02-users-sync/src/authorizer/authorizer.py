"""M2 Lambda Authorizer — TOKEN type.

API Gateway calls this function BEFORE the backend (UsersFunction). It:
  1. Reads the JWT from the `Authorization` header (TOKEN authorizer).
  2. Verifies it against the Cognito user pool's public keys (JWKS): signature,
     issuer, audience (app client), expiry, and token_use == "id".
  3. Returns an IAM policy (Allow for this API) plus a `context` object carrying
     the caller's identity and an `isAdmin` flag (derived from cognito:groups).

If verification fails we raise Exception("Unauthorized"), which makes API
Gateway return 401 — the backend is never invoked.

WHY A LAMBDA AUTHORIZER (vs the native Cognito authorizer)?
The native COGNITO_USER_POOLS authorizer only checks "valid token?". A Lambda
authorizer lets us add CUSTOM logic — here, surfacing admin-group membership so
downstream code can make fine-grained decisions.

DEPENDENCY: python-jose (pure-Python backend) for JWT verification — see
requirements.txt. No compiled deps, so `sam build` works without a container.
"""

import json
import os
import urllib.request

from jose import jwt

# --- config from environment (set in template.yaml) -------------------------
USER_POOL_ID = os.environ["USER_POOL_ID"]
APP_CLIENT_ID = os.environ["APP_CLIENT_ID"]
ADMIN_GROUP_NAME = os.environ["ADMIN_GROUP_NAME"]
# Lambda sets AWS_REGION automatically.
REGION = os.environ["AWS_REGION"]

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# Fetch the pool's public keys ONCE per execution environment and cache them.
# These rotate rarely; caching avoids an HTTP call on every invocation.
with urllib.request.urlopen(JWKS_URL) as resp:  # noqa: S310 (trusted AWS URL)
    _JWKS = json.loads(resp.read())["keys"]


def lambda_handler(event, context):
    """TOKEN authorizer entry point.

    event = {"type": "TOKEN",
             "authorizationToken": "<Authorization header value>",
             "methodArn": "arn:aws:execute-api:...:.../<stage>/<METHOD>/<path>"}
    """
    token = (event.get("authorizationToken") or "").removeprefix("Bearer ").strip()
    method_arn = event["methodArn"]

    try:
        claims = _verify(token)
    except Exception as exc:  # any verification problem => 401
        print(f"Token verification failed: {exc}")
        # This exact string triggers API Gateway's 401 Unauthorized response.
        raise Exception("Unauthorized") from exc

    # cognito:groups is a list (or absent). Admin = member of the admin group.
    groups = claims.get("cognito:groups", [])
    is_admin = ADMIN_GROUP_NAME in groups

    # Allow the whole API for this valid user; fine-grained per-route checks are
    # done in the backend using the context below (avoids authorizer-cache
    # pitfalls where one cached policy would apply across methods).
    return {
        "principalId": claims["sub"],
        "policyDocument": _allow_policy(method_arn),
        # Context values must be strings/numbers/bools; API Gateway exposes them
        # at event.requestContext.authorizer.<key> (as strings) in the backend.
        "context": {
            "userid": claims["sub"],
            "email": claims.get("email", ""),
            "isAdmin": is_admin,
        },
    }


def _verify(token):
    """Verify a Cognito ID token and return its claims (raises on failure)."""
    kid = jwt.get_unverified_header(token)["kid"]
    key = next((k for k in _JWKS if k["kid"] == kid), None)
    if key is None:
        raise ValueError("Signing key not found in JWKS")

    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=APP_CLIENT_ID,   # ID token's `aud` is the app client id
        issuer=ISSUER,
    )
    if claims.get("token_use") != "id":
        raise ValueError("Not an ID token")
    return claims


def _allow_policy(method_arn):
    """Build an Allow policy scoped to this API/stage (all methods + paths)."""
    # methodArn: arn:aws:execute-api:<region>:<acct>:<apiId>/<stage>/<METHOD>/<path>
    parts = method_arn.split(":")
    api_id, stage, *_ = parts[5].split("/")
    api_scope = f"{parts[0]}:{parts[1]}:{parts[2]}:{parts[3]}:{parts[4]}:{api_id}/{stage}/*/*"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Action": "execute-api:Invoke", "Effect": "Allow", "Resource": api_scope}
        ],
    }
