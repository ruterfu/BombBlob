"""BombBlob 泡泡爆爆 — HTTP + WebSocket 服务器。

运行：python -m backend.server  （默认端口 8000，可用 PORT 环境变量修改）
登录方式由环境变量控制，见 backend/config.py（LOGIN_GUEST / LOGIN_GITHUB）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from aiohttp import web

from . import secure, store
from .config import Config, load_dotenv
from .lobby import Lobby
from .maps import map_summaries
from .oauth import GitHubOAuth, OAuthError

PUBLIC = Path(__file__).resolve().parent.parent / "public"
LOBBY_KEY = web.AppKey("lobby", Lobby)
DSN_KEY = web.AppKey("dsn", str)
CFG_KEY = web.AppKey("config", Config)
GH_KEY = web.AppKey("github", GitHubOAuth)
RSA_KEY = web.AppKey("rsa", object)
STATE_COOKIE = "bb_oauth_state"
CALLBACK_PATH = "/oauth/callback"  # 需与 GitHub OAuth App 中登记的 Authorization callback URL 一致


class Sealed(Exception):
    """加密接口的返回：(HTTP 状态码, 内容)，内容用本次请求的一次性密钥加密。"""

    def __init__(self, status: int, body: dict) -> None:
        self.status, self.body = status, body


def sealed(handler):
    """加密接口：请求体是 {ek, iv, ct}（RSA-OAEP 包裹的一次性 AES-128 密钥 + AES-GCM 密文），
    响应同样用这个一次性密钥 AES-GCM 加密。解不开的请求直接 400（不泄露任何信息）。"""

    async def wrapper(request: web.Request) -> web.Response:
        try:
            raw = await request.json()
            k, body = secure.open_request(request.app[RSA_KEY], raw)
        except (ValueError, UnicodeDecodeError, secure.CryptoError):
            return web.json_response({"code": "bad_request"}, status=400)
        try:
            status, data = 200, await handler(request, body)
        except Sealed as e:
            status, data = e.status, e.body
        return web.json_response(secure.seal_response(k, data), status=status)

    return wrapper


def _err(code: str, status: int) -> Sealed:
    """错误只返回错误码，文字由前端按语言翻译。"""
    return Sealed(status, {"code": code})


def _login_ok(user: dict, token: str, session: str, created: bool) -> dict:
    """登录成功：返回一次性登录 token、会话 ID 与 AES-128 会话密钥（整个响应已加密）。"""
    key = store.session_key(session)
    return {"token": token, "session": session, "key": secure.b64(key), "created": created, "user": store.public_user(user)}


async def login_config(request: web.Request) -> web.Response:
    """前端据此决定显示哪些登录方式。"""
    cfg = request.app[CFG_KEY]
    return web.json_response({"guest": cfg.login_guest, "github": cfg.login_github})


@sealed
async def guest_login(request: web.Request, b: dict) -> dict:
    """游客登录 / 一次性 token 自动登录。

    带 token：一次性消费该 token 恢复账号（游客或 GitHub 账号），并返回新的 token（旧 token 立即作废）。
    不带 token：创建新游客账号（需要 LOGIN_GUEST=true）。
    返回的 session 用于 WebSocket 连接与断线重连（仅保存在服务器内存中）。
    """
    cfg = request.app[CFG_KEY]
    if not b.get("token") and not cfg.login_guest:
        raise _err("guest_disabled", 403)
    try:
        user, token, session, created = await store.guest_login(
            b.get("name"), b.get("skin"), b.get("hat"), token=b.get("token"), allowed=cfg.allowed_providers,
            lang=b.get("lang"),
        )
    except store.TokenInvalid:
        raise _err("token_invalid", 401)
    except store.ProviderDisabled:
        raise _err("provider_disabled", 403)
    return _login_ok(user, token, session, created)


@sealed
async def id_login(request: web.Request, b: dict) -> dict:
    """凭 8 位 ID 登录游客账号（需要 LOGIN_GUEST=true；GitHub 账号不能凭 ID 登录）。"""
    cfg = request.app[CFG_KEY]
    if not cfg.login_guest:
        raise _err("guest_disabled", 403)
    try:
        user, token, session, _ = await store.guest_login(
            uid=str(b.get("id") or ""), allowed=cfg.allowed_providers, lang=b.get("lang")
        )
    except store.UnknownId:
        raise _err("unknown_id", 404)
    return _login_ok(user, token, session, False)


def _public_base(request: web.Request) -> str:
    cfg = request.app[CFG_KEY]
    if cfg.public_url:
        return cfg.public_url
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{proto}://{host}"


def _redirect_home(fragment: str) -> web.HTTPFound:
    return web.HTTPFound("/#" + fragment)


async def github_start(request: web.Request) -> web.StreamResponse:
    """跳转到 GitHub 授权页。"""
    cfg = request.app[CFG_KEY]
    if not cfg.login_github:
        raise _redirect_home("oauth_error=disabled")
    gh = request.app[GH_KEY]
    state = gh.new_state({"lang": request.query.get("lang")})
    resp = web.HTTPFound(gh.authorize_url(_public_base(request) + CALLBACK_PATH, state))
    resp.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, samesite="Lax",
                    secure=_public_base(request).startswith("https"), path="/")
    raise resp


async def github_callback(request: web.Request) -> web.StreamResponse:
    """GitHub 回调：校验 state → 换 token → 读用户 → 登录 → 发一次性交换码跳回首页。"""
    cfg = request.app[CFG_KEY]
    if not cfg.login_github:
        raise _redirect_home("oauth_error=disabled")
    gh = request.app[GH_KEY]
    state = request.query.get("state", "")
    code = request.query.get("code", "")
    if request.query.get("error"):
        raise _redirect_home("oauth_error=denied")
    meta = gh.consume_state(state) if state and state == request.cookies.get(STATE_COOKIE) else None
    if meta is None:
        raise _redirect_home("oauth_error=state")
    try:
        access = await gh.exchange_code(code, _public_base(request) + CALLBACK_PATH)
        info = await gh.fetch_user(access)
    except (OAuthError, OSError, ValueError) as e:
        print(f"[oauth] GitHub 登录失败: {e}")
        raise _redirect_home("oauth_error=github")
    user, token, session, created = await store.github_login(info["id"], info.get("avatar_url"), lang=meta.get("lang"))
    ex = gh.issue_code(_login_ok(user, token, session, created))
    resp = _redirect_home("oauth=" + ex)
    resp.del_cookie(STATE_COOKIE, path="/")
    raise resp


@sealed
async def oauth_exchange(request: web.Request, b: dict) -> dict:
    """用一次性交换码换取登录 token 与会话密钥（交换码 60 秒内有效、只能用一次）。"""
    if not request.app[CFG_KEY].login_github:
        raise _err("github_disabled", 403)
    payload = request.app[GH_KEY].redeem_code(str(b.get("code") or ""))
    if not payload:
        raise _err("code_invalid", 401)
    return payload


async def maps(request: web.Request) -> web.Response:
    return web.json_response({"maps": map_summaries()})


async def health(request: web.Request) -> web.Response:
    lobby = request.app[LOBBY_KEY]
    return web.json_response({"ok": True, "online": len(lobby.clients), "rooms": len(lobby.rooms)})


async def websocket(request: web.Request) -> web.StreamResponse:
    sid = request.query.get("session")
    user = store.user_by_session(sid)
    # 关闭 permessage-deflate：状态帧很小，压缩只会增加两端的处理延迟
    ws = web.WebSocketResponse(heartbeat=4, max_msg_size=4096, compress=False)  # 4 秒心跳：尽快发现断线
    await ws.prepare(request)
    if not user:
        await ws.close(code=4001, message=b"unauthorized")
        return ws
    # 第一帧（明文）告诉客户端本连接的连接号；之后所有帧都是 AES-128-GCM 二进制帧
    conn = store.next_conn(sid)
    await ws.send_str(json.dumps({"t": "hello", "c": conn}))
    channel = secure.Channel(store.session_key(sid), conn, secure.S2C)
    await request.app[LOBBY_KEY].serve(ws, user, channel)
    return ws


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(PUBLIC / "index.html")


@web.middleware
async def no_cache(request: web.Request, handler):
    resp = await handler(request)
    if not request.path.startswith("/vendor/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


async def _on_shutdown(app: web.Application) -> None:
    lobby = app[LOBBY_KEY]
    for room in list(lobby.rooms.values()):
        if room.game:
            room.game.stop()
    for c in list(lobby.clients.values()):
        await c.close(1001, "server shutdown")


async def _db_ctx(app: web.Application):
    await store.init(app.get(DSN_KEY))
    yield
    await store.close()
    await app[GH_KEY].close()


def create_app(dsn: str | None = None, config: Config | None = None, github: GitHubOAuth | None = None,
               rsa_key=None) -> web.Application:
    cfg = config or Config.from_env()
    app = web.Application(middlewares=[no_cache], client_max_size=16 * 1024)
    app[RSA_KEY] = rsa_key or secure.load_private_key()
    if app[RSA_KEY] is None:
        raise SystemExit("缺少 RSA_PRIVATE_KEY：先运行 python scripts/gen_rsa.py 生成密钥对（见 README「传输加密」）")
    app[LOBBY_KEY] = Lobby()
    app[CFG_KEY] = cfg
    app[GH_KEY] = github or GitHubOAuth(cfg.github_client_id, cfg.github_client_secret)
    if dsn:
        app[DSN_KEY] = dsn
    app.cleanup_ctx.append(_db_ctx)
    app.router.add_get("/api/config", login_config)
    app.router.add_post("/api/guest", guest_login)
    app.router.add_post("/api/login", id_login)
    app.router.add_get("/auth/github", github_start)
    app.router.add_get(CALLBACK_PATH, github_callback)
    app.router.add_get("/auth/github/callback", github_callback)  # 兼容旧地址
    app.router.add_post("/api/oauth/exchange", oauth_exchange)
    app.router.add_get("/api/maps", maps)
    app.router.add_get("/api/health", health)
    app.router.add_get("/gamesocket", websocket)
    app.router.add_get("/", index)
    app.router.add_static("/", PUBLIC, show_index=False)
    app.on_shutdown.append(_on_shutdown)
    return app


def main() -> None:
    load_dotenv()
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    cfg = Config.from_env()
    key = secure.load_private_key()
    if key is None:
        raise SystemExit("缺少 RSA_PRIVATE_KEY：先运行 python scripts/gen_rsa.py 生成密钥对（见 README「传输加密」）")
    if secure.is_default_key(key):
        print("[secure] ⚠ 正在使用 .env.example 中公开的默认 RSA 私钥，任何人都能解密这些流量。"
              "正式部署前请运行 python scripts/gen_rsa.py 生成自己的密钥对。")
    if not secure.check_public_js(key):
        raise SystemExit("public/js/rsa-public.js 中的公钥与 RSA_PRIVATE_KEY 不匹配：请用 scripts/gen_rsa.py 重新生成，或换回对应的私钥")
    print(f"BombBlob 服务器启动: http://localhost:{port}  （游客登录: {'开' if cfg.login_guest else '关'} · GitHub 登录: {'开' if cfg.login_github else '关'}）")
    web.run_app(create_app(config=cfg, rsa_key=key), host=host, port=port, print=None)


if __name__ == "__main__":
    main()
