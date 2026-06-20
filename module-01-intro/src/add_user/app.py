"""M1 add_user Lambda — writes a user item into the DynamoDB Users table.

This function is invoked DIRECTLY (e.g. `aws lambda invoke` or `sam local
invoke`), not through API Gateway. It mirrors the workshop's "add data with a
Lambda function" step. Because it's invoked directly, the `event` argument is
exactly the JSON payload we send — here, the user item itself, e.g.:

    {"userid": "user-001", "name": "Ada Lovelace", "email": "ada@example.com"}
"""

import os

import boto3

# --- Module-level (cold-start) initialization -------------------------------
# Code outside the handler runs ONCE per execution environment ("cold start"),
# then is reused across many invocations on the same warm environment. Creating
# the boto3 client/resource here (not inside the handler) avoids rebuilding it
# on every call — a standard Lambda performance practice.
#
# boto3 is the AWS SDK for Python. `.resource("dynamodb")` gives a higher-level,
# object-oriented interface; `.Table(...)` returns a handle to one table.
dynamodb = boto3.resource("dynamodb")

# TABLE_NAME is injected by the SAM template (Globals > Environment > Variables)
# so the code never hardcodes the table name. Using os.environ[...] (not .get)
# means a missing variable fails loudly at startup rather than silently later.
table = dynamodb.Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    """Lambda entry point.

    Args:
        event:   the invocation payload. For a direct invoke this is the user
                 item dict we passed in.
        context: runtime info from Lambda (request id, time remaining, etc.).
                 Unused here, but it's always the second positional argument.
    """
    # Guard against an empty/None payload.
    user = event or {}

    # Validate the required key. `userid` is the table's partition key, so an
    # item without it cannot be written.
    if "userid" not in user:
        return {"ok": False, "error": "userid is required in the event payload"}

    # PutItem writes (or fully replaces) the item keyed by `userid`. Every other
    # attribute is stored as-is — DynamoDB is schemaless beyond the key.
    table.put_item(Item=user)

    # Return value of a directly-invoked function is just the invoke response
    # payload (no HTTP wrapping needed, unlike the API-fronted get_user).
    return {"ok": True, "message": "User added", "userid": user["userid"]}
