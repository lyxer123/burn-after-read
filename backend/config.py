#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""onedl backend configuration (env-overridable)."""
import os

BASE = os.environ.get("ONEDL_BASE", "/opt/onedl")
STORE = os.path.join(BASE, "store")          # original uploaded files
WM = os.path.join(BASE, "wm")                # watermarked copies (cache)
DB = os.path.join(BASE, "onedl.db")          # SQLite database
FRONTEND_DIST = os.environ.get("ONEDL_WEB", os.path.join(BASE, "web"))

PORT = int(os.environ.get("ONEDL_PORT", "8777"))
# When nginx runs in a Docker container it cannot reach 127.0.0.1 of the host;
# set ONEDL_HOST to the docker bridge gateway IP (e.g. 177.7.0.1).
HOST_BIND = os.environ.get("ONEDL_HOST", "127.0.0.1")
PUBLIC_HOST = os.environ.get("ONEDL_PUBLIC_HOST", "http://117.72.15.132")

# WeChat Official Account adapter (optional). Set ONEDL_WX_TOKEN to enable /wechat.
WX_TOKEN = os.environ.get("ONEDL_WX_TOKEN", "")

for _d in (BASE, STORE, WM):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass
