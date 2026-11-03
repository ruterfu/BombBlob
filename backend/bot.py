"""机器人 AI：三个难度（简单 / 中等 / 难）。

机器人和真人走同一套输入接口（in_dir / in_bomb）。难度只改变「看到什么、多快反应、想做什么」，
唯一的数值特权是「难」的速度加成（+3%）。

  简单  以自保为主：几乎不吃道具（只吃身边 2 格内的），很少主动炸人，不戳破敌人的泡泡（队友会救它）；
        反应慢，而且每次被别人的炸弹威胁时有 20% 的概率犯傻不躲（自己的炸弹会跑）。
  中等  看到道具就去吃（连减速鞋也吃，傻傻的）；炸弹快炸了才躲；只打附近的敌人，附近有被困的敌人会去戳破。
  难    +3% 速度；全图追击、救人 / 戳泡泡优先；按「时间」规划躲避路线：知道每个格子什么时候着火、什么时候熄灭，
        会利用时间差（先去晚爆的格子，等早爆的火灭了再回来），并按身体覆盖 46% 的命中规则计算；
        走到一半发现危险会立刻掉头；会避开能被敌人一颗炸弹封死的位置；敌人逃不掉时放封路炸弹。
"""
from __future__ import annotations

import heapq
import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .game import Game, Player

ITEM_KINDS = ("needle", "ishield", "boots", "ghost", "wings")  # 与 game.ITEM_KINDS 一致

DIRS = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
DIR_KEYS = list(DIRS)
INF = math.inf

LEVELS = ("easy", "normal", "hard")
DEFAULT_LEVEL = "normal"
# 每个难度的形象：从对应等级段能选的头饰里随机一个（简单 Lv0–19、中等 Lv20–39、难 Lv40 以上）
LEVEL_BAND = {"easy": (0, 19), "normal": (20, 39), "hard": (40, 10_000)}

# 身体覆盖某格 ≥ 46% 才算被该格火焰命中（与 game.HIT_OVERLAP 一致）。
# 身体宽 0.6 格：离格子中心 ≤ 0.524 格时覆盖该格 ≥ 46%。
NEAR = 0.8 - 0.46 * 0.6


@dataclass(frozen=True)
class Profile:
    speed_bonus: float  # 速度加成（AI 专属）
    reaction: tuple[float, float]  # 发现危险后的反应时间（秒）
    notice: float  # 只能察觉还剩多少秒就要爆炸的危险（INF = 全部）
    pu_radius: int  # 吃道具的最远步数
    eat_slow: bool  # 会不会去吃减速鞋（傻）
    hunt_radius: int  # 追击敌人的最远步数（0 = 不主动追）
    aggression: float  # 敌人在爆炸范围内时放炸弹的概率
    bomb_reach: int  # 只对这个曼哈顿距离内的敌人放炸弹
    pop_radius: int  # 去戳破敌人泡泡的最远步数（0 = 不戳）
    rescue_radius: int  # 去救队友的最远步数
    help_first: bool  # 救人 / 戳泡泡优先于一切
    bomb_cd: tuple[float, float]  # 两次放炸弹的间隔
    timed: bool  # 按时间规划躲避路线
    margin: float  # 规划时与火焰保持的时间余量（秒）
    mid_move: bool  # 走到一半也能重新决定（难）
    trapper: bool  # 敌人逃不掉时放封路炸弹（难）
    wander: float  # 无事可做时随机走动的概率
    blunder: float = 0.0  # 被别人的炸弹威胁时「犯傻不躲」的概率（简单 20%）
    item_roll: float = 0.0  # 道具掉落时离它最近的 AI 掷骰子「专门去捡」的概率（中等 50%；难总会去捡；简单从不专门去捡）
    use_items: frozenset = frozenset()  # 会用哪些道具（中等不会用针）
    smart_items: bool = False  # 挑时机用道具（难）
    see_ghost: float = 0.0  # 每 3 秒掷一次骰子「看见」透明人的概率（难 30%）


PROFILES: dict[str, Profile] = {
    "easy": Profile(0.0, (0.35, 0.55), INF, 2, False, 0, 0.12, 2, 0, 4, False, (1.4, 2.2), False, 0.2, False, False, 0.35, 0.2),
    "normal": Profile(0.0, (0.1, 0.2), 1.6, 99, True, 8, 0.7, 4, 4, 8, False, (0.5, 0.9), False, 0.15, False, False, 0.5,
                      item_roll=0.5, use_items=frozenset({"ishield", "boots", "ghost", "wings"})),
    "hard": Profile(0.03, (0.0, 0.03), INF, 99, False, 99, 1.0, 99, 99, 99, True, (0.2, 0.4), True, 0.1, True, True, 0.4,
                    item_roll=1.0, use_items=frozenset({"needle", "ishield", "boots", "ghost", "wings"}), smart_items=True,
                    see_ghost=0.3),
}


def level_of(v: object) -> str:
    return v if isinstance(v, str) and v in PROFILES else DEFAULT_LEVEL


@dataclass
class BotState:
    level: str
    prof: Profile
    bomb_cd: float
    wait: float = 0.0
    goal: int | None = None
    kind: str | None = None
    goal_t: float = 0.0
    react: float | None = None  # 发现危险后剩余的反应时间；None：当前没有察觉到危险
    frozen: bool = False  # 这一次危险「犯傻不躲」
    ghost_seen: dict = field(default_factory=dict)  # 透明人 id → (下次掷骰子的时刻, 这 3 秒能否看见)
    hold: dict = field(default_factory=dict)  # 中等：道具格 → 打算使用的时刻
    pu_seen: dict = field(default_factory=dict)


def create(rng: random.Random, level: object = None) -> BotState:
    lv = level_of(level)
    prof = PROFILES[lv]
    return BotState(level=lv, prof=prof, bomb_cd=0.5 + rng.random())


def rnd(v: float) -> int:
    return math.floor(v + 0.5)


def _sample(rng: random.Random, span: tuple[float, float]) -> float:
    return span[0] + rng.random() * (span[1] - span[0])


def bfs(
    g: "Game",
    p: "Player",
    danger: list[float],
    speed: float,
    is_goal: Callable[[int], bool],
    safe_only: bool,
    max_steps: int = 10_000,
    blocked: frozenset[int] | set[int] = frozenset(),
) -> tuple[str | None, int] | None:
    """广度优先搜索。返回 (第一步方向, 目标格)；起点即目标时方向为 None；找不到返回 None。
    会考虑传送门：踩上传送门就到了另一端。"""
    W = g.W
    start = rnd(p.y) * W + rnd(p.x)
    if is_goal(start):
        return None, start
    first: dict[int, str | None] = {start: None}
    steps = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if steps[cur] >= max_steps:
            continue
        cx, cy = cur % W, cur // W
        order = DIR_KEYS[:]
        g.rng.shuffle(order)
        for d in order:
            dx, dy = DIRS[d]
            nx, ny = cx + dx, cy + dy
            ni = ny * W + nx
            if ni in blocked or not g.can_enter(nx, ny):
                continue
            node = _through_tele(g, ni)
            if node in first:
                continue
            arrive = (steps[cur] + 1) / speed
            dz = min(danger[ni], danger[node])
            if dz != INF:
                if safe_only:
                    continue
                # 只有在火焰来临之前能穿过才走
                if dz <= arrive + 1 / speed + 0.15:
                    continue
            first[node] = first[cur] or d
            steps[node] = steps[cur] + 1
            if is_goal(node):
                return first[node], node
            q.append(node)
    return None


def _through_tele(g: "Game", i: int) -> int:
    """走进格子 i 后实际所在的格子（传送门 → 另一端；另一端有炸弹时不传送）。"""
    dest = g.tele.get(i)
    if dest is None or g.bomb_at(dest % g.W, dest // g.W):
        return i
    return dest


# ---------------- 按时间规划躲避（难） ----------------
def _unsafe(win: dict, cell: int, t0: float, t1: float, m: float) -> bool:
    for s, e in win.get(cell, ()):
        if s - m < t1 and e + m > t0:
            return True
    return False


def _safe_after(win: dict, cell: int, t: float, m: float) -> bool:
    """从时刻 t 起，这个格子再也不会有火。"""
    return all(e + m <= t for _, e in win.get(cell, ()))


def _body_cells(x: float, y: float, near: float = NEAR) -> list[tuple[int, int]]:
    """身体覆盖 ≥ 46% 的格子坐标（near 可以放宽，留出空间余量）。"""
    out = []
    for tx in {math.floor(x), math.ceil(x)}:
        if abs(x - tx) > near:
            continue
        for ty in {math.floor(y), math.ceil(y)}:
            if abs(y - ty) > near:
                continue
            out.append((tx, ty))
    return out


def timed_escape(g: "Game", p: "Player", win: dict, speed: float, margin: float,
                 enter: Callable[[int, int], bool] | None = None) -> tuple[bool, str | None]:
    """在「格子 × 时间」上搜索一条不碰到任何火焰时间段的路线，终点是之后再也不会着火的格子。
    返回 (找到了吗, 第一步方向)；方向为 None 表示原地不动就是最优（包括停在两格之间）。"""
    W = g.W
    enter = enter or g.can_enter
    # 原地（可能在两格之间）：身体覆盖 ≥ 46% 的格子以后都不会着火 → 不动
    here = [y * W + x for x, y in _body_cells(p.x, p.y, NEAR + 0.1) if g.in_bounds(x, y)]
    if all(_safe_after(win, c, 0.0, margin) for c in here):
        return True, None

    step_t = 1.0 / speed
    starts: list[tuple[float, int, str | None]] = []  # (到达时刻, 格子, 第一步方向)
    fx, fy = p.x - round(p.x), p.y - round(p.y)
    if abs(fx) < 1e-6 and abs(fy) < 1e-6:
        starts.append((0.0, rnd(p.y) * W + rnd(p.x), None))
    else:
        # 在两格之间：可以走回任一侧的格子中心
        horiz = abs(fx) >= 1e-6
        pos = p.x if horiz else p.y
        for target in (math.floor(pos), math.ceil(pos)):
            other = math.ceil(pos) if target == math.floor(pos) else math.floor(pos)
            dist = abs(pos - target)
            t_arr = dist / speed
            tc = (target, rnd(p.y)) if horiz else (rnd(p.x), target)
            oc = (other, rnd(p.y)) if horiz else (rnd(p.x), other)
            ti, oi = tc[1] * W + tc[0], oc[1] * W + oc[0]
            # 离开 other：身体离 other 中心超过 NEAR 之前仍算覆盖 other
            leave_other = max(0.0, (NEAR - abs(pos - other))) / speed
            enter_target = max(0.0, dist - NEAR) / speed
            if _unsafe(win, oi, 0.0, leave_other, margin) or _unsafe(win, ti, enter_target, t_arr, margin):
                continue
            d = (("right" if target > pos else "left") if horiz else ("down" if target > pos else "up"))
            starts.append((t_arr, ti, d))
    if not starts:
        return False, None

    horizon = max((e for ws in win.values() for _, e in ws if e < 1e8), default=0.0) + 0.6
    wait_t = 0.1
    seen: set[tuple[int, int]] = set()
    heap: list[tuple[float, int, int, str | None]] = []
    n = 0
    for t, c, d in starts:
        heapq.heappush(heap, (t, n, c, d))
        n += 1
    expanded = 0
    while heap and expanded < 6000:
        t, _, c, first = heapq.heappop(heap)
        key = (c, int(t / 0.05))
        if key in seen:
            continue
        seen.add(key)
        expanded += 1
        if _safe_after(win, c, t, margin):
            return True, first
        if t > horizon:
            continue
        # 原地等待
        if not _unsafe(win, c, t, t + wait_t, margin):
            heapq.heappush(heap, (t + wait_t, n, c, first))
            n += 1
        cx, cy = c % W, c // W
        for d, (dx, dy) in DIRS.items():
            nx, ny = cx + dx, cy + dy
            if not enter(nx, ny):
                continue
            ni = ny * W + nx
            # 走一格：前 52.4% 的时间仍覆盖原格，后 52.4% 的时间已覆盖新格（46% 命中规则）
            if _unsafe(win, c, t, t + NEAR * step_t, margin) or _unsafe(win, ni, t + (1 - NEAR) * step_t, t + step_t, margin):
                continue
            node = _through_tele(g, ni)  # 传送门：到达后立刻在另一端
            if node != ni and _unsafe(win, node, t + step_t, t + step_t + 0.05, margin):
                continue
            heapq.heappush(heap, (t + step_t, n, node, first if first is not None or t > 0 else d))
            n += 1
    return False, None


# ---------------- 决策 ----------------
def think(g: "Game", p: "Player", dt: float) -> None:
    from .game import FUSE

    ai: BotState = p.ai
    prof = ai.prof
    ai.bomb_cd -= dt
    ai.goal_t -= dt
    if ai.react is not None and ai.react > 0:
        ai.react -= dt  # 反应时间无论站着还是在走都在流逝
    at_center = abs(p.x - round(p.x)) < 1e-6 and abs(p.y - round(p.y)) < 1e-6
    W = g.W
    speed = g.player_speed(p)

    # 被困：难会挑时机用针（附近没有能来救的队友，或者敌人靠近 / 快要出局）
    if p.trapped > 0 and "needle" in p.items and "needle" in prof.use_items:
        mates = [o for o in g.players if o is not p and g.is_free(o) and g.mode == "team" and o.team == p.team
                 and abs(o.x - p.x) + abs(o.y - p.y) <= 4]
        foes = [o for o in g.players if g.is_free(o) and o.team != p.team and abs(o.x - p.x) + abs(o.y - p.y) <= 5]
        if not mates or foes or p.trapped < 2.0:
            g.use_item(p.id, p.items.index("needle"))
    if p.trapped <= 0 and prof.use_items:
        _casual_items(g, p, ai)

    # 难：走到一半也盯着火焰时间表，一有危险当帧重新规划
    if prof.mid_move and not at_center and p.trapped <= 0:
        win = g.flame_windows()
        if win and _threatened(g, p, win):
            ok, d = timed_escape(g, p, win, speed, prof.margin)
            if ok:
                p.in_dir = d
                ai.goal = None
                return
    if ai.wait > 0:
        ai.wait -= dt
        return
    if p.moving and not at_center:
        return  # 只在格子中心做决定
    here = g.idx(p.x, p.y)
    full = g.danger_map()
    # 察觉范围：中等对别人的炸弹只在「快要炸了」才发现（自己的炸弹当然知道）
    if prof.notice == INF:
        danger = full
    else:
        own = {i for b in g.bombs if b.owner == p.id for i in g.blast_tiles(b.px, b.py, b.range)}
        danger = [d if d <= prof.notice or i in own else INF for i, d in enumerate(full)]

    # 0. 被困：向最近的自由队友靠拢，等待救援
    if p.trapped > 0:
        mates = {g.idx(o.x, o.y) for o in g.players if o is not p and g.is_free(o) and g.mode == "team" and o.team == p.team}
        r = bfs(g, p, [INF] * len(danger), speed, lambda i: i in mates, True) if mates else None
        p.in_dir = r[0] if r else None
        return

    # 1. 躲避危险（先经过反应时间）
    if danger[here] != INF or (not at_center and _threatened_cells(g, p, danger)):
        if ai.react is None:
            ai.react = _sample(g.rng, prof.reaction)
            # 犯傻只针对别人的炸弹（自己刚放的炸弹总会跑）
            own_here = any(here in g.blast_tiles(b.px, b.py, b.range) for b in g.bombs if b.owner == p.id)
            ai.frozen = not own_here and g.rng.random() < prof.blunder
        if ai.frozen:
            if at_center:
                p.in_dir = None  # 犯傻：愣在原地不躲
            return
        if ai.react > 0:
            if at_center:
                p.in_dir = None  # 还没反应过来：愣在原地（不会顺着原方向冲进火里）
            return
        ai.goal = None
        if prof.timed:
            win = g.flame_windows()
            ok, d = timed_escape(g, p, win, speed, prof.margin)
            if ok:
                p.in_dir = d
                return
            if _rescue_items(g, p, win, speed, prof):  # 躲不掉：腾飞之翼 / 超级跑鞋 / 无敌盾牌
                return
        r = bfs(g, p, danger, speed, lambda i: danger[i] == INF, False)
        if r is None and "ishield" in p.items and "ishield" in prof.use_items and p.ishield_t <= 0:
            g.use_item(p.id, p.items.index("ishield"))  # 中等：没路可逃就开无敌盾牌
        if r is None and not at_center:
            p.in_dir = _toward_center(p)
            return
        p.in_dir = r[0] if r else None
        return
    ai.react = None
    if not at_center:
        # 停在两格之间（躲完火焰之后）：回到格子中心再做决定
        p.in_dir = _toward_center(p)
        return

    enemies = [o for o in g.players if g.is_free(o) and o is not p and o.team != p.team and _sees(g, ai, o)]
    enemy_tiles = {g.idx(e.x, e.y) for e in enemies}
    near_enemy_tiles = {g.idx(e.x, e.y) for e in enemies if abs(rnd(e.x) - rnd(p.x)) + abs(rnd(e.y) - rnd(p.y)) <= prof.bomb_reach}
    trapped_enemy = {g.idx(o.x, o.y) for o in g.players if o.alive and o.trapped > 0 and o.team != p.team and _sees(g, ai, o)}
    trapped_mate = {g.idx(o.x, o.y) for o in g.players if o.alive and o.trapped > 0 and o is not p and o.team == p.team}

    def near_crate(i: int) -> bool:
        x, y = i % W, i // W
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if g.in_bounds(nx, ny) and g.blocks[ny * W + nx] in ("x", "m", "e"):
                return True
        return False

    def enemy_in_line(i: int, tiles: set[int] = near_enemy_tiles) -> bool:
        if not tiles:
            return False
        return any(t in tiles for t in g.blast_tiles(i % W, i // W, p.range))

    def try_bomb() -> bool:
        if ai.bomb_cd > 0 or g.active_bombs(p) >= p.max_bombs or g.bomb_at(rnd(p.x), rnd(p.y)):
            return False
        extra = (p.x, p.y, FUSE, p.range)
        if prof.timed:
            ok, d = timed_escape(g, p, g.flame_windows(extra), speed, prof.margin + 0.05)
            if not ok or d is None:
                return False
        else:
            d2 = g.danger_map(extra)
            r = bfs(g, p, d2, speed, lambda i: d2[i] == INF, False)
            if not r or not r[0]:
                return False
            d = r[0]
        p.in_bomb = True
        p.in_dir = d
        ai.bomb_cd = _sample(g.rng, prof.bomb_cd)
        ai.goal = None
        return True

    def enemy_cornered() -> bool:
        """在脚下放一颗炸弹后，范围内的某个敌人来不及逃出去。"""
        if not enemies:
            return False
        extra = (p.x, p.y, FUSE, p.range)
        d2 = g.danger_map(extra)
        mine = frozenset({here})
        for e in enemies:
            ei = g.idx(e.x, e.y)
            if d2[ei] == INF:
                continue
            r = bfs(g, e, d2, g.player_speed(e), lambda i: d2[i] == INF, False, max_steps=12, blocked=mine)
            if r is None:
                return True
        return False

    # 2. 缩圈：自己所在的格子快要落墙了，提前往「最后才落墙」的方向走（难看 8 秒，其他看 4 秒）。
    #    目标是能走到的格子里最晚落墙的那个，而不是「刚好安全」的格子，避免钻进会被封死的死胡同。
    if g.sd_started:
        rank = g.sd_rank
        limit = g.sd_index + int((8.0 if prof.timed else 4.0) / max(g.sd_interval, 1e-3))
        if rank.get(here, 1 << 30) < limit:
            deepest = _deepest_cell(g, p, full)
            if deepest is not None and deepest != here:
                r = bfs(g, p, full, speed, lambda i: i == deepest, True)
                if r and r[0]:
                    p.in_dir = r[0]
                    ai.goal = None
                    return

    # 2b. 站位（难）：附近的敌人若在原地放一颗炸弹就能把我封死，先离开这个位置
    if prof.timed:
        near = [e for e in enemies if abs(rnd(e.x) - rnd(p.x)) + abs(rnd(e.y) - rnd(p.y)) <= e.range + 3]
        if near:
            hyp = g.danger_map([(float(rnd(e.x)), float(rnd(e.y)), FUSE, e.range) for e in near])
            if hyp[here] != INF and bfs(g, p, hyp, speed, lambda i: hyp[i] == INF, False) is None:
                r = bfs(g, p, full, speed, lambda i: hyp[i] == INF, True, max_steps=8)
                if r and r[0]:
                    p.in_dir = r[0]
                    ai.goal = None
                    return

    # 3. 封路炸弹（难）：敌人逃不掉就立刻放
    if prof.trapper and ai.bomb_cd <= 0 and g.active_bombs(p) < p.max_bombs and enemy_cornered() and try_bomb():
        return

    # 4. 敌人在爆炸范围内就放炸弹
    if enemy_in_line(here) and g.rng.random() < prof.aggression and try_bomb():
        return

    # 5. 到达目标后执行动作
    if ai.goal == here:
        if (ai.kind == "crate" and near_crate(here)) or (ai.kind == "hunt" and enemy_in_line(here, enemy_tiles)):
            if try_bomb():
                return
            if ai.bomb_cd > 0 and g.active_bombs(p) < p.max_bombs:
                p.in_dir = None  # 等冷却
                return
        ai.goal = None

    def want_pu(i: int) -> bool:
        kind = g.powerups.get(i)
        if kind is None:
            return False
        if kind in ITEM_KINDS:
            # 道具：简单不会专门去捡（路过碰到会捡起来，但不会用）；中等只去捡掷骰子决定的；难都去捡
            if "" not in p.items:
                return False
            return prof.smart_items or g.item_claims.get(i) == p.id
        return prof.eat_slow or kind != "slow"

    # 6. 目标失效则重新选
    def valid() -> bool:
        if ai.goal is None or ai.goal_t <= 0 or danger[ai.goal] != INF:
            return False
        if ai.kind == "pu":
            return want_pu(ai.goal)
        if ai.kind == "rescue":
            return ai.goal in trapped_mate
        if ai.kind == "pop":
            return ai.goal in trapped_enemy
        if ai.kind == "crate":
            return near_crate(ai.goal)
        if ai.kind == "hunt":
            return enemy_in_line(ai.goal, enemy_tiles)
        return True

    if not valid():
        ai.goal = None
        order: list[tuple[str, Callable[[int], bool], int]] = []
        help_ = [("rescue", lambda i: i in trapped_mate, prof.rescue_radius)]
        if prof.pop_radius:
            help_.append(("pop", lambda i: i in trapped_enemy, prof.pop_radius))
        pu = [("pu", want_pu, prof.pu_radius)]
        hunt = [("hunt", lambda i: enemy_in_line(i, enemy_tiles), prof.hunt_radius)] if prof.hunt_radius else []
        crate = [("crate", lambda i: i != here and near_crate(i), 99)]
        chase = [("chase", lambda i: i in enemy_tiles, prof.hunt_radius)] if prof.hunt_radius else []
        if prof.help_first:
            order = help_ + hunt + pu + crate + chase
        elif g.rng.random() < prof.aggression * 0.5:
            order = help_ + pu + hunt + crate + chase
        else:
            order = help_ + pu + crate + hunt + chase
        for kind, fn, radius in order:
            r = bfs(g, p, danger, speed, fn, True, max_steps=radius)
            if r and r[1] != here:
                ai.goal, ai.kind = r[1], kind
                ai.goal_t = 1.2 if kind in ("hunt", "chase", "rescue", "pop") else 4.0
                break

    # 难：主动用道具（追击时开透明人 / 超级跑鞋）
    if prof.smart_items and enemies:
        near = min(abs(rnd(e.x) - rnd(p.x)) + abs(rnd(e.y) - rnd(p.y)) for e in enemies)
        if near <= 6 and p.ghost_t <= 0 and "ghost" in p.items:
            g.use_item(p.id, p.items.index("ghost"))
        elif 4 <= near <= 10 and ai.kind in ("chase", "hunt") and p.boots_t <= 0 and "boots" in p.items:
            g.use_item(p.id, p.items.index("boots"))

    # 7. 朝目标走一步
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
        if opts and g.rng.random() < prof.wander:
            step = g.rng.choice(opts)
    p.in_dir = step
    if step is None:
        ai.wait = 0.08 if prof.mid_move else _sample(g.rng, (0.05, 0.17))


def _deepest_cell(g: "Game", p: "Player", danger: list[float]) -> int | None:
    """能安全走到的格子里，缩圈最晚落墙的那个（不在缩圈顺序里的视为最晚）。"""
    W = g.W
    start = g.idx(p.x, p.y)
    rank = g.sd_rank
    best, best_r = start, rank.get(start, 1 << 30)
    seen = {start}
    q = deque([start])
    while q:
        c = q.popleft()
        cx, cy = c % W, c // W
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            ni = ny * W + nx
            if not g.can_enter(nx, ny) or danger[ni] != INF:
                continue
            ni = _through_tele(g, ni)
            if ni in seen or danger[ni] != INF:
                continue
            seen.add(ni)
            r = rank.get(ni, 1 << 30)
            if r > best_r:
                best, best_r = ni, r
            q.append(ni)
    return best


def _sees(g: "Game", ai: BotState, o: "Player") -> bool:
    """透明人：简单 / 中等看不见；难每 3 秒掷一次骰子，30% 能看见（这 3 秒内透明对它无效）。"""
    if o.ghost_t <= 0:
        return True
    if ai.prof.see_ghost <= 0:
        return False
    nxt, seen = ai.ghost_seen.get(o.id, (-1.0, False))
    if g.elapsed >= nxt:
        nxt, seen = g.elapsed + 3.0, g.rng.random() < ai.prof.see_ghost
        ai.ghost_seen[o.id] = (nxt, seen)
    return seen


def _rescue_items(g: "Game", p: "Player", win: dict, speed: float, prof: Profile) -> bool:
    """难：躲不掉的时候按顺序试：腾飞之翼（穿过炸弹能逃）→ 超级跑鞋（跑得更快能逃）→ 无敌盾牌（火快到了）。"""
    from .game import BLOCKING, MAX_SPEED_LV, SPEED_STEP

    if "wings" in p.items and p.wings_t <= 0:
        def fly(x: int, y: int) -> bool:
            return g.in_bounds(x, y) and g.blocks[y * g.W + x] not in BLOCKING
        ok, d = timed_escape(g, p, win, speed, prof.margin, enter=fly)
        if ok:
            g.use_item(p.id, p.items.index("wings"))
            p.in_dir = d
            return True
    if "boots" in p.items and p.boots_t <= 0:
        fast = speed * (1 + SPEED_STEP * MAX_SPEED_LV) / (1 + SPEED_STEP * g.speed_level(p))
        ok, d = timed_escape(g, p, win, fast, prof.margin)
        if ok:
            g.use_item(p.id, p.items.index("boots"))
            p.in_dir = d
            return True
    if "ishield" in p.items and p.ishield_t <= 0:
        here = [y * g.W + x for x, y in _body_cells(p.x, p.y) if g.in_bounds(x, y)]
        soon = min((s for c in here for s, _ in win.get(c, ())), default=INF)
        if soon <= 0.35:
            g.use_item(p.id, p.items.index("ishield"))
            p.in_dir = None
            return True
    return False


def _casual_items(g: "Game", p: "Player", ai: BotState) -> None:
    """中等：捡到跑鞋 / 透明人 / 翅膀后过 2–5 秒就随手用掉（不挑时机）。"""
    if ai.prof.smart_items:
        return
    for slot, kind in enumerate(p.items):
        if kind not in ("boots", "ghost", "wings") or kind not in ai.prof.use_items:
            ai.hold.pop(slot, None)
            continue
        at = ai.hold.setdefault(slot, g.elapsed + 2 + g.rng.random() * 3)
        if g.elapsed >= at:
            ai.hold.pop(slot, None)
            g.use_item(p.id, slot)
            return


def _toward_center(p: "Player") -> str | None:
    fx, fy = p.x - round(p.x), p.y - round(p.y)
    if abs(fx) >= 1e-6:
        return "left" if fx > 0 else "right"
    if abs(fy) >= 1e-6:
        return "up" if fy > 0 else "down"
    return None


def _threatened(g: "Game", p: "Player", win: dict) -> bool:
    """身体覆盖的格子或正要进入的格子在近期会着火。"""
    W = g.W
    cells = {y * W + x for x, y in _body_cells(p.x, p.y) if g.in_bounds(x, y)}
    if p.in_dir:
        dx, dy = DIRS[p.in_dir]
        nx, ny = rnd(p.x + dx * 0.5), rnd(p.y + dy * 0.5)
        if g.in_bounds(nx, ny):
            cells.add(ny * W + nx)
    return any(c in win for c in cells)


def _threatened_cells(g: "Game", p: "Player", danger: list[float]) -> bool:
    W = g.W
    return any(danger[y * W + x] != INF for x, y in _body_cells(p.x, p.y) if g.in_bounds(x, y))
