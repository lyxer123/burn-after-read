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
WX_APPID = os.environ.get("ONEDL_WX_APPID", "")      # for active push / customer-service msg
WX_SECRET = os.environ.get("ONEDL_WX_SECRET", "")

# WeChat links must survive the platform's automated link-scanner (a full
# browser engine that downloads the file within seconds of the link being
# sent) while still behaving as "burn after read" for the human.
#   * Downloads that happen inside the grace window (the scanner) never burn.
#   * The first download AFTER the window (the human) burns the link.
#   * A hard cap on total deliveries is a secondary safety net against anyone
#     sharing the link and re-downloading it indefinitely.
WECHAT_GRACE_SECONDS = 120   # scanner fires within this window -> free fetches
WECHAT_MAX_FETCHES = 3       # total deliveries allowed before the link burns

for _d in (BASE, STORE, WM):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass
