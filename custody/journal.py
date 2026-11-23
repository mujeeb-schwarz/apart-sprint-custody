"""The ledger: the journal of one run, written before each delivery.

A journal line is written once, before the witness is told, with receipt null.
The witness receipt lives in the in-memory record and in the witness log.
"""
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import List

from custody.core import J, LedgerError, ContractError, Record, canon, fingerprint
from custody.witness import Witness

ROOT = Path(__file__).resolve().parents[1]


def record_fingerprint(rec: J) -> str:
    """The fingerprint of a record as a plain dict, without fp and receipt."""
    body = {k: v for k, v in rec.items() if k not in ("fp", "receipt")}
    return fingerprint(body)


def witness_key(choices: J) -> bytes:
    spec = choices["witness"]
    use = spec.get("use", "test_key")
    if use == "test_key":
        return bytes.fromhex(spec["test_key_hex"])
    if use == "key_file":
        path = Path(spec["key_file"])
        if not path.is_absolute():
            path = ROOT / path
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(os.urandom(32).hex(), encoding="utf-8")
            return bytes.fromhex(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError) as exc:
            raise LedgerError("the witness key cannot be read: %s" % exc)
    raise ContractError("witness.use must be test_key or key_file, not %r" % (use,))


class Ledger:
    def __init__(self, run_dir, run_id: str, choices: J):
        self.run_id = run_id
        self._use_witness = bool(choices.get("guards", {}).get("witness", True))
        run_dir = Path(run_dir)
        self._journal = run_dir / "journal" / ("%s.jsonl" % run_id)
        try:
            self._journal.parent.mkdir(parents=True, exist_ok=True)
            self._journal.write_text("", encoding="utf-8")
        except OSError as exc:
            raise LedgerError("the journal cannot be opened: %s" % exc)
        self._witness = Witness(witness_key(choices), run_dir / "witness" / "log.jsonl")
        self._records: List[Record] = []

    def write(self, record: Record) -> Record:
        prev_fp = self._records[-1].fp if self._records else ""
        filled = replace(record, seq=len(self._records), prev_fp=prev_fp, fp="", receipt=None)
        fp = record_fingerprint(asdict(filled))
        filled = replace(filled, fp=fp)
        try:
            with open(str(self._journal), "a", encoding="utf-8") as fh:
                fh.write(canon(asdict(filled)) + "\n")
                fh.flush()
        except (OSError, TypeError, ValueError) as exc:
            raise LedgerError("the journal refused the record: %s" % exc)
        self._records.append(filled)
        if self._use_witness:
            receipt = self._witness.submit(fp, filled.t)
            filled = replace(filled, receipt=asdict(receipt))
            self._records[-1] = filled
        return filled

    def records(self) -> List[Record]:
        return list(self._records)


def make_ledger(run_dir, run_id: str, choices: J) -> Ledger:
    return Ledger(run_dir, run_id, choices)
