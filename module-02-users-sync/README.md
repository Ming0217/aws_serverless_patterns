# Module 2 — Synchronous Invocation: Users Service (SAM)

A synchronous **Users microservice** (create / read / update / delete / list) built with IaC
(AWS SAM) using a **mono-lambda** design. This module is aligned with the workshop's
**"v4 - Amazon Cognito"** template.

> **Build order (stages):**
> 1. ✅ Stage 1 — mono-lambda backend + DynamoDB + REST API
> 2. ✅ Stage 2 — Amazon Cognito + Lambda authorizer
>    - 2a ✅ Cognito resources (pool/client/domain/admin group), explicit API, X-Ray tracing,
>      DELETE route
>    - 2b ✅ Lambda authorizer (validate JWT + admin group), attached as the API default
> 3. ✅ Stage 3 — unit + integration tests
> 4. ✅ Stage 4 — observability (X-Ray tracing + structured logs + EMF custom metrics)

## Architecture

```
                              Authorization: <ID token>
                                       │
                    ┌─────────── RestAPI (explicit REST API) ───────────┐
Client ── HTTP ──>  │  AuthorizerFunction (Lambda authorizer) validates  │
                    │  the JWT + flags isAdmin, then:                     │
                    │  GET/POST /users   GET/PUT/DELETE /users/{userid}   │
                    └───────────────────────┬───────────────────────────┘
                                             │  (all 5 routes -> one function)
                                     UsersFunction (MONO-LAMBDA, X-Ray traced)
                                             │  CRUD (DELETE = admin only)
                                             v
                                  DynamoDB  <stack>-Users table

Cognito: UserPool + UserPoolClient + UserPoolDomain (hosted UI) + admin Group
         (authentication; the Lambda authorizer does authorization)
```

> **Authorization is live.** Every route requires a valid Cognito JWT (→ **401** without).
> `DELETE` additionally requires membership in the `apiAdmins` group (→ **403** for non-admins).

| Route | Method | Handler fn | Action |
| --- | --- | --- | --- |
| `/users` | POST | `create_user` | create (409 if id exists) |
| `/users` | GET | `list_users` | list all (Scan) |
| `/users/{userid}` | GET | `get_user` | fetch one (404 if missing) |
| `/users/{userid}` | PUT | `update_user` | merge fields (404 if missing) |
| `/users/{userid}` | DELETE | `delete_user` | delete (404 if missing, 204 on success) |

## Concept — mono-lambda vs. single-function

- **Mono-lambda (this module):** ONE Lambda handles every route; it dispatches internally on
  `event["httpMethod"]` + `event["resource"]`. Easiest migration from a traditional framework;
  one deployable, one cold-start path, simplest IAM.
- **Single-function (later modules):** one Lambda per route. More isolation (a bug/throttle in
  one route doesn't affect others), finer-grained scaling and permissions, smaller packages.

## Concept — native Cognito authorizer vs. Lambda authorizer

API Gateway REST APIs can authorize requests several ways. Two relevant here:

- **Native Cognito authorizer (`COGNITO_USER_POOLS`):** API Gateway itself validates the JWT
  against the user pool. No custom code, but **coarse** — valid token → allowed. It can't, by
  itself, enforce "only `apiAdmins` may DELETE."
- **Lambda authorizer (custom):** a separate Lambda that API Gateway calls first. It verifies the
  Cognito JWT *and* applies **custom logic** (e.g. check the `cognito:groups` claim for the admin
  group), then returns an **IAM policy** (Allow/Deny) plus a **context** object passed to the
  backend. More flexible — fine-grained, multi-source, external lookups.

**The workshop uses the Lambda authorizer** — that's why it creates the `apiAdmins` group and the
`UserPoolAdminGroupName` parameter: the authorizer will use the group for admin-only routes.
Roles split cleanly: **Cognito user pool = authentication**; **Lambda authorizer = authorization**.

## Concept — authentication vs. authorization

- **Authentication (who are you?)** — the **Cognito user pool**. Sign up / sign in → Cognito
  issues **JWTs** (ID, access, refresh tokens).
- **Authorization (are you allowed?)** — the **authorizer** (here, the Lambda authorizer, stage
  2b). It validates the token (and applies rules) *before* the request reaches the backend
  Lambda. No/invalid token → **401**; authenticated-but-not-allowed → **403**.

```
Client ──(1) sign in──> Cognito User Pool ──issues JWT──> Client
Client ──(2) request + Authorization: <JWT> ──> API Gateway
                                                 │ (2b) Lambda authorizer validates + checks group
                                          401/403◄┤  (deny: stops here)
                                                 └──allow──> UsersFunction ──> DynamoDB
```

Validating at the edge means rejected calls never invoke the backend (no run, no cost), and auth
stays out of the business logic.

## Concept — coarse vs. fine-grained authorization

Even with an authorizer, there are degrees:

- **Coarse:** any valid user can call any route (what a bare token check gives you).
- **Fine-grained:** decisions use the token's **signed claims** — `sub` (stable user id),
  `cognito:groups` (e.g. `apiAdmins`), custom attributes, or OAuth `scope`. The Lambda authorizer
  can enforce group-based rules; the backend can also read claims
  (`event["requestContext"]["authorizer"][...]`) for ownership checks like "you may only edit
  your own profile" (→ **403** otherwise).

## Concept — Cognito: UserPool vs. UserPoolClient

**The pool is the "who and how" of authentication; the client is a per-app door into that pool.**
Users live in the pool, never in the client.

- **`UserPool`** — directory of users **plus** auth rules (sign-in via email, email
  verification, password policy, MFA, triggers, token lifetimes). **Issues the JWTs.**
- **`UserPoolClient`** — registration for **one app**: allowed flows (`ExplicitAuthFlows`),
  secret-or-not (`GenerateSecret`), OAuth flows/scopes/callback URLs. Holds **no users**; belongs
  to one pool. **One pool → many clients** sharing the same users.
- **`UserPoolDomain`** — hosts the Cognito sign-up/sign-in web page (the `CognitoLoginURL`).
- **Admin `UserPoolGroup`** — membership surfaces as the `cognito:groups` claim for authz.

## Concept — how `sam deploy` updates a stack (incremental, declarative IaC)

`sam deploy` does **not** tear down and rebuild — CloudFormation diffs the live stack against the
new template (a **change set**) and applies only the differences (idempotent).

**Critical nuance — in-place update vs. replacement:** changing an **immutable** property forces
a **replacement** (create new + delete old). For DynamoDB, changing `TableName` or the key schema
triggers replacement, which **destroys the data**.

> ⚠️ **This refactor triggers replacements.** If you already deployed the earlier stage-1/stage-2
> draft of this module and redeploy this v4 template into the **same stack**, expect:
> - the **DynamoDB table is replaced** (the name changed to `<stack>-Users`) → **stage-1 test
>   data is lost** (fine for the workshop);
> - the API switches from the implicit `ServerlessRestApi` to the explicit `RestAPI` → **the API
>   URL changes**.
> Guardrails for real data: `DeletionPolicy: Retain` / `UpdateReplacePolicy: Retain`.

## Files

```
module-02-users-sync/
├── template.yaml              # DynamoDB + mono-lambda + explicit REST API + Cognito + authorizer
├── src/
│   ├── api/users.py           # mono-lambda router + route handlers (Handler: src/api/users.lambda_handler)
│   └── authorizer/
│       ├── authorizer.py      # TOKEN Lambda authorizer (verifies JWT, flags isAdmin)
│       └── requirements.txt   # python-jose (pure-Python JWT verify)
├── tests/
│   ├── conftest.py            # fixtures: mocked-DynamoDB handler, stubbed authorizer, event factory
│   ├── unit/                  # test_users.py, test_authorizer.py (moto, no AWS)
│   └── integration/           # test_api.py (hits the deployed API; gated by env vars)
└── events/                    # API Gateway proxy events for `sam local invoke`
    ├── create_user.json
    ├── list_users.json
    ├── get_user.json
    ├── update_user.json
    └── delete_user.json
```

> `UsersFunction` has no `CodeUri` (defaults to the template dir; `Handler:
> src/api/users.lambda_handler`). `AuthorizerFunction` uses `CodeUri: src/authorizer/` so its
> `requirements.txt` (python-jose) is installed by `sam build` — no container needed (pure Python).

## Deploy (workshop checkpoint — Cognito user pool)

```bash
cd module-02-users-sync
export AWS_PROFILE=serverless-workshop

sam build && sam deploy --guided     # stack: module-02-users-sync; allow IAM role creation;
                                     #   accept the UserPoolAdminGroupName parameter (apiAdmins)
# later: sam build && sam deploy
```

Note the new **Outputs**: `APIEndpoint`, `UserPool`, `UserPoolClient`, `UserPoolAdminGroupName`,
`CognitoLoginURL`, and `CognitoAuthCommand`.

## Register a user (hosted UI)

The `CognitoLoginURL` output points at the **Cognito Hosted UI** (served by `UserPoolDomain`):

1. Open the **CognitoLoginURL** output in a browser.
2. Click **Sign up**. Because the pool schema marks **name** and **email** as required, the form
   asks for **email** (this is also the username), **name**, and a **password**.
3. Submit — Cognito emails a verification code. Enter the code to **confirm** the account.
4. After confirming/sign-in the browser redirects to `http://localhost?code=...` and shows a
   connection error — **that's expected** (nothing runs on localhost; the account is already
   created). You don't need that code for the workshop.

Verify and grab a token:

```bash
POOL_ID=$(aws cloudformation describe-stacks --stack-name module-02-users-sync \
  --query "Stacks[0].Outputs[?OutputKey=='UserPool'].OutputValue" --output text)
aws cognito-idp list-users --user-pool-id "$POOL_ID" \
  --query "Users[].[Username,UserStatus]" --output table   # expect CONFIRMED
```

> ⚠️ **Password policy:** this template defines no `PasswordPolicy`, so Cognito's **default**
> applies — 8+ chars with **uppercase, lowercase, number, AND a special character**. So
> `Passw0rd1` is rejected; use e.g. `Passw0rd!`.
>
> CLI-only alternative (skip the browser): `aws cognito-idp sign-up ...` then
> `aws cognito-idp admin-confirm-sign-up ...`.

## Test (authorizer attached — token required)

Every route now returns **401** without a valid JWT. `DELETE` also requires the `apiAdmins` group.

```bash
API=$(aws cloudformation describe-stacks --stack-name module-02-users-sync \
      --query "Stacks[0].Outputs[?OutputKey=='APIEndpoint'].OutputValue" --output text)
CLIENT_ID=$(aws cloudformation describe-stacks --stack-name module-02-users-sync \
      --query "Stacks[0].Outputs[?OutputKey=='UserPoolClient'].OutputValue" --output text)
POOL_ID=$(aws cloudformation describe-stacks --stack-name module-02-users-sync \
      --query "Stacks[0].Outputs[?OutputKey=='UserPool'].OutputValue" --output text)

# No token -> 401
curl -i "$API/users"

# Get an ID token (user registered via the hosted UI above)
ID_TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=you@example.com,PASSWORD='Passw0rd!' \
  --query 'AuthenticationResult.IdToken' --output text)

# Authenticated calls (raw token, no "Bearer " prefix needed)
curl "$API/users" -H "Authorization: $ID_TOKEN"                       # 200
curl -X POST "$API/users" -H "Authorization: $ID_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Grace Hopper", "email": "grace@example.com"}'         # 201

# DELETE as a NON-admin -> 403
curl -i -X DELETE "$API/users/<userid>" -H "Authorization: $ID_TOKEN"

# Make yourself an admin, then re-auth (group membership is baked into the token)
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL_ID" \
  --username you@example.com --group-name apiAdmins
ID_TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=you@example.com,PASSWORD='Passw0rd!' \
  --query 'AuthenticationResult.IdToken' --output text)

# DELETE as an admin -> 204
curl -i -X DELETE "$API/users/<userid>" -H "Authorization: $ID_TOKEN"
```

Key checks: **401** without a token, **200/201** with one, **403** on DELETE as a non-admin, and
**204** on DELETE after joining `apiAdmins` and re-authenticating.

> Re-authenticate after a group change — `cognito:groups` is embedded in the token at sign-in, so
> an old token won't reflect new membership. The authorizer also caches per token (default 5 min).

### Local testing (needs Docker)

`sam local` doesn't run the authorizer, so there's no `isAdmin` in the context — `DELETE` will
return 403 locally. The other routes work:

```bash
sam local invoke UsersFunction -e events/create_user.json
sam local start-api      # serves all routes on http://localhost:3000 (no authorizer locally)
```

## Tests (stage 3)

Dev dependencies (`pytest`, `moto`, `requests`, `python-jose`) live in the repo's
`pyproject.toml` under `[dependency-groups].dev`. Install once with `uv sync`.

**Unit tests** (no AWS — `moto` mocks DynamoDB; the authorizer's JWKS fetch and `_verify` are
stubbed). Run from the repo root:

```bash
uv run pytest module-02-users-sync/tests/unit -v
```

Coverage: every route + status path (`201/200/404/409/400`), the partial-update merge, and the
admin-only `DELETE` (`403` vs `204`); the authorizer's `isAdmin` logic, IAM policy scoping, and
the `Unauthorized` (401) path.

**Integration tests** (hit the *deployed* API; gated by env vars so they're skipped otherwise):

```bash
export API_BASE_URL=$(aws cloudformation describe-stacks --stack-name module-02-users-sync \
  --query "Stacks[0].Outputs[?OutputKey=='APIEndpoint'].OutputValue" --output text)
export ID_TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=your-email@example.com,PASSWORD='Passw0rd!' \
  --query 'AuthenticationResult.IdToken' --output text)

uv run pytest module-02-users-sync/tests/integration -m integration -v
```

> Why load handlers by file path in `conftest.py`? The functions are standalone files (no
> package) and bind their boto3 table / fetch JWKS at *import* time — so the fixtures set the
> env + mocks first, then import the module fresh, guaranteeing setup runs against the mock.

## Observability (stage 4)

Three layers, all without extra dependencies:

- **Tracing (X-Ray):** enabled in the template (`Tracing: Active` on functions, `TracingEnabled`
  on the API) — no code. View end-to-end traces in the X-Ray/CloudWatch ServiceLens console.
- **Structured logging:** `_log(message, **fields)` emits JSON log lines (route, status, userid,
  `request_id`). Query them in **CloudWatch Logs Insights**, e.g.:
  ```
  fields @timestamp, message, status, resource
  | filter message = "request_completed" and status >= 400
  ```
- **Custom metrics (EMF):** `_emit_metric("UserCreated")` prints an [Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
  log line; CloudWatch auto-extracts it into a metric under namespace **`UsersService`**
  (dimension `Service=users`). Emitted on create (`UserCreated`) and delete (`UserDeleted`).
  **No `put_metric_data` call and no extra IAM** — that's the appeal of EMF.

See the metrics after exercising the API:

```bash
aws cloudwatch list-metrics --namespace UsersService --output table
```

> **Why hand-rolled, not Powertools?** Module 3 introduces **Powertools for AWS Lambda (Python)**
> for logging/metrics/tracing/idempotency. Keeping M2 on stdlib `logging` + raw EMF makes the M3
> upgrade a clear before/after.

## Cleanup

```bash
sam delete --stack-name module-02-users-sync
```

## Notes / learnings

**Status: ✅ all stages complete** (backend → Cognito + Lambda authorizer → tests → observability).

Key takeaways:
- **IaC at scale:** SAM template defines the whole service (table, function, REST API, Cognito,
  authorizer) — `sam deploy` reconciles incrementally; only `sam delete` tears down.
- **Mono-lambda:** one function, internal router on `httpMethod` + `resource`. Easy migration;
  Module 3 splits into single-purpose functions.
- **Cognito = authentication; Lambda authorizer = authorization.** The native Cognito authorizer
  is coarse (valid token → in); the custom Lambda authorizer adds group-based rules. Admin-only
  `DELETE` is enforced via the `isAdmin` flag the authorizer passes in the request context.
- **Auth gotchas:** raw token (no `Bearer`) for the authorizer; re-authenticate after a group
  change (claims are baked into the token at sign-in); default password policy needs a symbol.
- **Testing:** `moto` mocks DynamoDB for fast unit tests; load standalone handler files via
  `importlib` *after* setting env + mocks so module-level setup binds to the mock.
- **Observability without deps:** X-Ray (template flag), structured JSON logs (`_log`), and EMF
  custom metrics (`_emit_metric` — CloudWatch auto-extracts, no `put_metric_data`/IAM).

Gotchas hit (and fixes):
- **Wrong stack name** in commands (`m2-users-service` vs actual `module-02-users-sync` from
  `samconfig.toml`) → empty `$POOL_ID`. Always match `samconfig.toml`.
- **`401` vs `200` confusion**: a `200` without a token meant the authorizer wasn't deployed yet;
  "No changes to deploy" confirmed it had landed in a prior deploy.
- **pytest path**: run from repo root (`module-02-users-sync/tests/unit`) or from the module dir
  (`tests/unit`) — not the repo-root path while inside the module.
- **AWS CLI v2** required (`initiate-auth`, `--cli-binary-format` in M1).
