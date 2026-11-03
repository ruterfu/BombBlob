# BombBlob 部署手册

本文档说明如何把 BombBlob 部署到线上服务器，以及日常运维、升级、排障。
本地开发请看 [README](../README.md#快速开始本地开发)。

---

## 1. 架构概览

```
浏览器 ──HTTPS / WSS──▶ 反向代理（Nginx / Caddy，负责 TLS）──HTTP──▶ BombBlob（单进程，端口 8000）──▶ PostgreSQL
```

| 组件 | 说明 |
| --- | --- |
| 游戏服务器 | Python 3.12 + aiohttp，单进程。HTTP 页面 + 加密 WebSocket（`/gamesocket`），游戏判定全部在服务器 |
| 数据库 | PostgreSQL 13+（推荐 17）。启动时自动建表 / 迁移（`db/init.sql`） |
| 反向代理 | 必须提供 **HTTPS**：浏览器只在 HTTPS（或 localhost）下开放加密功能，否则无法登录 |

> ⚠ **只能运行一个游戏服务器实例**：会话、大厅、房间、对局都在进程内存里，不能水平扩展成多实例。
> 单进程实测 300 人同时在线 CPU 约 17%（未开传输加密时）；开启加密后 100 人约 19%。

---

## 2. 部署前准备

- [ ] 一台 Linux 服务器，已安装 Docker
- [ ] 一个域名，例如 `bomb.example.com`，并能申请 HTTPS 证书
- [ ] **自己的 RSA 密钥对**（第 3 节）——不要使用仓库里公开的默认密钥
- [ ] （可选）GitHub OAuth App（第 4 节）
- [ ] 决定登录方式：GitHub 登录、游客登录，或两者都开

---

## 3. 生成传输加密密钥（必做）

网页里写死 RSA 公钥（`public/js/rsa-public.js`），服务器持有私钥。仓库自带的默认私钥写在公开的 `.env.example` 里，**任何人都能用它解密流量**，正式部署前必须换成自己的：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/gen_rsa.py --print
```

命令会：

1. 生成新的 RSA-2048 密钥对；
2. **改写 `public/js/rsa-public.js`**（新公钥，需要随镜像一起构建）；
3. 打印一行 `RSA_PRIVATE_KEY=…`（私钥，单行 base64）——保存到密码管理器 / 服务器的密钥管理里，**不要提交到仓库**。

注意：

- 换密钥后必须**重新构建镜像**（公钥在镜像里），并用新的 `RSA_PRIVATE_KEY` 启动；
- 服务器启动时会检查公钥与私钥是否配对，不配对会直接拒绝启动并说明原因；
- 不传 `RSA_PRIVATE_KEY` 时会退回 `.env.example` 里的默认密钥，启动日志会打印 `⚠ 正在使用 .env.example 中公开的默认 RSA 私钥` 警告。

---

## 4. GitHub OAuth App（开启 GitHub 登录时）

1. GitHub → Settings → Developer settings → **OAuth Apps** → **New OAuth App**
2. **Homepage URL**：`https://bomb.example.com`
3. **Authorization callback URL**：`https://bomb.example.com/oauth/callback`（必须与 `PUBLIC_URL` + `/oauth/callback` 完全一致）
4. 创建后复制 **Client ID**；点 **Generate a new client secret** 得到 **Client Secret**

说明：

- 登录时**不申请任何权限（scope）**，只读取 GitHub 公开的**用户 ID**（用来绑定账号）和**头像地址**（显示给其他玩家）；
- 不读取、不保存 GitHub 用户名；游戏里显示的是玩家自己创建角色时取的名字；
- Client Secret 泄露后请在 GitHub 上重新生成，并更新 `GITHUB_CLIENT_SECRET` 后重启。

---

## 5. Docker 部署（docker run）

所有配置都用 `docker run -e` 传入，镜像里不包含 `.env`。

```bash
# 1. 构建镜像（第 3 节生成新密钥后再构建）
docker build -t bombblob .

# 2. 网络 + 数据库
docker network create bombblob
docker run -d --name bombblob-db --network bombblob --restart unless-stopped \
  -e POSTGRES_USER=bombblob \
  -e POSTGRES_PASSWORD='换成强密码' \
  -e POSTGRES_DB=bombblob \
  -v bombblob-pgdata:/var/lib/postgresql/data \
  postgres:17-alpine

# 3. 游戏服务器（只监听本机，由反向代理对外提供 HTTPS）
docker run -d --name bombblob --network bombblob --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e DATABASE_URL='postgresql://bombblob:换成强密码@bombblob-db:5432/bombblob' \
  -e PUBLIC_URL='https://bomb.example.com' \
  -e LOGIN_GITHUB=true \
  -e GITHUB_CLIENT_ID='你的 Client ID' \
  -e GITHUB_CLIENT_SECRET='你的 Client Secret' \
  -e LOGIN_GUEST=false \
  -e RSA_PRIVATE_KEY='第 3 节生成的单行私钥' \
  bombblob
```

### 环境变量

| 变量 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `DATABASE_URL` | ✔ | — | PostgreSQL 连接串。启动时会等待数据库就绪（最多重试 30 次） |
| `PUBLIC_URL` | 开 GitHub 时 ✔ | 按请求推断 | 对外访问地址（不带结尾 `/`）。OAuth 回调 = `PUBLIC_URL/oauth/callback` |
| `RSA_PRIVATE_KEY` | 强烈建议 | `.env.example` 中的公开默认密钥 | 传输加密私钥（PEM 文本或单行 base64），必须与镜像里的 `rsa-public.js` 配对 |
| `LOGIN_GITHUB` | | `false` | `true` 开启 GitHub 登录（需同时提供 Client ID / Secret） |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | 开 GitHub 时 ✔ | — | GitHub OAuth App 凭证 |
| `LOGIN_GUEST` | | `false` | `true` 允许游客登录与 8 位 ID 登录；不开时只能 GitHub 登录 |
| `PORT` / `HOST` | | `8000` / `0.0.0.0` | 监听端口 / 地址 |

> 若 `LOGIN_GUEST` 与 `LOGIN_GITHUB` 都没开，**服务器拒绝启动**。某一种关闭时，它对应的接口直接返回 404：游客关闭时是 `/api/guest` 和 `/api/login`；GitHub 关闭时是 `/auth/github`、`/oauth/callback` 和 `/api/oauth/exchange`。登录页进入时请求 `/login-info`（只返回 `{guest, github}`），据此只显示开启的登录方式。

---

## 6. HTTPS 反向代理

反向代理需要：终止 TLS、**透传 WebSocket（`/gamesocket`）**、转发 `X-Forwarded-Proto` / `X-Forwarded-Host`。

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name bomb.example.com;
    ssl_certificate     /etc/letsencrypt/live/bomb.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bomb.example.com/privkey.pem;

    location /gamesocket {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_read_timeout 120s;      # 服务器每 4 秒心跳一次，超时只需大于心跳间隔
        proxy_buffering off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}

server {
    listen 80;
    server_name bomb.example.com;
    return 301 https://$host$request_uri;
}
```

### Caddy

```caddy
bomb.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

（Caddy 自动申请证书并透传 WebSocket。）

---

## 7. 部署后检查

```bash
curl -s https://bomb.example.com/api/health      # {"ok": true, "online": 0, "rooms": 0}
docker logs bombblob | tail                      # 不应出现「默认 RSA 私钥」警告
```

浏览器检查：

1. 打开 `https://bomb.example.com`，登录页显示「连接 GitHub」/「游客登录」（按配置）；
2. GitHub 登录：授权页**不要求任何权限**，回调后进入「创建角色」；
3. 进入大厅、开一局（可加 AI），右上角延迟显示正常；
4. 开发者工具 → Network → `/gamesocket`：消息应全部是二进制帧（已加密）。

---

## 8. 数据库

### 自动迁移

服务器每次启动都会在咨询锁保护的事务中执行 [`db/init.sql`](../db/init.sql)：建表、加列、建索引、写入初始数据。脚本可以重复执行，也可以手动执行：

```bash
docker exec -i bombblob-db psql -U bombblob bombblob < db/init.sql
```

| 表 | 用途 |
| --- | --- |
| `users` | 账号（游客 / GitHub）、角色外观、语言、经验、等级、点数、改名卡、战绩 |
| `login_tokens` | 一次性登录 token（只存 SHA-256） |
| `levels` | 等级表（1–50 级；之后由 `bb_level()` 按曲线无限延伸） |
| `matches` / `match_players` | 对局记录与每位真人玩家的结果（对战记录数据来源） |
| `cosmetics` / `user_items` | 商店装饰目录 / 已购买的装饰 |
| `name_changes` | 改名记录 |
| `meta` | 内部元数据 |

调整数值（等级曲线、装饰价格 / 解锁等级）直接改 `levels` / `cosmetics` 表后重启即可。

**所有字段都是 NOT NULL，数据库里不存 NULL**：没有值时文本存 `''`，数字存 `0`，时间存 `'epoch'`（1970-01-01，表示「尚未发生」，例如 token 未使用）。唯一例外是 `matches.winner_team`：没有获胜队伍时存 `-1`，因为 `0` 是红队。对局结果 JSON（`matches.result`）写入前也会把 null 换掉。旧库里可为空的列，启动时会自动迁移（一次性）。

### 备份与恢复

```bash
# 备份（建议每天定时执行，保留多份）
docker exec bombblob-db pg_dump -U bombblob -Fc bombblob > bombblob-$(date +%F).dump

# 恢复
docker exec -i bombblob-db pg_restore -U bombblob -d bombblob --clean --if-exists < bombblob-2026-11-03.dump
```

---

## 9. 升级

```bash
git pull
docker build -t bombblob .
docker exec bombblob-db pg_dump -U bombblob -Fc bombblob > before-upgrade.dump   # 先备份
docker rm -f bombblob
docker run -d --name bombblob ...（与第 5 节相同的参数）
```

- 数据库迁移在启动时自动完成；
- 会话保存在内存里，重启后玩家的连接会断开，玩家需要重新点登录（不做自动登录）；进行中的对局会丢失；
- 部分迁移**不可逆**（例如旧版「金币」按 5:1 并入点数后删除金币列），升级前务必备份；
- 如果更换了 RSA 密钥：新镜像 + 新 `RSA_PRIVATE_KEY` 必须一起上线，旧页面需要刷新。

---

## 10. 运维说明

| 项 | 说明 |
| --- | --- |
| 健康检查 | `GET /api/health`；镜像内置 `HEALTHCHECK`（每 15 秒） |
| 日志 | `docker logs -f bombblob`。数据库写入失败会自动重试（指数退避），失败信息以 `[store]` 开头 |
| 断线 | 服务器每 4 秒心跳；对局中断线的玩家会在其他人屏幕上显示「断开连接 / 重新连接」，可以随时回到对局；房间里（未开局）断线超过 10 秒自动离开房间 |
| 数据保留 | 已使用 30 天以上 / 签发 180 天仍未使用的登录 token 在启动时分批清理 |
| 关闭 | `docker stop` 会等待所有数据库写入完成后再退出 |
| 压力测试 | `.venv/bin/python scripts/loadtest.py --players 100 --seconds 40 --url http://127.0.0.1:8000 --pid <pid>` |

---

## 11. 安全清单

- [ ] 使用自己生成的 RSA 密钥，没有出现默认密钥警告
- [ ] 全站 HTTPS，HTTP 跳转到 HTTPS
- [ ] 游戏服务器只监听 `127.0.0.1`（`-p 127.0.0.1:8000:8000`），只通过反向代理对外
- [ ] 数据库不对外暴露端口，使用强密码
- [ ] `GITHUB_CLIENT_SECRET`、`RSA_PRIVATE_KEY` 只存在于服务器环境变量 / 密钥管理中，不进仓库
- [ ] 定时备份数据库，并演练过恢复

---

## 12. 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 网页提示「当前连接不安全」，无法登录 | 没有用 HTTPS 访问（浏览器只在 HTTPS / localhost 下提供 WebCrypto）。配置第 6 节的反向代理 |
| 服务器启动即退出：`rsa-public.js 中的公钥与 RSA_PRIVATE_KEY 不匹配` | 镜像里的公钥和传入的私钥不是同一对。用同一次 `gen_rsa.py` 生成的结果，并重新构建镜像 |
| 服务器启动即退出：`缺少 RSA_PRIVATE_KEY` | 镜像里缺少 `.env.example` 且没传私钥。传入 `-e RSA_PRIVATE_KEY=…` |
| GitHub 页面显示 404 / Page not found | `GITHUB_CLIENT_ID` 填错（多 / 少字符） |
| GitHub 提示 redirect_uri 不匹配 | OAuth App 的 callback URL 与 `PUBLIC_URL/oauth/callback` 不一致（协议、域名、端口都要相同） |
| 能打开页面但一直「正在重连」 | 反向代理没有透传 WebSocket：检查 `/gamesocket` 的 `Upgrade` / `Connection` 头 |
| 玩家频繁断线 | 代理的读超时太短，或网络不稳定。`proxy_read_timeout` 应远大于 4 秒心跳 |
| 启动时一直打印「等待数据库就绪」 | `DATABASE_URL` 不对，或数据库容器没在同一个 Docker 网络里 |
