#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SQLite persistence for onedl.

Replaces the old file-based tokens/consumed directories. Three tables:
  files       - one row per uploaded original file
  links       - one row per generated one-time download link
  access_log  - every view / download / burn / recall event
"""
import os
import sqlite3
import random
from datetime import datetime, timezone, timedelta

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY,
    original_name TEXT NOT NULL,
    store_path    TEXT NOT NULL,
    size          INTEGER,
    mime          TEXT,
    keywords      TEXT,    -- comma-separated aliases for WeChat matching (e.g. 白皮书,中压直挂充电白皮书)
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    id             INTEGER PRIMARY KEY,
    token          TEXT UNIQUE NOT NULL,
    file_id        INTEGER NOT NULL,
    recipient      TEXT,
    watermark_text TEXT,
    status         TEXT NOT NULL DEFAULT 'generated',  -- generated|shared|downloaded|burned
    created_at     TEXT NOT NULL,
    shared_at      TEXT,
    downloaded_at  TEXT,
    burned_at      TEXT,
    download_ip    TEXT,
    download_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(file_id) REFERENCES files(id)
);
CREATE TABLE IF NOT EXISTS access_log (
    id      INTEGER PRIMARY KEY,
    token   TEXT,
    event   TEXT NOT NULL,   -- view|download|burn|recall|denied|share
    ip      TEXT,
    ua      TEXT,
    at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_links_token ON links(token);
CREATE INDEX IF NOT EXISTS idx_links_status ON links(status);
"""


def _conn():
    c = sqlite3.connect(config.DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = _conn()
    c.executescript(SCHEMA)
    c.commit()
    c.close()
    _migrate()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def add_file(original_name, store_path, size, mime, keywords=""):
    c = _conn()
    cur = c.execute(
        "INSERT INTO files (original_name, store_path, size, mime, keywords, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (original_name, store_path, size, mime, keywords or "", now_iso()))
    fid = cur.lastrowid
    c.commit()
    c.close()
    return fid


def _migrate():
    """Add columns that may be missing on old DBs."""
    c = _conn()
    cols = [r[1] for r in c.execute("PRAGMA table_info(files)")]
    if "keywords" not in cols:
        c.execute("ALTER TABLE files ADD COLUMN keywords TEXT")
        c.commit()
    lcols = [r[1] for r in c.execute("PRAGMA table_info(links)")]
    for col, ctype in (("captcha_q", "TEXT"), ("captcha_a", "INTEGER"),
                       ("grace_until", "TEXT")):
        if col not in lcols:
            c.execute("ALTER TABLE links ADD COLUMN %s %s" % (col, ctype))
            c.commit()
    # Existing rows predate the grace window: treat their grace as already
    # expired so they burn on the very next fetch (one-time behaviour).
    if "grace_until" not in lcols:
        c.execute("UPDATE links SET grace_until=created_at WHERE grace_until IS NULL")
        c.commit()
    c.close()


def _make_captcha():
    """A trivial arithmetic question used as an anti-bot gate.

    WeChat's link-security scanner runs a real WebView: it loads the landing
    page AND submits the download form, which would burn a one-time link ahead
    of the user. A human reads "7 + 5 = ?" and types 12; an automated scanner
    never solves it, so the link survives until a real person downloads.
    """
    a = random.randint(3, 15)
    b = random.randint(3, 15)
    return "%d + %d" % (a, b), a + b


def add_link(token, file_id, recipient, watermark_text, ignore_dup=False):
    q, a = _make_captcha()
    # WeChat links get a scanner grace window so the platform's automated
    # link-scanner (a real browser engine) cannot burn the one-time link ahead
    # of the human. Manual links get no grace (they burn on first download).
    grace_until = None
    if recipient and str(recipient).startswith("wechat:"):
        grace_until = (datetime.now(timezone.utc)
                       + timedelta(seconds=config.WECHAT_GRACE_SECONDS)).isoformat()
    c = _conn()
    sql = ("INSERT OR IGNORE INTO links (token, file_id, recipient, watermark_text, "
           "status, created_at, captcha_q, captcha_a, grace_until) "
           "VALUES (?,?,?,?,?,?,?,?,?)" if ignore_dup else
           "INSERT INTO links (token, file_id, recipient, watermark_text, "
           "status, created_at, captcha_q, captcha_a, grace_until) "
           "VALUES (?,?,?,?,?,?,?,?,?)")
    c.execute(sql,
              (token, file_id, recipient or "", watermark_text or "",
               "generated", now_iso(), q, a, grace_until))
    c.commit()
    c.close()


def get_link(token):
    c = _conn()
    row = c.execute(
        "SELECT l.*, f.original_name, f.store_path, f.mime, f.size "
        "FROM links l JOIN files f ON f.id=l.file_id WHERE l.token=?",
        (token,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_file(file_id):
    c = _conn()
    row = c.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def list_links():
    c = _conn()
    rows = c.execute(
        "SELECT l.*, f.original_name, f.mime, f.size "
        "FROM links l JOIN files f ON f.id=l.file_id "
        "ORDER BY l.created_at DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]


def find_file_by_keyword(keyword):
    """Latest file that matches the WeChat keyword.

    Matches if the user message (keyword) is contained in the file's
    original_name OR its keywords aliases, or vice versa (alias/message
    contains the file name). Returns the most recently uploaded match.
    """
    kw = (keyword or "").strip()
    if not kw:
        return None
    c = _conn()
    rows = c.execute(
        "SELECT * FROM files ORDER BY id DESC").fetchall()
    c.close()
    for r in rows:
        hay = (r["original_name"] or "") + " " + (r["keywords"] or "")
        if kw in hay or hay in kw:
            return dict(r)
    return None


def mark_shared(token):
    c = _conn()
    c.execute(
        "UPDATE links SET shared_at=?, status='shared' "
        "WHERE token=? AND status IN ('generated','shared')",
        (now_iso(), token))
    c.commit()
    c.close()


def log(token, event, ip, ua):
    c = _conn()
    c.execute(
        "INSERT INTO access_log (token, event, ip, ua, at) VALUES (?,?,?,?,?)",
        (token, event, ip, ua, now_iso()))
    c.commit()
    c.close()


def reserve(token):
    """Atomically flip status to 'downloaded' so only ONE request wins.
    Returns number of rows changed (0 == already taken)."""
    c = _conn()
    cur = c.execute(
        "UPDATE links SET status='downloaded', downloaded_at=? "
        "WHERE token=? AND status!='burned'",
        (now_iso(), token))
    n = cur.rowcount
    c.commit()
    c.close()
    return n


def finalize_burn(token, ip):
    """Called after the file has been streamed: mark burned + count."""
    c = _conn()
    c.execute(
        "UPDATE links SET status='burned', burned_at=?, download_ip=?, "
        "download_count=download_count+1 WHERE token=? AND status='downloaded'",
        (now_iso(), ip, token))
    c.commit()
    c.close()
    log(token, "burn", ip, "")


def inc_fetch(token):
    """Record one successful file delivery (used for the fetch cap)."""
    c = _conn()
    c.execute("UPDATE links SET download_count=download_count+1 WHERE token=?",
              (token,))
    c.commit()
    c.close()


def burn_downloaded(token, ip):
    """Burn a WeChat (reusable) link after the human's download.

    Unlike finalize_burn this does not require status='downloaded' (WeChat
    links never pass through reserve()), and it does NOT increment
    download_count again because inc_fetch() already counted this delivery.
    """
    c = _conn()
    c.execute(
        "UPDATE links SET status='burned', burned_at=?, download_ip=? "
        "WHERE token=? AND status!='burned'",
        (now_iso(), ip, token))
    c.commit()
    c.close()
    log(token, "burn", ip, "")


def burn(token, reason="recall"):
    """Admin recall: burn a link that has not been downloaded yet."""
    c = _conn()
    cur = c.execute(
        "UPDATE links SET status='burned', burned_at=? "
        "WHERE token=? AND status!='burned'",
        (now_iso(), token))
    n = cur.rowcount
    c.commit()
    c.close()
    if n:
        log(token, reason, "", "")
    return n
