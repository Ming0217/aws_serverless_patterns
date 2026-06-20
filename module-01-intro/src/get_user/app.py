"""M1 get_user Lambda — reads one user from DynamoDB by id.

This function sits behind API Gateway on `GET /users/{userid}` using **Lambda
proxy integration**. With proxy integration:

  * the entire HTTP request is delivered to the handler as the `event` dict
    (path parameters, query string, headers, body, ...), and
  * the handler must return a specific dict shape — statusCode / headers / body
    (body as a string) — which API Gateway turns back into the HTTP response.
"""

import json
import os

import boto3

# Initialized once per execution environment and reused across warm invocations
# (see add_user/app.py for the cold-start rationale). Read-only access to this
# table is granted by the DynamoDBReadPolicy in template.yaml.
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    """Handle `GET /users/{userid}`.

    The path parameter {userid} arrives under event["pathParameters"]["userid"].
    """
    # `pathParameters` can be None when there are no path params, so default to
    # {} before indexing to avoid a TypeError.
    userid = (event.get("pathParameters") or {}).get("userid")

    if not userid:
        # 400 Bad Request — the route requires a userid.
        return _response(400, {"error": "userid path parameter is required"})

    # GetItem fetches a single item by its full primary key. If no item matches,
    # the response simply has no "Item" key (it does NOT raise).
    result = table.get_item(Key={"userid": userid})
    item = result.get("Item")

    if item is None:
        # 404 Not Found — valid request, but no such user.
        return _response(404, {"error": f"User '{userid}' not found"})

    # 200 OK with the stored item.
    return _response(200, item)


def _response(status_code, body):
    """Build a Lambda proxy integration response.

    API Gateway requires `body` to be a STRING, so we json.dumps the dict and
    advertise the type via the Content-Type header.
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
