"""Rule 5 round 2: how far each used planted change moved the level (target and judge's reading). Read-only."""
import json, sys
from collections import Counter
R = sys.argv[1]
S = {'very low': 0, 'low': 1, 'moderate': 2, 'high': 3}
f = json.load(open(R + '/round2/out/exp2_faults.json'))['faults']
used = {k for k in f if k.startswith('P5')}
rows = {}
for l in open(R + '/round2/out/confirmed_union.jsonl'):
    x = json.loads(l)
    if str(x['rule']) == '5' and x['plant_id'] in used:
        rows[x['plant_id']] = x   # union: last wins
made = {}
with open(R + '/runs/round2_e2_second_pass/texts.jsonl') as fh:
    for l in fh:
        if '+P5-' not in l: continue
        t = json.loads(l)
        it = t['item'] if isinstance(t['item'], dict) else eval(t['item'])
        made[it['item_id']] = it.get('made_by')
jl = {}
for l in open(R + '/runs/round2_e2_second_pass/judge.jsonl'):
    j = json.loads(l)
    if j['rule'] == 5 and '+P5-' in j['visit_id']:
        jl[(j['visit_id'].split('+')[1], made.get(j['item_id']))] = j.get('level')
tgt, jud = Counter(), Counter()
for pid in sorted(used):
    x = rows.get(pid)
    if not x: tgt['no row'] += 1; continue
    h = S.get(x['honest_level']); t = S.get(x['target_level'])
    tgt[(abs(t - h) if h is not None and t is not None else ('honest ' + x['honest_level']))] += 1
    lv = jl.get((pid, x['step']))
    jud[(abs(S[lv] - h) if lv in S and h is not None else (x['honest_level'] + '->' + str(lv)))] += 1
out = {'used': len(used), 'rows_found': len(rows), 'target_distance': {str(k): v for k, v in tgt.items()}, 'judge_distance_at_planted_step': {str(k): v for k, v in jud.items()}}
print(json.dumps(out, indent=1))
