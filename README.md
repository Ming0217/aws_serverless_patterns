# AWS Serverless Patterns Workshop — Journey Log

A personal log of my way through the AWS **Serverless Patterns** workshop, along with all the
code I write along the way. The workshop builds a food-delivery style application one pattern at
a time — Users, Orders, User Profiles, and Order Status tracking.

- **Workshop:** https://catalog.us-east-1.prod.workshops.aws/workshops/76bc5278-3f38-46e8-b306-f0bfda551f5a/en-US
- **Patterns overview:** https://catalog.us-east-1.prod.workshops.aws/workshops/76bc5278-3f38-46e8-b306-f0bfda551f5a/en-US/patterns
- **Started:** _YYYY-MM-DD_
- **Status:** 🟡 In progress

---

## What this workshop covers

The workshop introduces the synchronous, asynchronous, and polling patterns developers build
every day, layering in tooling and operational concerns as it goes. Core building blocks:

| Service / Tool | Role in the workshop |
| --- | --- |
| **AWS Lambda** | Compute — runs the business logic |
| **Amazon API Gateway** | Synchronous HTTP/REST front door |
| **Amazon DynamoDB** | Serverless data store |
| **Amazon Cognito / JWT authorizers** | Authentication & authorization |
| **Amazon EventBridge** | Event routing (the "orders bus") |
| **AWS SAM / CloudFormation / AWS CLI** | Infrastructure-as-code + automated deploys |
| **Powertools for AWS Lambda (Python)** | Idempotency, logging, metrics, tracing |
| **Amazon CloudWatch** | Observability — logs & custom metrics |

---

## Prerequisites & environment

- [ ] AWS account with appropriate IAM permissions
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] AWS SAM CLI installed (`sam --version`)
- [ ] Python 3.12+ (this repo targets `>=3.12`, see `pyproject.toml`)
- [ ] Workshop environment provisioned (Workshop Studio account / local)

**Setup notes:**

> _Record the exact setup steps you took, account/region, and anything that tripped you up._

---

## Toolchain setup (macOS)

Dependencies the workshop requires: Python 3.11+, Node.js 18+, Boto3, AWS CLI, AWS SAM CLI,
AWS CDK, Powertools for AWS Lambda (Python), Docker, Terraform, jq, and git.

I use **`uv`** to manage Python and Python-based tooling, **Homebrew** for system binaries, and
**npm** for the CDK CLI.

### 1. Python packages & tools (via `uv`)

```bash
# Pin a workshop-compatible Python
uv python install 3.11

# Libraries imported by Lambda / CDK code (added to pyproject.toml)
uv add boto3 aws-lambda-powertools aws-cdk-lib

# Python-based CLIs installed as isolated global tools
uv tool install aws-sam-cli
```

> ⚠️ **Do NOT install the AWS CLI via `uv`/pip.** The PyPI `awscli` package is only ever
> **version 1.x**. AWS CLI **v2** (which the workshop and current AWS docs assume) is *not*
> published to PyPI — install it from Homebrew instead (see below). The SAM CLI, by contrast,
> is genuinely distributed on PyPI, so `uv tool install aws-sam-cli` is correct.

### 2. System binaries (via Homebrew)

```bash
brew install node jq git
brew install awscli               # AWS CLI v2 (the pip/uv 'awscli' is v1 — avoid it)
brew install --cask docker        # Docker Desktop; required for `sam local` testing
```

Confirm you got v2:

```bash
aws --version                     # expect aws-cli/2.x.x
```

If it still reports `aws-cli/1.x`, a v1 shim is earlier on your `PATH`. Remove it and refresh:

```bash
uv tool uninstall awscli          # if you previously installed it via uv
hash -r                           # clear the shell's cached command lookups
which -a aws                      # check which 'aws' wins on PATH
```

### 3. AWS CDK CLI (via npm)

`aws-cdk-lib` (the construct library) is installed via `uv add` above, but the `cdk` CLI ships
through npm:

```bash
npm install -g aws-cdk
```

### 4. Terraform (via HashiCorp's tap)

Terraform was relicensed (BUSL) and removed from Homebrew core, so it now lives in HashiCorp's
own tap. Newer Homebrew also refuses to load third-party taps until you explicitly **trust**
them, which causes:

```
Error: Refusing to load formula hashicorp/tap/terraform from untrusted tap hashicorp/tap.
```

Fix — tap, trust, then install:

```bash
brew tap hashicorp/tap
brew trust hashicorp/tap
brew install hashicorp/tap/terraform
```

> Trusting a tap lets Homebrew run that tap's code without prompting — only do this for vendors
> you trust (HashiCorp is the official source here).
>
> Alternative without the tap: `brew install tfenv && tfenv install latest && tfenv use latest`,
> or grab the macOS `arm64` binary from https://developer.hashicorp.com/terraform/install.

### Verify the install

Run the bundled checker — it verifies every dependency, enforces the workshop's minimum
versions (Python 3.11+, Node 18+), confirms the uv-managed Python libraries import, and checks
whether the Docker daemon is running:

```bash
./verify-dependencies.sh
```

It prints a per-tool pass/fail checklist and exits non-zero if anything is missing or outdated.

<details>
<summary>Manual one-off checks</summary>

```bash
python --version          # 3.11+
node --version            # v18+
docker --version
aws --version
sam --version
cdk --version
terraform version
jq --version
git --version
uv run python -c "import boto3, aws_lambda_powertools; print('python libs OK')"
```
</details>

---

## Progress overview

| # | Module | Pattern | Est. duration | Status |
| --- | --- | --- | --- | --- |
| 1 | Intro to Serverless | Console-built microservice | 20–30 min | ✅ Done (via SAM) |
| 2 | Synchronous Invocation — *Users Service* | Sync request/response + IaC + auth | 2–3 hrs | ✅ Done (via SAM) |
| 3 | Synchronous Invocation + Idempotence — *Orders Service* | Idempotent sync + observability | 1–2 hrs | ⬜ Not started |
| 4 | Asynchronous Invocation — *User Profile Service* | Async (fire-and-forget) | 1–2 hrs | ⬜ Not started |
| 5 | Polling — *Order Status Polling Service* | Polling + event bus | — | ⬜ Not started |

Legend: ⬜ Not started · 🟡 In progress · ✅ Done

---

## Module 1 — Intro to Serverless

**Estimated duration:** 20–30 minutes

Everyone needs to start somewhere. Get familiar with the environment, tools, and terms while
building a microservice. Data storage and retrieval is the cornerstone here: create a **DynamoDB
table**, add data with a **Lambda function**, and retrieve it with another Lambda integrated
with **API Gateway** — all from the web console.

**Objective:** Build a basic store/retrieve microservice from the console and learn core terms.

> **Done programmatically with AWS SAM instead of the console** — see
> [`module-01-intro/`](module-01-intro/) for the template, code, and detailed notes.

**What I did**
- Built the *Example User Service* as IaC: a DynamoDB `Users` table, an `add_user` Lambda
  (invoked directly to seed data), and a `get_user` Lambda fronted by an API Gateway **REST API**
  on `GET /users/{userid}`.
- Deployed with `sam build` / `sam deploy --guided` (stack `m1-intro-serverless`, us-east-1).
- Verified end to end: seeded a user via `aws lambda invoke`, then `curl`ed the API and got the
  record back from DynamoDB.

**Key learnings**
- IaC vs. console: the same table + 2 functions + REST API is one declarative `template.yaml`.
- Direct-invoke event (raw payload) vs. API Gateway proxy integration (HTTP request as event,
  `{statusCode, headers, body}` response).
- Least privilege via SAM policy templates (`DynamoDBRead/WritePolicy`).
- REST API = Resources + Methods + Integration; implicit vs. explicit `AWS::Serverless::Api`.
- Event-driven architecture: events flow **API Gateway ⇄ Lambda**, while client↔API Gateway is
  HTTP and Lambda↔DynamoDB is an SDK call.

**Code / artifacts**
- [`module-01-intro/template.yaml`](module-01-intro/template.yaml) — implicit REST API
- [`module-01-intro/template-explicit-api.yaml`](module-01-intro/template-explicit-api.yaml) — explicit API variant
- [`module-01-intro/src/`](module-01-intro/src/) — `add_user` / `get_user` handlers
- [`module-01-intro/README.md`](module-01-intro/README.md) — full run log + concept notes

**Gotchas**
- AWS CLI **v1 vs v2**: `uv`/pip `awscli` is v1; the v2-only `--cli-binary-format` flag failed
  until switching to the Homebrew v2 (and removing a stray v1 from a mise Python on `PATH`).
- Doubled `https://` in the `curl` URL → `Could not resolve host: https`.

---

## Module 2 — Synchronous Invocation — *Users Service*

**Estimated duration:** 2–3 hours

Revisit the synchronous data-retrieval pattern, but replace manual console clicks with tooling:
**AWS SAM**, **AWS CLI**, and **CloudFormation** to automate and simplify provisioning across
environments (dev, stage, prod). Also learn to authenticate users with **Amazon Cognito** or a
custom **authorizer function using JWTs**.

**Objective:** Rebuild the sync pattern as IaC with automated deploys and added authentication.

> **Done with AWS SAM** — see [`module-02-users-sync/`](module-02-users-sync/) for the template,
> handlers, authorizer, tests, and detailed notes.

**What I did**
- Built a **mono-lambda** Users microservice (one Lambda, internal router) over DynamoDB with a
  REST API: `POST/GET /users`, `GET/PUT/DELETE /users/{userid}`.
- Added **Amazon Cognito** (user pool, app client, hosted-UI domain, admin group) for auth, and a
  custom **Lambda authorizer** that verifies the JWT and enforces the `apiAdmins` group
  (admin-only `DELETE`).
- Wrote **unit tests** (pytest + moto) and gated **integration tests**; added **observability**
  (X-Ray tracing, structured JSON logs, EMF custom metrics).

**Key learnings**
- IaC at scale: one SAM template for table + function + REST API + Cognito + authorizer;
  `sam deploy` updates incrementally (only `sam delete` tears down).
- Mono-lambda vs. single-function tradeoffs (single-function comes in M3).
- **Cognito = authentication; Lambda authorizer = authorization** (coarse native authorizer vs.
  custom group-based logic); 401 (no token) vs. 403 (not allowed).
- `UserPool` vs. `UserPoolClient`; the token carries `cognito:groups` for authz.
- Testing standalone handlers with moto via `importlib`; EMF metrics need no IAM/SDK call.

**Code / artifacts**
- [`module-02-users-sync/template.yaml`](module-02-users-sync/template.yaml) — full stack
- [`module-02-users-sync/src/api/users.py`](module-02-users-sync/src/api/users.py) — mono-lambda handler
- [`module-02-users-sync/src/authorizer/authorizer.py`](module-02-users-sync/src/authorizer/authorizer.py) — Lambda authorizer
- [`module-02-users-sync/tests/`](module-02-users-sync/tests/) — unit + integration tests
- [`module-02-users-sync/README.md`](module-02-users-sync/README.md) — concept notes + run log

**Gotchas**
- Used the wrong stack name in CLI commands (placeholder vs. the real `module-02-users-sync` in
  `samconfig.toml`) → empty query results.
- A `200` without a token meant the authorizer wasn't deployed yet; pass the **raw** ID token (no
  `Bearer`), and **re-authenticate after a group change** (claims are baked in at sign-in).
- Default Cognito password policy requires a special character; run pytest from the right dir.

---

## Module 3 — Synchronous Invocation + Idempotence — *Orders Service*

**Estimated duration:** 1–2 hours

Build an **Orders API** with **single-purpose functions** (one function per request route).
Use **Lambda layers** to share code between functions, and adopt **Powertools for AWS Lambda
(Python)** to make operations **idempotent** and **observable**. Idempotence ensures *Add Order*
can be retried (e.g. after a network blip) but results in only **one** placed order. Write
**integration tests** to verify the API, and add **logging** plus **custom metrics** to observe
internal application state.

**Objective:** Make the sync Add-Order operation idempotent and observable, with shared layers and tests.

**What I did**
- _..._

**Key learnings**
- _How Powertools idempotency works (persistence store, idempotency key)_
- _Single-purpose functions vs. fat functions_
- _Lambda layers for shared code_
- _Custom metrics & structured logging_

**Code / artifacts**
- _..._

**Gotchas**
- _..._

---

## Module 4 — Asynchronous Invocation — *User Profile Service*

**Estimated duration:** 1–2 hours

After placing an order, customers can save a delivery address and a list of favorite
restaurants. Build a **User Profile Service** made up of an **Address Service** and a
**Favorite Service**, both running **asynchronously** — the user gets immediate acknowledgement
that their info was accepted without waiting for downstream processing to finish. This data also
feeds tasks like restaurant leaderboard calculations and delivery-zone map updates.

**Objective:** Build async Address + Favorite services that ack immediately and process later.

**What I did**
- _..._

**Key learnings**
- _Sync vs. async invocation tradeoffs (latency vs. eventual consistency)_
- _How immediate acknowledgement is returned while work continues downstream_

**Code / artifacts**
- _..._

**Gotchas**
- _..._

---

## Module 5 — Polling — *Order Status Polling Service*

**Estimated duration:** _(not specified)_

A hungry customer wants to know when their order is prepared and when to expect delivery. Build a
**polling** service so customers can track order status — **polling** being the process of
repeatedly calling an API endpoint and comparing responses to detect status changes. Also create
an **orders bus** that connects events sent by restaurants and delivery riders into the orders
table.

**Objective:** Let customers track order status via polling, fed by an event-driven orders bus.

**What I did**
- _..._

**Key learnings**
- _Polling mechanics and when to use it vs. push (e.g. WebSockets)_
- _Event bus routing events from multiple producers into the orders table_

**Code / artifacts**
- _..._

**Gotchas**
- _..._

---

## Cleanup

**Objective:** Tear down all deployed resources to avoid ongoing charges.

- [ ] `sam delete` (or stack deletion) run for each deployed module
- [ ] DynamoDB tables removed
- [ ] Cognito user pools removed
- [ ] EventBridge buses/rules removed
- [ ] CloudWatch log groups cleaned up
- [ ] Confirmed no lingering resources in the console

**Notes:**
- _..._

---

## Repo layout

```
aws_serverless_patterns_workshop/
├── README.md           # this journey log
├── main.py             # scaffold entry point
├── pyproject.toml      # project metadata (Python >=3.12)
└── (module folders added as the workshop progresses)
    ├── module-01-intro/
    ├── module-02-users-sync/
    ├── module-03-orders-idempotent/
    ├── module-04-user-profile-async/
    └── module-05-order-status-polling/
```

> As I work through each module I'll add its folder holding that module's Lambda code,
> SAM template, and tests.

---

## Resources

- [AWS SAM documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [Powertools for AWS Lambda (Python)](https://docs.powertools.aws.dev/lambda/python/latest/)
- [Amazon API Gateway docs](https://docs.aws.amazon.com/apigateway/)
- [AWS Lambda docs](https://docs.aws.amazon.com/lambda/)
- [Amazon DynamoDB docs](https://docs.aws.amazon.com/dynamodb/)
- [Amazon Cognito docs](https://docs.aws.amazon.com/cognito/)
- [Amazon EventBridge docs](https://docs.aws.amazon.com/eventbridge/)
- [Serverless Land — patterns](https://serverlessland.com/patterns)
