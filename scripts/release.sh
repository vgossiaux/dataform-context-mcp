#!/usr/bin/env bash
set -euo pipefail

# scripts/release.sh — cut a release: bump pyproject.toml, pin every install
# snippet (README + integrations/*) to the new tag, commit, and tag.
#
# Why: uvx installs of this tool are consumed as `git+ssh://.../dataform-context-mcp`
# by client repos. Left unpinned, that resolves to whatever is on `main` at the
# moment the MCP server (re)starts — i.e. unreviewed code execution on every
# restart once this repo's SSH access is shared beyond a single maintainer.
# Every install snippet in this repo must always show a pinned `@vX.Y.Z`.
#
# Usage: scripts/release.sh <version>   (e.g. scripts/release.sh 0.2.0)
# Does NOT push — review the commit/tag locally, then:
#   git push origin main --tags

VERSION="${1:?Usage: scripts/release.sh <version> (e.g. 0.2.0)}"
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
sed -i '' -E "s/^version = \"[^\"]+\"/version = \"${VERSION}\"/" pyproject.toml

echo "== Pinning install snippets to @${TAG} =="
# Only the uvx-style git+ssh install URL, never the plain `git clone` URL used
# for dev setup (that one legitimately tracks main).
PATTERN='git\+ssh://git@github\.com/vgossiaux/dataform-context-mcp(@[A-Za-z0-9._/-]+)?'
REPLACEMENT="git+ssh://git@github.com/vgossiaux/dataform-context-mcp@${TAG}"

FILES=$(grep -rl "git+ssh://git@github.com/vgossiaux/dataform-context-mcp" README.md integrations/ 2>/dev/null || true)
if [[ -z "$FILES" ]]; then
  echo "No install snippets found referencing the git+ssh URL — nothing to pin." >&2
else
  for f in $FILES; do
    sed -i '' -E "s#${PATTERN}#${REPLACEMENT}#g" "$f"
    echo "  pinned: $f"
  done
fi

echo
echo "== Diff =="
git diff --stat

git add pyproject.toml README.md integrations/
git commit -m "chore(release): ${TAG}"
git tag -a "$TAG" -m "Release ${TAG}"

echo
echo "Done: ${TAG} committed and tagged locally."
echo "Review: git show ${TAG}"
echo "Publish: git push origin main --tags"
