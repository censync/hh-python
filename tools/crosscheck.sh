#!/bin/sh
# Differential test of hh-python against hh-cpp. Two batches go through hh_cli of hh-cpp and
# through the command line tool of this package, run from the source tree: pseudo-random cases,
# valid and invalid, and the hand-made cases of tools/edge-cases.txt, which pin down the batch
# format itself. Every printed value and every written file (PNG, BMP, JPEG, raw pixels) must be
# identical.
#
# usage: tools/crosscheck.sh <path to hh_cli> [case count] [seed]
# PYTHON names the interpreter (default python3).
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
hh_cli=${1:?usage: tools/crosscheck.sh <path to hh_cli> [case count] [seed]}
count=${2:-400}
seed=${3:-1}
python=${PYTHON:-python3}
work=$here/build/crosscheck
rm -rf "$work"
mkdir -p "$work"

export PYTHONPATH="$here/src"
export PYTHONDONTWRITEBYTECODE=1

# compare <name> <cases>: both tools run the cases; the values and the files must agree.
compare() {
    "$hh_cli" --batch "$2" "$work/$1-cpp" > "$work/$1-cpp.txt"
    "$python" -m humanized_hash --batch "$2" "$work/$1-python" > "$work/$1-python.txt"
    if ! diff "$work/$1-cpp.txt" "$work/$1-python.txt" > "$work/$1-values.diff"; then
        echo "crosscheck: the printed values differ, see $work/$1-values.diff" >&2
        head -n 20 "$work/$1-values.diff" >&2
        exit 1
    fi
    if ! diff -r "$work/$1-cpp" "$work/$1-python" > "$work/$1-files.diff"; then
        echo "crosscheck: the written files differ, see $work/$1-files.diff" >&2
        head -n 20 "$work/$1-files.diff" >&2
        exit 1
    fi
}

"$python" -m humanized_hash --generate "$count" "$seed" > "$work/generated.txt"
compare generated "$work/generated.txt"
compare edge "$here/tools/edge-cases.txt"

edge=$(wc -l < "$work/edge-cpp.txt" | tr -d ' ')
ok=$(cat "$work/generated-cpp.txt" "$work/edge-cpp.txt" | grep -c "	ok	" || true)
files=$(find "$work/generated-cpp" "$work/edge-cpp" -type f | wc -l | tr -d ' ')
echo "crosscheck: $count generated and $edge hand-made cases agree" \
    "($ok rendered, $files files compared byte for byte)"
