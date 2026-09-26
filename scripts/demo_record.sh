#!/usr/bin/env bash
# One-key paced run for the 60 s demo recording. Press Enter once, then talk.
#   scripts/demo_record.sh            # paced (pauses at each stage, highlights key lines)
#   PAUSE=0 scripts/demo_record.sh    # no pauses
set -euo pipefail
cd "$(dirname "$0")/.."
PAUSE="${PAUSE:-1.6}"
OUT="${OUT:-out}"

B=$'\033[1m'; G=$'\033[1;32m'; Y=$'\033[1;33m'; R=$'\033[1;31m'; C=$'\033[1;36m'; N=$'\033[0m'

# pytest runs in the background from the start so its real result is ready by the closing shot
PYTEST_LOG="$(mktemp)"; ( uv run pytest -q >"$PYTEST_LOG" 2>&1; echo "exit=$?" >>"$PYTEST_LOG" ) &
PYTEST_PID=$!

clear
echo "${B}Rekurse${N}  finds the turn where a coding agent went wrong,"
echo "         and proves which one-sentence rule would have saved it."
echo
echo "${C}\$ uv run rekurse demo --fake --heldout heldout${N}"
sleep 1

uv run rekurse demo --fake --heldout heldout --out "$OUT" 2>&1 | python3 -c '
import sys, time, re, os
pause = float(os.environ.get("PAUSE", "1.6"))
B, G, Y, R, C, N = "\033[1m", "\033[1;32m", "\033[1;33m", "\033[1;31m", "\033[1;36m", "\033[0m"
for line in sys.stdin:
    line = line.rstrip("\n")
    if line.startswith("=="):
        time.sleep(pause); print(f"\n{B}{line}{N}"); sys.stdout.flush(); time.sleep(0.4); continue
    if "wrong turn =" in line:            print(f"{Y}{line}   <- the turn it stopped recovering{N}")
    elif "lesson rejected" in line:        print(f"{R}{line}{N}"); time.sleep(pause)
    elif "lesson merged" in line:          print(f"{C}{line}   <- Atlas Vector Search dedupe{N}"); time.sleep(pause)
    elif "lesson candidate" in line:       print(f"{G}{line}{N}")
    elif line.startswith("== ADOPTED") or "ADOPTED" in line: print(f"{G}{line}{N}")
    elif "REJECTED" in line:               print(f"{R}{line}{N}")
    elif re.search(r"(report\.html|postmortem\.md|AGENTS\.md)$", line): continue  # paths shown below
    else:                                  print(line)
    sys.stdout.flush(); time.sleep(0.05)
'

sleep "$PAUSE"
echo
echo "${C}\$ cat $OUT/AGENTS.md${N}"
sleep 0.5
cat "$OUT/AGENTS.md"
sleep "$PAUSE"; sleep "$PAUSE"

echo
echo "${C}\$ uv run pytest -q${N}"
sleep 0.5
wait "$PYTEST_PID" || true
grep -v '^exit=' "$PYTEST_LOG" | tail -2; rm -f "$PYTEST_LOG"
echo
echo "${B}Never lose the same afternoon twice.${N}   github.com/a-boat-on-water/rekurse"
