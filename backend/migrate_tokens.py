#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""One-shot migration: import legacy file-based tokens (minimal onedl) into SQLite.

Usage (inside the onedl container, legacy dirs mounted at /legacy):
    python migrate_tokens.py /legacy/tokens /legacy/consumed

Token file format (legacy):
    line 1: internal store filename (e.g. whitepaper.pdf)
    line 2 (optional): original display filename
Active tokens  -> links row status='generated'
Consumed tokens-> links row status='burned'
Files are expected under ONEDL_BASE/store/<internal filename>.
"""
import os
import sys

import config
import db


def read_token_file(path):
    with open(path) as f:
        lines = [l.strip() for l in f.read().splitlines() if l.strip()]
    if not lines:
        return None, None
    internal = os.path.basename(lines[0])
    display = lines[1] if len(lines) > 1 else internal
    return internal, display


def main(tokens_dir, consumed_dir):
    db.init()
    file_ids = {}  # internal filename -> file_id

    def file_id_for(internal, display):
        if internal not in file_ids:
            store_path = os.path.join(config.STORE, internal)
            if not os.path.exists(store_path):
                print("SKIP (missing store file):", store_path)
                return None
            size = os.path.getsize(store_path)
            fid = db.add_file(display, store_path, size, "application/pdf")
            file_ids[internal] = fid
        return file_ids[internal]

    n_gen = n_burn = 0
    if os.path.isdir(tokens_dir):
        for name in sorted(os.listdir(tokens_dir)):
            internal, display = read_token_file(os.path.join(tokens_dir, name))
            fid = file_id_for(internal, display) if internal else None
            if fid is None:
                continue
            db.add_link(name, fid, "legacy", "", ignore_dup=True)
            n_gen += 1
    if os.path.isdir(consumed_dir):
        for name in sorted(os.listdir(consumed_dir)):
            internal, display = read_token_file(os.path.join(consumed_dir, name))
            fid = file_id_for(internal, display) if internal else None
            if fid is None:
                continue
            db.add_link(name, fid, "legacy", "", ignore_dup=True)
            db.burn(name, reason="legacy-consumed")
            n_burn += 1
    print("migrated: generated=%d burned=%d" % (n_gen, n_burn))


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "/legacy/tokens"
    c = sys.argv[2] if len(sys.argv) > 2 else "/legacy/consumed"
    main(t, c)
