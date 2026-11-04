"""服务器权威的游戏模拟（60Hz）。

所有判定（移动、碰撞、爆炸、受困 / 救援、道具、缩圈、胜负）都在这里完成，
客户端只发送按键输入（带序号，用于客户端预测校正），只负责渲染。

规则要点：
  * 被火焰击中 → 被困 10 秒（只能缓慢移动、不能放炸弹 / 捡道具）
      - 队友碰到：救出并复活（短暂无敌）
      - 敌人碰到：直接击破（淘汰，计为击倒）
      - 10 秒内无人救援：淘汰
  * 护盾可抵挡一次击中
  * 跑鞋 +5% 速度（最多 +35%），超级跑鞋 5 秒内 +50%，减速道具 -5%（最多 -25%）
  * 炸弹道具：可同时放置数 +1（起始 1，最多 8）
  * 钢制货箱需两次爆炸；爆炸油桶被引爆后会二次爆炸
"""
from __future__ import annotations

import asyncio
import math
import random
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import bot
from .maps import build_map

TICK_RATE = 60  # 服务器模拟频率（判定精度）
NET_RATE = 30  # 默认状态广播频率（同步 Hz，可用环境变量 SYNC_HZ 调整，10–60）
NET_RATE_MIN, NET_RATE_MAX = 10, 60
DT = 1 / TICK_RATE
ROUND_TIME = 600.0  # 一局 10 分钟
SD_TIME = 60.0  # 最后 60 秒开始缩圈
COUNTDOWN = 3.0
WAIT_MAX = 15.0  # 开局前等待玩家加载完成（连接就绪）的最长时间，超时后不再等
FUSE = 2.5
FLAME_TIME = 0.55
INVULN_RESCUE = 3.0  # 被救活后无敌 3 秒
INVULN_START = 3.0  # 开局无敌 3 秒
RESPAWN_TIME = 3.0  # 复活赛：被淘汰后多久自动复活
INVULN_RESPAWN = 3.0  # 复活后无敌 3 秒
RANK_BONUS = (25, 15, 5)
FIXED_BOMBS = 3  # 关闭道具模式：固定可连放 3 个
FIXED_RANGE = 3  # 关闭道具模式：固定威力 7×7
AIRDROP_DELAY = (30.0, 80.0)  # 道具模式：箱子炸完、地上道具都被吃掉后，隔多久（随机）空投一个道具  # 复活赛：按得分前三名的点数加成（%）
BODY_HALF = 0.3  # 角色碰撞半宽（格）
HIT_OVERLAP = 0.46  # 身体覆盖某格的比例 ≥ 46% 才会被该格火焰命中
TOUCH_DIST = 0.6  # 两名角色中心距离小于此值视为接触（救援 / 击破）
TRAP_TIME = 10.0
TRAP_SPEED = 0.3  # 被困时的移动速度倍率
BASE_SPEED = 3.8
SPEED_STEP = 0.05  # 每级 ±5%
MAX_SPEED_LV = 7  # +35%
BOOTS_SPEED_LV = 10  # 超级跑鞋：+50%
MIN_SPEED_LV = -5  # -25%
MAX_BOMBS = 8
START_RANGE = 1  # 初始威力：中心向四个方向各 1 格（3x3 十字）
MAX_RANGE = 6  # 最大威力：每个方向 6 格（13x13 十字）
BARREL_RANGE = 2
KICK_SPEED = 9.0
ICE_MULT = 1.35
CORNER_ASSIST = 0.6  # 偏离通道不超过该距离时自动滑角对齐
TELE_SNAP = 0.2  # 靠近传送门中心该距离内触发
EPS = 1e-6
MOVE_TOLERANCE = 1.15  # 客户端上报移动的速度容差
BOMB_RATE = 10.0  # 放炸弹请求：每秒最多 10 次（按键不连发，正常手速远低于此）
BOMB_BURST = 4.0  # 允许网络抖动造成的成批到达
MOVE_BURST = 1.0  # 额度最多累积 1 秒（容忍网络抖动 / 卡顿后成批到达的位置上报）
HIT_GRACE_MAX = 0.15  # 延迟补偿：火焰命中客户端移动的玩家前，最多等待其上报位置的时间
PATH_STEP = 0.05  # 路径碰撞检测采样步长（格）
DROP_CHANCE = 0.5
END_DELAY = 3.0
KEYFRAME_TICKS = 120  # 每 2 秒强制下发一次完整地图
INF = math.inf
BOMB_STYLES = ("poison", "water", "gold")  # 商店里的炸弹特效（纯画面）

DIRS: dict[str, tuple[int, int]] = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
DIR_LIST = ["up", "right", "down", "left"]
OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}
BIT = {"up": 1, "right": 2, "down": 4, "left": 8}
CENTER_BIT = 16
CONVEYOR = {"^": "up", "v": "down", "<": "left", ">": "right"}
# 道具：bomb 连放+1 / fire 威力+1 / speed 跑鞋+5% / slow 减速-5% / shield 护盾 / kick 踢弹 / max 威力 +50%
POWERUP_TABLE = [("bomb", 26), ("fire", 28), ("speed", 16), ("slow", 10), ("shield", 8), ("kick", 6), ("max", 2),
                 # 道具（放进道具栏，按 1–6 使用）
                 ("needle", 5), ("ishield", 4), ("boots", 4), ("ghost", 3), ("wings", 3)]
# 道具：针（被困时使用，立即脱困）/ 无敌盾牌（3 秒内不会被炸到）/ 超级跑鞋（5 秒速度 +50%）
#       透明人（隐身 10 秒）/ 腾飞之翼（5 秒内可以穿过炸弹，被火焰炸到照样判定）
ITEM_KINDS = ("needle", "ishield", "boots", "ghost", "wings")
ITEM_SLOTS = 6
ISHIELD_TIME = 3.0
BOOTS_TIME = 5.0
GHOST_TIME = 10.0
WINGS_TIME = 5.0
BLOCKING = ("#", "x", "m", "e", "g", "w", "Y", "H", "~")
HARD = ("#", "Y", "H", "w")  # 挡住火焰且不可破坏（w = 升起的冰墙闸门）
SOFT = ("x", "m", "e", "g")  # 挡住火焰、可被炸毁

# ---- 地图机关 ----
REGROW_TIME = 15.0  # 樱花庭院：草丛被烧掉后多久重新长出来
GATE_PERIOD = 7.0  # 极光冰川：两组冰墙闸门每隔多久轮换一次
GATE_WARN = 1.5  # 闸门升起前的预警时间
SUPPLY_PERIOD = 12.0  # 星际空港：补给台每隔多久空投一次道具
VENT_PERIOD = 9.0  # 烈日斗兽场：火焰喷口喷火间隔
VENT_RANGE = 2
METEOR_PERIOD = 6.5  # 火山孤岛：陨石间隔
METEOR_COUNT = 3
METEOR_RANGE = 1
HAZARD_WARN = 1.6  # 喷火 / 陨石落地前的预警时间
MECH_DELAY = 6.0  # 开局多久后机关才开始运作
CHEST_TABLE = [("bomb", 30), ("fire", 30), ("speed", 16), ("kick", 9), ("shield", 10), ("max", 5)]
WALKABLE_FOR_BOMB = (".", "b")


def pick_powerup(rng: random.Random, items: bool = True) -> str:
    """按权重随机一种掉落物；items=False（房间关闭道具）时只掉普通加成。"""
    table = POWERUP_TABLE if items else [(k, w) for k, w in POWERUP_TABLE if k not in ITEM_KINDS]
    r = rng.random() * sum(w for _, w in table)
    for k, w in table:
        r -= w
        if r < 0:
            return k
    return "bomb"


def _is_int(v: float) -> bool:
    return abs(v - round(v)) < EPS


def rnd(v: float) -> int:
    """四舍五入到最近的整数（与 JS Math.round 对正数一致）。"""
    return math.floor(v + 0.5)


def r3(v: float) -> float:
    return round(v, 3)


@dataclass
class Target:
    x: int
    y: int
    fx: float
    fy: float


@dataclass
class Player:
    id: str
    name: str
    skin: int
    hat: int
    team: int
    is_bot: bool
    x: float
    y: float
    moving: bool = False
    facing: str = "down"
    in_dir: str | None = None
    tap_dir: str | None = None  # 快速点按：按下又在同一帧松开时也至少走一帧
    in_bomb: bool = False
    ack: int = 0  # 最后处理的输入序号（客户端预测校正用）
    alive: bool = True
    trapped: float = 0.0  # 剩余被困时间
    trap_by: str | None = None
    max_bombs: int = 1
    range: int = START_RANGE
    speed_lv: int = 0
    kick: bool = False
    shield: bool = False
    invuln: float = 0.0
    kills: int = 0
    rescues: int = 0
    level: int = 0
    avatar: str | None = None  # GitHub 头像地址（游客为空）
    death_at: float | None = None
    tele_lock: bool = False
    client_move: bool = False  # 由客户端上报位置（服务器只做校验）
    quit: bool = False  # 主动退出了本局：无论结果如何都没有奖励
    bomb_tokens: float = BOMB_BURST  # 放炸弹请求额度
    move_budget: float = 0.0  # 可移动距离额度（按速度随时间累积）
    fix: int = 0  # 位置被服务器拒绝的次数（客户端据此回滚）
    one_way: float = 0.05  # 客户端上报的单程延迟（秒，用于命中延迟补偿）
    pending_hit: tuple | None = None  # (判定时刻, 火焰来源) 等待延迟补偿窗口结束再确认
    ai: Any = None
    speed_bonus: float = 0.0  # AI 专属速度加成（难 +3%）
    bomb_style: str = ""  # 当前生效的炸弹特效（纯画面，范围 / 威力 / 时间与普通炸弹完全一样）
    items: list = field(default_factory=lambda: [""] * ITEM_SLOTS)  # 道具栏（"" = 空格）
    # 道具效果剩余时间（≤ 0 表示没有生效；从 -1 开始，移动校验对「刚结束」留 0.5 秒网络延迟余量）
    ishield_t: float = -1.0  # 无敌盾牌
    boots_t: float = -1.0  # 超级跑鞋
    ghost_t: float = -1.0  # 透明人
    wings_t: float = -1.0  # 腾飞之翼
    streak: int = 0  # 当前连杀（被泡泡包住就清零；不在游戏中显示，结算时折算点数加成）
    deaths: int = 0
    respawn_t: float = 0.0  # 复活赛：距离复活还剩几秒（> 0 表示正在等待复活）


@dataclass
class Bomb:
    id: int
    owner: str
    skin: int
    x: int
    y: int
    px: float
    py: float
    fuse: float
    range: int
    slide: tuple[int, int] | None = None
    tgt: tuple[int, int] | None = None
    barrel: bool = False  # 油桶引发的爆炸
    style: str = ""  # 炸弹特效（商店购买：poison / water / gold），只影响画面


@dataclass
class Flame:
    t: float
    mask: int
    owner: str
    style: str = ""  # 来自哪种炸弹特效（只影响画面）


class Game:
    def __init__(
        self,
        map_id: str,
        mode: str,
        lives: int = 1,  # 兼容旧接口，已不使用
        players: list[dict] | None = None,
        broadcast: Callable[[dict], None] | None = None,
        on_end: Callable[[dict], None] | None = None,
        on_anomaly: Callable[[str, str], None] | None = None,  # (玩家 ID, 'move' / 'bomb')
        rng: random.Random | None = None,
        round_time: float = ROUND_TIME,
        shrink: bool = True,  # 最后 60 秒是否缩圈（房间可选）
        items: bool = True,  # 是否掉落道具（房间可选）
        net_rate: int = NET_RATE,  # 状态广播频率（同步 Hz）
        revive: bool = False,  # 复活赛：被淘汰 3 秒后复活，时间到按击倒 / 得分排名
    ) -> None:
        players = players or []
        self.rng = rng or random.Random()
        self.gid = uuid.uuid4().hex[:12]  # 本局唯一 ID（重连时用来判断是否同一局）
        self.mode = "team" if mode == "team" else "ffa"
        self.broadcast = broadcast or (lambda msg: None)
        self.on_end = on_end or (lambda result: None)
        self.on_anomaly = on_anomaly or (lambda pid, kind: None)
        self.round_time = round_time
        self.revive = bool(revive)
        self.shrink = bool(shrink) and not self.revive  # 复活赛不缩圈（出生点在四角，会被墙封住）
        self.items_on = bool(items)
        self.net_rate = max(NET_RATE_MIN, min(NET_RATE_MAX, int(net_rate)))
        self._last_key = 0  # 上次下发完整地图（关键帧）的帧号
        self.sd_time = min(SD_TIME, round_time) if self.shrink else 0.0

        m = build_map(map_id, self.rng)
        self.map_id = m.id
        self.theme = m.theme
        self.W, self.H = m.w, m.h
        self.floor = m.floor
        self.blocks = m.blocks
        self.tele = m.tele
        self.has_ice = "i" in self.floor
        # 地图机关
        self.mech = m.mech
        self.gates = [i for i, f in enumerate(self.floor) if f in ("w", "u")]
        self.gate_rise: set[int] = set()  # 等待升起（格子里有人 / 炸弹时先不升）
        self.gate_t = MECH_DELAY + GATE_PERIOD
        self.gate_warned = False
        self.gate_flip = False  # False：下次升起 'u' 组（开局落下的那组）；True：下次升起 'w' 组
        self.pads = [i for i, f in enumerate(self.floor) if f == "s"]
        self.vents = [i for i, f in enumerate(self.floor) if f == "f"]
        self.regrow: dict[int, float] = {}
        self.hazards: list[list] = []  # [剩余秒数, x, y, 威力]：已预警、即将爆炸的机关火焰
        self.mech_t = MECH_DELAY

        self.spawn_points = list(m.spawns)
        spawns = self._assign_spawns(m.spawns, players)
        self.players: list[Player] = []
        for i, pl in enumerate(players):
            sx, sy = spawns[i]
            self.players.append(
                Player(
                    id=pl["id"],
                    name=pl["name"],
                    skin=int(pl.get("skin", 0)),
                    hat=int(pl.get("hat", 0)),
                    team=int(pl.get("team", 0)) if self.mode == "team" else i,
                    is_bot=bool(pl.get("is_bot")),
                    x=sx,
                    y=sy,
                    ai=bot.create(self.rng, pl.get("ai")) if pl.get("is_bot") else None,
                    level=int(pl.get("level", 0) or 0),
                    avatar=pl.get("avatar") if isinstance(pl.get("avatar"), str) else None,
                    bomb_style=pl.get("bomb") if pl.get("bomb") in BOMB_STYLES else "",
                )
            )
        self._by_id = {p.id: p for p in self.players}
        if not self.items_on:
            for p in self.players:
                p.max_bombs, p.range = FIXED_BOMBS, FIXED_RANGE
        self.airdrop_t: float | None = None
        for p in self.players:
            if p.ai is not None:
                p.speed_bonus = p.ai.prof.speed_bonus

        self.bombs: list[Bomb] = []
        self.next_bomb_id = 1
        self.flames: dict[int, Flame] = {}
        self.powerups: dict[int, str] = {}
        self.item_claims: dict[int, str] = {}  # 道具格 → 决定去捡它的「中等」AI
        self.events: list[dict] = []
        self.reveal: list[int] = []

        # 开局先「等待玩家连接」：所有真人加载完场景并回报后才开始倒计时（延迟大 / 加载慢时不会错过开场）
        self.phase = "wait"
        self.waiting: set[str] = {p.id for p in self.players if not p.is_bot}
        self.wait_left = WAIT_MAX
        self.countdown = COUNTDOWN
        self.time_left = round_time
        self.elapsed = 0.0
        self.tick_no = 0
        self.sd_started = False
        self.sd_order = self._build_spiral()
        self.sd_rank = {c: k for k, c in enumerate(self.sd_order)}  # 格子在缩圈顺序中的位置（AI 用来提前往里走）
        self.sd_index = 0
        self.sd_timer = 0.0
        self.sd_interval = (self.sd_time * 0.8) / max(1, len(self.sd_order))
        self.end_timer = 0.0
        self.result: dict | None = None
        self._blocks_sent: str | None = None
        self._t0 = time.monotonic()
        self._task: asyncio.Task | None = None

    # ---------- 辅助 ----------
    def idx(self, x: float, y: float) -> int:
        return rnd(y) * self.W + rnd(x)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.W and 0 <= y < self.H

    def player(self, pid: str | None) -> Player | None:
        return self._by_id.get(pid) if pid else None

    def bomb_at(self, x: int, y: int) -> Bomb | None:
        for b in self.bombs:
            if (b.x == x and b.y == y) or (b.tgt is not None and b.tgt == (x, y)):
                return b
        return None

    def can_enter(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        if self.blocks[y * self.W + x] in BLOCKING:
            return False
        return self.bomb_at(x, y) is None

    def can_pass(self, p: Player, x: int, y: int) -> bool:
        """这名玩家能否走进格子：腾飞之翼期间（含网络延迟的余量）无视炸弹。"""
        if p.wings_t > -0.5:
            return self.in_bounds(x, y) and self.blocks[y * self.W + x] not in BLOCKING
        return self.can_enter(x, y)

    def active_bombs(self, p: Player) -> int:
        return sum(1 for b in self.bombs if b.owner == p.id and not b.barrel)

    @staticmethod
    def speed_level(p: Player) -> int:
        """生效的速度等级：超级跑鞋期间直接提到 +50%。"""
        return BOOTS_SPEED_LV if p.boots_t > 0 else p.speed_lv

    def player_speed(self, p: Player) -> float:
        s = BASE_SPEED * (1 + SPEED_STEP * self.speed_level(p)) * (1 + p.speed_bonus)
        if self.floor[self.idx(p.x, p.y)] == "i":
            s *= ICE_MULT
        if p.trapped > 0:
            s *= TRAP_SPEED
        return s

    def is_free(self, p: Player) -> bool:
        return p.alive and p.trapped <= 0

    def _assign_spawns(self, spawns: list[tuple[int, int]], players: list[dict]) -> list[tuple[int, int]]:
        if self.mode == "team":
            left = sorted(spawns, key=lambda s: (s[0], s[1]))
            right = list(reversed(left))
            used: set[tuple[int, int]] = set()
            out = []
            for pl in players:
                lst = right if int(pl.get("team", 0)) == 1 else left
                s = next(s for s in lst if s not in used)
                used.add(s)
                out.append(s)
            return out
        # 个人模式：最远点采样，让玩家尽量分散
        pool = list(spawns)
        chosen = [pool.pop(self.rng.randrange(len(pool)))] if pool else []
        while len(chosen) < len(players) and pool:
            best = max(
                range(len(pool)),
                key=lambda k: min(abs(c[0] - pool[k][0]) + abs(c[1] - pool[k][1]) for c in chosen),
            )
            chosen.append(pool.pop(best))
        self.rng.shuffle(chosen)
        return chosen

    def _build_spiral(self) -> list[int]:
        order: list[int] = []
        W, H = self.W, self.H
        for r in range(4):
            x0, x1, y0, y1 = 1 + r, W - 2 - r, 1 + r, H - 2 - r
            order += [y0 * W + x for x in range(x0, x1 + 1)]
            order += [y * W + x1 for y in range(y0 + 1, y1 + 1)]
            order += [y1 * W + x for x in range(x1 - 1, x0 - 1, -1)]
            order += [y * W + x0 for y in range(y1 - 1, y0, -1)]
        return order

    def server_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            task, self._task = self._task, None
            if task is not asyncio.current_task():
                task.cancel()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_t = loop.time()
        try:
            while self._task is not None:
                try:
                    finished = self.tick()
                except Exception:  # noqa: BLE001 - 保护游戏循环
                    import traceback

                    traceback.print_exc()
                    finished = False
                if finished:
                    self._task = None
                    self.on_end(self.result)
                    return
                next_t += DT
                delay = next_t - loop.time()
                if delay < -0.25:  # 落后太多就重新对齐，避免追帧
                    next_t = loop.time()
                    delay = 0
                await asyncio.sleep(max(0.0, delay))
        except asyncio.CancelledError:
            pass

    def set_input(self, pid: str, *, direction: Any = "__keep__", bomb: bool = False, seq: Any = None) -> None:
        """客户端输入。输入一到达就生效（不等下一帧），并记录序号用于预测校正。"""
        p = self.player(pid)
        if p is None or not p.alive or p.is_bot:
            return
        if direction != "__keep__":
            p.in_dir = direction if direction in DIRS else None
            if p.in_dir:
                p.tap_dir = p.in_dir
        if bomb:
            if p.bomb_tokens < 1.0:
                self.on_anomaly(p.id, "bomb")  # 放炸弹间隔异常：丢弃本次请求
            else:
                p.bomb_tokens -= 1.0
                p.in_bomb = True
        if isinstance(seq, int) and seq > p.ack:
            p.ack = seq

    def forfeit(self, pid: str) -> None:
        """主动退出：判负出局（已阵亡后再退出也一样），本局不获得任何奖励。"""
        self.waiting.discard(pid)
        p = self.player(pid)
        if p is None or self.phase == "end":
            return
        p.quit = True
        if p.alive:
            self.die(p, None)

    def player_loaded(self, pid: str) -> None:
        """玩家的场景加载完成（或断线 / 退出，不再等他）。"""
        self.waiting.discard(pid)

    def tick(self) -> bool:
        """推进一帧；返回 True 表示本局已结束。"""
        self.tick_no += 1
        if self.phase == "wait":
            self.wait_left -= DT
            if not self.waiting or self.wait_left <= 0:
                self.waiting.clear()
                self.phase = "countdown"
        elif self.phase == "countdown":
            self.countdown -= DT
            if self.countdown <= 0:
                self.phase = "play"
                for p in self.players:
                    p.invuln = INVULN_START
                self.events.append({"k": "go"})
        elif self.phase == "play":
            self.update(DT)
        elif self.phase == "end":
            self._update_flames(DT)
            self.end_timer -= DT
            if self.end_timer <= 0:
                self.broadcast(self.snapshot())
                self.events = []
                return True
        # 60Hz 模拟、按同步 Hz 广播：事件在两次广播之间累积。
        # 按比例累积决定哪一帧广播（例如 25Hz 不能整除 60 帧），平均频率正好是设定值
        due = (self.tick_no * self.net_rate) // TICK_RATE != ((self.tick_no - 1) * self.net_rate) // TICK_RATE
        if due or any(e["k"] in ("go", "end") for e in self.events):
            self.broadcast(self.snapshot())
            self.events = []
        return False

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self.time_left -= dt

        if self.revive:
            for p in self.players:
                if not p.alive and p.respawn_t > 0:
                    p.respawn_t -= dt
                    if p.respawn_t <= 0:
                        self._respawn(p)

        for p in self.players:
            if p.alive and p.is_bot:
                bot.think(self, p, dt)

        for p in self.players:
            if not p.alive:
                continue
            if p.invuln > 0:
                p.invuln -= dt
            # 道具效果计时（减到 -1 为止：移动校验对刚结束的效果留一点网络延迟余量）
            p.ishield_t = max(-1.0, p.ishield_t - dt)
            p.boots_t = max(-1.0, p.boots_t - dt)
            p.ghost_t = max(-1.0, p.ghost_t - dt)
            p.wings_t = max(-1.0, p.wings_t - dt)
            if p.in_bomb:
                p.in_bomb = False
                if p.trapped <= 0:
                    self.place_bomb(p)
            if not p.is_bot:
                # 真人玩家的移动额度（客户端上报位置时消耗）
                cap = self.max_speed(p)
                p.move_budget = min(p.move_budget + cap * dt * MOVE_TOLERANCE, cap * MOVE_BURST + 0.2)
                p.bomb_tokens = min(BOMB_BURST, p.bomb_tokens + BOMB_RATE * dt)
            if not p.client_move:
                self._move_player(p, dt)

        for b in self.bombs:
            if b.slide:
                self._update_slide(b, dt)
            b.fuse -= dt
            if self.idx(b.px, b.py) in self.flames:
                b.fuse = min(b.fuse, 0)

        for _ in range(64):
            ready = [b for b in self.bombs if b.fuse <= 0]
            if not ready:
                break
            for b in ready:
                self.explode(b)

        self._update_mechanics(dt)
        self._update_airdrop(dt)

        for i in self.reveal:
            if self.items_on and self.rng.random() < DROP_CHANCE:
                self.powerups[i] = kind = pick_powerup(self.rng, self.items_on)
                if kind in ITEM_KINDS:
                    self._claim_item(i)
        self.reveal = []

        self._update_flames(dt)

        # 火焰命中（按身体覆盖区域判定）、道具拾取
        for p in self.players:
            if not p.alive:
                continue
            i = self.idx(p.x, p.y)
            if p.invuln <= 0 and p.trapped <= 0 and p.ishield_t <= 0:  # 无敌盾牌期间被炸到什么都不会发生
                f = self._flame_on_body(p)
                if not p.client_move:
                    if f:
                        self.hit(p, f.owner)
                elif p.pending_hit is None:
                    if f:
                        # 服务器看到的位置比玩家自己屏幕上的晚约一个单程延迟：
                        # 等这段时间内的位置上报到达，若届时已离开火焰则视为已躲开
                        p.pending_hit = (self.elapsed, f.owner)
                elif self.elapsed - p.pending_hit[0] >= min(HIT_GRACE_MAX, p.one_way + 1 / 30):
                    owner = p.pending_hit[1]
                    p.pending_hit = None
                    if f:
                        self.hit(p, f.owner or owner)
            else:
                p.pending_hit = None
            if self.is_free(p) and i in self.powerups:
                kind = self.powerups[i]
                if kind not in ITEM_KINDS:
                    self.apply_powerup(p, self.powerups.pop(i))
                elif "" in p.items:
                    # 道具放进第一个空格（所有人走上去都会捡起来）；道具栏满了捡不起来（留在地上）
                    p.items[p.items.index("")] = self.powerups.pop(i)
                    self.item_claims.pop(i, None)
                    self.events.append({"k": "pick", "id": p.id, "type": kind, "x": p.x, "y": p.y})

        self._update_traps(dt)

        if self.shrink and self.time_left <= self.sd_time:
            if not self.sd_started:
                self.sd_started = True
                self.events.append({"k": "sd"})
            self.sd_timer -= dt
            while self.sd_timer <= 0 and self.sd_index < len(self.sd_order):
                i = self.sd_order[self.sd_index]
                self.sd_index += 1
                if self.blocks[i] in HARD:
                    continue
                self.drop_wall(i)
                self.sd_timer += self.sd_interval

        self.check_end()

    def _update_traps(self, dt: float) -> None:
        """被困倒计时、队友救援、敌人击破。"""
        for p in self.players:
            if not p.alive or p.trapped <= 0:
                continue
            for o in self.players:
                if o is p or not self.is_free(o) or abs(o.x - p.x) + abs(o.y - p.y) > TOUCH_DIST:
                    continue
                if self.mode == "team" and o.team == p.team:
                    p.trapped = 0
                    p.invuln = INVULN_RESCUE
                    o.rescues += 1
                    self.events.append({"k": "rescue", "id": p.id, "by": o.id, "x": p.x, "y": p.y})
                else:
                    self._credit_kill(o)
                    self.events.append({"k": "pop", "id": p.id, "by": o.id, "x": p.x, "y": p.y})
                    self.die(p, o, counted=True)
                break
            if p.alive and p.trapped > 0:
                p.trapped -= dt
                if p.trapped <= 0:
                    p.trapped = 0
                    killer = self.player(p.trap_by)
                    if killer and killer is not p and (self.mode != "team" or killer.team != p.team):
                        self._credit_kill(killer)
                    self.die(p, killer, counted=True)

    @staticmethod
    def _credit_kill(o: Player) -> None:
        o.kills += 1
        o.streak += 1

    def _flame_on_body(self, p: Player) -> Flame | None:
        """返回覆盖角色身体（覆盖比例 ≥ HIT_OVERLAP）的火焰。"""
        best = None
        for tx in {math.floor(p.x), math.ceil(p.x)}:
            ox = max(0.0, min(p.x + BODY_HALF, tx + 0.5) - max(p.x - BODY_HALF, tx - 0.5)) / (2 * BODY_HALF)
            if ox <= 0:
                continue
            for ty in {math.floor(p.y), math.ceil(p.y)}:
                oy = max(0.0, min(p.y + BODY_HALF, ty + 0.5) - max(p.y - BODY_HALF, ty - 0.5)) / (2 * BODY_HALF)
                if ox * oy < HIT_OVERLAP or not self.in_bounds(tx, ty):
                    continue
                f = self.flames.get(ty * self.W + tx)
                if f:
                    best = f
        return best

    # ---------- 移动 ----------
    # ---------- 客户端移动校验 ----------
    def max_speed(self, p: Player) -> float:
        # 超级跑鞋刚结束时客户端可能还在用加速后的速度（网络延迟），额度按最高等级计算
        lv = BOOTS_SPEED_LV if p.boots_t > -0.5 else p.speed_lv
        s = BASE_SPEED * (1 + SPEED_STEP * lv) * (1 + p.speed_bonus)
        if self.has_ice:
            s *= ICE_MULT
        if p.trapped > 0:
            s *= TRAP_SPEED
        return s

    @staticmethod
    def _cells(x: float, y: float) -> list[tuple[int, int]]:
        """身体（1×1）覆盖的格子。"""
        xs = range(math.floor(x + 1e-4), math.ceil(x - 1e-4) + 1)
        ys = range(math.floor(y + 1e-4), math.ceil(y - 1e-4) + 1)
        return [(cx, cy) for cx in xs for cy in ys]

    def _segment_ok(self, p: Player, x0: float, y0: float, x1: float, y1: float, exempt: set) -> bool:
        n = max(1, math.ceil((abs(x1 - x0) + abs(y1 - y0)) / PATH_STEP))
        for k in range(1, n + 1):
            x, y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
            for c in self._cells(x, y):
                if c not in exempt and not self.can_pass(p, *c):
                    return False
        return True

    def _path_ok(self, p: Player, x: float, y: float) -> bool:
        """轴向移动：先横后竖或先竖后横，任一条路径不穿过障碍即可。
        起点已经覆盖的格子（例如脚下刚放的炸弹）不算阻挡。"""
        exempt = set(self._cells(p.x, p.y))
        return (self._segment_ok(p, p.x, p.y, x, p.y, exempt) and self._segment_ok(p, x, p.y, x, y, exempt)) or (
            self._segment_ok(p, p.x, p.y, p.x, y, exempt) and self._segment_ok(p, p.x, y, x, y, exempt)
        )

    def _tele_jump(self, p: Player, x: float, y: float) -> bool:
        i = self.idx(p.x, p.y)
        dest = self.tele.get(i)
        if dest is None or p.tele_lock:
            return False
        cx, cy = i % self.W, i // self.W
        dx, dy = dest % self.W, dest // self.W
        near = TELE_SNAP + 0.1
        return (abs(p.x - cx) <= near and abs(p.y - cy) <= near and abs(x - dx) <= near and abs(y - dy) <= near
                and not self.bomb_at(dx, dy))

    def client_move(self, pid: str, x: Any, y: Any, *, facing: Any = None, moving: Any = False,
                    kick: Any = None, seq: Any = None, epoch: Any = None, ping: Any = None) -> bool:
        """客户端上报的位置。合理则采用，不合理则拒绝（位置不变，fix+1 通知客户端回滚）。"""
        p = self.player(pid)
        if p is None or p.is_bot or not p.alive:
            return False
        if isinstance(seq, int) and seq > p.ack:
            p.ack = seq
        if isinstance(ping, (int, float)) and math.isfinite(ping):
            p.one_way = min(0.3, max(0.0, ping / 2000))
        if self.phase != "play":
            return False
        if isinstance(epoch, int) and epoch != p.fix:
            # 基于已被拒绝状态发出的旧上报（还在网络中飞行），直接丢弃，避免连锁回滚
            return False
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            return False
        if not p.client_move:
            p.client_move = True
            p.in_dir = p.tap_dir = None
        if facing in DIRS:
            p.facing = facing
        p.moving = bool(moving)
        if isinstance(kick, list) and len(kick) == 2:
            self._client_kick(p, kick)
        if (x, y) == (p.x, p.y):
            return True
        ok = math.isfinite(x) and math.isfinite(y) and 0 <= x <= self.W - 1 and 0 <= y <= self.H - 1
        if ok and self._tele_jump(p, x, y):
            self.events.append({"k": "tele", "id": p.id, "x": p.x, "y": p.y, "x2": round(x), "y2": round(y)})
            p.x, p.y = x, y
            p.tele_lock = True
            return True
        if ok:
            dist = abs(x - p.x) + abs(y - p.y)
            ok = dist <= p.move_budget + 1e-3 and self._path_ok(p, x, y)
        if not ok:
            p.fix += 1
            p.moving = False
            self.on_anomaly(p.id, "move")
            return False
        p.move_budget -= dist
        p.x, p.y = x, y
        if self.tele.get(self.idx(x, y)) is None:
            p.tele_lock = False
        return True

    def _client_kick(self, p: Player, cell: list) -> None:
        try:
            bx, by = int(cell[0]), int(cell[1])
        except (TypeError, ValueError):
            return
        if not p.kick or p.trapped > 0:
            return
        dx, dy = DIRS.get(p.facing, (0, 0))
        b = self.bomb_at(bx, by)
        if b is None or b.slide is not None or (b.x, b.y) != (bx, by):
            return
        if (rnd(p.x) + dx, rnd(p.y) + dy) != (bx, by) or abs(p.x - rnd(p.x)) + abs(p.y - rnd(p.y)) > 0.25:
            return
        b.slide = (dx, dy)
        self.events.append({"k": "kick", "x": bx, "y": by})

    def _move_player(self, p: Player, dt: float) -> None:
        """自由移动（像素级）：可以停在两格之间。
        沿主轴连续移动；进入新格子前检查前方格子；侧向偏离通道时自动“滑角”对齐（CORNER_ASSIST 以内）。"""
        dist = self.player_speed(p) * dt
        tap = p.tap_dir
        p.tap_dir = None
        p.moving = False
        for _ in range(8):
            if dist <= EPS:
                break
            held = p.in_dir or tap
            d = held
            if not d:
                d = CONVEYOR.get(self.floor[self.idx(p.x, p.y)])
            if not d:
                break
            if held:
                p.facing = held
            dx, dy = DIRS[d]
            horiz = dx != 0
            sgn = dx or dy
            m, q = (p.x, p.y) if horiz else (p.y, p.x)
            if not _is_int(m):
                # 两格之间：走到下一个格子中心线之前不会接触新格子
                t = math.ceil(m) if sgn > 0 else math.floor(m)
                step = min(dist, abs(t - m))
                m = float(t) if abs(t - m) - step < EPS else m + sgn * step
                dist -= step
            else:
                m = float(round(m))
                nm = int(m) + sgn
                lanes = [round(q)] if _is_int(q) else [math.floor(q), math.ceil(q)]
                cell = (lambda L: (nm, L)) if horiz else (lambda L: (L, nm))
                free = [L for L in lanes if self.can_pass(p, *cell(L))]
                if len(free) == len(lanes):
                    step = min(dist, 1.0)
                    m = float(nm) if 1.0 - step < EPS else m + sgn * step
                    dist -= step
                elif free:
                    # 滑角：只有一侧通道可走，侧向挪过去
                    L = free[0]
                    gap = abs(L - q)
                    if gap > CORNER_ASSIST:
                        break
                    step = min(dist, gap)
                    q = float(L) if gap - step < EPS else q + (1 if L > q else -1) * step
                    dist -= step
                else:
                    if len(lanes) == 1 and held == d and p.kick and p.trapped <= 0:
                        b = self.bomb_at(*cell(lanes[0]))
                        if b and b.slide is None and (b.x, b.y) == cell(lanes[0]):
                            b.slide = (dx, dy)
                            self.events.append({"k": "kick", "x": b.x, "y": b.y})
                    break
            if horiz:
                p.x, p.y = m, q
            else:
                p.x, p.y = q, m
            p.moving = True
            tap = None if p.in_dir else tap
            if p.is_bot and _is_int(p.x) and _is_int(p.y):
                # 机器人在格子中心做决定（与真人一样只能改变输入）
                p.x, p.y = float(round(p.x)), float(round(p.y))
                self._check_tele(p)
                bot.think(self, p, 0.0)
                if p.in_bomb:
                    p.in_bomb = False
                    if p.trapped <= 0:
                        self.place_bomb(p)
        self._check_tele(p)

    def _check_tele(self, p: Player) -> None:
        i = self.idx(p.x, p.y)
        dest = self.tele.get(i)
        if dest is None:
            p.tele_lock = False
            return
        cx, cy = i % self.W, i // self.W
        if p.tele_lock or abs(p.x - cx) > TELE_SNAP or abs(p.y - cy) > TELE_SNAP:
            return
        dx, dy = dest % self.W, dest // self.W
        if self.bomb_at(dx, dy):
            return
        self.events.append({"k": "tele", "id": p.id, "x": p.x, "y": p.y, "x2": dx, "y2": dy})
        p.x, p.y = float(dx), float(dy)
        p.tele_lock = True

    # ---------- 炸弹 ----------
    def place_bomb(self, p: Player) -> None:
        x, y = rnd(p.x), rnd(p.y)
        if self.active_bombs(p) >= p.max_bombs or self.bomb_at(x, y):
            return
        if self.blocks[y * self.W + x] not in WALKABLE_FOR_BOMB:
            return
        self.bombs.append(Bomb(self.next_bomb_id, p.id, p.skin, x, y, float(x), float(y), FUSE, p.range, style=p.bomb_style))
        self.next_bomb_id += 1
        self.events.append({"k": "place", "id": p.id, "x": x, "y": y, "st": p.bomb_style})

    def _bomb_can_enter(self, b: Bomb, x: int, y: int) -> bool:
        if not self.in_bounds(x, y) or self.blocks[y * self.W + x] not in WALKABLE_FOR_BOMB:
            return False
        other = self.bomb_at(x, y)
        if other is not None and other is not b:
            return False
        return not any(p.alive and rnd(p.x) == x and rnd(p.y) == y for p in self.players)

    def _update_slide(self, b: Bomb, dt: float) -> None:
        dist = KICK_SPEED * dt
        for _ in range(6):
            if dist <= 1e-6 or b.slide is None:
                break
            if b.tgt is None:
                nx, ny = b.x + b.slide[0], b.y + b.slide[1]
                if not self._bomb_can_enter(b, nx, ny):
                    b.slide = None
                    break
                b.tgt = (nx, ny)
            ddx, ddy = b.tgt[0] - b.px, b.tgt[1] - b.py
            rem = abs(ddx) + abs(ddy)
            if rem <= dist:
                b.x, b.y = b.tgt
                b.px, b.py = float(b.x), float(b.y)
                b.tgt = None
                dist -= rem
            else:
                b.px += _sign(ddx) * dist
                b.py += _sign(ddy) * dist
                dist = 0

    def blast_tiles(self, cx: float, cy: float, rng_: int) -> list[int]:
        """计算爆炸范围（不修改地图），供 AI 使用。"""
        cx, cy = rnd(cx), rnd(cy)
        out = [cy * self.W + cx]
        for d in DIR_LIST:
            dx, dy = DIRS[d]
            for r in range(1, rng_ + 1):
                x, y = cx + dx * r, cy + dy * r
                if not self.in_bounds(x, y):
                    break
                i = y * self.W + x
                blk = self.blocks[i]
                if blk in HARD:
                    break
                out.append(i)
                if blk in SOFT:
                    break
        return out

    def explode(self, b: Bomb) -> None:
        if b not in self.bombs:
            return
        self.bombs.remove(b)
        cx, cy = rnd(b.px), rnd(b.py)
        self.events.append({"k": "boom", "x": cx, "y": cy, "r": b.range, "barrel": b.barrel, "st": b.style})
        center_mask = CENTER_BIT
        for d in DIR_LIST:
            dx, dy = DIRS[d]
            for r in range(1, b.range + 1):
                x, y = cx + dx * r, cy + dy * r
                if not self.in_bounds(x, y):
                    break
                i = y * self.W + x
                blk = self.blocks[i]
                if blk in HARD:
                    break
                if r == 1:
                    center_mask |= BIT[d]
                mask = BIT[OPP[d]]
                stop = False
                if blk == "x":
                    self.blocks[i] = "."
                    self.reveal.append(i)
                    self.events.append({"k": "crate", "x": x, "y": y})
                    stop = True
                elif blk == "m":
                    self.blocks[i] = "x"  # 钢箱被打裂，变成普通木箱
                    self.events.append({"k": "steel", "x": x, "y": y})
                    stop = True
                elif blk == "g":
                    self.blocks[i] = "."
                    if self.items_on:
                        self.powerups[i] = _weighted(self.rng, CHEST_TABLE)  # 宝箱必出道具（关闭道具模式时什么都不掉）
                    self.events.append({"k": "chest", "x": x, "y": y})
                    stop = True
                elif blk == "e":
                    self.blocks[i] = "."
                    self.events.append({"k": "barrel", "x": x, "y": y})
                    self.bombs.append(
                        Bomb(self.next_bomb_id, b.owner, b.skin, x, y, float(x), float(y), 0.06, BARREL_RANGE, barrel=True)
                    )
                    self.next_bomb_id += 1
                    stop = True
                else:
                    if blk == "b":
                        self.blocks[i] = "."
                        self.events.append({"k": "bush", "x": x, "y": y})
                        if self.mech == "regrow":
                            self.regrow[i] = REGROW_TIME
                    for other in self.bombs:
                        if rnd(other.px) == x and rnd(other.py) == y:
                            other.fuse = min(other.fuse, 0.08)
                    if i in self.powerups:
                        del self.powerups[i]
                        self.events.append({"k": "burn", "x": x, "y": y})
                    if r < b.range:
                        mask |= BIT[d]
                self._add_flame(i, mask, b.owner, b.style)
                if stop:
                    break
        self._add_flame(cy * self.W + cx, center_mask, b.owner, b.style)

    def _add_flame(self, i: int, mask: int, owner: str, style: str = "") -> None:
        f = self.flames.get(i)
        if f:
            f.mask |= mask
            f.t = FLAME_TIME
            f.owner = owner
            f.style = style
        else:
            self.flames[i] = Flame(FLAME_TIME, mask, owner, style)

    def _update_flames(self, dt: float) -> None:
        for i in list(self.flames):
            f = self.flames[i]
            f.t -= dt
            if f.t <= 0:
                del self.flames[i]

    # ---------- 战斗 ----------
    def hit(self, p: Player, owner_id: str | None) -> None:
        if p.shield:
            p.shield = False
            p.invuln = 1.0
            self.events.append({"k": "shield", "id": p.id, "x": p.x, "y": p.y})
            return
        p.trapped = TRAP_TIME
        p.trap_by = owner_id
        p.streak = 0  # 被泡泡包住：连杀清零
        p.in_bomb = False
        self.events.append({"k": "trap", "id": p.id, "by": owner_id, "x": p.x, "y": p.y})

    def die(self, p: Player, killer: Player | None, counted: bool = False) -> None:
        if not p.alive:
            return
        p.alive = False
        p.trapped = 0
        p.death_at = self.elapsed
        p.moving = False
        p.in_dir = None
        p.deaths += 1
        p.streak = 0
        respawn = self.revive and self.phase == "play" and not p.quit
        self.events.append(
            {"k": "die", "id": p.id, "x": p.x, "y": p.y, "by": killer.id if killer and killer is not p else None,
             **({"rs": RESPAWN_TIME} if respawn else {})}
        )
        items = (
            ["bomb"] * (p.max_bombs - 1)
            + ["fire"] * max(0, p.range - START_RANGE)
            + ["speed"] * max(0, p.speed_lv)
            + (["kick"] if p.kick else [])
        )
        free = [
            i
            for i, blk in enumerate(self.blocks)
            if blk == "."
            and i not in self.powerups
            and i not in self.flames
            and i not in self.tele
            and not self.bomb_at(i % self.W, i // self.W)
        ]
        # 掉落：复活赛掉出身上全部能力道具，普通模式最多 4 个；道具栏里没用掉的道具都会掉出来。
        # 位置由服务器在全图空地中随机挑选。
        self.rng.shuffle(items)
        drops = ((items if respawn else items[:4]) + [it for it in p.items if it]) if self.items_on else []
        p.items = [""] * ITEM_SLOTS
        for it in drops:
            if not free:
                break
            i = free.pop(self.rng.randrange(len(free)))
            self.powerups[i] = it
            if it in ITEM_KINDS:
                self._claim_item(i)
        if respawn:
            # 能力回到初始值，3 秒后复活
            p.max_bombs, p.range = (1, START_RANGE) if self.items_on else (FIXED_BOMBS, FIXED_RANGE)
            p.speed_lv, p.kick, p.shield = 0, False, False
            p.ishield_t = p.boots_t = p.ghost_t = p.wings_t = -1.0
            p.respawn_t = RESPAWN_TIME

    def _claim_item(self, i: int) -> None:
        """道具掉出来时，离它最近的 AI 掷骰子：中等 50% 决定去捡（难总会去捡，简单从不捡）。"""
        x, y = i % self.W, i // self.W
        bots = [p for p in self.players if p.is_bot and self.is_free(p)]
        if not bots:
            return
        near = min(bots, key=lambda p: abs(p.x - x) + abs(p.y - y))
        if near.ai.prof.item_roll and self.rng.random() < near.ai.prof.item_roll:
            self.item_claims[i] = near.id

    def use_item(self, pid: str, slot: object) -> bool:
        """使用道具栏第 slot 格（0–5）的道具。针只能在被困时用；其他道具被困时不能用。"""
        p = self.player(pid)
        if p is None or not p.alive or self.phase != "play" or not isinstance(slot, int) or not 0 <= slot < ITEM_SLOTS:
            return False
        kind = p.items[slot]
        if not kind:
            return False
        if kind == "needle":
            if p.trapped <= 0:
                return False
            p.trapped = 0
            p.trap_by = None
            p.invuln = max(p.invuln, 1.0)  # 刚脱困的 1 秒内不会被残留的火焰再次困住
        elif p.trapped > 0:
            return False
        elif kind == "ishield":
            p.ishield_t = ISHIELD_TIME
        elif kind == "boots":
            p.boots_t = BOOTS_TIME
        elif kind == "ghost":
            p.ghost_t = GHOST_TIME
        elif kind == "wings":
            p.wings_t = WINGS_TIME
        p.items[slot] = ""
        self.events.append({"k": "use", "id": p.id, "it": kind, "x": p.x, "y": p.y})
        return True

    def apply_powerup(self, p: Player, kind: str) -> None:
        if kind == "bomb":
            p.max_bombs = min(MAX_BOMBS, p.max_bombs + 1)
        elif kind == "fire":
            p.range = min(MAX_RANGE, p.range + 1)
        elif kind == "max":  # 威力 +50%（向上取整）：3×3 → 5×5 → 7×7 → 11×11 → 13×13
            p.range = min(MAX_RANGE, math.ceil(p.range * 1.5))
        elif kind == "speed":
            p.speed_lv = min(MAX_SPEED_LV, p.speed_lv + 1)
        elif kind == "slow":
            p.speed_lv = max(MIN_SPEED_LV, p.speed_lv - 1)
        elif kind == "kick":
            p.kick = True
        elif kind == "shield":
            p.shield = True
        self.events.append({"k": "pick", "id": p.id, "type": kind, "x": p.x, "y": p.y})

    # ---------- 地图机关 ----------
    def _body_on(self, i: int) -> bool:
        x, y = i % self.W, i // self.W
        return any(p.alive and (x, y) in self._cells(p.x, p.y) for p in self.players)

    def _shrunk(self, i: int) -> bool:
        return self.sd_started and self.sd_rank.get(i, 1 << 30) < self.sd_index

    def _update_airdrop(self, dt: float) -> None:
        """道具模式：地图上已经没有能出道具的箱子、地上的道具也都被吃完后，每隔 30–80 秒（随机）空投一个道具。"""
        if not self.items_on or self.powerups or any(b in ("x", "m", "g") for b in self.blocks):
            self.airdrop_t = None
            return
        if self.airdrop_t is None:
            self.airdrop_t = self.rng.uniform(*AIRDROP_DELAY)
            return
        self.airdrop_t -= dt
        if self.airdrop_t > 0:
            return
        self.airdrop_t = None  # 被吃掉后重新计时
        free = [
            i for i, blk in enumerate(self.blocks)
            if blk in (".", "b") and i not in self.flames and i not in self.tele and self.floor[i] not in ("w", "u")
            and not self._shrunk(i) and not self.bomb_at(i % self.W, i // self.W)
        ]
        if not free:
            return
        i = self.rng.choice(free)
        kind = pick_powerup(self.rng, True)
        while kind == "slow":  # 空投不投减速鞋
            kind = pick_powerup(self.rng, True)
        self.powerups[i] = kind
        if kind in ITEM_KINDS:
            self._claim_item(i)
        self.events.append({"k": "supply", "x": i % self.W, "y": i // self.W})

    def _hazard(self, x: int, y: int, rng_: int) -> None:
        """预警一次机关爆炸：先在地上标出范围，HAZARD_WARN 秒后爆炸（不属于任何玩家）。"""
        self.hazards.append([HAZARD_WARN, x, y, rng_])
        self.events.append({"k": "warn", "c": self.blast_tiles(x, y, rng_), "t": HAZARD_WARN})

    def _update_mechanics(self, dt: float) -> None:
        # 已预警的机关爆炸
        for h in self.hazards:
            h[0] -= dt
        for h in [h for h in self.hazards if h[0] <= 0]:
            self.hazards.remove(h)
            _, x, y, r = h
            if self.blocks[y * self.W + x] == "#":
                continue  # 已被缩圈的墙覆盖
            b = Bomb(self.next_bomb_id, "", 0, x, y, float(x), float(y), 0.0, r, barrel=True)
            self.next_bomb_id += 1
            self.bombs.append(b)
            self.explode(b)

        # 樱花庭院：烧掉的草丛重新长出来
        for i in list(self.regrow):
            self.regrow[i] -= dt
            if self.regrow[i] > 0:
                continue
            x, y = i % self.W, i // self.W
            if self.blocks[i] != ".":
                del self.regrow[i]
            elif i in self.flames or i in self.powerups or self.bomb_at(x, y):
                self.regrow[i] = 1.0  # 有东西挡着：稍后再试
            else:
                del self.regrow[i]
                self.blocks[i] = "b"
                self.events.append({"k": "grow", "x": x, "y": y})

        # 极光冰川：两组冰墙闸门轮流升降
        if self.gates:
            self.gate_t -= dt
            up_next = [i for i in self.gates if (self.floor[i] == "u") != self.gate_flip]
            if self.gate_t <= GATE_WARN and not self.gate_warned:
                self.gate_warned = True
                self.events.append({"k": "warn", "c": [i for i in up_next if self.blocks[i] == "."], "t": GATE_WARN, "g": 1})
            if self.gate_t <= 0:
                self.gate_t += GATE_PERIOD
                self.gate_warned = False
                self.gate_flip = not self.gate_flip
                for i in self.gates:
                    if i in up_next:
                        self.gate_rise.add(i)
                    elif self.blocks[i] == "w":
                        self.blocks[i] = "#" if self._shrunk(i) else "."
                        self.gate_rise.discard(i)
                        self.events.append({"k": "gate", "x": i % self.W, "y": i // self.W, "up": 0})
            for i in list(self.gate_rise):
                x, y = i % self.W, i // self.W
                if self.blocks[i] != ".":
                    self.gate_rise.discard(i)
                elif not self._body_on(i) and not self.bomb_at(x, y) and i not in self.flames:
                    self.gate_rise.discard(i)
                    self.blocks[i] = "w"
                    if self.powerups.pop(i, None):
                        self.events.append({"k": "burn", "x": x, "y": y})
                    self.events.append({"k": "gate", "x": x, "y": y, "up": 1})

        if not (self.pads or self.vents or self.mech == "meteor"):
            return
        self.mech_t -= dt
        if self.mech_t > 0:
            return
        if self.pads:  # 星际空港：补给台空投（关闭道具模式时不空投）
            self.mech_t = SUPPLY_PERIOD
            for i in (self.pads if self.items_on else []):
                x, y = i % self.W, i // self.W
                if self.blocks[i] == "." and i not in self.powerups and not self.bomb_at(x, y):
                    kind = _weighted(self.rng, CHEST_TABLE)
                    if self.items_on and self.rng.random() < 0.3:
                        kind = self.rng.choice(ITEM_KINDS)
                    self.powerups[i] = kind
                    if kind in ITEM_KINDS:
                        self._claim_item(i)
                    self.events.append({"k": "supply", "x": x, "y": y})
        elif self.vents:  # 烈日斗兽场：火焰喷口
            self.mech_t = VENT_PERIOD
            for i in self.vents:
                if self.blocks[i] != "#":
                    self._hazard(i % self.W, i // self.W, VENT_RANGE)
        else:  # 火山孤岛：陨石
            self.mech_t = METEOR_PERIOD
            cand = [i for i, blk in enumerate(self.blocks) if blk in (".", "b", "x") and not self._shrunk(i)]
            # 一颗砸在随机一名玩家附近，其余随机落下
            alive = [p for p in self.players if p.alive]
            picks: list[int] = []
            if alive:
                t = self.rng.choice(alive)
                near = [i for i in cand if abs(i % self.W - rnd(t.x)) + abs(i // self.W - rnd(t.y)) <= 3]
                if near:
                    picks.append(self.rng.choice(near))
            while len(picks) < METEOR_COUNT and cand:
                i = self.rng.choice(cand)
                if i not in picks:
                    picks.append(i)
            for i in picks:
                self._hazard(i % self.W, i // self.W, METEOR_RANGE)

    def _respawn(self, p: Player) -> None:
        """复活赛：服务器在全图随机挑一个空格复活。复活后无敌 3 秒，所以不用避开炸弹 / 火焰；
        只要求是空地（不是传送门 / 闸门），且四周至少能走一步，不会被困在死角里。"""

        def open_cell(x: int, y: int) -> bool:
            return self.in_bounds(x, y) and self.blocks[y * self.W + x] in (".", "b") and not self.bomb_at(x, y)

        cand = [
            (i % self.W, i // self.W)
            for i, blk in enumerate(self.blocks)
            if blk in (".", "b") and i not in self.tele and self.floor[i] not in ("w", "u")
            and not self.bomb_at(i % self.W, i // self.W)
            and any(open_cell(i % self.W + dx, i // self.W + dy) for dx, dy in DIRS.values())
        ]
        if not cand:  # 几乎不会发生：退回出生点
            cand = list(self.spawn_points)
        x, y = self.rng.choice(cand)
        p.x, p.y = float(x), float(y)
        p.alive = True
        p.respawn_t = 0.0
        p.trapped = 0
        p.trap_by = None
        p.invuln = INVULN_RESPAWN
        p.death_at = None
        p.moving = False
        p.in_dir = p.tap_dir = None
        p.tele_lock = False
        p.pending_hit = None
        p.move_budget = 0.0
        p.fix += 1  # 让客户端立即同步到复活位置（并丢弃复活前还在路上的位置上报）
        self.events.append({"k": "respawn", "id": p.id, "x": x, "y": y})

    def drop_wall(self, i: int) -> None:
        self.blocks[i] = "#"
        self.powerups.pop(i, None)
        x, y = i % self.W, i // self.W
        self.bombs = [b for b in self.bombs if not (rnd(b.px) == x and rnd(b.py) == y)]
        self.events.append({"k": "wall", "x": x, "y": y})
        for p in self.players:
            if not p.alive:
                continue
            if rnd(p.x) == x and rnd(p.y) == y:
                self.die(p, None)

    def revive_score(self, p: Player) -> float:
        """复活赛个人得分：个人赛 = 击倒；团队赛 = 击倒 + 0.5 × 救援。"""
        return p.kills + (0.5 * p.rescues if self.mode == "team" else 0)

    def check_end(self) -> None:
        if self.phase != "play":
            return
        if self.revive:
            teams = {p.team for p in self.players if not p.quit}
            if len(teams) <= 1:  # 对手都退出了
                self.finish(next(iter(teams)) if teams else None)
            elif self.time_left <= 0:
                if self.mode == "team":
                    score: dict[int, float] = {}
                    for p in self.players:
                        if not p.quit:
                            score[p.team] = score.get(p.team, 0) + self.revive_score(p)
                    best = max(score.values())
                    top = [t for t, v in score.items() if v == best]
                    self.finish(top[0] if len(top) == 1 else None)
                else:
                    keys = sorted(((p.kills, -p.deaths), p.team) for p in self.players if not p.quit)
                    unique = len(keys) == 1 or keys[-1][0] != keys[-2][0]
                    self.finish(keys[-1][1] if unique and keys[-1][0][0] > 0 else None)
            return
        alive = [p for p in self.players if p.alive]
        teams = {p.team for p in alive}
        if len(teams) <= 1:
            self.finish(next(iter(teams)) if teams else None)
            return
        if self.time_left <= 0:
            # 时间到：比较每队仍然自由（未被困）的人数
            score: dict[int, int] = {}
            for p in alive:
                score[p.team] = score.get(p.team, 0) + (1 if p.trapped <= 0 else 0)
            best = max(score.values())
            top = [t for t, s in score.items() if s == best]
            self.finish(top[0] if len(top) == 1 and best > 0 else None)

    def finish(self, winner_team: int | None) -> None:
        self.phase = "end"
        self.end_timer = END_DELAY

        def won(p: Player) -> bool:
            return winner_team is not None and p.team == winner_team and not p.quit

        def key(p: Player):
            if p.quit:
                return (True, 2, 0, 0)  # 退出的玩家排在最后
            if self.revive:
                return (not won(p), 0, -self.revive_score(p), p.deaths)
            if p.alive:
                return (not won(p), 0, p.trapped > 0, -p.kills)
            return (not won(p), 1, -(p.death_at or 0), -p.kills)

        ranked = sorted(self.players, key=key)
        # 复活赛：按个人得分排前三名（得分 > 0）分别 +25% / +15% / +5% 点数
        rank_bonus: dict[str, int] = {}
        if self.revive:
            order = sorted((p for p in self.players if not p.quit and self.revive_score(p) > 0),
                           key=lambda p: (-self.revive_score(p), p.deaths))
            for p, b in zip(order, RANK_BONUS):
                rank_bonus[p.id] = b
        self.result = {
            "mode": self.mode,
            "revive": self.revive,
            "mapId": self.map_id,
            "draw": winner_team is None,
            "winnerTeam": winner_team,
            "duration": round(self.elapsed),
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "skin": p.skin,
                    "hat": p.hat,
                    "team": p.team,
                    "isBot": p.is_bot,
                    "kills": p.kills,
                    "rescues": p.rescues,
                    "alive": p.alive,
                    "place": k + 1,
                    "win": won(p),
                    "quit": p.quit,
                    "avatar": p.avatar,
                    "level": p.level,
                    "streak": p.streak,  # 结束时的连杀（结算时折算加成）
                    "deaths": p.deaths,
                    **({"score": self.revive_score(p), "rankBonus": rank_bonus.get(p.id, 0)} if self.revive else {}),
                }
                for k, p in enumerate(ranked)
            ],
        }
        self.events.append({"k": "end", "draw": winner_team is None, "winnerTeam": winner_team})

    # ---------- 网络 ----------
    def start_info(self, rejoin: bool = False) -> dict:
        """开局信息。rejoin=True 用于断线重连：附带当前地图方块与阶段，客户端据此完全按服务器状态重建。"""
        return {
            "t": "start",
            "gid": self.gid,
            "rejoin": rejoin,
            "phase": self.phase,
            "k": "".join(self.blocks),
            "mapId": self.map_id,
            "theme": self.theme,
            "w": self.W,
            "h": self.H,
            "floor": "".join(self.floor),
            "water": "".join("~" if b == "~" else "." for b in self.blocks),
            "mode": self.mode,
            "revive": self.revive,
            "roundTime": self.round_time,
            "items": self.items_on,
            "sdTime": self.sd_time,
            "tickRate": TICK_RATE,
            "netRate": self.net_rate,
            "rules": {
                "baseSpeed": BASE_SPEED,
                "speedStep": SPEED_STEP,
                "iceMult": ICE_MULT,
                "cornerAssist": CORNER_ASSIST,
                "teleSnap": TELE_SNAP,
                "trapSpeed": TRAP_SPEED,
                "trapTime": TRAP_TIME,
            },
            "players": [
                {"id": p.id, "name": p.name, "skin": p.skin, "hat": p.hat, "team": p.team, "isBot": p.is_bot, "level": p.level, "avatar": p.avatar, "bomb": p.bomb_style}
                for p in self.players
            ],
        }

    def snapshot(self) -> dict:
        blocks = "".join(self.blocks)
        snap: dict[str, Any] = {
            "t": "s",
            "st": self.server_ms(),
            "tk": self.tick_no,
            "ph": self.phase,
            **({"wt": sorted(self.waiting), "wl": math.ceil(max(0.0, self.wait_left))} if self.phase == "wait" else {}),
            "cd": math.ceil(max(0.0, self.countdown)),
            "tl": max(0.0, round(self.time_left, 1)),
            "sd": 1 if self.sd_started else 0,
            "p": [
                {
                    "id": p.id,
                    "x": round(p.x, 4),
                    "y": round(p.y, 4),
                    "f": p.facing[0],
                    "a": 1 if p.alive else 0,
                    "tr": round(p.trapped, 1) if p.trapped > 0 else 0,
                    "iv": round(p.invuln, 1) if p.invuln > 0 else 0,
                    "sh": 1 if p.shield else 0,
                    "m": 1 if p.moving else 0,
                    "mb": p.max_bombs,
                    "r": p.range,
                    "s": self.speed_level(p),
                    "k": 1 if p.kick else 0,
                    "kl": p.kills,
                    "q": p.ack,
                    "fx": p.fix,
                    "tl": 1 if p.tele_lock else 0,
                    "it": ",".join(p.items),  # 道具栏 6 格
                    **({"rs": round(p.respawn_t, 1)} if p.respawn_t > 0 else {}),
                    **_effects(p),
                }
                for p in self.players
            ],
            "b": [[b.id, r3(b.px), r3(b.py), round(b.fuse / FUSE, 2), b.skin, b.owner, b.style] for b in self.bombs if not b.barrel],
            "f": [[i, f.mask, f.style] if f.style else [i, f.mask] for i, f in self.flames.items()],
            "u": [[i, t] for i, t in self.powerups.items()],
            "e": self.events,
        }
        # 地图只在变化时下发（另外每 2 秒一个关键帧）
        if blocks != self._blocks_sent or self.tick_no - self._last_key >= KEYFRAME_TICKS:
            snap["k"] = blocks
            self._blocks_sent = blocks
            self._last_key = self.tick_no
        return snap

    def blast_schedule(self, extra=None) -> list[list]:
        """所有已知炸弹（含连锁、油桶二次爆炸）的 [爆炸时刻, 覆盖格子, 炸弹所在格]。
        extra=(px,py,fuse,range) 或它的列表：假设再放下的炸弹。"""
        src = [(b.px, b.py, b.fuse, b.range) for b in self.bombs]
        src.extend((hx, hy, ht, hr) for ht, hx, hy, hr in self.hazards)  # 已预警的喷火 / 陨石
        if extra:
            src.extend(extra if isinstance(extra, list) else [extra])
        info = [[max(0.0, fu), self.blast_tiles(px, py, r), self.idx(px, py)] for px, py, fu, r in src]
        # 被炸到的油桶会二次爆炸
        for t, tiles, _ in list(info):
            for i in tiles:
                if self.blocks[i] == "e":
                    info.append([t, self.blast_tiles(i % self.W, i // self.W, BARREL_RANGE), i])
        for _ in range(3):
            for a in info:
                for c in info:
                    if a is not c and c[0] > a[0] and c[2] in a[1]:
                        c[0] = a[0]
        return info

    def flame_windows(self, extra=None) -> dict[int, list[tuple[float, float]]]:
        """每个格子将会（或正在）有火焰的时间段 [(开始, 结束)]（秒，相对现在）。高难度 AI 用它规划躲避路线。"""
        w: dict[int, list[tuple[float, float]]] = {}
        for i, f in self.flames.items():
            w.setdefault(i, []).append((0.0, f.t))
        for t, tiles, _ in self.blast_schedule(extra):
            for i in tiles:
                w.setdefault(i, []).append((t, t + FLAME_TIME))
        for i, eta in self.wall_eta().items():
            w.setdefault(i, []).append((eta, 1e9))  # 即将落墙：从落下那一刻起永远不能待
        return w

    def wall_eta(self, horizon: float = 8.0) -> dict[int, float]:
        """缩圈：接下来 horizon 秒内会落墙的格子 → 还剩几秒落下。"""
        out: dict[int, float] = {}
        if not self.shrink or self.time_left - 2 > self.sd_time:
            return out
        t = max(0.0, self.sd_timer) if self.sd_started else max(0.0, self.time_left - self.sd_time)
        for k in range(self.sd_index, len(self.sd_order)):
            if t > horizon:
                break
            i = self.sd_order[k]
            if self.blocks[i] in HARD:
                continue  # 本来就是墙：缩圈时跳过，不占时间
            out[i] = t
            t += self.sd_interval
        return out

    def danger_map(self, extra=None) -> list[float]:
        """每个格子距离被火焰覆盖的剩余秒数（inf 表示安全）。extra=(px,py,fuse,range)"""
        d = [INF] * (self.W * self.H)
        for i in self.flames:
            d[i] = 0.0
        info = self.blast_schedule(extra)
        for t, tiles, _ in info:
            for i in tiles:
                if t < d[i]:
                    d[i] = t
        for i, eta in self.wall_eta().items():
            d[i] = min(d[i], eta)
        return d


def _weighted(rng: random.Random, table: list[tuple[str, int]]) -> str:
    r = rng.random() * sum(w for _, w in table)
    for k, w in table:
        r -= w
        if r < 0:
            return k
    return table[-1][0]


def _effects(p: Player) -> dict:
    """正在生效的道具效果（剩余秒数，只发送生效中的）。"""
    out = {}
    for key, t in (("ish", p.ishield_t), ("bt", p.boots_t), ("gh", p.ghost_t), ("wg", p.wings_t)):
        if t > 0:
            out[key] = round(t, 1)
    return out


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)
