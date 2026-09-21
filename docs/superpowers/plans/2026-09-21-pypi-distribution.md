# PyPI Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `dataform-context-mcp` on PyPI with automated, trusted-publishing releases, and switch every install snippet to `uvx --from dataform-context-mcp@latest` so users receive fixes at the next MCP server start.

**Architecture:** Packaging metadata is completed in `pyproject.toml`; a new tag-triggered GitHub Actions workflow builds with `uv build` and publishes via OIDC trusted publishing (TestPyPI for `rc` tags, PyPI otherwise); `release.sh` shrinks to bump + lock + commit + tag; all 7 snippet files and both READMEs move to the `@latest` form and document the network requirement at start-up.

**Tech Stack:** Python >= 3.12, `uv` 0.12 (`uv build`, `uv version`, `uv lock`), GitHub Actions, `pypa/gh-action-pypi-publish`, PyPI trusted publishing.

**Spec:** `docs/superpowers/specs/2026-09-21-pypi-distribution-design.md`

## Global Constraints

- Python floor: `requires-python = ">=3.12"`. No new runtime dependency (`mcp`, `sqlglot` only).
- Every GitHub Action is pinned by full commit SHA with the tag as a trailing comment.
- Snippet form, everywhere, verbatim: `["--from", "dataform-context-mcp@latest", "dataform-context", "serve"]`. `command` stays the absolute `uvx` path.
- No `git push`, no tag creation, no history rewrite from the agent: the user runs those with the `!` prefix. One commit per task is allowed.
- Lint gate before each commit: `uv run ruff check . && uv run ruff format --check .` (ruff also formats code blocks inside `.md` files).
- Tests must pass: `uv run pytest -q`.
- README.md is French, README.en.md is English; every documentation change is applied to both.
- Do not touch `docs/superpowers/**` except this plan's checkboxes.
- The GitHub repo stays private until the user decides otherwise. The local branch `private-history` and tags `mvp-*` are never pushed.

## Findings that shaped the plan

- `uvx --from pkg@latest cmd` refreshes the cache on every run (uv docs). Offline, it fails; there is no cache fallback (tested 2026-09-21). Decision B: document it, no wrapper.
- `README.en.md` and `.mcp.json.example` were never pinned by `release.sh` (it only greps `README.md` and `integrations/`): they currently point at `main` through `git+ssh`. This plan replaces them too.
- `README.en.md` lacks the two governance bullets added to `README.md` on 2026-09-21 (trust boundary, cache contents). Task 5 adds them.
- No `LICENSE` file exists. PyPI and open source need one. Task 1 adds MIT; **the user confirms the licence choice before Task 1 is committed.**
- PyPI name `dataform-context-mcp` is free on pypi.org and test.pypi.org (HTTP 404 on both JSON endpoints, 2026-09-21).

---

### Task 1: Packaging metadata and licence

**Files:**
- Create: `LICENSE`
- Modify: `pyproject.toml:1-13` (`[project]` table)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a wheel and sdist under `dist/` that expose the `dataform-context` console script; Task 2's workflow relies on `uv build` producing exactly these two files.

- [ ] **Step 1: Confirm the licence with the user**

Ask: "MIT (default, permissive, one paragraph) or Apache-2.0 (adds an explicit patent grant)?" Do not proceed until answered. If MIT, continue; if Apache-2.0, use the canonical Apache-2.0 text from https://www.apache.org/licenses/LICENSE-2.0.txt and set `license = "Apache-2.0"` below.

- [ ] **Step 2: Write `LICENSE` (MIT)**

```text
MIT License

Copyright (c) 2026 Vincent Gossiaux

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Complete the `[project]` table**

Replace lines 1-13 of `pyproject.toml` with:

```toml
[project]
name = "dataform-context-mcp"
version = "0.4.0"
description = "Deterministic, self-hosted MCP server exposing structured Dataform pipeline context (lineage, schemas, layers) to coding agents"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [
    { name = "Vincent Gossiaux" }
]
requires-python = ">=3.12"
keywords = ["dataform", "bigquery", "mcp", "lineage", "analytics-engineering"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Database",
    "Topic :: Software Development :: Libraries",
]
dependencies = [
    "mcp[cli]>=2.0.0",
    "sqlglot>=30.17.0",
]

[project.urls]
Homepage = "https://github.com/vgossiaux/dataform-context-mcp"
Repository = "https://github.com/vgossiaux/dataform-context-mcp"
Issues = "https://github.com/vgossiaux/dataform-context-mcp/issues"
Changelog = "https://github.com/vgossiaux/dataform-context-mcp/releases"
```

Leave `version` at `0.4.0`: Task 6 bumps it through `release.sh`.

- [ ] **Step 4: Ignore build output**

Append to `.gitignore`:

```
dist/
```

- [ ] **Step 5: Build and smoke-test the wheel**

Run:
```bash
rm -rf dist && uv build && ls dist && uvx --from dist/dataform_context_mcp-0.4.0-py3-none-any.whl dataform-context --help | head -3
```
Expected: `dist/` holds `dataform_context_mcp-0.4.0-py3-none-any.whl` and `dataform_context_mcp-0.4.0.tar.gz`; the help text starts with `usage: dataform-context`. Then check the metadata landed:
```bash
unzip -p dist/dataform_context_mcp-0.4.0-py3-none-any.whl '*/METADATA' | grep -E '^(License|License-File|Project-URL|Classifier: Development)'
```
Expected: `License-Expression: MIT` (or `License: MIT`), `License-File: LICENSE`, four `Project-URL` lines, one `Classifier: Development Status :: 4 - Beta`.

- [ ] **Step 6: Lint, test, commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
rm -rf dist
git add LICENSE pyproject.toml .gitignore uv.lock
git commit -m "build: complete PyPI metadata and add MIT licence"
```
(`uv.lock` may have been touched by `uv build`; include it if `git status` shows it.)

---

### Task 2: Release workflow with trusted publishing

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `.github/workflows/ci.yml:1-8` (add top-level `permissions`)

**Interfaces:**
- Consumes: `uv build` output from Task 1 (two files in `dist/`).
- Produces: a workflow that publishes to TestPyPI for tags matching `v*rc*` and to PyPI for other `v*` tags. Task 7's checklist names the environments `testpypi` and `pypi` and the workflow file name `release.yml`; keep them exact.

- [ ] **Step 1: Write `release.yml`**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86 # v5
      - name: Tag must match pyproject version
        run: |
          expected="v$(uv version --short)"
          if [ "$expected" != "${GITHUB_REF_NAME}" ]; then
            echo "tag ${GITHUB_REF_NAME} != pyproject version ${expected}" >&2
            exit 1
          fi
      - run: uv build
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: dist
          path: dist/
          if-no-files-found: error

  publish-testpypi:
    if: contains(github.ref_name, 'rc')
    needs: build
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: testpypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # release/v1
        with:
          repository-url: https://test.pypi.org/legacy/

  publish-pypi:
    if: ${{ !contains(github.ref_name, 'rc') }}
    needs: build
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # release/v1
```

SHAs were resolved on 2026-09-21 with `git ls-remote`. Re-verify each one before committing:
```bash
bash -c 'for spec in "actions/checkout v4" "astral-sh/setup-uv v5" "actions/upload-artifact v4" "actions/download-artifact v4" "pypa/gh-action-pypi-publish release/v1"; do set -- $spec; echo "$1 $2 $(git ls-remote --tags --heads https://github.com/$1 | grep -E "refs/(tags|heads)/$2(\^\{\})?$" | tail -1 | cut -f1)"; done'
```
Expected: five lines whose SHAs equal the ones in the file. If one differs, use the freshly printed value.

- [ ] **Step 2: Lock down `ci.yml` permissions**

Insert after line 7 (`  pull_request:`) of `.github/workflows/ci.yml`, before `jobs:`:

```yaml

permissions:
  contents: read
```

- [ ] **Step 3: Validate both workflows**

Run:
```bash
uv run --with pyyaml python - <<'EOF'
import yaml
for f in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
    d = yaml.safe_load(open(f))
    assert d["permissions"] == {"contents": "read"}, f
    print(f, "ok", sorted(d["jobs"]))
r = yaml.safe_load(open(".github/workflows/release.yml"))
assert r["jobs"]["publish-pypi"]["environment"] == "pypi"
assert r["jobs"]["publish-testpypi"]["environment"] == "testpypi"
assert r["jobs"]["publish-pypi"]["permissions"] == {"id-token": "write"}
print("release.yml environments and permissions ok")
EOF
```
Expected: three `ok` lines. Then reproduce the version guard locally:
```bash
GITHUB_REF_NAME=v0.4.0 bash -c 'expected="v$(uv version --short)"; [ "$expected" = "$GITHUB_REF_NAME" ] && echo guard-pass'
GITHUB_REF_NAME=v9.9.9 bash -c 'expected="v$(uv version --short)"; [ "$expected" = "$GITHUB_REF_NAME" ] || echo guard-blocks'
```
Expected: `guard-pass` then `guard-blocks`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/ci.yml
git commit -m "ci: add tag-triggered release workflow with PyPI trusted publishing"
```

---

### Task 3: Simplify `release.sh`

**Files:**
- Modify: `scripts/release.sh` (whole file)

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/release.sh <version>` bumps `pyproject.toml`, runs `uv lock`, commits `pyproject.toml` + `uv.lock`, creates annotated tag `v<version>`, never pushes. Task 6 calls it.

- [ ] **Step 1: Write the failing check**

The script has no test harness; the check is a dry run in a throwaway clone. Run it first to see the current behaviour fail the new expectations:

```bash
rm -rf /tmp/relcheck && git clone -q . /tmp/relcheck && (cd /tmp/relcheck && git config user.email t@example.com && git config user.name t && scripts/release.sh 9.9.9 >/dev/null 2>&1; echo "exit=$?"; git show --stat --oneline HEAD | grep -E "uv.lock|README|integrations" ; grep -c "9.9.9" uv.lock)
```
Expected today: `exit=0`, `README.md` and `integrations/...` appear in the commit stat, `uv.lock` does not, and `grep -c` prints `0` (lock not synced). The new expectations are the inverse.

- [ ] **Step 2: Rewrite the script**

Replace the whole of `scripts/release.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

# scripts/release.sh — cut a release: bump pyproject.toml, sync uv.lock, commit, tag.
#
# Distribution model: the package is published to PyPI by .github/workflows/release.yml
# when the tag is pushed (trusted publishing). Install snippets use
# `uvx --from dataform-context-mcp@latest`, so users pick up the new version at their
# next MCP server start — nothing to rewrite in the docs here.
#
# Usage: scripts/release.sh <version>      e.g. scripts/release.sh 0.5.0
#        scripts/release.sh 0.5.0rc1       -> publishes to TestPyPI (dry run)
# Does NOT push. Review locally, then: git push origin main v<version>

VERSION="${1:?Usage: scripts/release.sh <version> (e.g. 0.5.0)}"
TAG="v${VERSION}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree not clean — commit or stash first." >&2
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag $TAG already exists." >&2
  exit 1
fi

echo "== Bumping pyproject.toml to ${VERSION} =="
uv version "${VERSION}"

echo "== Syncing uv.lock =="
uv lock

echo
echo "== Diff =="
git diff --stat

git add pyproject.toml uv.lock
git commit -m "chore(release): ${TAG}"
git tag -a "$TAG" -m "Release ${TAG}"

echo
echo "Done: ${TAG} committed and tagged locally."
echo "Review:  git show ${TAG}"
echo "Publish: git push origin main ${TAG}"
```

`uv version <x>` (uv >= 0.7) rewrites `version = "..."` in `pyproject.toml` portably; it replaces the macOS-only `sed -i ''`.

- [ ] **Step 3: Re-run the check**

```bash
rm -rf /tmp/relcheck && git clone -q . /tmp/relcheck && (cd /tmp/relcheck && git config user.email t@example.com && git config user.name t && scripts/release.sh 9.9.9 >/dev/null 2>&1; echo "exit=$?"; git show --stat --oneline HEAD | grep -E "pyproject|uv.lock|README|integrations"; grep -c '^version = "9.9.9"' pyproject.toml; grep -c 'version = "9.9.9"' uv.lock; git tag -l v9.9.9)
```
Expected: `exit=0`; stat lists `pyproject.toml` and `uv.lock` only; both greps print `1`; `v9.9.9` is listed. Clean up: `rm -rf /tmp/relcheck`.

- [ ] **Step 4: Commit**

```bash
chmod +x scripts/release.sh
git add scripts/release.sh
git commit -m "chore(release): drop snippet pinning, sync uv.lock, use uv version"
```

---

### Task 4: Switch every install snippet to `@latest`

**Files:**
- Modify: `.mcp.json.example`
- Modify: `integrations/antigravity/mcp_config.json.example`
- Modify: `integrations/claude-code/mcp.json.example`
- Modify: `integrations/codex/config.toml.snippet`
- Modify: `integrations/copilot/mcp.json.example`
- Modify: `integrations/cursor/mcp.json.example`
- Modify: `integrations/windsurf/mcp_config.json.snippet`
- Modify: `README.md:42`, `README.md:92`, `README.md:221`
- Modify: `README.en.md:42`, `README.en.md:91`, `README.en.md:220`

**Interfaces:**
- Consumes: nothing (the package is not on PyPI yet; snippets become valid at Task 6).
- Produces: zero `git+ssh` occurrences outside `docs/superpowers/`.

- [ ] **Step 1: Write the failing check**

```bash
grep -rn "git+ssh" --exclude-dir=.git --exclude-dir=docs --exclude-dir=.venv . ; echo "count=$(grep -rl 'git+ssh' --exclude-dir=.git --exclude-dir=docs --exclude-dir=.venv . | wc -l | tr -d ' ')"
```
Expected today: 9 files listed, `count=9`. Target: `count=0`.

- [ ] **Step 2: Rewrite the JSON/TOML snippet files**

In each of the 6 `integrations/*` files and `.mcp.json.example`, replace the two-line `args` value with the single line below (JSON files):

```json
      "args": ["--from", "dataform-context-mcp@latest", "dataform-context", "serve"]
```

and in `integrations/codex/config.toml.snippet`:

```toml
args = ["--from", "dataform-context-mcp@latest", "dataform-context", "serve"]
```

Keep every other key (`type`, `command`, server name) unchanged. Validate the JSON files parse:
```bash
for f in .mcp.json.example integrations/*/mcp.json.example integrations/*/mcp_config.json.example integrations/*/mcp_config.json.snippet; do python3 -c "import json,sys; json.load(open('$f')); print('ok', '$f')"; done
```
Expected: 6 `ok` lines.

- [ ] **Step 3: Rewrite the README snippets**

In `README.md` line 42-43 and `README.en.md` line 42-43 (Claude Code block), replace the two `args` lines with:
```json
      "args": ["--from", "dataform-context-mcp@latest", "dataform-context", "serve"]
```
In `README.md:92` and `README.en.md:91` (Codex block):
```toml
args = ["--from", "dataform-context-mcp@latest", "dataform-context", "serve"]
```
In `README.md:221` replace the inline command with:
```
`uvx --from dataform-context-mcp@latest dataform-context …` :
```
In `README.en.md:220`:
```
`uvx --from dataform-context-mcp@latest dataform-context …`:
```

- [ ] **Step 4: Re-run the check and commit**

```bash
grep -rl "git+ssh" --exclude-dir=.git --exclude-dir=docs --exclude-dir=.venv . | wc -l
```
Expected: `0`.
```bash
uv run ruff format --check .
git add .mcp.json.example integrations README.md README.en.md
git commit -m "docs: install from PyPI with uvx --from dataform-context-mcp@latest"
```

---

### Task 5: Document the network requirement, version pinning and align both READMEs

**Files:**
- Modify: `README.md` (Governance block lines 303-323, new subsection after the Claude Code install block ending line 65)
- Modify: `README.en.md` (Governance block, same new subsection after its Claude Code install block)

**Interfaces:**
- Consumes: snippet form from Task 4.
- Produces: documentation only.

- [ ] **Step 1: Governance block, French**

In `README.md`, replace the bullet

```markdown
- **Zéro appel réseau à l'exécution** : lecture des fichiers du repo + shell-out
  `dataform compile --json` local. Pas d'accès au warehouse, pas de télémétrie.
```
with
```markdown
- **Zéro appel réseau du serveur** : lecture des fichiers du repo + shell-out
  `dataform compile --json` local. Pas d'accès au warehouse, pas de télémétrie. Seul `uvx`
  interroge PyPI au démarrage pour servir la dernière version publiée (voir « Figer une
  version ou travailler hors ligne »).
```

- [ ] **Step 2: Governance block, English**

In `README.en.md`, replace

```markdown
- **Zero network calls at runtime**: reads the repo's files + local
  `dataform compile --json` shell-out. No warehouse access, no telemetry.
```
with
```markdown
- **Zero network calls from the server**: reads the repo's files + local
  `dataform compile --json` shell-out. No warehouse access, no telemetry. Only `uvx`
  reaches PyPI at start-up to serve the latest published version (see "Pin a version or
  work offline").
```
Then, right after the `- **Local data only**` bullet, add the two bullets missing from the English version:
```markdown
- **Trust boundary = the indexed repo**: `dataform compile` runs the target repo's
  JavaScript (`includes/`, `*.js`) with the user's privileges on every re-index. Only
  index Dataform repos you trust; never point `--repo` at an unreviewed clone.
- **Cache contents**: the SQLite index holds the compiled SQL of every action
  (`query`, `incremental_query`). The file is created with mode `0600` (owner-readable
  only). To purge: `rm -rf ~/.cache/dataform-context-mcp/`.
```

- [ ] **Step 3: New subsection, French**

In `README.md`, after the paragraph ending "…goldens). Ou copiez la commande" block of the Claude Code section (before `## Installation avec Cursor`, line 67), insert:

```markdown
### Figer une version ou travailler hors ligne

`@latest` demande à `uvx` de vérifier PyPI à chaque démarrage du serveur : vous recevez
les correctifs sans rien faire, au prix d'un accès réseau obligatoire au démarrage (1 à
3 s). Hors ligne, le serveur ne démarre pas. Pour figer une version, ou le temps d'une
coupure, remplacez `@latest` par une version exacte :

```json
"args": ["--from", "dataform-context-mcp@0.5.0", "dataform-context", "serve"]
```

Une version figée ne reçoit plus les correctifs : pensez à la remettre à jour.
```

- [ ] **Step 4: New subsection, English**

In `README.en.md`, at the same position (before `## Install with Cursor` or the equivalent heading), insert:

```markdown
### Pin a version or work offline

`@latest` makes `uvx` check PyPI on every server start: fixes reach you with no action on
your side, at the cost of a mandatory network access at start-up (1 to 3 s). Offline, the
server does not start. To pin a version, or to ride out an outage, replace `@latest` with an
exact version:

```json
"args": ["--from", "dataform-context-mcp@0.5.0", "dataform-context", "serve"]
```

A pinned version no longer receives fixes: remember to bump it.
```

- [ ] **Step 5: Verify and commit**

```bash
grep -n "Figer une version\|Pin a version\|Zéro appel réseau du serveur\|Zero network calls from the server\|Trust boundary" README.md README.en.md
uv run ruff format --check .
```
Expected: 5 matching lines (2 headings, 2 governance bullets, 1 English trust-boundary bullet); format check clean.
```bash
git add README.md README.en.md
git commit -m "docs: network requirement at start-up, version pinning, align English governance block"
```

---

### Task 6: Cut `v0.5.0rc1` (TestPyPI dry run) then `v0.5.0`

**Files:**
- Modify (via script): `pyproject.toml`, `uv.lock`

**Interfaces:**
- Consumes: `scripts/release.sh` from Task 3, `release.yml` from Task 2, PyPI/TestPyPI trusted publishers and GitHub environments from Task 7 (the user must have completed Task 7 first).
- Produces: `dataform-context-mcp` 0.5.0 on PyPI.

- [ ] **Step 1: Pre-flight**

```bash
git status --short; git log --oneline -1; uv run pytest -q | tail -1; uv run ruff check . && uv run ruff format --check .
```
Expected: clean tree, all tests pass, lint clean. Confirm with the user that Task 7 is done on pypi.org, test.pypi.org and GitHub.

- [ ] **Step 2: Dry run tag (user runs)**

Hand these to the user; the agent does not run them:
```
! scripts/release.sh 0.5.0rc1
! git push origin main v0.5.0rc1
```
Then watch: `gh run watch --exit-status $(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')`. Expected: `build` and `publish-testpypi` green, `publish-pypi` skipped.

- [ ] **Step 3: Verify the TestPyPI install**

```bash
uvx --index-url https://test.pypi.org/simple/ --index-strategy unsafe-best-match --from "dataform-context-mcp==0.5.0rc1" dataform-context --help | head -2
```
Expected: `usage: dataform-context …`. If TestPyPI lacks `mcp`/`sqlglot`, add `--extra-index-url https://pypi.org/simple/`.

- [ ] **Step 4: Real release (user runs)**

```
! scripts/release.sh 0.5.0
! git push origin main v0.5.0
```
Watch the run as in Step 2. Expected: `publish-pypi` green after the user approves the `pypi` environment.

- [ ] **Step 5: End-to-end check from a clean cache**

```bash
uv cache clean dataform-context-mcp >/dev/null 2>&1; uvx --from dataform-context-mcp@latest dataform-context --help | head -2
```
Expected: help text. Then, in a real Dataform repo whose `.mcp.json` carries the new snippet: `/mcp` restart, ask the agent to run `check_setup`, expect `"ok": true` and `index_meta.dataform_version` filled.

---

### Task 7: One-time account setup (user-only checklist)

**Files:**
- Create: `docs/publishing.md`

**Interfaces:**
- Consumes: names fixed in Task 2: workflow `release.yml`, environments `pypi` and `testpypi`.
- Produces: the checklist the user follows once; Task 6 depends on it being completed.

- [ ] **Step 1: Write `docs/publishing.md`**

```markdown
# Publier une release

Une fois, avant la première publication :

1. **Compte PyPI** : créer un compte sur https://pypi.org, activer le 2FA (obligatoire).
   Faire de même sur https://test.pypi.org (compte distinct).
2. **Trusted publisher PyPI** : https://pypi.org/manage/account/publishing/ → « Add a new
   pending publisher » :
   - PyPI project name : `dataform-context-mcp`
   - Owner : `vgossiaux`
   - Repository name : `dataform-context-mcp`
   - Workflow name : `release.yml`
   - Environment name : `pypi`
3. **Trusted publisher TestPyPI** : même formulaire sur
   https://test.pypi.org/manage/account/publishing/, environment name `testpypi`.
4. **Environments GitHub** : Settings → Environments du repo :
   - `pypi` : « Required reviewers » = vous. Chaque publication attend votre approbation.
   - `testpypi` : sans reviewer.
5. **2FA GitHub** activé sur le compte.

À chaque release :

1. Arbre propre sur `main`, tests verts : `uv run pytest -q`.
2. `scripts/release.sh X.Y.Z` (ou `X.Y.ZrcN` pour un essai sur TestPyPI).
3. `git push origin main vX.Y.Z`.
4. Approuver le job `publish-pypi` dans l'onglet Actions.
5. Vérifier : `uvx --from dataform-context-mcp@latest dataform-context --help`.

Les utilisateurs reçoivent la version au prochain démarrage de leur serveur MCP.
```

- [ ] **Step 2: Link it from both READMEs**

In `README.md`, inside the `Architecture du code & tests` details block (line 340-367), append a bullet:
```markdown
- Publication PyPI : [`docs/publishing.md`](docs/publishing.md).
```
In `README.en.md`, inside the equivalent block, append:
```markdown
- PyPI publishing: [`docs/publishing.md`](docs/publishing.md).
```

- [ ] **Step 3: Commit**

```bash
uv run ruff format --check .
git add docs/publishing.md README.md README.en.md
git commit -m "docs: add one-time PyPI publishing checklist"
```

---

## Execution order

Tasks 1 to 5 and 7 are independent in files except `README.md`/`README.en.md`, shared by Tasks 4, 5 and 7: run Task 4 first, then 5, then 7 sequentially, or give them to one agent. Task 6 is last and needs the user for every push and for the Task 7 checklist.

## Final verification

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pytest -q`
- [ ] `grep -rl "git+ssh" --exclude-dir=.git --exclude-dir=docs --exclude-dir=.venv . | wc -l` prints `0`
- [ ] `https://pypi.org/project/dataform-context-mcp/` shows 0.5.0 with the MIT licence and the README rendered
