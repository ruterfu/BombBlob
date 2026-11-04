"""账户（游客 / GitHub）、一次性登录 token、战绩 —— PostgreSQL（asyncpg）。

账号来源 provider：
  * guest  —— 游客账号，可凭 8 位 ID 登录（仅在开启游客登录时）
  * github —— GitHub OAuth 账号，只能通过 GitHub 或一次性 token 登录，不能凭 ID 登录

账号 ID：8 位数字（例如 48213907），玩家可以凭 ID 在任何设备登录。

奖励：每局获得经验，获胜另得点数（见 reward_for），写入数据库。

登录 token 规则：
  * 首次游客登录：创建账号，签发一个登录 token（客户端保存在 localStorage）。
  * 再次访问：客户端提交该 token；服务器在同一事务里原子地把它标记为已使用，
    并签发一个新 token 返回。旧 token 再次使用会被拒绝（一个 token 只能用 1 次）。
  * 数据库只保存 token 的 SHA-256 哈希，不保存明文。
  * 登录成功后另发一个仅存于内存的会话 session，用于 WebSocket 连接 / 断线重连。
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import math
import uuid
import json
import os
import random
import re
import secrets
import time
import time

from pathlib import Path

import asyncpg

from . import i18n, names, secure

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/bombblob")
SKINS = 8
NAME_MAX = 8  # 名字最多 8 个字
BASE_HATS = 6  # 0–5：按等级免费解锁；6 起为商店装饰（cosmetics 表）
SESSION_TTL = 12 * 3600

# 数据库结构与等级初始数据的唯一来源：db/init.sql（可单独用 psql 执行，也会在启动时自动执行）
INIT_SQL = Path(__file__).resolve().parent.parent / "db" / "init.sql"


def schema_sql() -> str:
    return INIT_SQL.read_text("utf-8")


class TokenInvalid(Exception):
    """token 不存在或已被使用。"""


class UnknownId(Exception):
    """ID 不存在（或不是可凭 ID 登录的游客账号）。"""


class ProviderDisabled(Exception):
    """该账号类型的登录方式当前未开启。"""


# ---------- 等级与奖励 ----------
# 经验 —— 获胜：100 + 每次击倒 10 + 每次救援 10；失败（含平局）：同一算式的 15%
WIN_BASE_EXP = 100
KILL_EXP = 10
RESCUE_EXP = 10
LOSS_RATE = 0.15
MIN_LOSS_EXP = 5
# 点数（钻石）—— 获胜：10 + 每次击倒 4 + 每次救援 2；失败：同一算式的 15%–35%（随机浮动）
WIN_POINTS, KILL_POINTS, RESCUE_POINTS = 10, 4, 2
LOSS_POINTS_PCT = (15, 35)
# 点数加成（百分比直接相加，不相乘）：
#   连杀：获胜时，结束时的连杀数 × 5%（被泡泡包住清零），最多 +30%
#   复活赛排名：前三名 +25% / +15% / +5%
#   点数卡：×1.5 / ×2 / ×3 即 +50% / +100% / +200%
#   例：连杀 +30% 且有双倍点数卡 → 100% + 30% + 100% = 230%
STREAK_PCT, STREAK_MAX = 5, 30
# 商店功能性道具（更名卡 / 炸弹特效 / 加成卡）：db/store_item.json，按商品 ID 配置价格与时长，启动时读取。
#   更名卡：可叠加，每次改名消耗 1 张。
#   炸弹特效（纯画面）：同一时间只有一种生效，再次购买会覆盖之前的，有效期从购买时重新计算。
#   加成卡：对局获得的经验 / 点数 ×1.5 / ×2 / ×3。经验与点数各占一个位置：
#     再买同一倍率 → 在当前到期时间上顺延；买更高倍率 → 立即替换，从现在起重新计算；
#     有更高倍率生效中时不能买低倍率（boost_lower）。
# 物品不可用（显示「物品不可用」、不能购买）：price 为 -1、JSON 里缺少该 ID、格式不对，
# 或内容与 ID 对不上（例如 exp150 的 kind / pct 不是 exp / 150）。
STORE_ITEMS_FILE = Path(__file__).resolve().parent.parent / "db" / "store_item.json"
BOMB_STYLES = ("poison", "water", "gold")  # 毒弹 / 水弹 / 金弹（与 users_bomb_style_chk 一致）
# 加成卡 ID → (种类, 倍率百分比)；倍率与 users_*_boost_chk 一致
BOOST_IDS = {"exp150": ("exp", 150), "exp200": ("exp", 200), "exp300": ("exp", 300),
             "pts150": ("points", 150), "pts200": ("points", 200), "pts300": ("points", 300)}
UNAVAILABLE = -1


def load_store_items(path: Path = STORE_ITEMS_FILE) -> dict[str, dict]:
    """读取 store_item.json → {商品 ID: {"price": 价格或 None（不可用）, "days" / "hours": …}}。
    单个物品配置有问题只会让它不可用（并打印原因），不影响其他物品和服务器启动。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("顶层必须是对象")
    except (OSError, ValueError) as e:
        print(f"[store] 读取 {path.name} 失败（{e}），所有商店道具不可用")
        data = {}

    def pos_int(v: object, lo: int) -> int | None:
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= lo else None

    def parse(iid: str, want: dict) -> dict:
        e = data.get(iid)
        if not isinstance(e, dict):
            print(f"[store] {path.name} 缺少 {iid}，该物品不可用")
            return {"price": None}
        price = e.get("price")
        if price == UNAVAILABLE:
            return {"price": None}
        price = pos_int(price, 0)
        bad = price is None
        for k, v in want.items():  # 内容必须与 ID 对上
            if e.get(k) != v:
                bad = True
        out: dict = {"price": price}
        dur = {"bomb": "days", "boost": "hours"}.get(want.get("type", ""))  # 炸弹特效按天、加成卡按小时
        if dur:
            out[dur] = pos_int(e.get(dur), 1)
            bad = bad or out[dur] is None
        if bad:
            print(f"[store] {path.name} 中 {iid} 的配置与 ID 不符或格式不对，该物品不可用")
            out["price"] = None
        return out

    items = {"rename": parse("rename", {})}
    for st in BOMB_STYLES:
        items[st] = parse(st, {"type": "bomb"})
    for cid, (kind, pct) in BOOST_IDS.items():
        items[cid] = {**parse(cid, {"type": "boost", "kind": kind, "pct": pct}), "kind": kind, "pct": pct}
    for k in data:
        if not k.startswith("_") and k not in items:
            print(f"[store] {path.name} 中的 {k} 不是已知商品，已忽略")
    return items


STORE_ITEMS = load_store_items()


def item_price(iid: str) -> int | None:
    """商品价格；None 表示物品不可用。"""
    e = STORE_ITEMS.get(iid)
    return e["price"] if e else None


RENAME_CARD_PRICE = item_price("rename")  # None = 不可用

# 等级曲线：第 n 级升到 n+1 级需要 100 + 50*(n-1) 经验；levels 表存 1–50 级，之后按同一曲线无限延伸
MAX_LEVEL = 50  # levels 表的行数（不是上限）
TIER_MIN_LEVEL = (1, 5, 10, 15, 20, 30, 40)  # 新兵 / 青铜 / 白银 / 黄金 / 铂金 / 钻石 / 大师
# 头饰解锁等级（索引对应 HATS：0 无 / 1 战术头带 / 2 王冠 / 3 耳机 / 4 犄角 / 5 鸭舌帽）
DEFAULT_HAT_UNLOCK = {0: 1, 1: 2, 3: 3, 4: 5, 5: 8, 2: 12}


def default_level_table() -> list[tuple[int, int, int, int]]:
    """[(level, exp_required, tier, unlock_hat)]：写入 levels 表的初始数据（unlock_hat 0 = 该级不解锁头饰）。"""
    rows = []
    cum = 0
    hat_at = {lv: h for h, lv in DEFAULT_HAT_UNLOCK.items() if lv > 1}
    for lv in range(1, MAX_LEVEL + 1):
        if lv > 1:
            cum += 100 + 50 * (lv - 2)
        tier = max(i for i, m in enumerate(TIER_MIN_LEVEL) if lv >= m)
        rows.append((lv, cum, tier, hat_at.get(lv, 0)))
    return rows


# 运行时的等级表（启动时从数据库 levels 表加载）
LEVEL_EXP: list[int] = [r[1] for r in default_level_table()]  # 索引 = level - 1
LEVEL_TIER: list[int] = [r[2] for r in default_level_table()]
HAT_UNLOCK: dict[int, int] = dict(DEFAULT_HAT_UNLOCK)


# 经验 → 等级（数据库函数 bb_level，见 db/init.sql；表内命中 levels_exp 索引，超出部分按公式计算）
LEVEL_SQL = "bb_level({exp})"


def _beyond(rest: int, d: int) -> int:
    """表外延伸：最后一级之后第 k 级所需经验为 d + 50k，返回剩余经验能再升几级。"""
    m = int((-(d - 25) + math.sqrt((d - 25) ** 2 + 100 * rest)) / 50)
    while 25 * (m + 1) ** 2 + (d - 25) * (m + 1) <= rest:
        m += 1
    while m > 0 and 25 * m * m + (d - 25) * m > rest:
        m -= 1
    return m


def level_of(exp: int) -> int:
    lo, hi = 0, len(LEVEL_EXP) - 1
    while lo < hi:  # 二分：最后一个 exp_required <= exp
        mid = (lo + hi + 1) // 2
        if LEVEL_EXP[mid] <= exp:
            lo = mid
        else:
            hi = mid - 1
    lv = lo + 1
    if lv == len(LEVEL_EXP):
        last = LEVEL_EXP[-1]
        d = (last - LEVEL_EXP[-2] if len(LEVEL_EXP) > 1 else 50) + 50
        lv += _beyond(exp - last, d)
    return lv


def level_exp(lv: int) -> int:
    """达到 lv 级所需的累计经验（含表外延伸）。"""
    n = len(LEVEL_EXP)
    if lv <= n:
        return LEVEL_EXP[max(0, lv - 1)]
    d = (LEVEL_EXP[-1] - LEVEL_EXP[-2] if n > 1 else 50) + 50
    m = lv - n
    return LEVEL_EXP[-1] + 25 * m * m + (d - 25) * m


def points_for(win: bool, kills: int, rescues: int = 0, loss_pct: int | None = None) -> int:
    """基础点数（不含加成）。失败时按 loss_pct%（默认在 15%–35% 之间随机）。"""
    full = WIN_POINTS + KILL_POINTS * kills + RESCUE_POINTS * rescues
    if win:
        return full
    if loss_pct is None:
        loss_pct = random.randint(*LOSS_POINTS_PCT)
    return round(full * loss_pct / 100)


def reward_for(win: bool, kills: int, rescues: int = 0, place: int = 99, loss_pct: int | None = None) -> tuple[int, int]:
    """返回基础 (经验, 点数)，不含连杀 / 排名 / 加成卡。"""
    full = WIN_BASE_EXP + KILL_EXP * kills + RESCUE_EXP * rescues
    if win:
        return full, points_for(True, kills, rescues)
    return max(MIN_LOSS_EXP, round(full * LOSS_RATE)), points_for(False, kills, rescues, loss_pct)


def streak_bonus(win: bool, streak: int) -> int:
    """连杀加成（%）：只有获胜才有，每连杀 1 人 +5%，最多 +30%。"""
    return min(STREAK_MAX, STREAK_PCT * max(0, int(streak))) if win else 0


# 商店装饰目录（启动时从 cosmetics 表加载）：id -> {"code", "level", "price"}
SHOP: dict[int, dict] = {}


def hat_count() -> int:
    return max([BASE_HATS - 1, *SHOP.keys()]) + 1


def hat_allowed(hat: int, level: int, owned: object = ()) -> bool:
    """基础头饰按等级解锁；商店装饰必须已购买。"""
    if hat in SHOP:
        return hat in owned
    return 0 <= hat < BASE_HATS and level >= HAT_UNLOCK.get(hat, 1)


def hats_in_levels(lo: int, hi: int) -> list[int]:
    """解锁等级在 [lo, hi] 之间的头饰（基础头饰 + 商店装饰），AI 按难度从中随机一个当形象。"""
    out = [h for h, lv in HAT_UNLOCK.items() if lo <= lv <= hi]
    out += [i for i, v in SHOP.items() if lo <= v["level"] <= hi]
    return sorted(out) or [0]


def shop_catalog() -> list[dict]:
    return [{"id": i, **v} for i, v in sorted(SHOP.items(), key=lambda kv: (kv[1]["level"], kv[0]))]


def level_table() -> list[dict]:
    """下发给客户端的等级表。"""
    unlock = {}
    for h, lv in HAT_UNLOCK.items():
        unlock.setdefault(lv, []).append(h)
    return [{"level": i + 1, "exp": LEVEL_EXP[i], "tier": LEVEL_TIER[i], "hats": unlock.get(i + 1, [])} for i in range(len(LEVEL_EXP))]


async def _load_levels(con) -> None:
    """把等级表与商店目录加载到内存。"""
    global LEVEL_EXP, LEVEL_TIER, HAT_UNLOCK, SHOP
    SHOP = {r["id"]: {"code": r["code"], "level": r["min_level"], "price": r["price"]}
            for r in await con.fetch("SELECT id, code, min_level, price FROM cosmetics ORDER BY id")}
    rows = await con.fetch("SELECT level, exp_required, tier, unlock_hat FROM levels ORDER BY level")
    LEVEL_EXP = [r["exp_required"] for r in rows]
    LEVEL_TIER = [r["tier"] for r in rows]
    HAT_UNLOCK = {0: 1}
    for r in rows:
        if r["unlock_hat"]:  # 0 = 该级不解锁头饰
            HAT_UNLOCK[int(r["unlock_hat"])] = r["level"]
    # 等级规则变化时（校验值不同）才全量同步用户等级，平时启动不扫描 users
    digest = hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest()
    if await con.fetchval("SELECT value FROM meta WHERE key = 'levels_digest'") != digest:
        await con.execute(f"UPDATE users u SET level = {LEVEL_SQL.format(exp='u.exp')} WHERE u.level IS DISTINCT FROM {LEVEL_SQL.format(exp='u.exp')}")
        await con.execute(
            "INSERT INTO meta (key, value) VALUES ('levels_digest', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            digest,
        )


ID_DIGITS = "012356789"  # 账号 ID 不含数字 4


def new_user_id() -> str:
    """随机 8 位账号 ID：首位不为 0，且任何一位都不是 4（9^7 × 8 ≈ 3,800 万个可用 ID）。"""
    return secrets.choice(ID_DIGITS[1:]) + "".join(secrets.choice(ID_DIGITS) for _ in range(7))


def is_valid_id(uid: object) -> bool:
    return isinstance(uid, str) and len(uid) == 8 and uid.isdigit()


_pool: asyncpg.Pool | None = None
_users: dict[str, dict] = {}  # 内存缓存：id -> user（大厅、房间直接引用同一个 dict）


def cached_user(uid: str) -> dict | None:
    return _users.get(uid)
_sessions: dict[str, "_Session"] = {}  # 会话 ID -> 会话（含 AES 会话密钥）
_bg: set[asyncio.Task] = set()
_NAME_BAD = re.compile(r"[\x00-\x1f\x7f<>&\"'`]")


async def init(dsn: str | None = None, retries: int = 30) -> None:
    """连接数据库并建表。Docker 中数据库可能稍后才就绪，因此会重试。"""
    global _pool
    for attempt in range(retries):
        try:
            _pool = await asyncpg.create_pool(
                dsn or os.environ.get("DATABASE_URL", DATABASE_URL),
                min_size=2, max_size=10,
                command_timeout=10,  # 单条语句超时，避免卡死游戏服务器
                max_inactive_connection_lifetime=300,
            )
            break
        except (OSError, asyncpg.PostgresError) as e:
            if attempt == retries - 1:
                raise
            print(f"[store] 等待数据库就绪…（{e.__class__.__name__}）")
            await asyncio.sleep(1)
    async with _pool.acquire() as con:
        # 多实例同时启动时用咨询锁串行化迁移
        async with con.transaction():
            await con.execute("SELECT pg_advisory_xact_lock(724519)")
            await con.execute(schema_sql())
            await _load_levels(con)
        # 清理 30 天前已使用的 token
    await cleanup_tokens()


async def cleanup_tokens(batch: int = 5000) -> int:
    """清理已使用超过 30 天 / 签发后 180 天仍未使用的 token。
    分批删除（每批一个短事务），避免长时间持锁；两个条件分别命中部分索引。"""
    assert _pool is not None
    total = 0
    # used_at = 'epoch'（1970-01-01）表示尚未使用（数据库不存 NULL）
    for cond in ("used_at > 'epoch' AND used_at < now() - interval '30 days'",
                 "used_at = 'epoch' AND created_at < now() - interval '180 days'"):
        while True:
            n = int((await _pool.execute(
                f"DELETE FROM login_tokens WHERE ctid = ANY(ARRAY(SELECT ctid FROM login_tokens WHERE {cond} LIMIT {int(batch)}))"
            )).split()[-1])
            total += n
            if n < batch:
                break
    return total


async def close() -> None:
    global _pool
    if _bg:
        await asyncio.gather(*_bg, return_exceptions=True)
    if _pool is not None:
        await _pool.close()
        _pool = None
    _users.clear()
    _sessions.clear()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sanitize_name(name: object) -> str:
    s = _NAME_BAD.sub("", str(name or ""))
    return re.sub(r"\s+", " ", s).strip()[:NAME_MAX]


def _clamp(v: object, hi: int) -> int | None:
    try:
        n = int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return n if 0 <= n < hi else None


def _row_to_user(row: asyncpg.Record) -> dict:
    uid = row["id"]
    u = _users.get(uid)
    data = {
        "id": uid,
        "name": row["name"],
        "skin": row["skin"],
        "hat": row["hat"],
        "exp": row["exp"],
        "points": row["points"],
        "renameCards": row["rename_cards"],
        "hasCharacter": row["has_character"],
        "provider": row["provider"],
        # 数据库里没有值时存 ''，对外仍用 null 表示「没有」
        "githubLogin": row["github_login"] or None,
        "avatar": row["avatar_url"] or None,
        "lang": row["lang"] or None,
        "bombStyle": row["bomb_style"],
        "bombUntil": _ms(row["bomb_until"]),
        "expBoost": row["exp_boost"], "expBoostUntil": _ms(row["exp_boost_until"]),
        "pointsBoost": row["points_boost"], "pointsBoostUntil": _ms(row["points_boost_until"]),
        "stats": {"games": row["games"], "wins": row["wins"], "kills": row["kills"]},
    }
    if u is None:
        _users[uid] = data
        return data
    u.update(data)
    return u


def public_user(u: dict) -> dict:
    return {
        "id": u["id"], "name": u["name"], "skin": u["skin"], "hat": u["hat"],
        "exp": u["exp"], "points": u.get("points", 0), "renameCards": u.get("renameCards", 0), "hasCharacter": u.get("hasCharacter", True), "level": level_of(u["exp"]),
        "stats": dict(u["stats"]), "hatUnlock": HAT_UNLOCK, "items": sorted(u.get("items", ())),
        "provider": u.get("provider", "guest"), "githubLogin": u.get("githubLogin"), "avatar": u.get("avatar"),
        "lang": u.get("lang"),
        # 炸弹特效：只在有效期内返回（过期后自动恢复普通火焰）
        "bomb": {"style": active_bomb(u), "until": u.get("bombUntil", 0) if active_bomb(u) else 0},
        # 加成卡：只返回生效中的 {"pct": 150, "until": 毫秒}
        "boosts": {k: {"pct": active_boost(u, k), "until": u.get(k + "BoostUntil", 0)} for k in ("exp", "points") if active_boost(u, k) > 100},
    }


class _Session:
    """内存会话：AES-128 会话密钥即唯一凭证，会话 ID 由密钥派生（见 secure.py）。"""

    __slots__ = ("uid", "key", "expires", "conns")

    def __init__(self, uid: str, key: bytes) -> None:
        self.uid, self.key, self.expires, self.conns = uid, key, time.time() + SESSION_TTL, 0


def _new_session(uid: str) -> str:
    now = time.time()
    for k in [k for k, v in _sessions.items() if v.expires < now]:
        del _sessions[k]
    sid, key = secure.new_session_key()
    _sessions[sid] = _Session(uid, key)
    return sid


def _session(sid: object) -> "_Session | None":
    if not sid:
        return None
    s = _sessions.get(str(sid))
    if s is None or s.expires < time.time():
        _sessions.pop(str(sid), None)
        return None
    s.expires = time.time() + SESSION_TTL
    return s


def user_by_session(sid: object) -> dict | None:
    s = _session(sid)
    return _users.get(s.uid) if s else None


def session_key(sid: object) -> bytes | None:
    s = _session(sid)
    return s.key if s else None


def next_conn(sid: object) -> int:
    """为该会话的新 WebSocket 连接分配连接号（参与 IV 构造，保证同一密钥下 IV 不重复）。"""
    s = _session(sid)
    if s is None:
        raise KeyError(sid)
    s.conns += 1
    return s.conns


async def guest_login(
    name: object = None, skin: object = None, hat: object = None, token: object = None, uid: object = None,
    allowed: frozenset[str] = frozenset({"guest", "github"}), lang: object = None,
) -> tuple[dict, str, str, bool]:
    """返回 (user, 新 token, session, 是否新建账号)。

    * uid：凭 8 位 ID 登录已有的游客账号（不存在或不是游客账号抛 UnknownId）。
    * token：消费一次性 token 恢复账号（无效或已使用抛 TokenInvalid）。
    * 都不给：新建游客账号，分配一个新的 8 位 ID。
    allowed：当前开启的账号类型；账号类型未开启时抛 ProviderDisabled（事务回滚，token 不会被消费）。
    lang：客户端当前语言；新账号或尚未设置语言的账号会记录它。
    """
    lg = i18n.normalize(lang) or ""  # 数据库不存 NULL：未知语言存 ''
    assert _pool is not None, "store.init() 未调用"
    clean, bad = names.check_name(name)
    clean = "" if bad else clean  # 不合规的名字直接改用默认名字
    sk, ht = _clamp(skin, SKINS), _clamp(hat, hat_count())
    new_token = secrets.token_hex(32)
    created = False
    async with _pool.acquire() as con, con.transaction():
        if uid is not None:
            uid = str(uid).strip()
            prov = await con.fetchval("SELECT provider FROM users WHERE id = $1", uid) if is_valid_id(uid) else None
            if prov != "guest":
                raise UnknownId()
            if "guest" not in allowed:
                raise ProviderDisabled()
            await con.execute("UPDATE users SET last_seen = now(), lang = CASE WHEN lang = '' THEN $2 ELSE lang END WHERE id = $1", uid, lg)
        elif token:
            # 原子地消费 token：并发的两个请求只有一个能成功
            uid = await con.fetchval(
                "UPDATE login_tokens SET used_at = now() WHERE token_hash = $1 AND used_at = 'epoch' RETURNING user_id",
                _hash(str(token)),
            )
            if uid is None:
                raise TokenInvalid()
            if await con.fetchval("SELECT provider FROM users WHERE id = $1", uid) not in allowed:
                raise ProviderDisabled()
            await con.execute(
                """UPDATE users SET skin = COALESCE($2, skin),
                   hat = COALESCE($3, hat), lang = CASE WHEN lang = '' THEN $4 ELSE lang END, last_seen = now() WHERE id = $1""",
                uid, sk,
                ht if ht is not None and hat_allowed(
                    ht, level_of(await con.fetchval("SELECT exp FROM users WHERE id = $1", uid)), await _owned(con, uid)) else None,
                lg,
            )
        else:
            created = True
            while True:  # 随机分配一个未被占用的 8 位 ID
                uid = new_user_id()
                ok = await con.fetchval(
                    """INSERT INTO users (id, name, skin, hat, lang, has_character) VALUES ($1, $2, $3, $4, $5, FALSE)
                       ON CONFLICT (id) DO NOTHING RETURNING true""",
                    uid,
                    clean or i18n.guest_name(lg, uid[-4:]),
                    sk if sk is not None else random.randrange(SKINS),
                    ht if ht is not None and hat_allowed(ht, 1) else 0,
                    lg,
                )
                if ok:
                    break
        await con.execute("INSERT INTO login_tokens (token_hash, user_id) VALUES ($1, $2)", _hash(new_token), uid)
        row = await con.fetchrow("SELECT * FROM users WHERE id = $1", uid)
        items = await _owned(con, uid)
    user = _row_to_user(row)
    user["items"] = items
    return user, new_token, _new_session(uid), created


async def github_login(gh_id: int, avatar: str | None = None, lang: object = None) -> tuple[dict, str, str, bool]:
    """GitHub 账号登录：按 GitHub 用户 ID 查找或创建账号，只额外保存头像地址（不保存用户名），签发一次性 token 与会话。"""
    assert _pool is not None, "store.init() 未调用"
    new_token = secrets.token_hex(32)
    created = False
    lg = i18n.normalize(lang) or ""  # 数据库不存 NULL
    avatar = avatar or ""
    async with _pool.acquire() as con, con.transaction():
        uid = await con.fetchval("SELECT id FROM users WHERE github_id = $1", int(gh_id))
        if uid:
            # 每次登录刷新头像（用户可能在 GitHub 换了头像）
            await con.execute(
                "UPDATE users SET github_login = '', avatar_url = $2, lang = CASE WHEN lang = '' THEN $3 ELSE lang END, last_seen = now() WHERE id = $1",
                uid, avatar, lg,
            )
        else:
            created = True
            while True:
                uid = new_user_id()
                ok = await con.fetchval(
                    """INSERT INTO users (id, name, skin, hat, provider, github_id, avatar_url, lang, has_character)
                       VALUES ($1, $2, $3, 0, 'github', $4, $5, $6, FALSE) ON CONFLICT (id) DO NOTHING RETURNING true""",
                    uid, i18n.player_name(lg, uid[-4:]), random.randrange(SKINS), int(gh_id), avatar, lg,
                )
                if ok:
                    break
        await con.execute("INSERT INTO login_tokens (token_hash, user_id) VALUES ($1, $2)", _hash(new_token), uid)
        row = await con.fetchrow("SELECT * FROM users WHERE id = $1", uid)
        items = await _owned(con, uid)
    user = _row_to_user(row)
    user["items"] = items
    return user, new_token, _new_session(uid), created


async def _owned(con, uid: str) -> set[int]:
    """已拥有的装饰（user_items 主键前缀扫描）。"""
    return {r["item_id"] for r in await con.fetch("SELECT item_id FROM user_items WHERE user_id = $1", uid)}


class ShopError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def _buy_bomb(u: dict, style: str) -> dict:
    """购买炸弹特效：扣点数并覆盖当前特效，有效期 = 现在 + days 天（并发安全：点数条件写在 UPDATE 里）。"""
    assert _pool is not None
    price = item_price(style)
    if price is None:
        raise ShopError("item_unavailable")
    days = STORE_ITEMS[style]["days"]
    if u.get("points", 0) < price:
        raise ShopError("item_points")
    async with _pool.acquire() as con, con.transaction():
        row = await con.fetchrow(
            """UPDATE users SET points = points - $2, bomb_style = $3, bomb_until = now() + make_interval(days => $4)
               WHERE id = $1 AND points >= $2 RETURNING points, bomb_style, bomb_until""",
            u["id"], price, style, days,
        )
        if row is None:
            raise ShopError("item_points")
        await con.execute(
            "INSERT INTO bomb_purchases (user_id, style, price_paid, expires_at) VALUES ($1, $2, $3, $4)",
            u["id"], style, price, row["bomb_until"],
        )
    u["points"] = row["points"]
    u["bombStyle"], u["bombUntil"] = row["bomb_style"], _ms(row["bomb_until"])
    return u


def _ms(ts) -> int:
    """时间 → 毫秒时间戳（'epoch' 即 0 表示没有）。"""
    return int(ts.timestamp() * 1000) if ts is not None else 0


def active_bomb(u: dict | None) -> str:
    """当前生效的炸弹特效；过期或没买返回 ''（普通火焰）。"""
    if not u or u.get("bombStyle") not in BOMB_STYLES:
        return ""
    return u["bombStyle"] if u.get("bombUntil", 0) > time.time() * 1000 else ""


def active_boost(u: dict | None, kind: str) -> int:
    """当前生效的加成倍率（百分比）；没有或已过期返回 100。kind = 'exp' / 'points'。"""
    if not u:
        return 100
    pct = u.get(kind + "Boost", 100)
    return pct if pct in (150, 200, 300) and u.get(kind + "BoostUntil", 0) > time.time() * 1000 else 100


def boosted(amount: int, pct: int) -> int:
    return amount * pct // 100 if pct > 100 else amount


def boost_shop() -> dict:
    """price 为 None 表示物品不可用。"""
    return {"cards": [{"id": cid, "kind": STORE_ITEMS[cid]["kind"], "pct": STORE_ITEMS[cid]["pct"],
                       "price": STORE_ITEMS[cid]["price"], "hours": STORE_ITEMS[cid].get("hours")} for cid in BOOST_IDS]}


async def _buy_boost(u: dict, item: str) -> dict:
    """购买加成卡：同一倍率顺延，更高倍率替换（从现在起重新计算）；有更高倍率生效中时不能买低倍率。
    点数与「没有更高倍率生效」两个条件都写在 UPDATE 里（并发安全）。"""
    assert _pool is not None
    kind, pct = BOOST_IDS[item]
    price = item_price(item)
    if price is None:
        raise ShopError("item_unavailable")
    hours = STORE_ITEMS[item]["hours"]
    if active_boost(u, kind) > pct:
        raise ShopError("boost_lower")  # 已有更高倍率生效中：买低倍率会把它替换掉，不允许
    if u.get("points", 0) < price:
        raise ShopError("item_points")
    col = "exp_boost" if kind == "exp" else "points_boost"
    async with _pool.acquire() as con, con.transaction():
        row = await con.fetchrow(
            f"""UPDATE users SET points = points - $2,
                   {col}_until = CASE WHEN {col} = $3 AND {col}_until > now() THEN {col}_until ELSE now() END
                                 + make_interval(hours => $4),
                   {col} = $3
               WHERE id = $1 AND points >= $2 AND NOT ({col} > $3 AND {col}_until > now())
               RETURNING points, {col} AS pct, {col}_until AS until""",
            u["id"], price, pct, hours,
        )
        if row is None:
            # 区分失败原因：点数不够，还是（并发购买后）已有更高倍率生效
            cur = await con.fetchrow(f"SELECT points, {col} AS pct, {col}_until > now() AS live FROM users WHERE id = $1", u["id"])
            raise ShopError("boost_lower" if cur and cur["live"] and cur["pct"] > pct else "item_points")
        await con.execute(
            "INSERT INTO boost_purchases (user_id, kind, pct, price_paid, expires_at) VALUES ($1, $2, $3, $4, $5)",
            u["id"], kind, pct, price, row["until"],
        )
    u["points"] = row["points"]
    u[kind + "Boost"], u[kind + "BoostUntil"] = row["pct"], _ms(row["until"])
    return u


def bomb_shop() -> dict:
    """price 为 None 表示物品不可用。"""
    return {"styles": [{"id": st, "price": STORE_ITEMS[st]["price"], "days": STORE_ITEMS[st].get("days")} for st in BOMB_STYLES]}


async def buy_item(u: dict, item: object) -> dict:
    """购买装饰：在一个事务里检查等级、扣点数、记录拥有，成功后自动装备。
    并发安全：points >= price 条件写在 UPDATE 里，主键冲突防止重复购买。"""
    assert _pool is not None
    if item in BOMB_STYLES:
        return await _buy_bomb(u, str(item))
    if isinstance(item, str) and item in BOOST_IDS:
        return await _buy_boost(u, item)
    if item == "rename":
        if RENAME_CARD_PRICE is None:
            raise ShopError("item_unavailable")
        if u.get("points", 0) < RENAME_CARD_PRICE:
            raise ShopError("item_points")
        row = await _pool.fetchrow(
            """UPDATE users SET points = points - $2, rename_cards = rename_cards + 1
               WHERE id = $1 AND points >= $2 RETURNING points, rename_cards""",
            u["id"], RENAME_CARD_PRICE,
        )
        if row is None:
            raise ShopError("item_points")
        u["points"], u["renameCards"] = row["points"], row["rename_cards"]
        return u
    try:
        iid = int(item)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ShopError("item_unknown")
    meta = SHOP.get(iid)
    if meta is None:
        raise ShopError("item_unknown")
    if iid in u.get("items", ()):
        raise ShopError("item_owned")
    if level_of(u["exp"]) < meta["level"]:
        raise ShopError("item_level")
    if u.get("points", 0) < meta["price"]:
        raise ShopError("item_points")
    async with _pool.acquire() as con, con.transaction():
        ok = await con.fetchval(
            """INSERT INTO user_items (user_id, item_id, price_paid) VALUES ($1, $2, $3)
               ON CONFLICT (user_id, item_id) DO NOTHING RETURNING true""",
            u["id"], iid, meta["price"],
        )
        if not ok:
            raise ShopError("item_owned")
        row = await con.fetchrow(
            f"""UPDATE users SET points = points - $2, hat = $3
                WHERE id = $1 AND points >= $2 AND {LEVEL_SQL.format(exp='exp')} >= $4 RETURNING points""",
            u["id"], meta["price"], iid, meta["level"],
        )
        if row is None:
            raise ShopError("item_points")  # 抛异常 → 事务回滚，拥有记录也撤销
    u["points"] = row["points"]
    u.setdefault("items", set()).add(iid)
    u["hat"] = iid
    return u


async def create_character(u: dict, name: object, skin: object, hat: object) -> dict:
    """新账号创建角色：设置名字、颜色、头饰（只能执行一次；创建时取名免费，之后改名需要改名卡）。"""
    assert _pool is not None
    if u.get("hasCharacter", True):
        raise ShopError("character_exists")
    clean, err = names.check_name(name)
    if err:
        raise ShopError(err)
    sk = _clamp(skin, SKINS)
    ht = _clamp(hat, hat_count())
    sk = u["skin"] if sk is None else sk
    ht = ht if ht is not None and hat_allowed(ht, level_of(u["exp"]), u.get("items", ())) else 0
    row = await _pool.fetchrow(
        """UPDATE users SET name = $2, skin = $3, hat = $4, has_character = TRUE
           WHERE id = $1 AND NOT has_character RETURNING id""",
        u["id"], clean, sk, ht,
    )
    if row is None:
        raise ShopError("character_exists")
    u.update(name=clean, skin=sk, hat=ht, hasCharacter=True)
    return u


async def rename(u: dict, name: object) -> dict:
    """使用 1 张更名卡改名：扣卡与改名在同一条 UPDATE 中完成（没有卡则不会改名），并记录改名历史。"""
    assert _pool is not None
    clean, err = names.check_name(name)
    if err:
        raise ShopError(err)
    if clean == u["name"]:
        raise ShopError("name_same")
    if u.get("renameCards", 0) <= 0:
        raise ShopError("rename_no_card")
    async with _pool.acquire() as con, con.transaction():
        row = await con.fetchrow(
            """UPDATE users u SET name = $2, rename_cards = u.rename_cards - 1
               FROM (SELECT name FROM users WHERE id = $1 FOR UPDATE) old
               WHERE u.id = $1 AND u.rename_cards > 0 RETURNING old.name AS old_name, u.rename_cards""",
            u["id"], clean,
        )
        if row is None:
            raise ShopError("rename_no_card")
        await con.execute("INSERT INTO name_changes (user_id, old_name, new_name) VALUES ($1, $2, $3)",
                          u["id"], row["old_name"], clean)
    u["name"], u["renameCards"] = clean, row["rename_cards"]
    return u


RETRYABLE = (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, asyncpg.DeadlockDetectedError,
             asyncpg.SerializationError, OSError, asyncio.TimeoutError)


async def _with_retry(factory, attempts: int = 3) -> None:
    """执行写库操作，连接 / 死锁 / 超时类错误自动重试（指数退避）。"""
    for i in range(attempts):
        try:
            return await factory()
        except RETRYABLE as e:
            if i == attempts - 1:
                raise
            print(f"[store] 写入失败，{0.5 * 2 ** i:.1f}s 后重试：{e!r}")
            await asyncio.sleep(0.5 * 2 ** i)


def _spawn(factory) -> None:
    """后台写库（不阻塞游戏循环）。factory 每次调用返回一个新的协程，便于重试。"""
    task = asyncio.get_running_loop().create_task(_with_retry(factory))
    _bg.add(task)
    task.add_done_callback(_bg.discard)
    task.add_done_callback(_report)


def _report(t: asyncio.Task) -> None:
    if not t.cancelled() and t.exception() is not None:
        print(f"[store] background error: {t.exception()!r}")


def update_profile(u: dict, name: object = None, skin: object = None, hat: object = None, lang: object = None) -> dict:
    """修改外观 / 语言。名字不能在这里改（需要使用更名卡，见 rename）。"""
    lg = i18n.normalize(lang)
    if lg:
        u["lang"] = lg
    sk, ht = _clamp(skin, SKINS), _clamp(hat, hat_count())
    if sk is not None:
        u["skin"] = sk
    if ht is not None and hat_allowed(ht, level_of(u["exp"]), u.get("items", ())):  # 未解锁 / 未购买的头饰不能装备
        u["hat"] = ht
    _spawn(functools.partial(_save_profile, u["id"], u["name"], u["skin"], u["hat"], u.get("lang")))
    return u


async def _save_profile(uid: str, name: str, skin: int, hat: int, lang: str | None) -> None:
    assert _pool is not None
    await _pool.execute("UPDATE users SET name=$2, skin=$3, hat=$4, lang=$5 WHERE id=$1", uid, name, skin, hat, lang or "")


def record_match(result: dict) -> None:
    """记录一局结果：计算奖励（写回 result 供客户端展示），更新真人战绩并保存对局。"""
    result.setdefault("matchKey", uuid.uuid4().hex)
    humans = []
    for p in result["players"]:
        # 机器人、主动退出的玩家：没有任何奖励
        none = p["isBot"] or p.get("quit")
        loss_pct = None if none or p["win"] else random.randint(*LOSS_POINTS_PCT)
        exp, points = (0, 0) if none else reward_for(p["win"], p["kills"], p.get("rescues", 0), p["place"], loss_pct)
        u = None if p["isBot"] else _users.get(p["id"])
        # 加成卡（按结算时刻是否在有效期内）
        eb, pb = active_boost(u, "exp"), active_boost(u, "points")
        exp = boosted(exp, eb)
        # 点数加成：连杀 + 复活赛排名 + 点数卡，百分比直接相加
        bonus = {"streak": streak_bonus(p["win"], p.get("streak", 0)), "rank": int(p.get("rankBonus", 0) or 0), "card": pb - 100}
        points = points * (100 + sum(bonus.values())) // 100
        p["exp"], p["points"] = exp, points
        if loss_pct is not None:
            p["lossPct"] = loss_pct
        if eb > 100 and exp:
            p["expBoost"] = eb
        if points and any(bonus.values()):
            p["bonus"] = {k: v for k, v in bonus.items() if v}
            p["pointsPct"] = 100 + sum(bonus.values())
        if p["isBot"]:
            continue
        humans.append(p)
        if u:
            u["stats"]["games"] += 1
            u["stats"]["wins"] += 1 if p["win"] else 0
            u["stats"]["kills"] += 0 if p.get("quit") else int(p["kills"])
            before = level_of(u["exp"])
            p["prevExp"] = u["exp"]
            u["exp"] += exp
            u["points"] = u.get("points", 0) + points
            p["totalExp"] = u["exp"]
            p["level"] = level_of(u["exp"])
            p["levelUp"] = p["level"] > before
            p["unlocked"] = [h for h, lv in HAT_UNLOCK.items() if before < lv <= p["level"]]
            p["shopUnlocked"] = [i for i, m in SHOP.items() if before < m["level"] <= p["level"]]
        else:
            p["level"] = 1
    _spawn(functools.partial(_save_match, result, humans))


def _no_null(v: object, key: str = "") -> object:
    """写进 JSONB 前把 null 换掉：winnerTeam → -1（0 是红队），其他 → ''。"""
    if v is None:
        return -1 if key == "winnerTeam" else ""
    if isinstance(v, dict):
        return {k: _no_null(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [_no_null(x) for x in v]
    return v


async def _save_match(result: dict, humans: list[dict]) -> None:
    """单个事务内写入对局、玩家战绩与用户统计。match_key 保证重试时不会重复结算。"""
    assert _pool is not None
    async with _pool.acquire() as con, con.transaction():
        match_id = await con.fetchval(
            """INSERT INTO matches (match_key, map_id, mode, duration, winner_team, result)
               VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (match_key) WHERE match_key <> '' DO NOTHING RETURNING id""",
            result["matchKey"], result["mapId"], result["mode"], int(result["duration"]),
            -1 if result["winnerTeam"] is None else int(result["winnerTeam"]),  # -1 = 没有获胜队伍（0 是红队）
            json.dumps(_no_null(result), ensure_ascii=False),
        )
        if match_id is None:
            return  # 已经写入过（上一次提交成功但确认丢失）
        # 按主键顺序更新，避免并发结算时互相死锁
        for p in sorted(humans, key=lambda x: x["id"]):
            row = await con.fetchrow(
                f"""UPDATE users SET games = games + 1, wins = wins + $2, kills = kills + $3,
                       exp = exp + $4, points = points + $5, level = {LEVEL_SQL.format(exp='users.exp + $4')}
                    WHERE id = $1 RETURNING exp, points, level""",
                p["id"], 1 if p["win"] else 0, 0 if p.get("quit") else int(p["kills"]), p["exp"], p["points"],
            )
            if row is None:
                continue
            u = _users.get(p["id"])
            if u:  # 以数据库为准刷新缓存
                u["exp"], u["points"] = row["exp"], row["points"]
            await con.execute(
                """INSERT INTO match_players (match_id, user_id, place, win, kills, rescues, exp_gained, points_gained, level_after)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                match_id, p["id"], p["place"], bool(p["win"]), int(p["kills"]), int(p.get("rescues", 0)),
                p["exp"], p["points"], row["level"],
            )


async def leaderboard(limit: int = 20) -> list[dict]:
    """排行榜：命中 users_leaderboard 部分覆盖索引（仅索引扫描，无排序）。"""
    assert _pool is not None
    rows = await _pool.fetch(
        """SELECT id, name, skin, hat, exp, level, avatar_url, games, wins, kills FROM users
           WHERE games > 0 ORDER BY wins DESC, kills DESC, games ASC, id ASC LIMIT $1""",
        max(1, min(100, int(limit))),
    )
    return [
        {"id": r["id"], "name": r["name"], "skin": r["skin"], "hat": r["hat"],
         "exp": r["exp"], "level": r["level"], "avatar": r["avatar_url"] or None,
         "stats": {"games": r["games"], "wins": r["wins"], "kills": r["kills"]}}
        for r in rows
    ]


async def match_history(uid: str, limit: int = 30) -> list[dict]:
    """对战记录：最近的对局（命中 match_players_user_recent 索引，再按主键取对局）。
    包括和谁一起玩、自己的胜负 / 名次、获得的经验与点数。"""
    assert _pool is not None
    rows = await _pool.fetch(
        """SELECT mp.match_id, mp.place, mp.win, mp.kills, mp.rescues, mp.exp_gained, mp.points_gained, mp.level_after,
                  m.map_id, m.mode, m.duration, m.winner_team, m.created_at, m.result
           FROM match_players mp JOIN matches m ON m.id = mp.match_id
           WHERE mp.user_id = $1 ORDER BY mp.match_id DESC LIMIT $2""",
        uid, max(1, min(50, int(limit))),
    )
    out = []
    for r in rows:
        res = json.loads(r["result"]) if isinstance(r["result"], str) else r["result"]
        players = [
            {k: p.get(k) for k in ("id", "name", "isBot", "team", "win", "place", "kills", "rescues", "skin", "hat", "avatar", "quit", "level")}
            for p in res.get("players", [])
        ]
        me = next((p for p in players if p["id"] == uid), {})
        out.append({
            "id": r["match_id"], "at": r["created_at"].isoformat(), "mapId": r["map_id"], "mode": r["mode"],
            "duration": r["duration"], "draw": bool(res.get("draw")), "win": r["win"], "quit": bool(me.get("quit")),
            "place": r["place"], "kills": r["kills"], "rescues": r["rescues"],
            "exp": r["exp_gained"], "points": r["points_gained"], "level": r["level_after"],
            "players": [{**p, "id": None if p["isBot"] else p["id"], "avatar": p.get("avatar") or None, "me": p["id"] == uid}
                        for p in players],
        })
    return out


async def recent_matches(uid: str, limit: int = 20) -> list[dict]:
    """个人最近战绩：命中 match_players_user_recent 索引。"""
    assert _pool is not None
    rows = await _pool.fetch(
        """SELECT mp.match_id, mp.place, mp.win, mp.kills, mp.rescues, mp.exp_gained, mp.points_gained, mp.level_after,
                  m.map_id, m.mode, m.created_at
           FROM match_players mp JOIN matches m ON m.id = mp.match_id
           WHERE mp.user_id = $1 ORDER BY mp.match_id DESC LIMIT $2""",
        uid, max(1, min(100, int(limit))),
    )
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]
