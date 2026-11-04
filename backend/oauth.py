"""GitHub OAuth（授权码模式）。

流程：
  1. GET /api/auth/github              生成随机 state（服务器内存 + HttpOnly Cookie 双重校验），跳转到 GitHub 授权页
  2. GET /api/oauth/callback       校验 state → 用 code 换 access_token → 读取 GitHub 用户信息
                                   → 查找或创建账号 → 生成 60 秒有效、只能使用一次的交换码
                                   → 跳回 /#oauth=<交换码>（URL 片段不会发送到服务器或出现在日志里）
  3. POST /api/oauth/exchange      前端用交换码换取一次性登录 token 与 session
"""
from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import aiohttp

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
STATE_TTL = 600
CODE_TTL = 60


class OAuthError(Exception):
    pass


AVATAR_PREFIX = "https://avatars.githubusercontent.com/"


def safe_avatar(url: object) -> str | None:
    """只接受 GitHub 官方头像域名的 https 地址（防止被塞入任意外链），并限制长度。"""
    if isinstance(url, str) and url.startswith(AVATAR_PREFIX) and len(url) <= 300 and not any(c in url for c in "\"'<> "):
        return url
    return None


class GitHubOAuth:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._states: dict[str, tuple[float, dict]] = {}
        self._codes: dict[str, tuple[float, dict]] = {}
        self._http: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._http:
            await self._http.close()

    def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._http

    @staticmethod
    def _gc(d: dict, ttl: float) -> None:
        now = time.time()
        for k in [k for k, v in d.items() if now - (v[0] if isinstance(v, tuple) else v) > ttl]:
            del d[k]

    def new_state(self, meta: dict | None = None) -> str:
        """生成 state；meta 为随 state 保存的附加信息（例如发起登录时的语言）。"""
        self._gc(self._states, STATE_TTL)
        st = secrets.token_hex(24)
        self._states[st] = (time.time(), meta or {})
        return st

    def consume_state(self, st: str) -> dict | None:
        """校验并作废 state；有效时返回附加信息。"""
        self._gc(self._states, STATE_TTL)
        entry = self._states.pop(st, None)
        return entry[1] if entry else None

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        # 不申请任何 scope：只需要 GitHub 用户 ID（未授权 scope 时只能读取公开信息）
        q = {"client_id": self.client_id, "redirect_uri": redirect_uri, "state": state, "allow_signup": "true"}
        return f"{AUTHORIZE_URL}?{urlencode(q)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        """用授权码换取 access_token。"""
        async with self._session().post(
            TOKEN_URL,
            data={"client_id": self.client_id, "client_secret": self.client_secret, "code": code, "redirect_uri": redirect_uri},
            headers={"Accept": "application/json"},
        ) as r:
            data = await r.json(content_type=None)
        token = data.get("access_token") if isinstance(data, dict) else None
        if not token:
            raise OAuthError(data.get("error_description") or data.get("error") or "无法获取 access_token")
        return token

    async def fetch_user(self, access_token: str) -> dict:
        """只读取 GitHub 用户 ID 与头像地址（不读取 / 保存用户名等其他任何信息）。"""
        async with self._session().get(
            USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json", "User-Agent": "BombBlob"},
        ) as r:
            if r.status != 200:
                raise OAuthError(f"读取 GitHub 用户信息失败（{r.status}）")
            data = await r.json()
        if not isinstance(data, dict) or "id" not in data:
            raise OAuthError("GitHub 用户信息格式异常")
        return {"id": int(data["id"]), "avatar_url": safe_avatar(data.get("avatar_url"))}

    # ---------- 一次性交换码 ----------
    def issue_code(self, payload: dict) -> str:
        self._gc(self._codes, CODE_TTL)
        code = secrets.token_hex(24)
        self._codes[code] = (time.time(), payload)
        return code

    def redeem_code(self, code: str) -> dict | None:
        self._gc(self._codes, CODE_TTL)
        entry = self._codes.pop(str(code), None)
        return entry[1] if entry else None
