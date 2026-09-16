# onedl — 阅后即焚下载服务（One-time Download / Burn-after-read）

一个「链接下载一次即失效」的服务：生成不可猜测的随机链接，对方点开下载成功后，
**同一个链接立刻作废（第二次起 404）**。本仓库提供两套实现：

| 模式 | 路径 | 依赖 | 能力 |
|------|------|------|------|
| **极简版** | 仓库根 `service.py` + `gen.py` | 仅 Python 2.7 标准库 | 阅后即焚（文件类型无关），无数据库 |
| **全栈版（推荐）** | `backend/` + `frontend/` | Python 3 + FastAPI + SQLite；Vue 3 | 上面全部 + **后台可视化 / SQLite / 自动水印 / 微信公众号衔接** |

> 仓库根的服务当前仍运行在京东云（`/opt/onedl`，python2.7，零依赖兜底）。
> 全栈版是后续主推方案，需要 Python 3（用 Docker 跑在京东云上）。

---

## 它能干什么（对应 4 个需求）

1. **前端页面生成 / 查看状态**：Vue 3 页面可批量生成链接，并实时查看每条链接
   **是否已分享 / 已下载 / 已焚毁**（`backend/` + `frontend/`）。
2. **SQLite 存储**：链接、文件、访问日志全部存进 `onedl.db`，替代原来的目录文件
   （`backend/db.py`）。
3. **微信公众号衔接**：用户在公众号说"我要某文件"，自动推送一次性链接，后台可追踪
   下载/焚毁状态。方案见 **`doc/wechat-integration.md`**，适配器见 `backend/wechat.py`。
4. **自动水印溯源**：生成链接时可填写水印文字（如"发给:张三 / 微信 openid"），下载时
   **自动把文字打进 PDF / 图片**再发出，文件外泄即可定位来源（`backend/watermark.py`）。

---

## 目录结构

```
onedl/
├── service.py            # 极简版服务（python2.7，零依赖，文件型 token）
├── gen.py                # 极简版：生成一次性链接
├── onedl.service         # 极简版 systemd 单元
├── onedl.nginx.conf      # nginx /dl/ 反代片段
├── install.sh            # 极简版一键安装
├── backend/              # 全栈版后端（FastAPI + SQLite + 水印 + 公众号）
│   ├── app.py            # REST API + /dl/<token> 焚毁下载
│   ├── db.py             # SQLite：files / links / access_log
│   ├── watermark.py      # PDF(reportlab+pypdf) / 图片(Pillow) 水印
│   ├── wechat.py         # 公众号 webhook 适配器（设 ONEDL_WX_TOKEN 自动挂载）
│   ├── config.py         # 环境变量配置
│   └── requirements.txt
├── frontend/             # 全栈版前端（Vue 3 + Vite）
│   └── src/App.vue       # 生成表单 + 链接状态表格
├── doc/
│   └── wechat-integration.md   # 公众号衔接方案（能否做 / 怎么做 / 限制）
├── Dockerfile            # 多阶段构建（前端构建 + Python3 后端）
├── docker-compose.yml
├── LICENSE               # MIT
└── README.md
```

---

## 全栈版本地开发

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 可选：前端构建产物目录（后端会托管 SPA）
export ONEDL_WEB=../frontend/dist
uvicorn app:app --host 127.0.0.1 --port 8777
```

主要接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/links` | 上传文件 + `count` + `recipient` + `watermark_text` → 生成 N 个链接 |
| GET  | `/api/links` | 列出全部链接（含 `status` / `shared_at` / `downloaded_at` / `burned_at` / `download_ip`） |
| GET  | `/api/links/{token}` | 单条状态 |
| POST | `/api/links/{token}/share` | 标记为已分享 |
| POST | `/api/links/{token}/burn` | 管理员召回（下载前焚毁） |
| GET  | `/dl/{token}` | 下载（首成即焚，自动水印） |
| GET  | `/wechat` | 公众号回调（需在 `ONEDL_WX_TOKEN` 时启用） |

### 前端

```bash
cd frontend
npm install
npm run dev          # 默认代理 /api、/dl 到 http://localhost:8777
# 生产：npm run build -> dist/，由后端 ONEDL_WEB 托管
```

---

## 部署到京东云

环境现状：宿主只有 **Python 2.7**（极简版可直接跑）；全栈版需要 **Python 3** → 用 Docker。

### 极简版（已在线上）

```bash
sudo bash install.sh
# nginx 把 /dl/ 反代到 177.7.0.1:8777（容器场景要点网桥网关 IP，非 127.0.0.1）
docker exec nginx nginx -t && docker restart nginx
```

### 全栈版（Docker，推荐）

```bash
docker compose up -d --build
# 先停掉老的 python2.7 onedl 服务，避免 8777 端口冲突：
systemctl stop onedl
```

nginx 把 `/dl/`、`/api/`（及启用公众号时的 `/wechat`）反代到宿主网桥网关
`177.7.0.1:8777` 即可（与极简版同一端口，无缝替换）。

> ⚠️ **nginx 在容器里的两个铁律**（踩过坑）：
> 1. 容器里的 `127.0.0.1` 是容器自己的回环，到不了宿主 → `proxy_pass` 用宿主机**网桥网关 IP**（如 `177.7.0.1`）。
> 2. **不要 `sed -i` 容器 bind-mount 的 nginx 配置**（容器会持有旧 inode）→ 改完 `docker restart nginx` 或 `kill -HUP`。

---

## 安全说明

- 链接 token 为 128-bit 随机熵，不可暴力猜测。
- 删除 `tokens/`（极简版）或 `links` 行（全栈版）即可「召回」尚未下载的链接。
- 全栈版 `download_count` / `download_ip` / `access_log` 提供审计与溯源。
- 服务本身**不鉴权**，安全性依赖「链接保密 + 一次性」；要访问控制请在 nginx 层加
  basic auth / IP 白名单。
- 水印用于溯源：下载时把"接收人 / openid"烧进文件，外泄即知来源。
