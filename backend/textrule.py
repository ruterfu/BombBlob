"""全局文本规则：客户端上报的所有字符串（WebSocket 消息、登录请求、查询参数）一律经过这里。

  * 先做 NFKC（全角字母 / 数字转半角），再去掉所有空白（空格、制表、换行、全角空格……）。
  * 剩下的只能是：中文（汉字）、英文字母 A–Z a–z、数字 0–9。
  * 例外：聊天消息（chat.text）不限制字符，只做纯文本清理（chat_text）。
  * 其他任何字符（标点、符号、表情、假名、韩文、带音标的字母……）都不允许：整条消息拒绝。
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any


class TextError(ValueError):
    """消息中含有不允许的字符。"""


def is_han(ch: str) -> bool:
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF  # 基本区
            or 0x3400 <= o <= 0x4DBF  # 扩展 A
            or 0xF900 <= o <= 0xFAFF  # 兼容汉字
            or 0x20000 <= o <= 0x323AF)  # 扩展 B–H


def char_ok(ch: str) -> bool:
    return ("0" <= ch <= "9") or ("a" <= ch <= "z") or ("A" <= ch <= "Z") or is_han(ch)


def clean(s: str) -> str:
    """返回去掉空白后的字符串；含不允许的字符时抛出 TextError。"""
    if s.isascii() and s.isalnum():  # 快速路径：绝大多数协议字段（"mv"、"right"、ID……）
        return s
    s = "".join(unicodedata.normalize("NFKC", s).split())  # 去掉所有空白
    if not all(map(char_ok, s)):
        raise TextError(s)
    return s


# ---------- 定向取值 ----------
# 每种消息按字段名逐个 get，只取约定的字段；其余字段一律不看。不认识的消息类型整条丢弃。
# 类型不对的字段当作没传（None）；文本字段含不允许的字符时抛出 TextError（整条消息拒绝）。


def text(v: Any) -> str | None:
    return clean(v) if isinstance(v, str) else None


def num(v: Any) -> float | int | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def integer(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def boolean(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def pair(v: Any) -> list | None:
    if not isinstance(v, list) or len(v) != 2:
        return None
    a, b = num(v[0]), num(v[1])
    return None if a is None or b is None else [a, b]


def text_or_int(v: Any) -> str | int | None:
    return text(v) if isinstance(v, str) else integer(v)


def _mv(m: dict) -> dict:
    return {"x": num(m.get("x")), "y": num(m.get("y")), "f": text(m.get("f")), "m": boolean(m.get("m")),
            "k": pair(m.get("k")), "q": integer(m.get("q")), "e": integer(m.get("e")), "p": num(m.get("p"))}


def _bomb(m: dict) -> dict:
    return {"x": num(m.get("x")), "y": num(m.get("y")), "e": integer(m.get("e")), "q": integer(m.get("q"))}


def _in(m: dict) -> dict:
    return {"d": text(m.get("d")), "q": integer(m.get("q"))}


def _use(m: dict) -> dict:
    return {"s": integer(m.get("s"))}  # 道具栏格子 0–5


def _ping(m: dict) -> dict:
    return {"ts": num(m.get("ts"))}


def _room_settings(m: dict) -> dict:
    return {"name": text(m.get("name")), "mapId": text(m.get("mapId")), "mode": text(m.get("mode")),
            "shrink": boolean(m.get("shrink")), "items": boolean(m.get("items")), "time": integer(m.get("time")),
            "revive": boolean(m.get("revive")), "lives": integer(m.get("lives"))}


def _create_room(m: dict) -> dict:
    return {**_room_settings(m), "password": text(m.get("password"))}


def _join_room(m: dict) -> dict:
    return {"id": text(m.get("id")), "password": text(m.get("password"))}


def _ready(m: dict) -> dict:
    return {"v": boolean(m.get("v"))}


def _team(m: dict) -> dict:
    return {"id": text(m.get("id")), "team": integer(m.get("team"))}


def _kick(m: dict) -> dict:
    return {"id": text(m.get("id"))}


CHAT_MAX = 120


def chat_text(s: str) -> str:
    """聊天内容：不限制字符（标点、符号、表情、各国文字都可以），只当作纯文本处理——
    去掉控制 / 格式 / 私用等不可见字符（含双向文本控制符，防止伪造显示顺序），
    连续空白合并成一个空格、去掉首尾，最多 120 字。内容永远不会被 eval / exec / 拼进 SQL 或 HTML。"""
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C" or ch in "\t\n")
    return " ".join(s.split())[:CHAT_MAX]


def _chat(m: dict) -> dict:
    v = m.get("text")
    return {"text": chat_text(v) if isinstance(v, str) else None}  # 聊天：不限制字符，只做纯文本清理


def _rename(m: dict) -> dict:
    return {"name": text(m.get("name"))}


def _buy(m: dict) -> dict:
    return {"item": text_or_int(m.get("item"))}


def _profile(m: dict) -> dict:
    return {"name": text(m.get("name")), "skin": integer(m.get("skin")), "hat": integer(m.get("hat")),
            "lang": text(m.get("lang"))}


def _create_character(m: dict) -> dict:
    return {"name": text(m.get("name")), "skin": integer(m.get("skin")), "hat": integer(m.get("hat"))}


def _add_bot(m: dict) -> dict:
    return {"level": text(m.get("level"))}  # AI 难度


def _bot_level(m: dict) -> dict:
    return {"id": text(m.get("id")), "level": text(m.get("level"))}


def _empty(m: dict) -> dict:
    return {}


WS_READERS = {
    "mv": _mv, "bomb": _bomb, "in": _in, "ping": _ping, "use": _use,
    "lobby": _empty, "quickJoin": _empty, "leaveRoom": _empty, "start": _empty, "addBot": _add_bot, "botLevel": _bot_level,
    "history": _empty, "leaderboard": _empty, "loaded": _empty,
    "createRoom": _create_room, "joinRoom": _join_room, "ready": _ready, "team": _team,
    "settings": _room_settings, "kick": _kick, "chat": _chat, "rename": _rename, "buy": _buy,
    "profile": _profile, "createCharacter": _create_character,
}


def read_ws(msg: Any) -> dict | None:
    """WebSocket 消息：按 t 选对应的读取函数；不认识的类型返回 None。"""
    if not isinstance(msg, dict):
        return None
    t = msg.get("t")
    reader = WS_READERS.get(t) if isinstance(t, str) else None
    if reader is None:
        return None
    out = reader(msg)
    out["t"] = t
    return out


# ---------- 登录接口（HTTP） ----------
def read_guest(b: dict) -> dict:
    # token 已停用（不再自动登录），不读取
    return {"name": text(b.get("name")), "skin": integer(b.get("skin")), "hat": integer(b.get("hat")),
            "lang": text(b.get("lang"))}


def read_login(b: dict) -> dict:
    return {"id": text(b.get("id")), "lang": text(b.get("lang"))}


def read_oauth(b: dict) -> dict:
    return {"code": text(b.get("code"))}
