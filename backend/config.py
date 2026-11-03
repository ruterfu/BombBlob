"""运行配置（环境变量）。

  LOGIN_GUEST           是否允许游客登录 / 8 位 ID 登录（默认关闭；需显式设为 true）
  LOGIN_GITHUB          是否开启 GitHub OAuth 登录（默认 false）
  GITHUB_CLIENT_ID      GitHub OAuth App 的 Client ID
  GITHUB_CLIENT_SECRET  GitHub OAuth App 的 Client Secret
  PUBLIC_URL            对外访问地址，例如 https://bomb.example.com（用于拼接 OAuth 回调地址；
                        不设置时根据请求头 X-Forwarded-Proto / Host 推断）
  DATABASE_URL / HOST / PORT  见 server.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def load_dotenv(path: str | None = None) -> None:
    """读取项目根目录的 .env（仅本地开发用），不覆盖已存在的环境变量（Docker 传入的变量优先）。"""
    from pathlib import Path

    f = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not f.is_file():
        return
    for line in f.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


SYNC_HZ_DEFAULT, SYNC_HZ_MIN, SYNC_HZ_MAX = 30, 10, 60


def env_sync_hz() -> int:
    """SYNC_HZ：对局状态同步频率，默认 30，范围 10–60（超出范围按边界取值，无法解析时用默认值）。"""
    raw = os.environ.get("SYNC_HZ", "").strip()
    if not raw:
        return SYNC_HZ_DEFAULT
    try:
        hz = int(float(raw))
    except ValueError:
        print(f"[config] SYNC_HZ={raw!r} 不是数字，使用默认值 {SYNC_HZ_DEFAULT}")
        return SYNC_HZ_DEFAULT
    clamped = max(SYNC_HZ_MIN, min(SYNC_HZ_MAX, hz))
    if clamped != hz:
        print(f"[config] SYNC_HZ={hz} 超出范围 {SYNC_HZ_MIN}–{SYNC_HZ_MAX}，已调整为 {clamped}")
    return clamped


@dataclass
class Config:
    login_guest: bool = False
    login_github: bool = False
    github_client_id: str = ""
    github_client_secret: str = ""
    public_url: str = ""
    sync_hz: int = 30  # 对局状态同步频率（Hz），SYNC_HZ，10–60

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            login_guest=env_bool("LOGIN_GUEST", False),
            login_github=env_bool("LOGIN_GITHUB", False),
            github_client_id=os.environ.get("GITHUB_CLIENT_ID", "").strip(),
            github_client_secret=os.environ.get("GITHUB_CLIENT_SECRET", "").strip(),
            public_url=os.environ.get("PUBLIC_URL", "").strip().rstrip("/"),
            sync_hz=env_sync_hz(),
        )
        if cfg.login_github and not (cfg.github_client_id and cfg.github_client_secret):
            print("[config] LOGIN_GITHUB=true 但缺少 GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET，已关闭 GitHub 登录")
            cfg.login_github = False
        return cfg

    def check(self) -> None:
        """两种登录方式都没开：没有人能登录，服务器拒绝启动。"""
        if not self.login_guest and not self.login_github:
            raise SystemExit("LOGIN_GUEST 与 LOGIN_GITHUB 都未开启，没有人能登录，服务器无法启动。"
                             "请至少开启一个（LOGIN_GITHUB 还需要 GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET）")

    @property
    def allowed_providers(self) -> frozenset[str]:
        out = set()
        if self.login_guest:
            out.add("guest")
        if self.login_github:
            out.add("github")
        return frozenset(out)
