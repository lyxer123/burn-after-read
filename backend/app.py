#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""onedl backend - FastAPI app.

Endpoints
  POST /api/links            upload a file + mint N one-time links
  GET  /api/links           list all links with status
  GET  /api/links/<token>   single link status
  POST /api/links/<token>/share   mark as shared (user sent it)
  POST /api/links/<token>/burn    admin recall (burn before download)
  GET  /dl/<token>          download (burns the link after first success)
  GET  /                    serves the built Vue frontend (if present)
"""
import os
import uuid
import shutil
import mimetypes
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
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


@app.get("/dl/{token}")
def download(token: str, request: Request, background: BackgroundTasks):
    l = db.get_link(token)
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    if not l or l["status"] == "burned":
        db.log(token if l else None, "denied", ip, ua)
        raise HTTPException(404, "Link expired or invalid")
    # atomically reserve so only one client ever gets the file
    if db.reserve(token) == 0:
        db.log(token, "denied", ip, ua)
        raise HTTPException(404, "Link expired or invalid")

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
