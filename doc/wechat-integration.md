# 微信公众号（公众号）衔接方案 · 阅后即焚下载

> 目标：用户在公众号里说"我要某某文件"，系统自动给他推送一个**一次性下载链接**，
> 对方点开下载后链接即焚；运营者在后台（Vue 页面）可看到该链接**是否已分享 / 已下载 / 已焚**。
> 同时，下载时文件**自动打上水印**（如"微信 openid:xxxx"），一旦外泄即可溯源到是谁要的。

---

## 1. 结论（能不能做？）

**能做，但受公众号消息能力约束，不是"想推就推"。**

| 场景 | 可行性 | 说明 |
|------|--------|------|
| 用户主动发消息 → 公众号被动回复链接 | ✅ 强烈推荐 | 5 秒内被动回复，最稳；本方案主路径 |
| 48 小时内互动过 → 用**客服消息**主动推送 | ✅ | 需"服务号"且开通客服接口 |
| 任意时间主动推送（模板/订阅消息） | ⚠️ 受限 | 模板消息已收紧；需申请模板或一次性订阅 |
| 完全无互动就推链接 | ❌ | 公众号做不到，需改用**企业微信/小程序** |

**所以可行的最小闭环是**：用户给公众号发关键词（或点菜单）→ 被动回复 / 客服消息带一次性链接 → 后台追踪状态。

---

## 2. 架构

```
   微信用户                微信服务器                 onedl 后端
     │  发消息 "白皮书"        │                         │
     │ ───────────────────▶  │  POST /wechat (XML)      │
     │                       │ ───────────────────────▶ │ 解析 openid + 关键词
     │                       │                         │ ① 查文件表得到 file_id
     │                       │                         │ ② 调 /api/links 逻辑 mint 一个
     │                       │                         │    token（watermark=openid）
     │                       │ ◀── 被动回复 XML(链接) ──│
     │ ◀────────────────────│                         │
     │  收到链接                                  │
     │  点开 /dl/<token>  ─────────────────────────────▶│ 下载 + 自动水印 + 焚毁
     │                                               │ 后台 /api/links 看到
     │                                               │ status=burned / 下载IP
```

后台（`frontend/` 的 Vue 页面）直接读 `/api/links`，无需改动即可看到每条链接的
`shared_at / downloaded_at / burned_at / download_ip`，与公众号来源完全打通。

---

## 3. 需要的资源（一次性的）

1. 一个**已认证的服务号**（订阅号没有客服消息/高级接口，只能被动回复）。
2. 公众号后台「基本配置」里设：
   - **服务器地址(URL)**：`https://你的域名/wechat`（必须 **HTTPS + 公网可访问**）
   - **Token**：自定义字符串（与后端 `ONEDL_WX_TOKEN` 一致）
   - **消息加解密方式**：明文模式（先跑通再说，后续可上安全模式）
3. **有效证书**：微信校验回调要求受信任 CA 签发的 HTTPS（自签证书会被拒）。
   京东云已有 nginx:443，但没有合法证书 → 用 **Let's Encrypt（certbot）** 签发，或把回调挂到已有可信域名的子路径。
4. AppID / AppSecret（被动回复不需要；若想拿用户昵称走 OAuth 才需要）。

> ⚠️ **证书坑**：当前 117.72.15.132 的 443 是自签证书，微信回调校验会失败。
> 必须先有合法域名 + Let's Encrypt 证书，否则公众号侧配置保存不了。

---

## 4. 后台契约（已有，直接复用）

`backend/app.py` 已具备：

- `POST /api/links`（multipart：`file, count, recipient, watermark_text`）→ 生成链接
- `GET  /api/links` → 列表含 `status / shared_at / downloaded_at / burned_at / download_ip`
- `GET  /dl/<token>` → 下载并自动水印 + 焚毁

公众号适配器只需"收到消息→调一次生成逻辑→把 URL 拼进回复"即可。

---

## 5. 适配器实现（见 `backend/wechat.py`，按 `ONEDL_WX_TOKEN` 自动挂载）

核心逻辑（伪代码，真实可用版在仓库内）：

```python
# 1) GET /wechat  微信签名校验（echostr 原样返回）
def verify(token, signature, timestamp, nonce, echostr):
    if sha1(sorted([token, timestamp, nonce])) == signature:
        return echostr

# 2) POST /wechat  收到用户消息
def on_message(xml):
    openid = xml.FromUserName
    keyword = xml.Content.strip()
    file_id = KEYWORD_MAP.get(keyword)          # 关键词 -> 文件
    if not file_id:
        return reply(openid, "发送文件名关键词获取下载链接")
    token = mint_link(file_id, recipient=openid,
                      watermark_text="微信:" + openid)   # 水印溯源
    url = f"{PUBLIC_HOST}/dl/{token}"
    return reply(openid, "你的文件（下载一次后失效）：\n" + url)
```

要点：
- **水印用 openid**：即使文件被二次转发，也能定位到最初是谁向公众号索要的。
- 想显示"张三"而不是 openid，需要 **OAuth 网页授权（snsapi_userinfo）** 拿到昵称，
  但要多一次重定向授权，按需开启。
- 被动回复只有 **5 秒**窗口，本系统 mint 是纯本地 SQLite 操作，毫秒级，足够。

---

## 6. 主动推送（客服消息）扩展

若用户在 48h 内与公众号互动过，可走客服消息主动推，不必等用户发消息：

```
POST https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token=ACCESS_TOKEN
{ "touser": "<openid>", "msgtype": "text",
  "text": { "content": "你的文件（下载一次后失效）：https://域名/dl/<token>" } }
```

`ACCESS_TOKEN` 用 `AppID+AppSecret` 向 `cgi-bin/token` 换取，需缓存（2 小时过期）。
建议在 `wechat.py` 里加一个 token 缓存。

---

## 7. 部署到京东云（关键变更）

1. **合法 HTTPS**：certbot 在 `117.72.15.132` 上签发 Let's Encrypt 证书，覆盖 `/wechat`。
2. **nginx 增加反代**：把 `/wechat` 也转发到 onedl 后端（与 `/dl`、`/api` 同端口）。
   ```nginx
   location ^~ /wechat { proxy_pass http://177.7.0.1:8777/wechat; }
   ```
3. **后端配置环境变量**：`ONEDL_WX_TOKEN`、`ONEDL_WX_APPID`、`ONEDL_WX_SECRET`、
   `ONEDL_WEB=前端dist`。`wechat.py` 在 `ONEDL_WX_TOKEN` 存在时自动挂载。
4. 新后端需 **Python 3**（当前宿主只有 python2.7）→ 用本项目 `backend/Dockerfile`
   起容器，或在宿主用 venv 跑 Python 3。原 python2.7 的极简 `service.py` 可保留作兜底。

---

## 8. 局限与替代

- **被动回复 5 秒 / 48h 客服窗口**是硬限制。若要做到"任何时候都能推"，用：
  - **企业微信**（可直接发应用消息给成员，无 48h 限制）；
  - **小程序**（订阅消息/一次性订阅消息，体验更顺）。
- **openid 溯源足够定位泄露者**；如需"人话"昵称要走 OAuth。
- 关键词→文件映射目前是扁平表（`KEYWORD_MAP`），生产可换成数据库表或后台配置界面。

---

## 9. 验收清单

- [ ] 服务号已认证，基本配置填好 Token + 服务器 URL（HTTPS 可达）
- [ ] certbot 证书就位，微信能保存配置（echostr 校验通过）
- [ ] 用户发关键词 → 收到一次性链接
- [ ] 点链接下载成功、文件带水印、后再点 404
- [ ] 后台 Vue 页面该链接状态变为 `已下载（已焚）`，`download_ip` 有值
- [ ] （可选）48h 内用客服消息主动推送
