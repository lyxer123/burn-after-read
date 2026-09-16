#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Optional WeChat Official Account (公众号) webhook adapter.

Enable by setting ONEDL_WX_TOKEN (and optionally ONEDL_WX_APPID / ONEDL_WX_SECRET).
app.py mounts /wechat automatically when ONEDL_WX_TOKEN is present.

Flow: user messages the OA -> WeChat POSTs XML to /wechat -> we mint a one-time
link (watermark = openid for traceability) -> reply with the link (passive reply,
or 客服消息 if within 48h). Status is then visible in the normal /api/links view.
"""
import hashlib
import time
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

import config
import db

router = APIRouter(prefix="/wechat", tags=["wechat"])

# Optional static keyword -> file_id mapping (takes priority over name match).
KEYWORD_MAP = {}


def _find_file(keyword):
    if keyword in KEYWORD_MAP:
        return db.get_file(KEYWORD_MAP[keyword])
    # dynamic match: latest uploaded file whose name contains the keyword
    return db.find_file_by_keyword(keyword)


def _sha1(*parts):
    return hashlib.sha1("".join(sorted(parts)).encode("utf-8")).hexdigest()


def _text_reply(from_user, to_user, content):
    ts = int(time.time())
    xml = (
        "<xml><ToUserName><![CDATA[%s]]></ToUserName>"
        "<FromUserName><![CDATA[%s]]></FromUserName>"
        "<CreateTime>%d</CreateTime><MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[%s]]></Content></xml>"
    ) % (from_user, to_user, ts, content)
    return xml


@router.get("")
async def verify(request: Request):
    q = request.query_params
    token = config.WX_TOKEN or ""
    sig = q.get("signature", "")
    ts, nonce, echostr = q.get("timestamp", ""), q.get("nonce", ""), q.get("echostr", "")
    if _sha1(token, ts, nonce) == sig:
        return PlainTextResponse(echostr)
    return PlainTextResponse("invalid", status_code=403)


@router.post("")
async def message(request: Request):
    body = await request.body()
    try:
        root = ET.fromstring(body)
        d = {c.tag: (c.text or "") for c in root}
    except Exception:
        return Response(content="", media_type="text/xml")
    openid = d.get("FromUserName", "")
    to_user = d.get("ToUserName", "")
    keyword = (d.get("Content") or "").strip()
    f = _find_file(keyword)
    if f is None:
        xml = _text_reply(openid, to_user, "未找到匹配的文件，请发送文件名关键词（如：白皮书）。")
        return Response(content=xml, media_type="application/xml")
    # mint a single one-time link, watermarked with the requester's openid
    import uuid
    token = uuid.uuid4().hex
    db.add_link(token, f["id"], "wechat:" + openid, "微信:" + openid)
    url = "%s/dl/%s" % (config.PUBLIC_HOST, token)
    xml = _text_reply(openid, to_user,
                      "你的文件（下载一次后失效）：\n" + url)
    return Response(content=xml, media_type="application/xml")
