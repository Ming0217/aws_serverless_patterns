#!/usr/bin/env bash
#
# verify-dependencies.sh
# Checks that all AWS Serverless Patterns Workshop dependencies are installed
# and meet the workshop's minimum version requirements.
#
# Usage:  ./verify-dependencies.sh
#
# Exit code 0 = all good, 1 = one or more checks failed (handy for CI/hooks).

# Shell safety flags:
#   -u  treat use of an unset variable as an error (catches typos)
#   -o pipefail  a pipeline fails if ANY command in it fails, not just the last
# We deliberately do NOT use `-e` (exit-on-error): we want every check to run so
# the user sees a full report, not just the first failure.
set -uo pipefail

# ---- output helpers ---------------------------------------------------------
# Only emit ANSI color codes when stdout is an interactive terminal ([[ -t 1 ]]).
# When the output is piped/redirected (e.g. in CI), we blank the codes so logs
# don't fill up with escape sequences.
if [[ -t 1 ]]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=""; RED=""; YELLOW=""; BOLD=""; RESET=""
fi

# Running tallies used by the helpers below and printed in the final summary.
PASS=0
FAIL=0

# Print a result line and update the counters. %-28s left-pads the name into a
# 28-char column so the values line up.
ok()   { printf "  ${GREEN}✔${RESET} %-28s %s\n" "$1" "$2"; PASS=$((PASS+1)); }
bad()  { printf "  ${RED}x${RESET} %-28s %s\n" "$1" "${2:-not found}"; FAIL=$((FAIL+1)); }
warn() { printf "  ${YELLOW}!${RESET} %-28s %s\n" "$1" "$2"; }  # advisory only, no counter change

# version_ge A B  ->  returns success (0) if version A >= version B.
# Trick: print both versions, sort them "version-aware" (sort -V), and take the
# smallest (head -n1). If the smallest equals B, then A must be >= B.
version_ge() {
  [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]
}

# Pull the first "x.y" or "x.y.z" number out of arbitrary tool output. Different
# tools format --version differently (e.g. "git version 2.39.3",
# "aws-cli/2.15.0 ..."), so we just grab the first version-looking token.
extract_version() {
  grep -Eo '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1
}

# ---- CLI tool check with optional minimum version ---------------------------
# Usage: check_cli <display name> <command> <version-args> <min-version-or-empty>
#   - confirms the command exists on PATH
#   - runs it to capture a version string
#   - if a minimum is given, enforces it; otherwise just reports presence
check_cli() {
  local name="$1" cmd="$2" vargs="$3" min="${4:-}"

  # command -v is the portable way to ask "is this on PATH?" without running it.
  if ! command -v "$cmd" >/dev/null 2>&1; then
    bad "$name" "not found on PATH"
    return
  fi

  local raw ver
  # Capture both stdout and stderr (2>&1): some tools print their version to stderr.
  # $vargs is intentionally unquoted so multi-word args (e.g. "--version") split.
  raw="$($cmd $vargs 2>&1)"
  ver="$(printf '%s' "$raw" | extract_version)"

  if [[ -n "$min" ]]; then
    # A minimum was requested: pass only if we parsed a version AND it's >= min.
    if [[ -n "$ver" ]] && version_ge "$ver" "$min"; then
      ok "$name" "v$ver (>= $min)"
    else
      bad "$name" "v${ver:-?} (needs >= $min)"
    fi
  else
    # No minimum: presence is enough. ${ver:+v$ver} prints "v<ver>" only if ver is set.
    ok "$name" "${ver:+v$ver}"
  fi
}

# ---- Python library check (uv-managed project venv) -------------------------
# Usage: check_pylib <display name> <python import name>
# These libraries live in the uv project virtualenv, not on the system Python,
# so we run the import through `uv run` when uv is available. That guarantees we
# test the exact interpreter/venv the Lambda & CDK code will use.
check_pylib() {
  local name="$1" mod="$2" runner out ver

  if command -v uv >/dev/null 2>&1; then
    runner=(uv run --quiet python)   # array form keeps the words separate and quotable
  else
    runner=(python3)                 # fall back to system python if uv isn't installed
  fi

  # Import the module and print its __version__ (empty string if it has none).
  # If the import fails (not installed), the python process exits non-zero and
  # we report it as a failure with the fix command.
  if out="$("${runner[@]}" -c "import ${mod} as m; print(getattr(m,'__version__',''))" 2>/dev/null)"; then
    ver="$(printf '%s' "$out" | extract_version)"
    ok "$name" "${ver:+v$ver}${ver:+ }(import ok)"
  else
    bad "$name" "import '${mod}' failed (run: uv add ${name})"
  fi
}

# ============================================================================
# Run the checks, grouped for readable output.
# ============================================================================
printf "\n${BOLD}AWS Serverless Patterns Workshop — dependency check${RESET}\n\n"

# Workshop version gates: Python 3.11+ and Node 18+. The rest just need to exist.
printf "${BOLD}Runtimes & version managers${RESET}\n"
check_cli "Python"        "python3"   "--version"  "3.11"
check_cli "Node.js"       "node"      "--version"  "18.0.0"
check_cli "uv"            "uv"        "--version"  ""

printf "\n${BOLD}AWS tooling${RESET}\n"
check_cli "AWS CLI"       "aws"       "--version"  "2.0.0"   # must be v2 (the pip/uv 'awscli' is v1)
check_cli "AWS SAM CLI"   "sam"       "--version"  ""
check_cli "AWS CDK (CLI)" "cdk"       "--version"  ""

printf "\n${BOLD}Infrastructure & utilities${RESET}\n"
check_cli "Terraform"     "terraform" "version"    ""   # note: terraform uses "version", not "--version"
check_cli "Docker"        "docker"    "--version"  ""
check_cli "jq"            "jq"        "--version"  ""
check_cli "git"           "git"       "--version"  ""

printf "\n${BOLD}Python libraries (uv project venv)${RESET}\n"
# First arg is the human/pip name (used in the "uv add" hint); second is the
# actual import name, which sometimes differs (aws-cdk-lib -> import aws_cdk).
check_pylib "boto3"                  "boto3"
check_pylib "aws-lambda-powertools"  "aws_lambda_powertools"
check_pylib "aws-cdk-lib"            "aws_cdk"

# ---- Docker daemon (optional but needed for `sam local`) --------------------
# Having the docker CLI installed isn't the same as the daemon running. `sam
# local invoke/start-api` need a live daemon, so we check and WARN (not fail)
# if it's down — you can still deploy to AWS without it.
printf "\n${BOLD}Runtime health${RESET}\n"
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    ok "Docker daemon" "running"
  else
    warn "Docker daemon" "installed but not running (start Docker Desktop for 'sam local')"
  fi
fi

# ---- summary ----------------------------------------------------------------
printf "\n${BOLD}Summary:${RESET} ${GREEN}%d passed${RESET}, ${RED}%d failed${RESET}\n\n" "$PASS" "$FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  printf "${RED}Some dependencies are missing or below the required version.${RESET}\n"
  printf "See the Toolchain setup section in README.md for install commands.\n\n"
  exit 1   # non-zero so callers (CI, hooks) can detect the failure
fi
printf "${GREEN}All workshop dependencies are present.${RESET}\n\n"
