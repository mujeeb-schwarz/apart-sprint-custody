#!/bin/bash
# The outside model's step of the night: once the clean cases of Experiment 2 are done, GPT writes the changed
# texts, they are confirmed, and the planted units are written. Runs outside the sandbox because Codex needs it.
# Written on Sat 14 Nov 2026 at 02:10 by the coordinator. It changes no frozen file.
cd "$(dirname "$0")/.." || exit 2
LOG=night/chain_g.log
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
END=$(date -j -f "%Y-%m-%d %H:%M:%S" "2026-11-14 11:30:00" +%s)
mkdir -p outside/test
say "chain G starts: waiting for the clean cases of Experiment 2"
until grep -q '"event": "stage_done".*"stage": "e2 clean"' night/a/night_checkpoints.jsonl 2>/dev/null; do
  [ -f night/CHAIN_DONE ] && { say "chain S ended before e2 clean was done; nothing to do"; exit 0; }
  [ "$(date +%s)" -ge "$END" ] && { say "deadline"; touch outside/test/GPT_FAILED; exit 3; }
  sleep 30
done
say "e2 clean is done; the outside model writes the changed texts"
STOP=$(( $(date +%s) + 9000 )); made=no; fours=0
while [ "$(date +%s)" -lt "$STOP" ]; do
  python3 tools/outside_texts.py make --plan plans/test/exp2_plan.json --clean-run runs/night_e2 --out outside/test >> "$LOG" 2>&1; rc=$?
  say "make exit $rc"
  [ "$rc" -eq 0 ] && { made=yes; break; }
  [ "$rc" -eq 2 ] && break
  if [ "$rc" -eq 4 ]; then fours=$((fours+1)); [ "$fours" -ge 2 ] && { made=yes; break; }; sleep 20; continue; fi
  sleep 600
done
if [ "$made" = yes ]; then
  conf=no
  while [ "$(date +%s)" -lt "$STOP" ]; do
    python3 tools/outside_texts.py confirm --dir outside/test >> "$LOG" 2>&1; rc=$?
    say "confirm exit $rc"
    [ "$rc" -eq 0 ] && { conf=yes; break; }
    [ "$rc" -eq 2 ] && break
    [ "$rc" -eq 4 ] && { conf=yes; break; }
    sleep 600
  done
  if [ "$conf" = yes ]; then
    python3 tools/make_plan.py faults-exp2 --plan plans/test/exp2_plan.json --confirmed outside/test/confirmed.jsonl --out outside/test/exp2_faults.json >> "$LOG" 2>&1; rc=$?
    say "faults-exp2 exit $rc"
    if [ "$rc" -eq 0 ] && [ -f outside/test/exp2_faults.json ]; then touch outside/test/GPT_DONE; say "the planted units of Experiment 2 are written"; else touch outside/test/GPT_FAILED; fi
  else touch outside/test/GPT_FAILED; say "confirm did not finish"; fi
else touch outside/test/GPT_FAILED; say "make did not finish"; fi
until [ -f night/CHAIN_DONE ] || [ "$(date +%s)" -ge "$END" ]; do sleep 60; done
say "chain G ends"
