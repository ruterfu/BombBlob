"""玩家名字校验：长度、允许的字符、不雅词与冒充系统提示的词。

规则
  * 去掉所有空格后，内容长度必须大于 0；最多 8 个字。
  * 只允许中文、英文字母和数字（与全局文本规则 textrule.py 一致）；括号【】[]「」、标点、下划线、
    表情符号、假名等一律不允许，避免伪造「【系统】」之类的提示。
  * 屏蔽词：比对前统一小写、去掉空格与符号，防止「你 妈 的」「f-u-c-k」这类拆字绕过。
"""
from __future__ import annotations

import unicodedata

from .textrule import char_ok

NAME_MAX = 8

# 不雅词（简 / 繁 / 粤 / 日 / 英）
_PROFANITY = [
    "你妈", "你媽", "妳妈", "妳媽", "他妈", "他媽", "她妈", "她媽", "尼玛", "泥马", "妈的", "媽的", "马的",
    "操你", "草你", "肏", "日你", "干你", "幹你", "狗日", "傻逼", "傻b", "煞笔", "沙比", "傻屌", "屌你", "屌",
    "鸡巴", "雞巴", "婊子", "贱人", "賤人", "杂种", "雜種", "畜生", "去死", "智障", "脑残", "腦殘", "白痴", "白癡",
    "妈逼", "媽逼", "屄", "逼样", "滚你", "王八蛋", "龟儿子", "龜兒子",
    "仆街", "撲街", "冚家", "戇鳩", "戆鸠", "閪", "西鳩", "柒頭", "柒头", "撚", "痴線",
    "死ね", "しね", "ころす", "殺す", "ちんこ", "まんこ", "きちがい", "キチガイ",
    "fuck", "fuk", "shit", "bitch", "cunt", "dick", "pussy", "nigger", "nigga", "faggot", "asshole", "bastard",
    "whore", "slut", "retard", "motherf",
]
# 冒充系统 / 官方 / 游戏提示的词
_RESERVED = [
    "系统", "系統", "官方", "管理员", "管理員", "客服", "运营", "運營", "公告", "通知",
    "断开", "斷開", "断线", "斷線", "连接", "連接", "连线", "連線", "重连", "重連", "已退出", "出局",
    "システム", "運営", "管理者", "公式",
    "admin", "system", "official", "moderator", "gamemaster", "server",
]
_WORDS = [w.lower() for w in _PROFANITY + _RESERVED]


def _squash(s: str) -> str:
    """比对用：全角转半角、统一小写、只保留文字和数字。"""
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(ch for ch in s if ch.isalnum())


def clean_name(name: object) -> str:
    """去掉控制字符和所有空白、截断到 8 个字。"""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    return "".join(s.split())[:NAME_MAX]


def check_name(name: object) -> tuple[str, str | None]:
    """返回 (规范化后的名字, 错误码)。错误码为 None 表示可以使用。"""
    s = clean_name(name)  # 已 trim
    if len(s) == 0:
        return s, "name_invalid"
    if len(str(name or "").strip()) > NAME_MAX * 3:  # 明显超长的输入直接拒绝（正常输入框最多 8 个字）
        return s, "name_too_long"
    if not all(map(char_ok, s)):  # 中文 / 英文字母 / 数字以外的一律不行
        return s, "name_chars"
    flat = _squash(s)
    if any(w in flat for w in _WORDS):
        return s, "name_forbidden"
    return s, None
