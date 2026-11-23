#!/bin/sh
# Round 2 of Experiment 2 (rule 5 rewritten to a target level; rule 4's dropped wrong sources confirmed again),
# or part 1b of Experiment 1, with the lenient import. Sun 15 Nov 2026, started by the coordinator.
#   sh round2/run_round2.sh e2     the whole chain for Experiment 2, then the judge's second pass and the scores
#   sh round2/run_round2.sh e1     part 1b of Experiment 1 (the hidden instruction in the patient's words)
# Every step logs to round2/out/run_<part>.log. A step that ends with an error is tried again after 10 minutes,
# at most 30 times (a usage limit or a failed call is the usual cause; answers already stored are never asked again).
cd <repo> || exit 1
PART="${1:?e1 or e2}"
LOG="round2/out/run_$PART.log"
R="15 Nov 2026, the coordinator's decision under the project lead's delegation: lenient import of monitor and review answers. FLAG and NO FLAGS lines are read as before; other lines are kept apart as extra_lines and never change a flag. The hidden-instruction table counts checker answers with a line that reads as a send, quotes included; the import prints answers with extra lines. Changed: tools/run_advice.py, custody/ai_live.py, custody/score_parts.py; watch, core, stats, score unchanged."
F="Round 2 faults file (round2/round2.py, round2/reconfirm_rule4.py): rule 5 rewritten to a target level in the outside model's own words (the expert grade where the reader cannot read the honest text; never the level of the advice text before it); rule 4 = round 1's confirmed rows plus the 52 round 1 wrong-source texts confirmed again under a corrected rule, first 100 in plan order."
say() { echo "=== $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
try() {
  name="$1"; shift; n=0
  while :; do
    say "start $name (try $((n+1)))"
    "$@" >> "$LOG" 2>&1; code=$?
    say "end $name exit $code"
    [ "$code" -eq 0 ] && return 0
    n=$((n+1))
    if [ "$n" -ge 30 ]; then say "STOP: $name failed 30 times"; exit 1; fi
    sleep 600
  done
}
if [ "$PART" = e1 ]; then
  try "exp1 hidden part" python3 tools/run_live.py --experiment 1 --split test --name night_e1 --live-dir live_night_e1 --plan plans/test/exp1_plan.json --part hidden --workers 8 --wait-on-limit --after-freeze-change "$R"
  try "exp1 score" sh -c 'python3 tools/score.py runs/night_e1 --text > round2/out/scores_e1_after_1b.txt && python3 tools/score_parts.py runs/night_e1 > round2/out/scores_parts_e1_after_1b.txt'
  say "DONE e1"
  exit 0
fi
try "make rule 5 texts (GPT-6.1)" python3 round2/round2.py make --out round2/out --no-rule4
try "confirm (frozen)" python3 tools/outside_texts.py confirm --dir round2/out
try "confirm rule 4 again" python3 round2/reconfirm_rule4.py --out round2/out
try "union" python3 round2/round2.py union --dir round2/out
try "faults" python3 tools/make_plan.py faults-exp2 --plan plans/test/exp2_plan.json --confirmed round2/out/confirmed_union.jsonl --out round2/out/exp2_faults.json
try "check" python3 round2/round2.py check --dir round2/out
if [ ! -d live_round2_e2 ]; then say "copy the live folder"; cp -Rp live_night_e2 live_round2_e2; fi
try "exp2 clean part" python3 tools/run_live.py --experiment 2 --split test --name round2_e2 --live-dir live_round2_e2 --plan plans/test/exp2_plan.json --part clean --workers 8 --wait-on-limit --after-freeze-change "$R"
try "exp2 planted rule 5" python3 tools/run_live.py --experiment 2 --split test --name round2_e2 --live-dir live_round2_e2 --plan plans/test/exp2_plan.json --faults round2/out/exp2_faults.json --part planted --rule 5 --workers 8 --wait-on-limit --after-freeze-change "$F"
try "exp2 planted rule 4" python3 tools/run_live.py --experiment 2 --split test --name round2_e2 --live-dir live_round2_e2 --plan plans/test/exp2_plan.json --faults round2/out/exp2_faults.json --part planted --rule 4 --workers 8 --wait-on-limit --after-freeze-change "$F"
try "exp2 score (frozen key)" sh -c 'python3 tools/score.py runs/round2_e2 --text > round2/out/scores_round2_frozen_key.txt'
if [ ! -d rejudge/round2_pass ]; then say "copy the second pass"; cp -Rp rejudge/night_e2_pass rejudge/round2_pass; fi
try "second pass build" python3 rejudge/rejudge.py build --run runs/round2_e2 --out rejudge/round2_pass --only-split test
try "second pass answer" python3 rejudge/rejudge.py answer --dir rejudge/round2_pass --workers 8
try "second pass collect" python3 rejudge/rejudge.py collect --dir rejudge/round2_pass --run runs/round2_e2 --copy runs/round2_e2_second_pass --force
try "second pass score" sh -c 'python3 rejudge/rejudge.py score --copy runs/round2_e2_second_pass > round2/out/scores_round2_second_pass.txt; python3 tools/score.py runs/round2_e2_second_pass --text >> round2/out/scores_round2_second_pass.txt; python3 tools/score_parts.py runs/round2_e2_second_pass > round2/out/scores_parts_round2_second_pass.txt'
say "DONE e2"
