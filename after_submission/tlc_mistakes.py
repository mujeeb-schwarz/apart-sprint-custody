#!/usr/bin/env python3
"""TLC on the model of every connection mistake the bench knows, and on the clean wiring.

Written Sun 22 Nov 2026, after the submission. The sprint's own TLC run (Sat 14 Nov) stopped with an
exception, so Z3 and the bench's own search were the only tools that checked the wiring during the
sprint (night/proof/proofs_list.md). On Sun 22 Nov TLC checked the model as submitted and found no
error (after_submission/tlc_as_submitted.txt). This program asks the opposite question:
does TLC find each known mistake? For each one it applies the mistake's patch to a copy of the wiring in
memory (the wiring file is never changed), writes the TLA+ model with model/gen_tla.py, and runs TLC with
the same configuration as the clean run (SPECIFICATION Spec, INVARIANTS P1 P2 P3 P4). TLC stops at the
first state that breaks a property and prints the path to it, so each row names one broken property, the
first TLC met; a mistake can break more (night/proof/proofs_list.md lists what Z3 found). The list of
mistakes is the one night/proof/proof_list.py reads.

Run from the folder above this one:

    python3 after_submission/tlc_mistakes.py

It needs Java and the TLA+ tools: JAVA (default "java") and TLA_JAR (default ~/tla/tla2tools.jar). Each
model and its TLC output go to after_submission/tlc_mistakes/<id>/; the summary goes to
after_submission/tlc_mistakes/summary.json. No AI is called and no network is used.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "model"))
sys.path.insert(0, str(ROOT / "night" / "proof"))

from custody import faults as F  # noqa: E402
from custody.prove import load_choices, load_wiring  # noqa: E402
import gen_tla  # noqa: E402

OUT = ROOT / "after_submission" / "tlc_mistakes"
CFG = "SPECIFICATION Spec\nINVARIANTS P1 P2 P3 P4\n"


def collect(choices):
    """The connection mistakes, as night/proof/proof_list.py collects them (that file runs on import)."""
    out = []
    for f in choices["faults"]["development"]:
        if f["kind"] == "wiring":
            out.append(("config/design_choices.json", f, False))
    for p in ("faults/practice/practice_faults.json", "faults/practice/practice_advice_faults.json"):
        d = json.load(open(ROOT / p))
        for f in d["faults"]:
            if f["kind"] == "wiring":
                out.append((p, f, False))
        for f in d.get("clean_cases", []):
            if f["kind"] == "wiring":
                out.append((p + " (clean_cases)", f, True))
    return out


def run_tlc(folder: Path, tmp: str) -> dict:
    java = os.environ.get("JAVA", "java")
    jar = os.environ.get("TLA_JAR", str(Path.home() / "tla" / "tla2tools.jar"))
    cmd = [java, "-Djava.io.tmpdir=" + tmp, "-cp", jar, "tlc2.TLC", "-workers", "1",
           "-metadir", str(Path(tmp) / ("states_" + folder.name)), "-config", "Custody.cfg", "Custody.tla"]
    r = subprocess.run(cmd, cwd=str(folder), capture_output=True, text=True, timeout=600)
    text = r.stdout + r.stderr
    (folder / "tlc_output.txt").write_text(text, encoding="utf-8")
    broken = re.findall(r"Invariant (P\d) is violated", text)
    clean = r.returncode == 0 and "No error has been found" in text
    m = re.search(r"([\d,]+) states generated, ([\d,]+) distinct states found", text)
    return {"exit": r.returncode, "first_broken": broken[0] if broken else None, "no_error": clean,
            "tlc_error": (not clean and not broken),
            "states": m and int(m.group(2).replace(",", ""))}


def main() -> int:
    choices = load_choices()
    base = load_wiring()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [("clean wiring", None, True)] + collect(choices)
        for src, f, control in jobs:
            fid = "clean" if f is None else f["fault_id"]
            folder = OUT / fid
            folder.mkdir(exist_ok=True)
            wiring = base if f is None else F.apply_patch(base, f.get("patch") or [])
            (folder / "Custody.tla").write_text(gen_tla.generate(wiring, choices), encoding="utf-8")
            (folder / "Custody.cfg").write_text(CFG, encoding="utf-8")
            res = run_tlc(folder, tmp)
            row = {"id": fid, "source": src, "control": control,
                   "rule": None if f is None else f["rule"], "says": None if f is None else f["says"],
                   "patch": None if f is None else f.get("patch"), "events": None if f is None else f.get("events")}
            row.update(res)
            rows.append(row)
            print("%-6s %-8s first_broken=%-4s no_error=%-5s tlc_error=%-5s exit=%s states=%s" % (
                fid, "control" if control else "mistake", res["first_broken"] or "-", res["no_error"],
                res["tlc_error"], res["exit"], res["states"]))
    (OUT / "summary.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
