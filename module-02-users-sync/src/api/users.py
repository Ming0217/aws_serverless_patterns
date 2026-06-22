"""M2 Users Service — MONO-LAMBDA handler (workshop v4 layout).

One Lambda function serves every /users route. API Gateway (REST, proxy
integration) delivers the whole HTTP request as `event`, and this handler
dispatches on the HTTP method + resource path:

    POST   /users            -> create_user   (body = user fields)
    GET    /users            -> list_users
    GET    /users/{userid}   -> get_user
    PUT    /users/{userid}   -> update_user   (body = fields to change)
    DELETE /users/{userid}   -> delete_user

MONO-LAMBDA vs SINGLE-FUNCTION
------------------------------
ONE function with an internal router (the if/elif ladder). Simplest migration
target; one deployable, one IAM role. Later modules split to one function per
route for isolation and finer scaling.

The table name comes from the USERS_TABLE env var (set in template.yaml), so the
same code runs against any environment's table.

HTTP status codes: 200 OK, 201 Created, 204 No Content (delete), 400 Bad
Request, 404 Not Found, 409 Conflict.

OBSERVABILITY (stage 4)
-----------------------
* X-Ray tracing is enabled in template.yaml (Tracing: Active) — no code needed.
* Structured JSON logs via `_log(...)` so CloudWatch Logs Insights can query by
  field (route, status, userid, request id).
* Custom metrics via the Embedded Metric Format (EMF): `_emit_metric(...)` prints
  a specially-shaped JSON line that CloudWatch auto-extracts into a metric — no
  put_metric_data call, no extra IAM, no dependency. (Module 3 swaps this hand-
  rolled approach for Powertools for AWS Lambda.)
"""

import json
import logging
import os
import time
import uuid

import boto3
from botocore.exceptions import ClientError

# Created once per execution environment, reused on warm invocations.
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["USERS_TABLE"])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# EMF metric namespace/dimension — groups our custom metrics in CloudWatch.
METRIC_NAMESPACE = "UsersService"
SERVICE_NAME = "users"


def lambda_handler(event, context):
    """Entry point — the internal router.

    Routes on `event["resource"]` (API Gateway's route template, e.g.
    "/users/{userid}") + `event["httpMethod"]`. The single try/except turns a
    malformed JSON body anywhere into a clean 400 instead of a 500.
    """
    method = event.get("httpMethod")
    resource = event.get("resource")
    request_id = getattr(context, "aws_request_id", None)
    _log("request_received", method=method, resource=resource, request_id=request_id)

    try:
        if resource == "/users" and method == "POST":
            resp = create_user(event)
        elif resource == "/users" and method == "GET":
            resp = list_users(event)
        elif resource == "/users/{userid}" and method == "GET":
            resp = get_user(event)
        elif resource == "/users/{userid}" and method == "PUT":
            resp = update_user(event)
        elif resource == "/users/{userid}" and method == "DELETE":
            resp = delete_user(event)
        else:
            resp = _response(404, {"error": f"No route for {method} {resource}"})
    except json.JSONDecodeError:
        resp = _response(400, {"error": "Request body must be valid JSON"})

    _log("request_completed", method=method, resource=resource,
         status=resp["statusCode"], request_id=request_id)
    return resp


# ---- route handlers --------------------------------------------------------
def create_user(event):
    """POST /users — create a user; generates a userid if none supplied."""
    body = _parse_body(event)
    userid = body.get("userid") or str(uuid.uuid4())
    item = {**body, "userid": userid}

    # attribute_not_exists(userid) => write only if the id is new (no clobber).
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(userid)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(409, {"error": f"User '{userid}' already exists"})
        raise
    _emit_metric("UserCreated")
    return _response(201, item)


def list_users(event):
    """GET /users — return all users (Scan; fine for a workshop-sized table)."""
    result = table.scan()
    return _response(200, {"users": result.get("Items", [])})


def get_user(event):
    """GET /users/{userid} — fetch one user by primary key."""
    userid = event["pathParameters"]["userid"]
    item = table.get_item(Key={"userid": userid}).get("Item")
    if item is None:
        return _response(404, {"error": f"User '{userid}' not found"})
    return _response(200, item)


def update_user(event):
    """PUT /users/{userid} — merge supplied fields into an existing user."""
    userid = event["pathParameters"]["userid"]
    body = _parse_body(event)

    fields = {k: v for k, v in body.items() if k != "userid"}
    if not fields:
        return _response(400, {"error": "No fields to update"})

    # Parameterized SET expression. ExpressionAttributeNames (#k) dodge DynamoDB
    # reserved words (e.g. "name"); ExpressionAttributeValues (:k) keep values
    # out of the expression string.
    set_clause = ", ".join(f"#{k} = :{k}" for k in fields)
    expr_names = {f"#{k}": k for k in fields}
    expr_values = {f":{k}": v for k, v in fields.items()}

    try:
        result = table.update_item(
            Key={"userid": userid},
            UpdateExpression=f"SET {set_clause}",
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ConditionExpression="attribute_exists(userid)",  # must already exist
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(404, {"error": f"User '{userid}' not found"})
        raise
    return _response(200, result["Attributes"])


def delete_user(event):
    """DELETE /users/{userid} — remove a user. ADMIN ONLY.

    Fine-grained authorization: the Lambda authorizer puts an `isAdmin` flag in
    the request context (from the caller's cognito:groups). Only admins may
    delete. Non-admins get 403 Forbidden (authenticated, but not allowed).

    ConditionExpression makes the delete fail with 404 if the user doesn't
    exist (otherwise DynamoDB's delete_item is a silent no-op on a missing key).
    Returns 204 No Content on success.
    """
    if not _is_admin(event):
        return _response(403, {"error": "Admin privileges required to delete users"})

    userid = event["pathParameters"]["userid"]
    try:
        table.delete_item(
            Key={"userid": userid},
            ConditionExpression="attribute_exists(userid)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(404, {"error": f"User '{userid}' not found"})
        raise
    _emit_metric("UserDeleted")
    return _response(204, "")


# ---- helpers ---------------------------------------------------------------
def _log(message, **fields):
    """Emit a structured (JSON) log line — queryable in CloudWatch Logs Insights."""
    logger.info(json.dumps({"message": message, **fields}))


def _emit_metric(name, value=1, unit="Count"):
    """Emit a custom CloudWatch metric via Embedded Metric Format (EMF).

    Printing a log line with this `_aws` envelope makes CloudWatch automatically
    extract `name` as a metric in METRIC_NAMESPACE (dimension Service=users).
    No put_metric_data call and no extra IAM permission required.
    """
    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": METRIC_NAMESPACE,
                "Dimensions": [["Service"]],
                "Metrics": [{"Name": name, "Unit": unit}],
            }],
        },
        "Service": SERVICE_NAME,
        name: value,
    }))


def _is_admin(event):
    """True if the Lambda authorizer flagged this caller as an admin.

    The authorizer sets context.isAdmin; API Gateway forwards it as a STRING
    under requestContext.authorizer, so compare case-insensitively to "true".
    """
    authz = (event.get("requestContext") or {}).get("authorizer") or {}
    return str(authz.get("isAdmin", "")).lower() == "true"


def _parse_body(event):
    """Parse the JSON request body string into a dict (or {} if empty)."""
    raw = event.get("body")
    if not raw:
        return {}
    return json.loads(raw)


def _response(status_code, body):
    """Build a Lambda proxy integration response (body must be a string)."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        # For 204 we pass "" (no JSON content); otherwise serialize the dict.
        "body": json.dumps(body) if body != "" else "",
    }
