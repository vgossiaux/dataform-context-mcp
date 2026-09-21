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
