#!/bin/bash
# The Claude stages of the night in order (parts a, b, c). When a stage stops because the usage limit was
# reached, the runner is started again every 10 minutes; a second start goes on where the first stopped.
# Written on Sat 14 Nov 2026 at 02:10 by the coordinator. It changes no frozen file: it only calls tools/run_night.py.
cd "$(dirname "$0")/.." || exit 2
LOG=night/chain_s.log
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
DEADLINE=$(date -j -f "%Y-%m-%d %H:%M:%S" "2026-11-14 11:30:00" +%s)
fresh() { f="night/$1/night_heartbeat.json"; [ -f "$f" ] || return 1; [ $(( $(date +%s) - $(stat -f %m "$f") )) -lt 90 ]; }
run_plan() {
  p="night/$1/plan.json"
  while fresh "$1"; do
    st=$(python3 -c "import json;print(json.load(open('night/$1/night_heartbeat.json')).get('status'))" 2>/dev/null)
    case "$st" in finished|stopped) break;; esac
    say "plan $1: a runner still writes its heartbeat (status $st); waiting"; sleep 30
  done
  n=0
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
    [ "$why" = "limit" ] || { say "plan $1: this is no usage limit; the chain does not go on with it"; return 1; }
    [ "$(date +%s)" -ge "$DEADLINE" ] && { say "plan $1: deadline reached while waiting for the limit"; return 3; }
    sleep 600
  done
}
say "chain S starts"
run_plan a; ra=$?
if [ "$ra" -ne 0 ]; then say "part a did not finish (code $ra); chain S ends"; touch night/CHAIN_DONE; exit 1; fi
W=$(( $(date +%s) + 9000 ))
while [ ! -f outside/test/GPT_DONE ] && [ ! -f outside/test/GPT_FAILED ] && [ "$(date +%s)" -lt "$W" ]; do sleep 30; done
rb=skipped
if [ -f outside/test/GPT_DONE ] && [ -f outside/test/exp2_faults.json ]; then
  say "the outside model's texts are there; part b"
  run_plan b; rb=$?
  if [ "$rb" -eq 0 ]; then run_plan c; rc=$?; else run_plan c_nofaults; rc=$?; fi
else
  say "no texts from the outside model (failed or not in time); the parts that need none"
  run_plan c_nofaults; rc=$?
fi
say "chain S ends: a=$ra b=$rb c=$rc"
touch night/CHAIN_DONE
for x in a b c c_nofaults; do [ -f "night/$x/night_state.json" ] && { echo "--- $x"; python3 tools/run_night.py "night/$x/plan.json" --status 2>&1 | tail -7; }; done
