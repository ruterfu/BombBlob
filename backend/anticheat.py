"""异常行为观察：客户端异常移动 / 异常放炸弹间隔。

每个玩家一条记录（存 map，不用定时器，靠到期时间判断）：
    if 异常:
        if 时间已过（10 秒观察期结束）或 没有时间:
            异常 = 1; 时间 = 现在 + 10 秒
        else:
            异常 += 1
        if 异常 >= 3: 触发提醒（提醒后清零）
10 秒内没凑够 3 次，到期后下一次异常重新从 1 开始计。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

OBSERVE_SECONDS = 10.0  # 观察期
STRIKES_TO_WARN = 3  # 观察期内累计几次触发提醒


@dataclass
class Watch:
    count: int = 0
    until: float | None = None  # 观察期到期时间（None = 没有时间）

    def report(self, now: float) -> bool:
        """记录一次异常；返回 True 表示应触发提醒。"""
        if self.until is None or now >= self.until:
            self.count = 1
            self.until = now + OBSERVE_SECONDS
        else:
            self.count += 1
        if self.count >= STRIKES_TO_WARN:
            self.count = 0
            self.until = None
            return True
        return False


class Watcher:
    """玩家 ID → 观察记录。"""

    def __init__(self) -> None:
        self.watches: dict[str, Watch] = {}

    def report(self, uid: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if len(self.watches) > 5000:  # 顺手清掉已到期的记录
            self.watches = {k: w for k, w in self.watches.items() if w.until is not None and w.until > now}
        return self.watches.setdefault(uid, Watch()).report(now)
