# onedl — 阅后即焚下载服务（One-time Download）

一个极简的「链接下载一次即失效」服务。生成一个不可猜测的随机链接，对方点开下载成功后，
**同一个链接立刻作废（第二次起 404）**。支持**任意文件类型**（PDF / ZIP / 图片 / 视频 / 安装包…），
自动识别 MIME 并保留原始文件名。无数据库、无第三方依赖，单文件 Python 服务，Python 2.7 / 3.x 通吃。

---

## 它能干什么

- 发一份保密合同给客户，他下完你就知道链接已废，不怕被二次转发。
- 给一批人各发一个独立链接（一人一链），谁下载了、谁没下载一目了然。
- 临时分享一个大文件，不希望它长期挂在公网上。

**注意**：链接是「随机不可猜测」而非「需要登录」。任何人拿到链接都能下一次，所以**别把同一个链接发给两个人**。

---

## 原理

```
         /dl/<token>            consume(token)               stream
浏览器 ───────────▶ nginx ───────────▶ onedl 服务 ─────────────────────▶ 文件
                  (反代)         token 文件被原子 rename 到 consumed/    (仅一次)
```

1. `gen.py <文件> [数量]` 把文件以随机内部名存入 `store/`，并写入 N 个 token 文件（位于 `tokens/`）。
2. 每个 token 文件两行：`内部存储名` + `原始下载文件名`。
3. 访问 `/dl/<token>` 时，服务**先把 token 原子移入 `consumed/`**（谁先到谁得），再流式吐文件。
4. 同一 token 第二次访问时，`tokens/` 里已无此文件 → 直接 `404`。

因为「先消费、后发送」，并发也不会让两个人各拿到一份；链接严格一次性。

---

## 目录结构

```
onedl/
├── service.py          # 主服务（HTTP，python2/3 兼容）
├── gen.py              # 生成一次性下载链接
├── onedl.service       # systemd 单元（开机自启 / 崩溃自重启）
├── onedl.nginx.conf    # nginx location 片段（反代 /dl/）
├── install.sh          # 一键安装（建目录 + systemd + 提示 nginx）
├── LICENSE
└── README.md
```

运行时数据（**不入库**，见 `.gitignore`）：

```
/opt/onedl/
├── store/        # 实际文件，随机内部名
├── tokens/       # 未消费的链接（每一行一个 token 文件）
├── consumed/     # 已消费的链接
└── links.log     # 生成过的链接记录
```

---

## 部署

### 1. 安装

```bash
git clone <your-repo> onedl
cd onedl
sudo bash install.sh
```

`install.sh` 会：建好 `/opt/onedl` 目录、安装 `service.py`/`gen.py`、注册并启动 systemd 服务。

### 2. nginx（关键坑位）

把 `onedl.nginx.conf` 的内容放进你的 `server {}` 块。**默认 `proxy_pass` 是 `127.0.0.1`**，
仅当 nginx 与 onedl 同主机时成立。

> ⚠️ **nginx 在 Docker 容器里时**：容器的 `127.0.0.1` 是它自己的回环，到不了宿主机。
> 必须把 `proxy_pass` 改成**宿主机在 docker 网桥上的网关 IP**（例如 `http://177.7.0.1:8777/`），
> 同时 systemd 单元的 `ONEDL_HOST` 也要设成同一个网关 IP，并且 onedl 服务要 `bind` 到该 IP。

> ⚠️ **bind-mount 配置陷阱**：不要对「被容器绑定挂载」的 nginx 配置做 `sed -i` —— 容器会一直持有旧 inode，
> 改完 `nginx -t` 通过、实际还是旧配置。正确做法：就地编辑文件后 `docker kill -s HUP nginx`，
> 或直接 `docker restart nginx` 让它重新绑定当前文件。

改完务必：

```bash
docker exec nginx nginx -t      # 语法检查
docker exec nginx nginx -s reload   # 或 docker restart nginx
```

### 3. 环境变量（改 `/etc/systemd/system/onedl.service` 的 `Environment=`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `ONEDL_BASE` | `/opt/onedl` | 工作目录 |
| `ONEDL_PORT` | `8777` | 服务监听端口 |
| `ONEDL_HOST` | `127.0.0.1` | 服务 bind 地址（容器场景填网桥网关 IP） |
| `ONEDL_PUBLIC_HOST` | `http://117.72.15.132` | `gen.py` 生成的链接前缀 |

---

## 使用

```bash
# 给某个文件生成 10 个一次性链接（默认打印到 stdout，并追加到 links.log）
python /opt/onedl/gen.py /path/to/secret.pdf 10

# 换一个文件也完全一样
python /opt/onedl/gen.py /path/to/release-v2.zip 3
```

输出形如：

```
http://117.72.15.132/dl/4633195281c7a2d99fa1adf1a2caecee
http://117.72.15.132/dl/7a366db4039e101bd59dcbbefe030450
...
```

把链接发出去即可。每个链接：第一次 `200` 下载成功，之后 `404`。

### 运维命令

```bash
systemctl status onedl                       # 服务状态
journalctl -u onedl                          # 日志
ls /opt/onedl/tokens   | wc -l               # 当前未消费的链接数
ls /opt/onedl/consumed | wc -l               # 已消费的链接数
```

---

## 验证「阅后即焚」

```bash
L=$(python /opt/onedl/gen.py /etc/hostname 1)
echo "$L"
curl -s -o /tmp/a -w '第一次: HTTP=%{http_code} TYPE=%{content_type} SIZE=%{size_download}\n' "$L"
curl -s -o /dev/null -w '第二次: HTTP=%{http_code}\n' "$L"
curl -s -o /dev/null -w '第三次: HTTP=%{http_code}\n' "$L"
```

预期：第一次 `200` + 正确 `Content-Type`，第二、三次 `404`。

---

## 安全说明

- 链接随机 token 为 16 字节熵（128-bit），不可暴力猜测。
- 删除 `tokens/` 里的某个文件即可「召回」一条尚未被下载的链接。
- 消费后文件仍在 `store/` 中（便于审计/重发），如不需保留可自行清理 `consumed/` 对应记录。
- 服务本身**不鉴权**，安全性依赖「链接保密 + 一次性」。如需访问管控，请在 nginx 层加 basic auth 或 IP 白名单。
