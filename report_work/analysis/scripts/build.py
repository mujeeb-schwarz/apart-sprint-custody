"""Runs every part of the analysis and writes report_work/analysis/tables.json. Prints Markdown tables for ANALYSIS.md.

    cd report_work/analysis/scripts && python3 build.py
"""
import json
import subprocess
from common import OUT, ROOT, RUNS, jload, clopper_pearson, md_table, pct
import e1
import e2
import same_text
import seen_elsewhere


def r(x, d=1):
    return round(100 * x, d)


def main():
    A = e1.run()
    B = e2.run()
    h1 = e1.hidden_1b()
    cl = e1.complete_list()
    proof = jload(ROOT / "night" / "proof" / "replay_rows.json")
    ideas_rows = jload(ROOT / "night" / "ideas" / "ideas_run_rows.json")
    st = same_text.check()
    se1 = seen_elsewhere.missed_seen_elsewhere(RUNS / "night_e1", RUNS / "night_e1" / "scores.json")
    se2 = seen_elsewhere.missed_seen_elsewhere(RUNS / "night_e2", RUNS / "night_e2_second_pass" / "scores_second_pass.json")
    date = subprocess.run(["date"], capture_output=True, text=True).stdout.strip()

    T = {"made_at": date, "provisional": ["rule 5: its planted part is being redone on Sun 15 Nov 2026"]}

    def main_rows(rows):
        o = []
        for x in rows:
            o.append({"rule": x["rule"], "method": x["method"], "planted": x["planted"], "did_not_take_effect": x["did_not_take_effect"],
                      "violations": x["violations"], "blocked": x["blocked"], "flagged": x["flagged"], "missed": x["missed"],
                      "miss_rate": x["missed"] / x["violations"] if x["violations"] else None,
                      "miss_ci95": x["miss_ci"], "misses_allowed": x["misses_allowed"], "false_alarms": x["false_alarms"],
                      "clean_cases": x["clean"], "false_alarm_rate": x["false_alarms"] / x["clean"], "false_alarm_ci95": x["fa_ci"],
                      "grade": x["grade"], "least_enough": x["least_enough"], "provisional": x.get("provisional", False)})
        return o

    T["main_table"] = main_rows(A["table"]) + main_rows(B["table"])
    T["e2_frozen_key_table"] = B["frozen_table"]
    T["e1_by_kind"] = A["by_kind"]
    T["e2_by_kind_step_set"] = B["by_kind_step_set"]
    T["flags_by_part"] = A["flags_by_part"] + B["flags_by_part"]
    T["variants"] = {"e1_variants_per_rule": A["variants_per_rule"], "e1_max_uses_of_one_variant": A["max_uses_of_one_variant"],
                     "e2_distinct_kind_and_step": B["distinct_kind_step"], "e2_planted_by_set": B["planted_by_set"]}
    T["shared_cases"] = {"e1_transcripts": A["shared_transcripts"], "e2_questions": B["shared_questions"]}
    T["other_rule_flags"] = {"e1": A["other_rule_flags"], "e2": B["other_rule_flags"],
                             "e1_true_side_violations_scorer": A["other_rule_true_violations_scorer"],
                             "e2_true_side_violations_scorer": B["other_rule_true_violations"]}
    T["missed_but_flagged_for_another_rule"] = {"e1": se1, "e2": se2}
    T["repeat"] = {"e1": A["repeat"], "e2_second_pass": B["repeat_second_pass"], "e2_frozen_recomputed": B["repeat_frozen"],
                   "scorer": {"e1": A["repeat_scorer"], "e2": B["repeat_scorer"]}}
    T["kept_copy"] = A["kept_copy"]
    T["hidden_1b_first_answers"] = h1
    T["hidden_2b"] = {"recomputed": B["hidden_2b"], "scorer": B["hidden_2b_scorer"]}
    T["rule0_on_clean"] = {"e1_monitored": A["rule0_on_clean_monitored"],
                           "e2_monitored": {"cases": B["hidden_2b"]["rule0_Monitored_on_clean"], "clean": B["hidden_2b"]["clean"]}}
    T["natural"] = {"e1": A["natural"], "e2_recomputed": B["natural_recomputed"], "e2_scorer": B["natural_scorer"],
                    "e2_cases_any_rule": B["natural_cases_any_rule"], "e2_outcomes": B["natural_scorer_outcomes"],
                    "e2_frozen_key": B["natural_frozen_key"], "e2_rule5_detail": B["natural_rule5_detail"]}
    T["entry_check"] = B["entry_check"]
    T["answer_key"] = {"clean_texts": B["key"], "planted_rows_changed_by_key": B["planted_rows_changed_by_key"]}
    T["took_effect"] = {"recomputed": B["took_effect_recomputed"], "mismatch": B["took_effect_mismatch"],
                        "rule5_levels": B["rule5_planted_levels"]}
    T["confirm"] = B["confirm"]
    T["judge2_rule5"] = B["judge2_rule5"]
    T["rule3_promised_by_subkind"] = A["rule3_promised_by_subkind"]
    T["rule3_added_same_time"] = A["rule3_added_same_time"]
    T["simple_check"] = {"e1": {"agree": A["simple_vs_scorer"]["agree"], "rows": A["simple_vs_scorer"]["rows"],
                                "disagree": A["simple_vs_scorer"]["disagree"]},
                         "e2": {"agree": B["simple_vs_scorer"]["agree"], "rows": B["simple_vs_scorer"]["rows"],
                                "disagree": B["simple_vs_scorer"]["disagree"]}}
    T["complete_list"] = {"variants": cl["variants"], "units": cl["units"], "cases_per_variant": cl["cases_per_variant"],
                          "cannot_see": cl["cannot_see"], "by_kind": cl["by_kind"]}
    T["proof_replay"] = [{"id": x["id"], "control": x["control"], "case": x["case"],
                          "outcomes": {a["condition"]: a["outcome"] for a in x["attempts"] if not a["natural"]}} for x in proof]
    T["ideas"] = {"groups": {"A": {"all": 55, "rule1": 20, "rule2": 16, "rule3": 19},
                             "B": {"all": 60, "rule1": 10, "rule2": 2, "rule3": 48},
                             "C": {"all": 12, "rule1": 0, "rule2": 6, "rule3": 6}},
                  "groups_source": "night/ideas/ideas_compared.md (counts table)",
                  "run_rows": len(ideas_rows) if isinstance(ideas_rows, list) else None}
    T["same_text"] = st
    T["mismatches"] = A["mismatches"] + B["mismatches"]
    T["cases"] = {"e1": A["cases"], "e2": B["cases"], "e1_crashed": A["crashed"], "e2_crashed": B["crashed"],
                  "e2_clean_graded": B["clean_graded"], "e2_clean_stored": B["clean_stored"]}
    T["notes"] = B["notes"]

    with open(OUT / "tables.json", "w") as fh:
        json.dump(T, fh, indent=1, default=list)
    # Markdown for the main table
    rows = []
    for x in T["main_table"]:
        rows.append([x["rule"], x["method"], x["planted"], x["did_not_take_effect"], x["violations"], x["blocked"], x["flagged"],
                     x["missed"], "%.1f%% (%.1f to %.1f)" % (r(x["miss_rate"] or 0), r(x["miss_ci95"][0]), r(x["miss_ci95"][1])),
                     x["misses_allowed"], "%d of %d" % (x["false_alarms"], x["clean_cases"]),
                     "%.1f%% (%.1f to %.1f)" % (r(x["false_alarm_rate"]), r(x["false_alarm_ci95"][0]), r(x["false_alarm_ci95"][1])),
                     x["grade"] + (" (provisional)" if x["provisional"] else ""), x["least_enough"]])
    print(md_table(["Rule", "Method", "Planted", "Did not take effect", "Violations", "Blocked", "Flagged", "Missed",
                    "Miss rate (95% interval)", "Misses allowed", "False alarms", "False-alarm rate (95% interval)", "Grade",
                    "Least that is enough"], rows))
    print()
    print("mismatches:", T["mismatches"])
    print("made at", date)
    # intervals for other counts used in the text
    for k, n in ((60, 100), (40, 100), (33, 100), (67, 100), (12, 100), (88, 100), (54, 100), (69, 100), (93, 100), (52, 207),
                 (1, 412), (1, 157), (7, 413), (1, 62), (8, 62), (0, 62), (0, 100), (188, 200), (37, 157), (1, 413), (50, 67),
                 (5, 11), (28, 33)):
        lo, hi = clopper_pearson(k, n)
        print("%d of %d: %.1f%%, 95%% interval %.1f to %.1f%%" % (k, n, 100 * k / n, 100 * lo, 100 * hi))


if __name__ == "__main__":
    main()
