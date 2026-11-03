"""大厅、房间、聊天与 WebSocket 消息路由。"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

from aiohttp import web

from . import anticheat, i18n, secure, store, textrule
from .bot import LEVEL_BAND
from .bot import level_of as bot_level
from .game import Game
from .maps import MAP_IDS, get_map, map_summaries

BOT_NAMES = ["疾风", "赤焰", "幽影", "雷霆", "寒霜", "猎鹰", "夜枭", "铁卫", "游侠", "暴君"]
MAX_ROOMS = 200
MAX_PLAYERS = 6  # 每个房间最多 6 人（真人 + 机器人）
LEAVE_GRACE = 10.0  # 在房间（未开局）里断线后保留的秒数，超时自动离开


def clean_text(s: object, n: int) -> str:
    """文本在入口处已按全局规则清理（无空白、只有中文 / 英文字母 / 数字），这里只截断长度。"""
    return s[:n] if isinstance(s, str) else ""


ROUND_MINUTES = (3, 5, 10)  # 可选的时间限制（分钟）


def bot_hat(level: str) -> int:
    """按 AI 难度随机一个对应等级段的头饰。"""
    return random.choice(store.hats_in_levels(*LEVEL_BAND[level]))


def clamp_int(v: object, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def dumps(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))


class Client:
    """一个 WebSocket 连接。发送走独立队列，慢客户端不会阻塞游戏循环。"""

    MAX_QUEUE = 120

    def __init__(self, ws: web.WebSocketResponse, user: dict, channel: "secure.Channel") -> None:
        self.ws = ws
        self.user = user
        self.channel = channel  # AES-128-GCM 加密通道
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.last_chat = 0.0
        self.chat_burst = 0.0
        self.writer = asyncio.get_running_loop().create_task(self._writer())

    @property
    def id(self) -> str:
        return self.user["id"]

    def send_raw(self, data: str, droppable: bool = False) -> None:
        if self.ws.closed:
            return
        if droppable and self.queue.qsize() > self.MAX_QUEUE // 4:
            return  # 状态帧积压时直接丢弃，下一帧会覆盖
        if self.queue.qsize() >= self.MAX_QUEUE:
            return
        self.queue.put_nowait(data)

    def send(self, msg: dict) -> None:
        self.send_raw(dumps(msg))

    async def _writer(self) -> None:
        try:
            while True:
                data = await self.queue.get()
                if data is None or self.ws.closed:
                    return
                # 在真正发出时才加密：帧序号与发送顺序严格一致（被丢弃的状态帧不占序号）
                await self.ws.send_bytes(self.channel.seal(data))
        except (ConnectionError, RuntimeError, asyncio.CancelledError):
            return

    async def close(self, code: int = 1000, message: str = "") -> None:
        self.queue.put_nowait(None)
        if not self.ws.closed:
            await self.ws.close(code=code, message=message.encode())


class Room:
    def __init__(self, lobby: "Lobby", rid: str, name: str, settings: dict) -> None:
        self.lobby = lobby
        self.id = rid
        self.name = name
        self.host_id: str | None = None
        self.members: list[dict] = []  # {id,name,skin,hat,isBot,ready,team,connected}
        # items：是否掉落道具（针 / 无敌盾牌 / 超级跑鞋 / 透明人 / 腾飞之翼）；time：时间限制（分钟）
        self.settings = {"mapId": "meadow", "mode": "ffa", "lives": 2, "maxPlayers": MAX_PLAYERS, "shrink": True,
                         "items": True, "time": 10}
        self.apply_settings(settings)
        self.state = "waiting"
        self.password: str | None = None  # 房间密码（6 位数字 / 英文），只保存在内存
        self.game: Game | None = None
        self.bot_seq = 1

    def apply_settings(self, s: dict) -> None:
        map_id = s.get("mapId")
        if map_id == "random" or (isinstance(map_id, str) and get_map(map_id)):
            self.settings["mapId"] = map_id
        if s.get("mode") in ("ffa", "team"):
            self.settings["mode"] = s["mode"]
        if isinstance(s.get("shrink"), bool):
            self.settings["shrink"] = s["shrink"]
        if isinstance(s.get("items"), bool):
            self.settings["items"] = s["items"]
        if s.get("time") in ROUND_MINUTES:
            self.settings["time"] = s["time"]
        if s.get("lives") is not None:
            self.settings["lives"] = clamp_int(s["lives"], 1, 3, 2)

    def humans(self) -> list[dict]:
        return [m for m in self.members if not m["isBot"]]

    def member(self, mid: str) -> dict | None:
        return next((m for m in self.members if m["id"] == mid), None)

    def smaller_team(self) -> int:
        a = sum(1 for m in self.members if m["team"] == 0)
        b = sum(1 for m in self.members if m["team"] == 1)
        return 0 if a <= b else 1

    def add_user(self, user: dict) -> bool:
        if self.member(user["id"]):
            return True
        if self.state != "waiting" or len(self.members) >= MAX_PLAYERS:
            return False
        self.members.append(
            {
                "id": user["id"], "name": user["name"], "skin": user["skin"], "hat": user["hat"],
                "level": store.level_of(user.get("exp", 0)), "avatar": user.get("avatar"),
                "isBot": False, "ready": False, "team": self.smaller_team(), "connected": True,
            }
        )
        if not self.host_id:
            self.host_id = user["id"]
        return True

    def bot_limit(self) -> int:
        """机器人上限 = 6 - 真人数量（只有 1 个真人时最多 5 个机器人）。"""
        return MAX_PLAYERS - len(self.humans())

    def add_bot(self, level: object = None) -> bool:
        """添加 AI；level：easy / normal / hard（简单 / 中等 / 难）。"""
        bots = len(self.members) - len(self.humans())
        if self.state != "waiting" or len(self.members) >= MAX_PLAYERS or bots >= self.bot_limit():
            return False
        used = {m["name"] for m in self.members}
        name = next(("AI·" + n for n in BOT_NAMES if "AI·" + n not in used), f"AI·{self.bot_seq}")
        used_skins = {m["skin"] for m in self.members}
        free = [s for s in range(store.SKINS) if s not in used_skins] or list(range(store.SKINS))
        self.members.append(
            {
                "id": f"bot{self.id}x{self.bot_seq}", "name": name, "skin": random.choice(free),
                "hat": bot_hat(bot_level(level)), "isBot": True, "ready": True, "ai": bot_level(level),
                "team": self.smaller_team(), "connected": True,
            }
        )
        self.bot_seq += 1
        return True

    def set_bot_level(self, mid: object, level: object) -> bool:
        """房主修改 AI 难度：形象（头饰）随难度一起换。"""
        m = self.member(str(mid))
        if self.state != "waiting" or not m or not m.get("isBot"):
            return False
        lv = bot_level(level)
        if m.get("ai") != lv:
            m["ai"] = lv
            m["hat"] = bot_hat(lv)
        return True

    def remove_member(self, mid: str) -> None:
        m = self.member(mid)
        if not m:
            return
        self.members.remove(m)
        if self.game:
            self.game.forfeit(mid)
        if self.host_id == mid:
            humans = self.humans()
            nxt = next((h for h in humans if h["connected"]), humans[0] if humans else None)
            self.host_id = nxt["id"] if nxt else None

    def info(self) -> dict:
        return {
            "id": self.id, "name": self.name, "hostId": self.host_id, "state": self.state,
            "settings": self.settings, "members": [dict(m) for m in self.members],
            "botLimit": self.bot_limit(), "password": self.password,  # 只发给房间内的成员
        }

    def summary(self) -> dict:
        return {
            "id": self.id, "name": self.name, "state": self.state,
            "mapId": self.settings["mapId"], "mode": self.settings["mode"],
            "players": len(self.members), "humans": len(self.humans()),
            "maxPlayers": self.settings["maxPlayers"], "locked": bool(self.password),
        }

    def broadcast(self, msg: dict | str) -> None:
        droppable = isinstance(msg, dict) and msg.get("t") == "s"
        data = msg if isinstance(msg, str) else dumps(msg)
        for m in self.members:
            if not m["isBot"]:
                self.lobby.send_raw(m["id"], data, droppable)

    def broadcast_info(self) -> None:
        self.broadcast({"t": "room", "room": self.info()})

    def can_start(self) -> tuple[str, dict] | None:
        """返回 (错误码, 参数)；可以开局时返回 None。"""
        if self.state != "waiting":
            return "start_in_progress", {}
        if len(self.members) < 2:
            return "start_need_two", {}
        not_ready = [m["name"] for m in self.members if not m["isBot"] and m["id"] != self.host_id and not m["ready"]]
        if not_ready:
            return "start_not_ready", {"names": ", ".join(not_ready)}
        if self.settings["mode"] == "team":
            teams = {m["team"] for m in self.members}
            if teams != {0, 1}:
                return "start_team_empty", {}
        return None

    def start_game(self) -> None:
        map_id = self.settings["mapId"]
        if map_id == "random":
            map_id = random.choice(MAP_IDS)
        self.state = "playing"
        self.game = Game(
            map_id,
            self.settings["mode"],
            self.settings["lives"],
            [
                {"id": m["id"], "name": m["name"], "skin": m["skin"], "hat": m["hat"],
                 "team": m["team"], "is_bot": m["isBot"], "level": m.get("level", 0),
                 "avatar": m.get("avatar"), "ai": m.get("ai"),
                 "bomb": "" if m["isBot"] else store.active_bomb(store.cached_user(m["id"]))}
                for m in self.members
            ],
            broadcast=self.broadcast,
            on_end=self.end_game,
            on_anomaly=self.lobby.anomaly,
            shrink=self.settings["shrink"],
            items=self.settings.get("items", True),
            net_rate=self.lobby.net_rate,
            round_time=60.0 * self.settings.get("time", 10),
        )
        self.broadcast_info()
        self.broadcast(self.game.start_info())
        self.game.start()
        self.lobby.broadcast_lobby()

    def end_game(self, result: dict) -> None:
        self.game = None
        self.state = "waiting"
        store.record_match(result)
        for m in self.members:
            m["ready"] = m["isBot"]
            u = self.lobby.clients.get(m["id"])
            if u and not m["isBot"]:
                m["level"] = store.level_of(u.user["exp"])
        self.broadcast({"t": "end", "result": result})
        for m in self.humans():  # 推送最新的经验 / 金币 / 战绩
            c = self.lobby.clients.get(m["id"])
            if c:
                c.send({"t": "me", "user": store.public_user(c.user)})
        # 清理对局中掉线的玩家
        for m in [m for m in self.members if not m["isBot"] and not m["connected"]]:
            self.remove_member(m["id"])
            self.lobby.member_room.pop(m["id"], None)
        if not self.humans():
            self.lobby.delete_room(self)
            return
        self.broadcast_info()
        self.lobby.broadcast_lobby()


class Lobby:
    def __init__(self, net_rate: int = 30) -> None:
        self.net_rate = net_rate  # 对局状态同步频率（Hz，来自 SYNC_HZ）
        self.clients: dict[str, Client] = {}
        self.rooms: dict[str, Room] = {}
        self.member_room: dict[str, str] = {}
        self.next_room_id = 1
        self.lobby_dirty = False
        self.lobby_chat: list[dict] = []
        self.pending_leave: dict[str, asyncio.TimerHandle] = {}  # 房间内断线的宽限计时
        self.watcher = anticheat.Watcher()  # 异常移动 / 异常放炸弹观察

    # ---------- 发送 ----------
    def send_raw(self, uid: str, data: str, droppable: bool = False) -> None:
        c = self.clients.get(uid)
        if c:
            c.send_raw(data, droppable)

    def send_to(self, uid: str, msg: dict) -> None:
        self.send_raw(uid, dumps(msg))

    def anomaly(self, uid: str, kind: str) -> None:
        """服务器发现客户端异常（移动不合理 / 放炸弹过快）：10 秒观察期内累计 3 次则提醒。"""
        if self.watcher.report(uid):
            print(f"[anticheat] {uid} repeated anomalies (last: {kind})")
            self.send_to(uid, {"t": "warn", "code": "anomaly"})

    def room_of(self, uid: str) -> Room | None:
        rid = self.member_room.get(uid)
        return self.rooms.get(rid) if rid else None

    def lobby_info(self) -> dict:
        return {"t": "lobby", "online": len(self.clients), "rooms": [r.summary() for r in self.rooms.values()]}

    def broadcast_lobby(self) -> None:
        """合并 100ms 内的多次大厅变更，只推送一次。"""
        if self.lobby_dirty:
            return
        self.lobby_dirty = True

        def flush() -> None:
            self.lobby_dirty = False
            data = dumps(self.lobby_info())
            for uid in list(self.clients):
                if uid not in self.member_room:
                    self.send_raw(uid, data)

        try:
            asyncio.get_running_loop().call_later(0.1, flush)
        except RuntimeError:
            flush()

    # ---------- 连接 ----------
    async def serve(self, ws: web.WebSocketResponse, user: dict, channel: "secure.Channel") -> None:
        old = self.clients.get(user["id"])
        self._cancel_leave(user["id"])  # 宽限期内重连：留在房间
        client = Client(ws, user, channel)
        self.clients[user["id"]] = client
        if old and old.ws is not ws:
            await old.close(4000, "replaced")

        room = self.room_of(user["id"])
        client.send({"t": "welcome", "user": store.public_user(user), "maps": map_summaries(), "levels": store.level_table(),
                     "shop": store.shop_catalog(), "renameCardPrice": store.RENAME_CARD_PRICE, "bombShop": store.bomb_shop(),
                     "roomId": room.id if room else None, "inGame": bool(room and room.game)})
        if room:
            m = room.member(user["id"])
            if m:
                m["connected"] = True
            room.broadcast_info()
            if room.game:
                # 断线重连 / 关闭浏览器后重新登录：自动回到对局，按服务器的当前状态完整同步
                client.send(room.game.start_info(rejoin=True))
                room.broadcast({"t": "presence", "id": user["id"], "name": user["name"], "on": True})
        else:
            self.member_room.pop(user["id"], None)
            client.send(self.lobby_info())
            client.send({"t": "chatlog", "scope": "lobby", "list": self.lobby_chat[-30:]})
        self.broadcast_lobby()

        try:
            async for msg in ws:
                if msg.type != web.WSMsgType.BINARY:
                    continue  # 只接受加密帧
                try:
                    data = json.loads(channel.open(msg.data))
                except secure.CryptoError:
                    # 解密失败：篡改、重放或密钥不对，直接断开
                    await client.close(4002, "bad frame")
                    break
                except ValueError:
                    continue
                try:
                    # 定向取值：按消息类型只取约定的字段；文本去空白，只允许中文 / 英文字母 / 数字
                    data = textrule.read_ws(data)
                except textrule.TextError:
                    client.send({"t": "error", "code": "text_invalid"})
                    continue
                if data is None:
                    continue  # 不认识的消息类型
                try:
                    self.handle(client, data)
                except Exception:  # noqa: BLE001
                    import traceback

                    traceback.print_exc()
        finally:
            self.disconnect(client)
            client.queue.put_nowait(None)

    def disconnect(self, client: Client) -> None:
        uid = client.id
        if self.clients.get(uid) is not client:
            return  # 已被新连接替换
        del self.clients[uid]
        room = self.room_of(uid)
        if room:
            if room.state == "playing":
                m = room.member(uid)
                if m:
                    m["connected"] = False
                if room.game:
                    room.game.set_input(uid, direction=None)
                    # 对局中断线：全场广播
                    room.broadcast({"t": "presence", "id": uid, "name": client.user["name"], "on": False})
                room.broadcast_info()
            else:
                # 未开局：先标记离线，10 秒内没重连才自动离开房间
                m = room.member(uid)
                if m:
                    m["connected"] = False
                    room.broadcast_info()
                    self._cancel_leave(uid)
                    self.pending_leave[uid] = asyncio.get_running_loop().call_later(LEAVE_GRACE, self._leave_if_gone, uid)
        self.broadcast_lobby()

    def _cancel_leave(self, uid: str) -> None:
        h = self.pending_leave.pop(uid, None)
        if h:
            h.cancel()

    def _leave_if_gone(self, uid: str) -> None:
        self.pending_leave.pop(uid, None)
        if uid in self.clients:
            return  # 已经重连
        room = self.room_of(uid)
        if room and room.state == "waiting":
            self.leave_room(uid)

    # ---------- 房间 ----------
    def delete_room(self, room: Room) -> None:
        if room.game:
            room.game.stop()
            room.game = None
        for m in room.members:
            self.member_room.pop(m["id"], None)
        self.rooms.pop(room.id, None)
        self.broadcast_lobby()

    def leave_room(self, uid: str) -> None:
        room = self.room_of(uid)
        self.member_room.pop(uid, None)
        if not room:
            return
        room.remove_member(uid)
        if not room.humans():
            self.delete_room(room)
        else:
            room.broadcast_info()
            self.broadcast_lobby()

    def join_room(self, client: Client, room: Room, password: Any = None) -> bool:
        uid = client.id
        if self.room_of(uid) is room:
            room.broadcast_info()
            return True
        if room.password and password != room.password:
            client.send({"t": "error", "code": "room_password" if not password else "room_password_wrong", "params": {"id": room.id}})
            return False
        if self.room_of(uid):
            self.leave_room(uid)
        if not room.add_user(client.user):
            client.send({"t": "error", "code": "room_in_game" if room.state != "waiting" else "room_full"})
            return False
        self.member_room[uid] = room.id
        room.broadcast_info()
        room.broadcast({"t": "chat", "scope": "room", "sys": True, "key": "joined", "params": {"name": client.user["name"]}})
        self.broadcast_lobby()
        return True

    def create_room(self, client: Client, msg: dict) -> None:
        if len(self.rooms) >= MAX_ROOMS:
            client.send({"t": "error", "code": "room_limit"})
            return
        rid = str(self.next_room_id)
        self.next_room_id += 1
        name = clean_text(msg.get("name"), 16) or i18n.room_name(client.user.get("lang"), client.user["name"])
        pw = msg.get("password")
        if pw not in (None, "") and not (isinstance(pw, str) and len(pw) == 6 and pw.isascii() and pw.isalnum()):  # 6 位数字 / 英文
            client.send({"t": "error", "code": "room_password_format"})
            return
        room = Room(self, rid, name, msg)
        room.password = pw or None
        self.rooms[rid] = room
        self.join_room(client, room, password=pw)

    # ---------- 消息 ----------
    NEED_CHARACTER = {"createRoom", "joinRoom", "quickJoin", "ready", "start", "chat", "buy", "rename"}

    def handle(self, client: Client, msg: dict[str, Any]) -> None:
        if msg.get("t") == "createCharacter":
            task = asyncio.get_running_loop().create_task(self._create_character(client, msg))
            task.add_done_callback(lambda tk: tk.cancelled() or tk.exception() and print(f"[lobby] character error: {tk.exception()!r}"))
            return
        if msg.get("t") in self.NEED_CHARACTER and not client.user.get("hasCharacter", True):
            client.send({"t": "error", "code": "character_required"})
            return
        self._handle(client, msg)

    async def _create_character(self, client: Client, msg: dict) -> None:
        try:
            await store.create_character(client.user, msg.get("name"), msg.get("skin"), msg.get("hat"))
        except store.ShopError as e:
            client.send({"t": "error", "code": e.code})
            return
        client.send({"t": "me", "user": store.public_user(client.user)})
        self.broadcast_lobby()

    def _handle(self, client: Client, msg: dict[str, Any]) -> None:
        uid = client.id
        room = self.room_of(uid)
        is_host = room is not None and room.host_id == uid
        t = msg["t"]

        if t == "ping":
            client.send({"t": "pong", "ts": msg.get("ts")})
        elif t == "lobby":
            client.send(self.lobby_info())
        elif t == "createRoom":
            self.create_room(client, msg)
        elif t == "joinRoom":
            r = self.rooms.get(str(msg.get("id")))
            if r:
                self.join_room(client, r, password=msg.get("password"))
            else:
                client.send({"t": "error", "code": "room_not_found"})
        elif t == "quickJoin":
            r = next(
                (x for x in self.rooms.values() if x.state == "waiting" and len(x.members) < MAX_PLAYERS and not x.password),
                None,
            )
            if r:
                self.join_room(client, r)
            else:
                self.create_room(client, {})
        elif t == "leaveRoom":
            self.leave_room(uid)
            client.send(self.lobby_info())
        elif t == "ready" and room and room.state == "waiting":
            m = room.member(uid)
            if m:
                m["ready"] = bool(msg.get("v"))
            room.broadcast_info()
        elif t == "team" and room and room.state == "waiting":
            target = msg.get("id") if (msg.get("id") and is_host) else uid
            m = room.member(str(target))
            if m and msg.get("team") in (0, 1):
                m["team"] = msg["team"]
            room.broadcast_info()
        elif t == "settings" and is_host and room.state == "waiting":
            room.apply_settings(msg)
            name = clean_text(msg.get("name"), 16)
            if name:
                room.name = name
            room.broadcast_info()
            self.broadcast_lobby()
        elif t == "addBot" and is_host:
            if not room.add_bot(msg.get("level")):
                client.send({"t": "error", "code": "bot_limit", "params": {"max": MAX_PLAYERS, "limit": room.bot_limit()}})
            room.broadcast_info()
            self.broadcast_lobby()
        elif t == "botLevel" and is_host:
            if room.set_bot_level(msg.get("id"), msg.get("level")):
                room.broadcast_info()
        elif t == "kick" and is_host and room.state == "waiting" and msg.get("id") != uid:
            m = room.member(str(msg.get("id")))
            if m:
                if m["isBot"]:
                    room.remove_member(m["id"])
                else:
                    self.leave_room(m["id"])
                    self.send_to(m["id"], {"t": "kicked"})
                    self.send_to(m["id"], self.lobby_info())
                room.broadcast_info()
                self.broadcast_lobby()
        elif t == "start" and is_host:
            err = room.can_start()
            if err:
                client.send({"t": "error", "code": err[0], "params": err[1]})
            else:
                room.start_game()
        elif t == "in":
            if room and room.game:
                room.game.set_input(uid, direction=msg.get("d"), seq=msg.get("q"))
        elif t == "mv":
            if room and room.game:
                room.game.client_move(uid, msg.get("x"), msg.get("y"), facing=msg.get("f"), moving=msg.get("m"),
                                      kick=msg.get("k"), seq=msg.get("q"), epoch=msg.get("e"), ping=msg.get("p"))
        elif t == "use":
            if room and room.game:
                room.game.use_item(uid, msg.get("s"))  # 使用道具栏第 s 格（0–5）
        elif t == "bomb":
            if room and room.game:
                if msg.get("x") is not None:
                    # 放炸弹前先同步放置时的位置（同样经过校验）
                    room.game.client_move(uid, msg.get("x"), msg.get("y"), epoch=msg.get("e"))
                room.game.set_input(uid, bomb=True, seq=msg.get("q"))
        elif t == "chat":
            self._chat(client, room, msg)
        elif t == "history":
            task = asyncio.get_running_loop().create_task(self._history(client))
            task.add_done_callback(lambda tk: tk.cancelled() or tk.exception() and print(f"[lobby] history error: {tk.exception()!r}"))
        elif t == "leaderboard":
            task = asyncio.get_running_loop().create_task(self._leaderboard(client))
            task.add_done_callback(lambda tk: tk.cancelled() or tk.exception() and print(f"[lobby] leaderboard error: {tk.exception()!r}"))
        elif t == "rename":
            task = asyncio.get_running_loop().create_task(self._rename(client, msg.get("name")))
            task.add_done_callback(lambda tk: tk.cancelled() or tk.exception() and print(f"[lobby] rename error: {tk.exception()!r}"))
        elif t == "buy":
            task = asyncio.get_running_loop().create_task(self._buy(client, msg.get("item")))
            task.add_done_callback(lambda tk: tk.cancelled() or tk.exception() and print(f"[lobby] buy error: {tk.exception()!r}"))
        elif t == "profile":
            store.update_profile(client.user, msg.get("name"), msg.get("skin"), msg.get("hat"), msg.get("lang"))
            client.send({"t": "me", "user": store.public_user(client.user)})
            if room and room.state == "waiting":
                m = room.member(uid)
                if m:
                    m.update(name=client.user["name"], skin=client.user["skin"], hat=client.user["hat"],
                             level=store.level_of(client.user["exp"]))
                    room.broadcast_info()

    async def _buy(self, client: Client, item: Any) -> None:
        try:
            await store.buy_item(client.user, item)
        except store.ShopError as e:
            client.send({"t": "error", "code": e.code})
            return
        client.send({"t": "bought", "item": item if item == "rename" or item in store.BOMB_STYLES else client.user["hat"]})
        client.send({"t": "me", "user": store.public_user(client.user)})
        room = self.room_of(client.id)
        if room and room.state == "waiting":
            m = room.member(client.id)
            if m:
                m.update(hat=client.user["hat"])
                room.broadcast_info()

    async def _history(self, client: Client) -> None:
        client.send({"t": "history", "list": await store.match_history(client.id, 30)})

    async def _leaderboard(self, client: Client) -> None:
        client.send({"t": "leaderboard", "list": await store.leaderboard(20)})

    async def _rename(self, client: Client, name: Any) -> None:
        try:
            await store.rename(client.user, name)
        except store.ShopError as e:
            client.send({"t": "error", "code": e.code})
            return
        client.send({"t": "renamed", "name": client.user["name"]})
        client.send({"t": "me", "user": store.public_user(client.user)})
        room = self.room_of(client.id)
        if room and room.state == "waiting":
            m = room.member(client.id)
            if m:
                m.update(name=client.user["name"])
                room.broadcast_info()

    def _chat(self, client: Client, room: Room | None, msg: dict) -> None:
        text = clean_text(msg.get("text"), 120)
        if not text:
            return
        now = time.monotonic()
        client.chat_burst = max(0.0, client.chat_burst - (now - client.last_chat))
        client.last_chat = now
        if client.chat_burst > 5:
            client.send({"t": "error", "code": "chat_too_fast"})
            return
        client.chat_burst += 1
        entry = {
            "t": "chat", "from": client.user["name"], "skin": client.user["skin"],
            "text": text, "ts": int(time.time() * 1000),
        }
        if room:
            room.broadcast({**entry, "scope": "room"})
        else:
            e = {**entry, "scope": "lobby"}
            self.lobby_chat = (self.lobby_chat + [e])[-50:]
            data = dumps(e)
            for cid in list(self.clients):
                if cid not in self.member_room:
                    self.send_raw(cid, data)
