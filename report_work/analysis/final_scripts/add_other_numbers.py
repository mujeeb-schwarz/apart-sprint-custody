"""Adds to final_numbers.json the numbers Appendix C takes from files other than the scorer's runs. Read-only on run files."""
import json, sys
R = sys.argv[1]
p = R + '/report_work/analysis/final_numbers.json'
d = json.load(open(p))
t = json.load(open(R + '/report_work/analysis/tables.json'))
d['from_other_files'] = {
    'proof_replay_checked': {x['id']: x['outcomes']['B'] for x in t['proof_replay'] if not x['control']},
    'proof_distinct': 10, 'proof_note': 'F3 and PF17 are one mistake [report_work/audits/AUDIT_PROOF.md]',
    'ideas': {'all': 127, 'on_list': 55, 'new_plantable': 60, 'not_plantable': 12, 'checked': {'blocked': 10, 'flagged': 44, 'did_not_take_effect': 6, 'missed': 0}, 'promised_monitored_missed_rule3': 48, 'source': 'night/ideas/ideas_run.md'},
    'hidden_e2': t['hidden_2b'],
    'e1_variant_summary': t['after_review']['e1_variant_summary'],
    'rule3_variant_resampled_interval_pct': [1.7, 28.6],
    'rule3_added_same_time': t['rule3_added_same_time'],
    'timing_ms_median_clean': {'e1': {'Promised': 3.2, 'Monitored': 3.4, 'Checked': 9.6}, 'e2': {'Promised': 13.8, 'Monitored': 14.0, 'Checked': 25.2}, 'source': 'report_work/facts/METHOD_FACTS.md'},
    'repeat_cases': {'e1': 75, 'e2': 63, 'total': 138, 'different_cases': 1},
    'pass_bands': {'0': [36, 53], '1': [54, 69], '2': [70, 84], '3': [85, 99], '4': [100, 113]},
}
json.dump(d, open(p, 'w'), indent=1, default=str)
print('ok')
