#!/usr/bin/env bash
# Builds the public history: one commit per release on the `public` branch, with
# the tree of `main` minus the team-only files and none of the private history.
# The first run makes a root commit; later runs add a commit on top of `public`.
#
#   PUBLIC_AUTHOR="Cloutlab <email>" scripts/public_snapshot.sh "CloutFox 3.0.0"
#   git push <github remote> public:main
set -euo pipefail

# Team-only files that stay out of the public tree.
PRIVATE_PATHS=(OPEN_QUESTIONS.md)

die() {
    echo "public_snapshot: $*" >&2
    exit 1
}

message="${1:-}"
[ -n "$message" ] || die "usage: PUBLIC_AUTHOR=\"Name <email>\" $0 <commit message>"
[ -n "${PUBLIC_AUTHOR:-}" ] || die "set PUBLIC_AUTHOR=\"Name <email>\" (the public commit identity)"
[[ "$PUBLIC_AUTHOR" =~ ^(.+)\ \<(.+)\>$ ]] || die "PUBLIC_AUTHOR must look like \"Name <email>\""
name="${BASH_REMATCH[1]}"
email="${BASH_REMATCH[2]}"

source="${SOURCE:-main}"
cd "$(git rev-parse --show-toplevel)"
git diff --quiet && git diff --cached --quiet || die "commit or stash local changes first"
git rev-parse --verify --quiet "$source^{commit}" >/dev/null || die "no such ref: $source"

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
export GIT_INDEX_FILE="$scratch/index"
git read-tree "$source"
git rm -q --cached --ignore-unmatch -- "${PRIVATE_PATHS[@]}"
tree="$(git write-tree)"
unset GIT_INDEX_FILE

# Private references that must not reach the public tree. The names themselves
# are private, so they live in an untracked file shared by this clone's
# worktrees: one extended regex per line in .git/public-deny.
deny="$(git rev-parse --git-common-dir)/public-deny"
[ -s "$deny" ] || die "list the private names (one regex per line) in $deny first"
patterns=(-e 'BEGIN [A-Z ]*PRIVATE KEY')
while IFS= read -r line; do
    [ -n "$line" ] && patterns+=(-e "$line")
done <"$deny"
if git grep -I -n -i -E "${patterns[@]}" "$tree"; then
    die "private references in $source (above)"
fi
if grep -q -i -E "${patterns[@]}" <<<"$PUBLIC_AUTHOR $message"; then
    die "private references in the author or the message"
fi

parent=()
if old="$(git rev-parse --verify --quiet refs/heads/public)"; then
    [ "$(git rev-parse "$old^{tree}")" != "$tree" ] || die "public already matches $source"
    parent=(-p "$old")
fi

# Unsigned: the team's signing key must not appear in the public history.
commit="$(GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email" \
    GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email" \
    git commit-tree --no-gpg-sign "$tree" "${parent[@]}" -m "$message")"
git update-ref refs/heads/public "$commit" ${old:+"$old"}
echo "public -> $commit ($(git rev-list --count public) commits)"
