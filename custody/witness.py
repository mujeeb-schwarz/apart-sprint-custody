"""The witness: a chain of fingerprints and nothing else.

head = sha256(prev_head + record_fp), starting from 64 zeros;
mac = hmac_sha256(key, "index|record_fp|head|t").
One log file holds every run of a folder, in order. No step receives the key.
"""
import hashlib
import hmac
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import List

from custody.core import LedgerError, WitnessReceipt, canon

ZERO_HEAD = "0" * 64


def chain_head(prev_head: str, record_fp: str) -> str:
    return hashlib.sha256((prev_head + record_fp).encode("utf-8")).hexdigest()


def mac_for(key: bytes, index: int, record_fp: str, head: str, t: int) -> str:
    msg = "%d|%s|%s|%d" % (index, record_fp, head, t)
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def entry_from_dict(d: dict) -> WitnessReceipt:
    return WitnessReceipt(
        index=int(d["index"]),
        record_fp=str(d["record_fp"]),
        prev_head=str(d["prev_head"]),
        head=str(d["head"]),
        t=int(d["t"]),
        mac=str(d["mac"]),
    )


class Witness:
    def __init__(self, key: bytes, log_path):
        if isinstance(key, str):
            key = bytes.fromhex(key.strip())
        self._key = key
        self._path = Path(log_path)
        self._entries: List[WitnessReceipt] = []
        self._size = -1
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch(exist_ok=True)
        except OSError as exc:
            raise LedgerError("the witness log cannot be opened: %s" % exc)
        self._refresh()

    def _refresh(self) -> None:
        """Read the log again when another writer has changed the file."""
        try:
            size = os.path.getsize(str(self._path))
            if size == self._size:
                return
            rows = []
            with open(str(self._path), "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(entry_from_dict(json.loads(line)))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise LedgerError("the witness log cannot be read: %s" % exc)
        self._entries = rows
        self._size = size

    def submit(self, record_fp: str, t: int) -> WitnessReceipt:
        self._refresh()
        index = len(self._entries)
        prev_head = self._entries[-1].head if self._entries else ZERO_HEAD
        head = chain_head(prev_head, record_fp)
        receipt = WitnessReceipt(
            index=index,
            record_fp=record_fp,
            prev_head=prev_head,
            head=head,
            t=int(t),
            mac=mac_for(self._key, index, record_fp, head, int(t)),
        )
        line = canon(asdict(receipt)) + "\n"
        try:
            with open(str(self._path), "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            raise LedgerError("the witness log cannot be written: %s" % exc)
        self._entries.append(receipt)
        self._size += len(line.encode("utf-8"))
        return receipt

    def entries(self) -> List[WitnessReceipt]:
        self._refresh()
        return list(self._entries)

    def check(self, receipt: WitnessReceipt) -> bool:
        self._refresh()
        if not isinstance(receipt, WitnessReceipt):
            try:
                receipt = entry_from_dict(receipt)
            except (KeyError, TypeError, ValueError):
                return False
        if receipt.index < 0 or receipt.index >= len(self._entries):
            return False
        held = self._entries[receipt.index]
        if held != receipt:
            return False
        want = mac_for(self._key, held.index, held.record_fp, held.head, held.t)
        return hmac.compare_digest(want, held.mac)
