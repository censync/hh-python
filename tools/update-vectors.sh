#!/bin/sh
# Copies the golden vectors from a checkout of hh-cpp and records where they came from in
# testdata/SOURCE. The checkout must be clean and at a release tag (vMAJOR.MINOR.PATCH).
#
# usage: tools/update-vectors.sh <path to the hh-cpp checkout>
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
cpp=$(cd "${1:?usage: tools/update-vectors.sh <path to the hh-cpp checkout>}" && pwd)

# Everything is checked before anything is touched.
[ -f "$cpp/testdata/vectors.tsv" ] || { echo "$cpp has no testdata/vectors.tsv" >&2; exit 1; }
git -C "$cpp" rev-parse HEAD > /dev/null 2>&1 || { echo "$cpp is not a git checkout" >&2; exit 1; }
tag=$(git -C "$cpp" describe --tags --exact-match 2> /dev/null || true)
if ! printf '%s\n' "$tag" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "$cpp is not at a release tag (vMAJOR.MINOR.PATCH)" >&2
    exit 1
fi
if [ -n "$(git -C "$cpp" status --porcelain -- testdata)" ]; then
    echo "$cpp/testdata has uncommitted changes" >&2
    exit 1
fi
commit=$(git -C "$cpp" rev-parse HEAD)

rm -rf "$here/testdata"
mkdir -p "$here/testdata/golden"
cp "$cpp/testdata/vectors.tsv" "$here/testdata/vectors.tsv"
cp "$cpp"/testdata/golden/*.png "$here/testdata/golden/"
{
    echo "# The files in this directory are a byte-identical copy of testdata/ in hh-cpp, the"
    echo "# reference implementation. Do not edit them; run tools/update-vectors.sh instead."
    echo "repository: https://github.com/censync/hh-cpp"
    echo "tag: $tag"
    echo "commit: $commit"
    cd "$here/testdata"
    find vectors.tsv golden -type f | LC_ALL=C sort | while read -r file; do
        if command -v sha256sum > /dev/null 2>&1; then
            sha256sum "$file"
        else
            shasum -a 256 "$file"
        fi
    done
} > "$here/testdata/SOURCE.tmp"
mv "$here/testdata/SOURCE.tmp" "$here/testdata/SOURCE"
echo "testdata/ now holds the vectors of hh-cpp $tag ($commit)"
