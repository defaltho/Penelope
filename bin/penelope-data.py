#!/usr/bin/env python3
"""Export / import of ALL Penelope data (single-file backup).

Bundles the whole `data/` directory into one `.penelope.zip`:
  - memory.db        (copied via SQLite's online backup API -> consistent even
                      while the app holds a WAL connection; the .db-wal/.db-shm
                      side files are intentionally NOT included)
  - images/          (attached images)
  - adventures/      (saved stories, if present)
  - any other files under data/ (except the live -wal/-shm and old _backups/)

Import restores such an archive, BACKING UP the current data first.

Run it with the server STOPPED (on Windows the live DB file is locked).

Usage:
  python bin/penelope-data.py export  [out.penelope.zip]
  python bin/penelope-data.py import  <in.penelope.zip>  [--yes]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ASSISTANT_DB_PATH", PROJECT_ROOT / "data" / "memory.db")).resolve().parent
DB_NAME = "memory.db"
SKIP = {"memory.db-wal", "memory.db-shm"}
SKIP_DIRS = {"_backups"}


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _consistent_db_copy(src: Path, dst: Path) -> None:
    """Copy a (possibly WAL-active) SQLite DB consistently via the backup API."""
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def do_export(out_path: Path) -> None:
    if not DATA_DIR.exists():
        sys.exit(f"data dir not found: {DATA_DIR}")
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db = DATA_DIR / DB_NAME
    tmp_db = DATA_DIR / f".export-{_ts()}.db"
    try:
        if db.exists():
            _consistent_db_copy(db, tmp_db)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            if tmp_db.exists():
                z.write(tmp_db, DB_NAME)
            for root, dirs, files in os.walk(DATA_DIR):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    p = Path(root) / f
                    rel = p.relative_to(DATA_DIR).as_posix()
                    if rel == DB_NAME or f in SKIP or p == tmp_db:
                        continue
                    z.write(p, rel)
    finally:
        if tmp_db.exists():
            tmp_db.unlink()

    size = out_path.stat().st_size
    print(f"Exported {DATA_DIR}  ->  {out_path}  ({size/1024/1024:.2f} MB)")


def do_import(in_path: Path, assume_yes: bool) -> None:
    in_path = in_path.resolve()
    if not in_path.exists():
        sys.exit(f"archive not found: {in_path}")
    with zipfile.ZipFile(in_path) as z:
        names = z.namelist()
        if not any(n == DB_NAME or n.startswith("images/") or n.startswith("adventures/") for n in names):
            sys.exit("this does not look like a Penelope data archive (no memory.db / images / adventures).")
        # Reject path traversal.
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts:
                sys.exit(f"unsafe path in archive: {n}")

    if not assume_yes:
        ans = input(f"Replace data in {DATA_DIR}? Current data is backed up first. [y/N] ").strip().lower()
        if ans not in ("y", "yes", "s", "sim"):
            sys.exit("aborted.")

    # 1) back up current data
    if DATA_DIR.exists() and any(DATA_DIR.iterdir()):
        backup = DATA_DIR / "_backups" / _ts()
        backup.mkdir(parents=True, exist_ok=True)
        for item in DATA_DIR.iterdir():
            if item.name == "_backups":
                continue
            shutil.move(str(item), str(backup / item.name))
        print(f"Current data backed up to: {backup}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 2) extract
    with zipfile.ZipFile(in_path) as z:
        z.extractall(DATA_DIR)
    print(f"Imported {in_path}  ->  {DATA_DIR}")
    print("Restart Penelope for the change to take effect.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Export / import all Penelope data.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("export", help="bundle all data into one archive")
    pe.add_argument("out", nargs="?", default=f"penelope-{_ts()}.penelope.zip")
    pi = sub.add_parser("import", help="restore data from an archive (backs up current data first)")
    pi.add_argument("infile")
    pi.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    if args.cmd == "export":
        do_export(Path(args.out))
    else:
        do_import(Path(args.infile), args.yes)


if __name__ == "__main__":
    main()
