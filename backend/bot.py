"""机器人 AI：躲避危险 → 有价值时放炸弹（确认有退路）→ 捡道具 / 炸箱子 / 追击敌人。

机器人和真人走同一套输入接口（in_dir / in_bomb），没有任何特权。
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .game import Game, Player

DIRS = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
DIR_KEYS = list(DIRS)
INF = math.inf


@dataclass
class BotState:
    bomb_cd: float
    aggression: float
    reaction: float
    wait: float = 0.0
    goal: int | None = None
    kind: str | None = None
    goal_t: float = 0.0


def create(rng: random.Random) -> BotState:
    return BotState(
        bomb_cd=0.5 + rng.random(),
        aggression=0.55 + rng.random() * 0.4,
        reaction=0.05 + rng.random() * 0.12,
    )


def rnd(v: float) -> int:
    return math.floor(v + 0.5)


def bfs(
    g: "Game",
    p: "Player",
    danger: list[float],
    speed: float,
    is_goal: Callable[[int], bool],
    safe_only: bool,
) -> tuple[str | None, int] | None:
    """广度优先搜索。返回 (第一步方向, 目标格)；起点即目标时方向为 None；找不到返回 None。"""
    W = g.W
    sx, sy = rnd(p.x), rnd(p.y)
    start = sy * W + sx
    if is_goal(start):
        return None, start
    prev = {start: -1}
    steps = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        cx, cy = cur % W, cur // W
        order = DIR_KEYS[:]
        g.rng.shuffle(order)
        for d in order:
            dx, dy = DIRS[d]
            nx, ny = cx + dx, cy + dy
            ni = ny * W + nx
            if ni in prev or not g.can_enter(nx, ny):
                continue
            arrive = (steps[cur] + 1) / speed
            dz = danger[ni]
            if dz != INF:
                if safe_only:
                    continue
                # 只有在火焰来临之前能穿过才走
                if dz <= arrive + 1 / speed + 0.15:
                    continue
            prev[ni] = cur
            steps[ni] = steps[cur] + 1
            if is_goal(ni):
                node = ni
                while prev[node] != start:
                    node = prev[node]
                fx, fy = node % W, node // W
                for k, (ddx, ddy) in DIRS.items():
                    if sx + ddx == fx and sy + ddy == fy:
                        return k, ni
            q.append(ni)
    return None


def think(g: "Game", p: "Player", dt: float) -> None:
    from .game import FUSE

    ai: BotState = p.ai
    ai.bomb_cd -= dt
    ai.goal_t -= dt
    if ai.wait > 0:
        ai.wait -= dt
        return
    if p.moving and not (abs(p.x - round(p.x)) < 1e-6 and abs(p.y - round(p.y)) < 1e-6):
        return  # 只在格子中心做决定
    W = g.W
    speed = g.player_speed(p)
    here = g.idx(p.x, p.y)
    danger = g.danger_map()

    # 0. 被困：向最近的自由队友靠拢，等待救援
    if p.trapped > 0:
        mates = {g.idx(o.x, o.y) for o in g.players if o is not p and g.is_free(o) and g.mode == "team" and o.team == p.team}
        r = bfs(g, p, [INF] * len(danger), speed, lambda i: i in mates, True) if mates else None
        p.in_dir = r[0] if r else None
        return

    # 1. 躲避危险
    if danger[here] != INF:
        r = bfs(g, p, danger, speed, lambda i: danger[i] == INF, False)
        p.in_dir = r[0] if r else None
        ai.goal = None
        return

    enemies = [o for o in g.players if g.is_free(o) and o is not p and o.team != p.team]
    enemy_tiles = {g.idx(e.x, e.y) for e in enemies}
    trapped_enemy = {g.idx(o.x, o.y) for o in g.players if o.alive and o.trapped > 0 and o.team != p.team}
    trapped_mate = {g.idx(o.x, o.y) for o in g.players if o.alive and o.trapped > 0 and o is not p and o.team == p.team}

    def near_crate(i: int) -> bool:
        x, y = i % W, i // W
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if g.in_bounds(nx, ny) and g.blocks[ny * W + nx] in ("x", "m", "e"):
                return True
        return False

    def enemy_in_line(i: int) -> bool:
        if not enemy_tiles:
            return False
        return any(t in enemy_tiles for t in g.blast_tiles(i % W, i // W, p.range))

    def try_bomb() -> bool:
        if ai.bomb_cd > 0 or g.active_bombs(p) >= p.max_bombs or g.bomb_at(rnd(p.x), rnd(p.y)):
            return False
        d2 = g.danger_map((p.x, p.y, FUSE, p.range))
        r = bfs(g, p, d2, speed, lambda i: d2[i] == INF, False)
        if not r or not r[0]:
            return False
        p.in_bomb = True
        p.in_dir = r[0]
        ai.bomb_cd = 0.35 + g.rng.random() * 0.5
        ai.goal = None
        return True

    # 2. 敌人在爆炸范围内就放炸弹
    if enemy_in_line(here) and g.rng.random() < ai.aggression and try_bomb():
        return

    # 3. 到达目标后执行动作
    if ai.goal == here:
        if (ai.kind == "crate" and near_crate(here)) or (ai.kind == "hunt" and enemy_in_line(here)):
            if try_bomb():
                return
            if ai.bomb_cd > 0 and g.active_bombs(p) < p.max_bombs:
                p.in_dir = None  # 等冷却
                return
        ai.goal = None

    # 4. 目标失效则重新选
    def valid() -> bool:
        if ai.goal is None or ai.goal_t <= 0 or danger[ai.goal] != INF:
            return False
        if ai.kind == "pu":
            return ai.goal in g.powerups
        if ai.kind == "rescue":
            return ai.goal in trapped_mate
        if ai.kind == "pop":
            return ai.goal in trapped_enemy
        if ai.kind == "crate":
            return near_crate(ai.goal)
        if ai.kind == "hunt":
            return enemy_in_line(ai.goal)
        return True

    if not valid():
        ai.goal = None
        order: list[tuple[str, Callable[[int], bool]]] = [
            ("rescue", lambda i: i in trapped_mate),
            ("pop", lambda i: i in trapped_enemy),
            ("pu", lambda i: i in g.powerups and g.powerups[i] != "slow"),
        ]
        hunt = ("hunt", enemy_in_line)
        crate = ("crate", lambda i: i != here and near_crate(i))
        order += [hunt, crate] if g.rng.random() < ai.aggression * 0.5 else [crate, hunt]
        order.append(("chase", lambda i: i in enemy_tiles))
        for kind, fn in order:
            r = bfs(g, p, danger, speed, fn, True)
            if r and r[1] != here:
                ai.goal, ai.kind = r[1], kind
                ai.goal_t = 1.2 if kind in ("hunt", "chase", "rescue", "pop") else 4.0
                break

    # 5. 朝目标走一步
    step = None
    if ai.goal is not None:
        goal = ai.goal
        r = bfs(g, p, danger, speed, lambda i: i == goal, True)
        if r:
            step = r[0]
        else:
            ai.goal = None
    if step is None and ai.goal is None:
        cx, cy = rnd(p.x), rnd(p.y)
        opts = [
            d
            for d, (dx, dy) in DIRS.items()
            if g.can_enter(cx + dx, cy + dy) and danger[(cy + dy) * W + cx + dx] == INF
        ]
        if opts and g.rng.random() < 0.5:
            step = g.rng.choice(opts)
    p.in_dir = step
    if step is None:
        ai.wait = ai.reaction
