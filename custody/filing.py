"""The wall around the test visits (13 Nov, G2).

The owner files his predictions before any test visit runs on real answers. Filing copies the predictions page
to docs/predictions_as_filed.md and records, in config/predictions_filed.json, the sha256 of that copy, the
local time with its time zone and the scorer's fingerprint. A run on real answers that holds a test visit
refuses unless the filing exists and the copy still matches it. The first such run also writes the freeze
file (live/frozen.json) with the fingerprint of every prompt file, of config/design_choices.json and of the
scorer; a later one refuses if any differs, unless it is given a reason, which is then kept in the file.

Standard library only; the scorer's fingerprint comes from custody.assemble.scorer_fingerprint, the function
the run manifest uses.
"""
import datetime
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from custody.core import CustodyError, J, canon

ROOT = Path(__file__).resolve().parents[1]
FILED_JSON = Path("config") / "predictions_filed.json"
FILED_MD = Path("docs") / "predictions_as_filed.md"


def _sha(path: Any) -> str:
    return hashlib.sha256(Path(str(path)).read_bytes()).hexdigest()


def scorer_fp() -> str:
    from custody import assemble  # late: assemble imports most of the program
    return assemble.scorer_fingerprint()


def now_local() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def paths(root: Any = None):
    root = Path(str(root)) if root else ROOT
    return root / FILED_JSON, root / FILED_MD


# ------------------------------------------------------------------ filing

def file_predictions(src: Any, root: Any = None, refile: bool = False) -> J:
    """Copy the page, write the filing record, return it. Refuses an existing filing unless refile is true;
    then the earlier json (and page) are kept beside it under a numbered name and the new json says it is a refiling."""
    src = Path(str(src))
    if not src.is_file():
        raise CustodyError("the predictions page %s does not exist" % src)
    jpath, mpath = paths(root)
    kept: Optional[str] = None
    if jpath.exists():
        if not refile:
            raise CustodyError("predictions are already filed (%s). Use --refile to file them again; the earlier "
                               "filing is then kept beside it under a numbered name" % jpath)
        n = 1
        while jpath.with_name("%s.%d.json" % (jpath.stem, n)).exists():
            n += 1
        kept = jpath.with_name("%s.%d.json" % (jpath.stem, n)).name
        jpath.replace(jpath.with_name(kept))
        if mpath.exists():
            mpath.replace(mpath.with_name("%s.%d%s" % (mpath.stem, n, mpath.suffix)))
    mpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(mpath))
    rec: J = {"page": str(FILED_MD), "page_sha256": _sha(mpath), "filed_at": now_local(), "scorer_fingerprint": scorer_fp(),
              "refiling": kept is not None}
    if kept:
        rec["earlier_filing"] = kept
    jpath.write_text(canon(rec) + "\n", encoding="utf-8")
    return rec


def read_filing(root: Any = None) -> Optional[J]:
    jpath, _ = paths(root)
    return json.loads(jpath.read_text(encoding="utf-8")) if jpath.exists() else None


def check_filed(root: Any = None) -> J:
    """The filing record, or CustodyError saying what to do."""
    jpath, mpath = paths(root)
    rec = read_filing(root)
    if rec is None:
        raise CustodyError("this run holds test visits and the predictions are not filed (%s is missing). File them "
                           "first: python3 tools/file_predictions.py <path to the predictions page>" % jpath)
    if not mpath.exists() or _sha(mpath) != rec.get("page_sha256"):
        raise CustodyError("this run holds test visits and %s no longer matches the filing in %s (changed or missing). "
                           "Restore the filed page, or, if the change is meant, file again with "
                           "python3 tools/file_predictions.py <page> --refile" % (mpath, jpath))
    return rec


def status(root: Any = None) -> J:
    """What the scorer prints about the filing: whether predictions were filed, whether the page still matches,
    and whether the scorer's fingerprint equals the filed one."""
    jpath, mpath = paths(root)
    rec = read_filing(root)
    now = scorer_fp()
    if rec is None:
        return {"predictions_filed": False, "page_matches_filing": None, "scorer_fingerprint": now,
                "filed_scorer_fingerprint": None, "scorer_equals_filed": None}
    return {"predictions_filed": True, "filed_at": rec.get("filed_at"), "refiling": bool(rec.get("refiling")),
            "page_matches_filing": mpath.exists() and _sha(mpath) == rec.get("page_sha256"),
            "scorer_fingerprint": now, "filed_scorer_fingerprint": rec.get("scorer_fingerprint"),
            "scorer_equals_filed": now == rec.get("scorer_fingerprint")}


# ----------------------------------------------------------------- freezing

EXTRA = "extra:"  # a freeze item taken the first time a stage uses it (the plan, the list, the faults file): recorded then, refused if it differs later


def code_fp() -> str:
    """One fingerprint over custody/*.py and tools/*.py (names and bytes, in order): the program of a run."""
    import hashlib as _h
    h = _h.sha256()
    for folder in ("custody", "tools"):
        for f in sorted((ROOT / folder).glob("*.py")):
            h.update(("%s/%s\n" % (folder, f.name)).encode("utf-8"))
            h.update(f.read_bytes())
    return h.hexdigest()


def freeze_items(choices: J, root: Any = None, visits_path: Any = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """name -> fingerprint of every prompt file named in D: prompts (step prompts, reminders, watcher, reviewer,
    judge), of config/design_choices.json, of the scorer and, when a visits file is given, of that file (`visits`;
    14 Nov, H5), so a later run refuses if the visit list changed."""
    out: Dict[str, str] = {}
    for key, pid in sorted(choices["prompts"].items()):
        if isinstance(pid, str) and len(pid) < 40 and " " not in pid and key not in ("slot",):
            f = ROOT / "prompts" / (pid + ".txt")
            if not f.exists():
                raise CustodyError("prompt file %s is missing" % f)
            out["prompt:" + pid] = _sha(f)
    out["design_choices"] = _sha(ROOT / "config" / "design_choices.json")
    out["scorer"] = scorer_fp()
    out["code"] = code_fp()
    if visits_path is not None:
        out["visits"] = _sha(visits_path)
    for name, fp in (extra or {}).items():
        out[EXTRA + name] = fp
    return out


def check_freeze(live_dir: Any, choices: J, reason: Optional[str] = None, root: Any = None,
                 visits_path: Any = None, extra: Optional[Dict[str, str]] = None) -> None:
    """First call on real answers with test visits: write live/frozen.json. Later calls: refuse when any item
    differs from the last accepted state, naming it; with a reason, go on and append the change and the reason to
    the list `changes_after_freeze`, so the report can state every change made after the freeze."""
    now = freeze_items(choices, root, visits_path, extra)
    path = Path(str(live_dir)) / "frozen.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canon({"frozen_at": now_local(), "fingerprints": now, "accepted": now,
                               "changes_after_freeze": []}) + "\n", encoding="utf-8")
        return
    rec = json.loads(path.read_text(encoding="utf-8"))
    if "accepted" not in rec:
        raise CustodyError("%s is in the old format (prompts only). Move it aside (no test visit has run on real "
                           "answers if it is only from a tuning-era export) and run again" % path)
    was = rec["accepted"]
    # an extra item (plan, list, faults file) is taken the first time a stage uses it; it is compared only when both have it
    first = {k: v for k, v in now.items() if k.startswith(EXTRA) and k not in was}
    if first:
        was = dict(was, **first)
        rec["accepted"] = was
        rec["fingerprints"] = dict(rec.get("fingerprints", {}), **first)
        path.write_text(canon(rec) + "\n", encoding="utf-8")
    changed = sorted(k for k in set(was) | set(now) if was.get(k) != now.get(k)
                     and not (k.startswith(EXTRA) and k not in now))
    if not changed:
        return
    if not reason:
        raise CustodyError("changed since the freeze in %s: %s. The prompts, the design choices and the scorer are "
                           "fixed before test visits run on real answers. To go on anyway, say why: "
                           "--after-freeze-change \"<reason>\"" % (path, ", ".join(changed)))
    rec["changes_after_freeze"].append({"at": now_local(), "changed": changed, "reason": reason,
                                        "before": {k: was.get(k) for k in changed},
                                        "after": {k: now.get(k) for k in changed}})
    rec["accepted"] = now
    path.write_text(canon(rec) + "\n", encoding="utf-8")


def guard(selection_has_test: bool, live_dir: Any, choices: J, reason: Optional[str] = None,
          root: Any = None, visits_path: Any = None, extra: Optional[Dict[str, str]] = None) -> None:
    """The one check every entry point of tools/run_advice.py that runs, exports, imports or scores real answers
    makes. A selection with no test visit passes with nothing filed."""
    if not selection_has_test:
        return
    check_filed(root)
    check_freeze(live_dir, choices, reason, root, visits_path, extra)
