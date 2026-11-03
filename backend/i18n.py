"""服务端语言常量。

服务器不翻译提示文字：REST 只返回错误码，WebSocket 只返回错误码 / 事件 key + 参数，
由前端（public/js/i18n.js）按玩家语言显示。这里只保存服务器需要生成的默认名称。
"""
from __future__ import annotations

LANGS = ("zh", "zh-HK", "ja", "en")
DEFAULT_LANG = "en"

GUEST_PREFIX = {"zh": "游客", "zh-HK": "訪客", "ja": "ゲスト", "en": "Guest"}
PLAYER_PREFIX = {"zh": "玩家", "zh-HK": "玩家", "ja": "プレイヤー", "en": "Player"}
ROOM_NAME = {"zh": "{name}的房间", "zh-HK": "{name}的房間", "ja": "{name}のルーム", "en": "{name}'s room"}


def normalize(lang: object) -> str | None:
    return lang if isinstance(lang, str) and lang in LANGS else None


def guest_name(lang: str | None, suffix: str) -> str:
    return (GUEST_PREFIX.get(lang or DEFAULT_LANG, GUEST_PREFIX[DEFAULT_LANG]) + suffix)[:8]  # 名字最多 8 个字


def room_name(lang: str | None, name: str) -> str:
    return ROOM_NAME.get(lang or DEFAULT_LANG, ROOM_NAME[DEFAULT_LANG]).format(name=name)


def player_name(lang: object, suffix: str) -> str:
    """GitHub 新账号的默认名字（不使用 GitHub 用户名）。"""
    return (PLAYER_PREFIX.get(normalize(lang) or "en", "Player") + suffix)[:8]  # 名字最多 8 个字
