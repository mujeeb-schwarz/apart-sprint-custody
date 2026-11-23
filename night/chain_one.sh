#!/bin/bash
# Like night/chain_s.sh, for the plan folders given as arguments, in order. It starts the runner again every 10
# minutes while a stage is stopped by the usage limit, and ends at the first plan that stops for another reason.
# It changes no frozen file: it only calls tools/run_night.py.
cd "$(dirname "$0")/.." || exit 2
LOG=night/chain_one.log
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
DEADLINE=$(( $(date +%s) + 21600 ))
run_plan() {
  p="night/$1/plan.json"; n=0
  while :; do
    n=$((n+1)); say "plan $1: start $n"
    python3 tools/run_night.py "$p" >> "night/$1/screen.log" 2>&1; rc=$?
    say "plan $1: runner exit $rc"
    [ "$rc" -eq 0 ] && return 0
    [ "$rc" -eq 2 ] && { say "plan $1: bad plan"; return 2; }
    why=$(python3 - "$1" <<'PY'
import json, sys
rows = [json.loads(l) for l in open('night/%s/night_log.jsonl' % sys.argv[1]) if l.strip()]
ends = [r for r in rows if r.get('event') == 'stage_end']
last = ends[-1] if ends else {}
f = last.get('failures') or {}
ok = last.get('check_failed') in (None, 'no_answer_stored') and set(f) <= {'other', 'limit', 'transient'} and last.get('exit_code') in (1, 5)
print('limit' if ok else 'other:%s:%s' % (last.get('check_failed'), ','.join(sorted(f))))
PY
)
    say "plan $1: stopped because: $why"
    [ "$why" = "limit" ] || return 1
    [ "$(date +%s)" -ge "$DEADLINE" ] && return 3
    sleep 600
  done
}
say "chain starts: $*"
for x in "$@"; do run_plan "$x" || { say "plan $x did not finish; the chain ends here"; exit 1; }; done
say "chain ends: every plan done"
