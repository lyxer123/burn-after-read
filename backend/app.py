#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""onedl backend - FastAPI app.

Endpoints
  POST /api/links            upload a file + mint N one-time links
  GET  /api/links           list all links with status
  GET  /api/links/<token>   single link status
  POST /api/links/<token>/share   mark as shared (user sent it)
  POST /api/links/<token>/burn    admin recall (burn before download)
  GET  /dl/<token>          landing page (does NOT burn; shows a download button)
  POST /dl/<token>/fetch    actually streams the file and burns the link
  GET  /                    serves the built Vue frontend (if present)
"""
import os
import uuid
import shutil
import mimetypes
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
import db
import watermark

app = FastAPI(title="onedl - burn after read")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def public_url(token):
    return "%s/dl/%s" % (config.PUBLIC_HOST, token)


@app.on_event("startup")
def _startup():
    db.init()


@app.post("/api/links")
async def create_links(
    file: UploadFile = File(...),
    count: int = Form(1),
    recipient: str = Form(""),
    watermark_text: str = Form(""),
    keywords: str = Form(""),
):
    ext = os.path.splitext(file.filename or "file")[1]
    internal = uuid.uuid4().hex + ext
    store_path = os.path.join(config.STORE, internal)
    with open(store_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size = os.path.getsize(store_path)
    mime, _ = mimetypes.guess_type(file.filename or "")
    fid = db.add_file(file.filename or internal, store_path, size,
                      mime or "application/octet-stream", keywords)
    links = []
    for _ in range(max(1, int(count))):
        token = uuid.uuid4().hex
        db.add_link(token, fid, recipient, watermark_text)
        links.append({
            "token": token,
            "url": public_url(token),
            "recipient": recipient,
            "watermark_text": watermark_text,
        })
    return {"links": links, "file_id": fid}


@app.get("/api/links")
def list_links():
    return {"links": db.list_links()}


@app.get("/api/links/{token}")
def get_link(token: str):
    l = db.get_link(token)
    if not l:
        raise HTTPException(404)
    return l


@app.post("/api/links/{token}/share")
def mark_shared(token: str):
    db.mark_shared(token)
    return {"ok": True}


@app.post("/api/links/{token}/burn")
def burn_link(token: str):
    n = db.burn(token, reason="recall")
    if not n:
        raise HTTPException(404, "link not found or already burned")
    return {"ok": True}


# ---------------------------------------------------------------------------
# GET  /dl/{token}        -> landing page (does NOT burn).
#     Automated prefetchers (e.g. WeChat link-preview / security scanner)
#     only ever issue GET, so they hit this route (or GET /fetch, which just
#     redirects back here). The one-time link survives until a human explicitly
#     clicks the download button.
# POST /dl/{token}/fetch  -> stream the file and burn the link (the real grab).
#     POST-only on purpose: prefetch bots never POST, so they can never
#     consume the link ahead of the user.
# ---------------------------------------------------------------------------
LANDING_TMPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>文件下载 · 阅后即焚</title>
<style>
  body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif;
       background:#f5f7fa;color:#1f2329;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
  .card{background:#fff;border-radius:14px;box-shadow:0 6px 24px rgba(0,0,0,.08);max-width:420px;width:100%;padding:28px}
  h1{font-size:19px;margin:0 0 16px}
  .file{background:#f5f7fa;border-radius:10px;padding:14px 16px;margin-bottom:14px}
  .file .name{font-weight:600;word-break:break-all}
  .file .meta{color:#8a9099;font-size:13px;margin-top:6px}
  .warn{color:#b54708;background:#fff7e6;border:1px solid #ffd591;border-radius:8px;padding:10px 12px;font-size:13px;margin-bottom:18px}
  .wm{color:#59606b;font-size:12px;margin-bottom:18px}
  a.btn,button.btn{display:block;width:100%;border:0;cursor:pointer;text-align:center;background:#1677ff;color:#fff;text-decoration:none;font-weight:600;
        padding:13px;border-radius:10px;font-size:16px;box-sizing:border-box;font-family:inherit}
  a.btn:active,button.btn:active{background:#0958d9}
</style></head>
<body><div class="card">
  <h1>🔒 文件下载（阅后即焚）</h1>
  <div class="file">
    <div class="name">{name}</div>
    <div class="meta">{size} · {mime}</div>
  </div>
  <div class="warn">此链接仅可下载一次，下载后将自动失效，无法再次打开。</div>
  {wm}
  <form method="post" action="{fetch_url}" onsubmit="this.querySelector('button').textContent='正在准备下载…';">
    <button class="btn" type="submit">下载文件</button>
  </form>
</div></body></html>"""

ERROR_TMPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>链接失效</title>
<style>
  body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif;
       background:#f5f7fa;color:#1f2329;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
  .card{background:#fff;border-radius:14px;box-shadow:0 6px 24px rgba(0,0,0,.08);max-width:420px;width:100%;padding:28px;text-align:center}
  h1{font-size:19px;margin:0 0 12px;color:#cf1322}
  p{color:#59606b;font-size:14px;line-height:1.6;margin:0}
</style></head>
<body><div class="card">
  <h1>链接已失效或无效</h1>
  <p>该下载链接不存在、已被下载一次，或已被撤回。</p>
</div></body></html>"""


def _fmt_size(n):
    try:
        n = int(n)
    except Exception:
        return "未知大小"
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024)
    return "%.1f MB" % (n / 1024 / 1024)


def _error_page():
    return HTMLResponse(content=ERROR_TMPL, status_code=404)


@app.get("/dl/{token}")
def download_page(token: str, request: Request):
    """Landing page for a one-time link. Never burns the link by itself,
    so link-preview / prefetch bots cannot consume it ahead of the user."""
    l = db.get_link(token)
    if not l or l["status"] == "burned":
        return _error_page()
    f = db.get_file(l["file_id"])
    wm = ""
    if l.get("watermark_text"):
        wm = '<div class="wm">文件已添加溯源水印：%s</div>' % l["watermark_text"]
    html = LANDING_TMPL
    html = html.replace("{name}", f["original_name"])
    html = html.replace("{size}", _fmt_size(f.get("size")))
    html = html.replace("{mime}", f.get("mime") or "文件")
    html = html.replace("{wm}", wm)
    html = html.replace("{fetch_url}", "/dl/%s/fetch" % token)
    return HTMLResponse(content=html)


@app.get("/dl/{token}/fetch")
def download_fetch_get(token: str):
    """Prefetch bots (WeChat link scanner, etc.) only ever issue GET.
    Never burn on GET - just bounce them back to the landing page."""
    return RedirectResponse(url="/dl/%s" % token, status_code=302)


@app.post("/dl/{token}/fetch")
def download_fetch(token: str, request: Request, background: BackgroundTasks):
    """Actually stream the file and burn the one-time link.
    POST-only so automated GET prefetchers can never consume it."""
    l = db.get_link(token)
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    if not l or l["status"] == "burned":
        db.log(token if l else None, "denied", ip, ua)
        return _error_page()
    # atomically reserve so only one client ever gets the file
    if db.reserve(token) == 0:
        db.log(token, "denied", ip, ua)
        return _error_page()

    f = db.get_file(l["file_id"])
    path = f["store_path"]
    mime = f["mime"]
    display = f["original_name"]
    if l["watermark_text"]:
        ext = os.path.splitext(path)[1]
        wm_path = os.path.join(config.WM, token + ext)
        if not os.path.exists(wm_path):
            watermark.apply(path, wm_path, l["watermark_text"])
        if os.path.exists(wm_path):
            path = wm_path

    def _burn():
        db.finalize_burn(token, ip)
        db.log(token, "download", ip, ua)

    background.add_task(_burn)
    return FileResponse(path, media_type=mime, filename=display)


if config.WX_TOKEN:
    from wechat import router as wechat_router
    app.include_router(wechat_router)

if os.path.isdir(config.FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True),
              name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST_BIND, port=config.PORT)
