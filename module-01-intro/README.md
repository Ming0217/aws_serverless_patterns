# Module 1 — Intro to Serverless (SAM version)

The workshop builds this in the AWS console; this folder builds the same *Example User
Service* programmatically with **AWS SAM**.

## Architecture

```
Client ──GET /users/{userid}──> API Gateway (REST) ──> get_user Lambda ──GetItem──┐
                                                                                   ├─> DynamoDB (Users)
                                          add_user Lambda ──PutItem───────────────┘
                                          (invoked directly to seed data)
```

| Resource | Type | Purpose |
| --- | --- | --- |
| `Users` | DynamoDB table | Stores user items, PK `userid` (String), on-demand billing |
| `m1-add-user` | Lambda | `PutItem` — invoked directly to add data |
| `m1-get-user` | Lambda | `GetItem` — fronted by API Gateway |
| REST API | API Gateway | `GET /users/{userid}` |

IAM is least-privilege via SAM policy templates: `DynamoDBWritePolicy` for add, `DynamoDBReadPolicy` for get.

## Concept — REST API vs. HTTP API

API Gateway offers three API types: **REST**, **HTTP**, and **WebSocket**. This module uses a
**REST API**. The workshop chooses REST (over the cheaper/simpler HTTP API) because later
modules rely on REST-only features like **mocking, request validation, and the advanced
test-invoke tooling**.

| | REST API | HTTP API |
| --- | --- | --- |
| Age / cost | Original; ~$3.50 / million | Newer; ~$1.00 / million |
| Latency | Higher overhead | Lower |
| Mapping templates (VTL) | ✅ | ❌ |
| Request validation | ✅ | ❌ |
| Mocking integrations | ✅ | ❌ |
| API keys & usage plans | ✅ | ❌ (limited) |
| Caching / WAF / private / edge | ✅ | ❌ (regional only) |
| Authorizers | IAM, Cognito, Lambda | IAM, native JWT/OIDC, Lambda |
| Built-in CORS / auto-deploy | manual | ✅ simpler |

Rule of thumb: **HTTP API** for a lean, cheap Lambda/HTTP proxy with JWT auth (the default for
most new APIs); **REST API** when you need the heavier features above. AWS keeps narrowing the
gap, so check the [official comparison](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
for production decisions.

In SAM: REST = function event `Type: Api` (explicit `AWS::Serverless::Api`, auto ID
`ServerlessRestApi`); HTTP = `Type: HttpApi` (explicit `AWS::Serverless::HttpApi`, auto ID
`ServerlessHttpApi`). See `template-explicit-api.yaml` for the explicit-REST variant.

## Concept — REST API terminology: Resource vs. Method

A REST API is a tree of two building blocks (don't let "method" suggest code — it means an
**HTTP verb**):

- **Resource** = a URL path / *noun*, e.g. `/users`, nesting under root: `/` → `/users` → `/users/{userid}`.
- **Method** = an HTTP verb / *action* on that resource: `GET`, `POST`, `PUT`, `DELETE`, ...

A resource + method = one **endpoint**, and each method is wired to an **integration** (Lambda,
HTTP backend, AWS service, or mock). So the workshop's console steps map like this:

| Console step | REST API term | Meaning |
| --- | --- | --- |
| Create Resource `users` | Resource | define path `/users` |
| Create Method `GET` | Method | this path answers HTTP GET |
| Integration = Lambda → `get-users` | Integration | route GET to that function |

"Bind the method to the Lambda" = "when someone does `GET /users`, run that function."

**Vocabulary tell:** REST APIs use *Resources + Methods*; HTTP APIs collapse this into a single
*Route* string like `GET /users`. Seeing "resource, then method" confirms it's a REST API.

In this module's `template.yaml`, SAM created the resource + method + integration + invoke
permission from just two lines:

```yaml
      Events:
        GetUser:
          Type: Api
          Properties:
            Path: /users/{userid}    # <- the RESOURCE (path)
            Method: get              # <- the METHOD (HTTP verb)
```

(The workshop console uses `/users`; this template uses `/users/{userid}` to fetch one user by
id — which is why the handler reads `event["pathParameters"]["userid"]`.)

## Concept — Event-driven architecture (EDA)

An **event** is just a chunk of JSON that one service hands to another to represent a request,
a state change, or some data. EDA means components communicate by **passing events** rather than
calling each other's code directly — which keeps them **loosely coupled**.

**Key insight — two independent axes:**
- *Synchronous vs. asynchronous* = timing (does the caller wait?). M1 is **synchronous**.
- *Event-driven* = how components talk (do they exchange events?). M1 is **event-driven**.

These aren't opposites, so M1 is **synchronous AND event-driven** at the same time. Modules 4–5
add the *asynchronous* flavor.

**You already handle events directly** — in `get_user`, the `event` arg *is* the event API
Gateway built from the HTTP request, and the returned `{statusCode, headers, body}` is the
*response event* (you never talk to the client directly):

```python
def lambda_handler(event, context):
    userid = (event.get("pathParameters") or {}).get("userid")   # read the inbound event
    ...
    return {"statusCode": 200, "headers": {...}, "body": json.dumps(item)}  # return a response event
```

**M1 flow, as events:**

```
Client ─GET /users/user-001─> API Gateway
        API Gateway converts the HTTP request into an EVENT (JSON) ──┐
        Lambda invokes get_user(event, context) ◄────────────────────┘
        get_user queries DynamoDB, builds a RESPONSE EVENT ──┐
        API Gateway receives the response event ◄────────────┘
        API Gateway returns the event's `body` to the client
```

Every arrow is a JSON event passed between services — nobody calls anyone's code directly.

**Shape vs. contents:** services agree on the *shape* (which keys exist — `pathParameters`,
`headers`, `body`) but not the *contents* (whether `userid` is `user-001` or `user-999`). The
handler depends on the shape, not the values.

**Why it matters (loose coupling):** API Gateway doesn't know a Lambda handles the event, and
`get_user` doesn't know API Gateway triggered it. As long as the event *shape* holds, you can
add, swap, or extend components without touching the others — the opposite of a monolith where
A calls B directly and changing B breaks A. That decoupling is what gives serverless its
scalability and extensibility.

**Where the events actually are (be precise about the boundaries):** in the `get_user` path the
event passing is specifically between **API Gateway ⇄ Lambda** — two events: a *request event*
(API Gateway → Lambda) and a *response event* (Lambda → API Gateway). The other two hops are
**not** events:
- **Client ⇄ API Gateway** is plain **HTTP**. API Gateway is the boundary that converts HTTP
  into an event (and the response event's `body` back into HTTP).
- **Lambda ⇄ DynamoDB** is a synchronous **AWS SDK (boto3) call** (`table.get_item(...)`), a
  request/response to a managed service — not an event in EDA terms.

Note this applies to `get_user`. The `add_user` function has no API Gateway in front of it —
you invoke it directly, so *its* event is passed from the **invoker** (your `aws lambda invoke`)
to Lambda.

## Files

```
module-01-intro/
├── template.yaml              # all resources (implicit REST API)
├── template-explicit-api.yaml # same, but with an explicit AWS::Serverless::Api
├── src/
│   ├── add_user/app.py        # PutItem handler
│   └── get_user/app.py        # GetItem handler (proxy response)
└── events/
    ├── add_user.json          # payload for invoking add_user
    └── get_user.json          # proxy event for local-invoking get_user
```

## Deploy

```bash
export AWS_PROFILE=serverless-workshop      # match your configured profile

sam build
sam deploy --guided                          # first time; saves to samconfig.toml
# subsequent deploys: sam deploy
```

During `--guided`, accept defaults; it's fine to allow SAM to create IAM roles. Note the
**Outputs** printed at the end (table name, add function name, API URL).

## Test

1. **Seed data** by invoking add_user directly:

   ```bash
   aws lambda invoke \
     --function-name m1-add-user \
     --cli-binary-format raw-in-base64-out \
     --payload file://events/add_user.json \
     /dev/stdout
   ```

   > AWS CLI **v2** is required, and `--cli-binary-format raw-in-base64-out` is a v2-only flag.
   > Without it, v2 expects a base64 payload and you'll hit an `Invalid base64` error.

2. **Retrieve via the API** (replace with your deployed URL from the outputs):

   ```bash
   curl https://<api-id>.execute-api.<region>.amazonaws.com/Prod/users/user-001
   ```

   Expected: the JSON user item. A missing id returns `404`.

### Local testing (optional, needs Docker)

```bash
sam local invoke AddUserFunction -e events/add_user.json
sam local invoke GetUserFunction -e events/get_user.json   # talks to the real table
sam local start-api                                        # serves the API on localhost:3000
```

## Cleanup

```bash
sam delete
```

## Notes / learnings

**Status: ✅ completed end to end.**

What the working flow proved:
`sam deploy` → `aws lambda invoke m1-add-user` (PutItem) → `curl` → API Gateway →
`m1-get-user` (GetItem) → DynamoDB → JSON back to the client.

Key takeaways:
- **IaC vs. console:** the same table + 2 functions + REST API the workshop clicks together in
  the console is one declarative `template.yaml` here — repeatable and reviewable.
- **Direct invoke vs. API invoke:** `add_user` is invoked directly (event = the raw payload),
  while `get_user` runs behind API Gateway proxy integration (event = the HTTP request;
  response must be `{statusCode, headers, body-as-string}`).
- **Least privilege:** SAM policy templates (`DynamoDBWritePolicy` / `DynamoDBReadPolicy`)
  scoped each function to only the access it needs on only this table.
- **Outputs live on the stack, not in `samconfig.toml`** (which only stores deploy answers).
  Retrieve the API URL anytime with:
  `aws cloudformation describe-stacks --stack-name m1-intro-serverless --query "Stacks[0].Outputs" --output table`

Gotchas hit (and fixes):
- **AWS CLI v1 vs v2:** `uv tool install awscli` / pip installs **v1** (v2 isn't on PyPI). The
  v2-only flag `--cli-binary-format raw-in-base64-out` errored as "unknown option" until I
  switched to the Homebrew v2 (`brew install awscli`). Also had a stray v1 in a mise Python
  ahead on `PATH` — removed it so the v2 resolved.
- **`https://` doubled** in the curl URL (the output value already includes the scheme) →
  `Could not resolve host: https`. Using command substitution avoids re-prepending it.

## Outputs from my run

- Stack: `m1-intro-serverless` (us-east-1)
- API URL: `https://8kfygdrbl6.execute-api.us-east-1.amazonaws.com/Prod/users/{userid}`
- Verified: `GET .../users/user-001` →
  `{"email": "ada@example.com", "name": "Ada Lovelace", "userid": "user-001"}`
