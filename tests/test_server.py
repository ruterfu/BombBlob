"""端到端测试（需要 PostgreSQL，先运行 scripts/db.sh start）。

覆盖：游客登录 / WebSocket / 建房 / 选房加入 / 6 人上限 /
机器人上限（6 - 真人数）/ 地图选择（5 张 + 随机）/ 开局 / 服务器权威状态 / 战绩入库。
"""
import asyncio
import json
import os
import unittest

import asyncpg
from aiohttp.test_utils import TestClient, TestServer

from backend.maps import MAP_IDS
from tests.secure_client import TEST_RSA, spost, sws
from backend.config import Config
from backend.server import LOBBY_KEY, create_app

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/bombblob_test")


async def recv_until(ws, t, timeout=8.0, pred=None):
    async def inner():
        while True:
            msg = await ws.receive()
            if msg.type != 1:  # TEXT
                raise AssertionError(f"socket closed while waiting for {t}: {msg}")
            data = json.loads(msg.data)
            if data["t"] == t and (pred is None or pred(data)):
                return data

    return await asyncio.wait_for(inner(), timeout)


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        con = await asyncpg.connect(TEST_DSN)
        await con.execute("DROP TABLE IF EXISTS bomb_purchases, user_items, cosmetics, match_players, login_tokens, matches, levels, meta, users CASCADE")
        await con.close()
        self.client = TestClient(TestServer(create_app(TEST_DSN, config=Config(login_guest=True), rsa_key=TEST_RSA)))
        await self.client.start_server()
        self.sockets = []

    async def asyncTearDown(self):
        for ws in self.sockets:
            await ws.close()
        await self.client.close()

    async def login(self, name=None, token=None, expect=200):
        r = await spost(self.client, "/api/guest", {"name": name, "skin": 2, "hat": 1, "token": token})  # token 不会被读取
        self.assertEqual(r.status, expect)
        return await r.json()

    async def connect(self, login):
        ws = await sws(self.client, login)
        self.sockets.append(ws)
        await recv_until(ws, "welcome")
        return ws

    # ---------- 登录 ----------
    async def test_guest_login_no_token(self):
        err = await self.login("小明<b>", expect=400)  # 含符号：全局文本规则整条拒绝
        self.assertEqual(err["code"], "text_invalid")
        a = await self.login()
        self.assertNotIn("token", a)  # 不再下发自动登录 token
        b = await self.login(token="a" * 64)  # token 字段不读取：仍是新建账号
        self.assertNotEqual(b["user"]["id"], a["user"]["id"])

    async def test_text_rule_on_ws(self):
        a = await self.login()
        ws = await self.connect(a)
        await ws.send_json({"t": "chat", "text": "大家 好 hi"})
        m = await recv_until(ws, "chat")
        self.assertEqual(m["text"] if "text" in m else m.get("msg", {}).get("text"), "大家 好 hi")
        # 聊天不限制字符：原样作为纯文本转发（前端用 textContent / 转义显示，不会执行）
        await ws.send_json({"t": "chat", "text": "<script>alert(1)</script> 哈哈！"})
        m = await recv_until(ws, "chat", pred=lambda d: "script" in d.get("text", ""))
        self.assertEqual(m["text"], "<script>alert(1)</script> 哈哈！")
        # 其他字段仍然遵守文本规则
        await ws.send_json({"t": "rename", "name": "<b>"})
        self.assertEqual((await recv_until(ws, "error"))["code"], "text_invalid")

    async def test_guest_gets_8_digit_id_and_can_login_by_id(self):
        a = await self.login("新号")
        self.assertTrue(a["created"])
        uid = a["user"]["id"]
        self.assertRegex(uid, r"^[1-9]\d{7}$")
        b = await self.login("另一个新号")
        self.assertNotEqual(b["user"]["id"], uid)
        r = await spost(self.client, "/api/login", {"id": uid})
        self.assertEqual(r.status, 200)
        d = await r.json()
        self.assertFalse(d["created"])
        self.assertEqual(d["user"]["id"], uid)
        self.assertEqual(d["user"]["name"], "新号")
        for bad in ["12345678", "abc", "1234567", None]:
            r = await spost(self.client, "/api/login", {"id": bad})
            self.assertEqual(r.status, 404, bad)

    async def test_session_auth(self):
        a = await self.login("会话")
        ws = await self.connect(a)
        await ws.send_json({"t": "ping", "ts": 1})
        self.assertEqual((await recv_until(ws, "pong"))["ts"], 1)
        # 明文 / 用户数据接口已移除：登录后只能通过加密 WebSocket 通信
        self.assertEqual((await self.client.get("/api/me")).status, 404)
        self.assertEqual((await self.client.get("/api/leaderboard")).status, 404)
        ws = await self.client.ws_connect("/gamesocket?session=bad")
        await ws.receive()
        self.assertEqual(ws.close_code, 4001)

    async def test_reconnect_rejoins_game_with_server_state(self):
        a = await self.login("重连")
        ws = await self.connect(a)
        await ws.send_json({"t": "createRoom", "name": "重连房"})
        await recv_until(ws, "room")
        await ws.send_json({"t": "addBot"})
        await recv_until(ws, "room", pred=lambda d: len(d["room"]["members"]) == 2)
        await ws.send_json({"t": "start"})
        start = await recv_until(ws, "start")
        self.assertFalse(start["rejoin"])
        await ws.send_json({"t": "loaded"})  # 场景加载完成
        await recv_until(ws, "s", timeout=10, pred=lambda d: d["ph"] == "play")
        # 服务器端改变地图（模拟对局进行中方块被炸掉）
        g = self.client.server.app[LOBBY_KEY].rooms[start and next(iter(self.client.server.app[LOBBY_KEY].rooms))].game
        g.blocks[g.W + 2] = "."
        await ws.close()
        await asyncio.sleep(0.3)
        # 重新连接（或关闭浏览器后重新登录）：自动回到同一局，并拿到服务器的当前状态
        ws2 = await self.connect(a)
        again = await recv_until(ws2, "start")
        self.assertTrue(again["rejoin"])
        self.assertEqual(again["gid"], start["gid"])
        self.assertEqual(again["phase"], "play")
        self.assertEqual(again["k"], "".join(g.blocks))
        s2 = await recv_until(ws2, "s")
        self.assertTrue(any(p["id"] == a["user"]["id"] for p in s2["p"]))
        r = await spost(self.client, "/api/login", {"id": a["user"]["id"]})  # 关闭浏览器后用 8 位 ID 重新登录
        a2 = await r.json()
        ws3 = await self.connect(a2)
        self.assertTrue((await recv_until(ws3, "start"))["rejoin"])

    async def test_room_password(self):
        h = await self.login("房主")
        g = await self.login("访客")
        wh = await self.connect(h)
        wg = await self.connect(g)
        await wh.send_json({"t": "createRoom", "name": "密室", "password": "12ab"})  # 格式不对
        self.assertEqual((await recv_until(wh, "error"))["code"], "room_password_format")
        await wh.send_json({"t": "createRoom", "name": "密室", "password": "Ab12Cd"})
        room = (await recv_until(wh, "room"))["room"]
        self.assertEqual(room["password"], "Ab12Cd")  # 房间内成员能看到密码
        lobby = await recv_until(wg, "lobby", pred=lambda d: any(r["id"] == room["id"] for r in d["rooms"]))
        summary = next(r for r in lobby["rooms"] if r["id"] == room["id"])
        self.assertTrue(summary["locked"])
        self.assertNotIn("password", summary)  # 大厅列表不泄露密码
        await wg.send_json({"t": "joinRoom", "id": room["id"]})
        self.assertEqual((await recv_until(wg, "error"))["code"], "room_password")
        await wg.send_json({"t": "joinRoom", "id": room["id"], "password": "zzzzzz"})
        self.assertEqual((await recv_until(wg, "error"))["code"], "room_password_wrong")
        await wg.send_json({"t": "quickJoin"})  # 快速匹配不会进有密码的房间
        self.assertNotEqual((await recv_until(wg, "room"))["room"]["id"], room["id"])
        await wg.send_json({"t": "leaveRoom"})
        await wg.send_json({"t": "joinRoom", "id": room["id"], "password": "Ab12Cd"})
        joined = await recv_until(wg, "room", pred=lambda d: d["room"]["id"] == room["id"])
        self.assertEqual(len(joined["room"]["members"]), 2)

    async def test_room_disconnect_grace(self):
        from backend import lobby as lobby_mod
        lobby_mod.LEAVE_GRACE = 0.6  # 测试中缩短宽限时间
        try:
            h = await self.login("房主")
            g = await self.login("访客")
            wh = await self.connect(h)
            wg = await self.connect(g)
            await wh.send_json({"t": "createRoom", "name": "宽限"})
            room = (await recv_until(wh, "room"))["room"]
            await wg.send_json({"t": "joinRoom", "id": room["id"]})
            await recv_until(wh, "room", pred=lambda d: len(d["room"]["members"]) == 2)
            # 断开后宽限期内重连：仍在房间
            await wg.close()
            off = await recv_until(wh, "room", pred=lambda d: any(not m["connected"] for m in d["room"]["members"]))
            self.assertEqual(len(off["room"]["members"]), 2)
            wg = await self.connect(g)
            back = await recv_until(wg, "room")
            self.assertEqual(len(back["room"]["members"]), 2)
            # 断开且超时无响应：自动离开房间
            await wg.close()
            gone = await recv_until(wh, "room", timeout=5, pred=lambda d: len(d["room"]["members"]) == 1)
            self.assertEqual(gone["room"]["members"][0]["id"], h["user"]["id"])
        finally:
            lobby_mod.LEAVE_GRACE = 10.0

    async def test_presence_broadcast_in_game(self):
        a = await self.login("甲")
        b = await self.login("乙")
        wa = await self.connect(a)
        wb = await self.connect(b)
        await wa.send_json({"t": "createRoom", "name": "广播"})
        room = (await recv_until(wa, "room"))["room"]
        await wb.send_json({"t": "joinRoom", "id": room["id"]})
        await recv_until(wb, "room")
        await wb.send_json({"t": "ready", "v": True})
        await recv_until(wa, "room", pred=lambda d: all(m["ready"] or m["id"] == a["user"]["id"] for m in d["room"]["members"]))
        await wa.send_json({"t": "start"})
        await recv_until(wa, "start")
        await wb.close()
        off = await recv_until(wa, "presence")
        self.assertEqual((off["id"], off["on"]), (b["user"]["id"], False))
        wb = await self.connect(b)
        on = await recv_until(wa, "presence")
        self.assertEqual((on["id"], on["on"]), (b["user"]["id"], True))

    # ---------- 传输加密 ----------
    async def test_plaintext_login_rejected(self):
        r = await self.client.post("/api/guest", json={"name": "明文"})
        self.assertEqual(r.status, 400)
        self.assertEqual(await r.json(), {"code": "bad_request"})

    async def test_wrong_rsa_key_rejected(self):
        from backend import secure
        from tests.secure_client import spost as _spost
        r = await _spost(self.client, "/api/guest", {"name": "x"}, key=secure.generate_key())
        self.assertEqual(r.status, 400)

    async def test_login_response_is_encrypted(self):
        from backend import secure
        k, wire = secure.client_seal_request(TEST_RSA.public_key(), {"name": "密文"})
        raw = await (await self.client.post("/api/guest", json=wire)).json()
        self.assertEqual(set(raw), {"iv", "ct"})  # 线上看到的只有密文
        self.assertNotIn("token", json.dumps(raw))
        data = secure.client_open_response(k, raw)
        self.assertEqual(len(secure.unb64(data["key"])), 16)  # AES-128 会话密钥
        self.assertEqual(data["session"], secure.session_id(secure.unb64(data["key"])))

    async def test_ws_frames_encrypted_and_replay_rejected(self):
        a = await self.login("帧")
        ws = await self.connect(a)
        # 服务器发来的都是二进制密文
        await ws.send_json({"t": "ping", "ts": 7})
        raw = await ws.ws.receive()
        self.assertEqual(raw.type, 2)  # BINARY
        self.assertNotIn(b"pong", raw.data)
        ws.channel.in_ctr += 1  # 手动消费掉这一帧的序号
        # 重放一帧之前发过的密文：序号对不上，GCM 校验失败，连接被关闭
        frame = ws.channel.seal(json.dumps({"t": "ping", "ts": 8}))
        await ws.send_raw(frame)
        await recv_until(ws, "pong")
        await ws.send_raw(frame)
        while True:
            m = await ws.ws.receive(timeout=5)
            if m.type in (8, 257, 258):  # CLOSE / CLOSING / CLOSED
                break
        self.assertEqual(ws.close_code, 4002)

    async def test_plaintext_ws_frames_ignored(self):
        a = await self.login("明文帧")
        ws = await self.connect(a)
        await ws.ws.send_str(json.dumps({"t": "createRoom", "name": "x"}))  # 明文帧被忽略
        await ws.send_json({"t": "ping", "ts": 3})
        self.assertEqual((await recv_until(ws, "pong"))["ts"], 3)

    # ---------- 房间 / 地图 / 机器人 ----------
    async def test_room_options_via_websocket(self):
        """创建房间 / 修改设置的每个玩法选项都要能经过消息校验到达服务器（复活赛曾被白名单漏掉）。"""
        a = await self.login("房主")
        ws = await self.connect(a)
        await ws.send_json({"t": "createRoom", "name": "选项房", "revive": True, "items": False, "shrink": False, "time": 5, "mode": "team"})
        room = (await recv_until(ws, "room"))["room"]
        self.assertEqual({k: room["settings"][k] for k in ("revive", "items", "shrink", "time", "mode")},
                         {"revive": True, "items": False, "shrink": False, "time": 5, "mode": "team"})
        await ws.send_json({"t": "settings", "revive": False})
        room = (await recv_until(ws, "room"))["room"]
        self.assertFalse(room["settings"]["revive"])
        await ws.send_json({"t": "settings", "revive": True})
        room = (await recv_until(ws, "room"))["room"]
        self.assertTrue(room["settings"]["revive"])

    async def test_fourteen_maps_plus_random(self):
        maps = (await (await self.client.get("/api/maps")).json())["maps"]
        self.assertEqual(len(maps), 14)
        a = await self.login("房主")
        ws = await self.connect(a)
        await ws.send_json({"t": "createRoom", "name": "地图房"})
        await recv_until(ws, "room")
        for mid in MAP_IDS + ["random"]:
            await ws.send_json({"t": "settings", "mapId": mid})
            room = (await recv_until(ws, "room"))["room"]
            self.assertEqual(room["settings"]["mapId"], mid)
        await ws.send_json({"t": "settings", "mapId": "lava"})  # 不存在的地图被忽略
        room = (await recv_until(ws, "room"))["room"]
        self.assertEqual(room["settings"]["mapId"], "random")

    async def test_room_capacity_and_bot_limit(self):
        host = await self.login("房主")
        wh = await self.connect(host)
        await wh.send_json({"t": "createRoom", "name": "满员测试"})
        room = (await recv_until(wh, "room"))["room"]
        self.assertEqual(room["botLimit"], 5)
        # 只有 1 个真人时最多 5 个机器人
        for _ in range(6):
            await wh.send_json({"t": "addBot"})
        err = await recv_until(wh, "error")
        self.assertEqual(err["code"], "bot_limit")
        self.assertNotIn("msg", err)
        room = (await recv_until(wh, "room", pred=lambda d: len(d["room"]["members"]) == 6))["room"]
        self.assertEqual(sum(m["isBot"] for m in room["members"]), 5)

        # 房间满 6 人，别人无法加入
        guest = await self.login("路人")
        wg = await self.connect(guest)
        lobby = await recv_until(wg, "lobby")
        self.assertEqual(lobby["rooms"][0]["players"], 6)
        await wg.send_json({"t": "joinRoom", "id": room["id"]})
        self.assertEqual((await recv_until(wg, "error"))["code"], "room_full")

        # 踢掉 2 个机器人后，第 2 个真人加入 → 机器人上限变为 4
        bots = [m for m in room["members"] if m["isBot"]]
        for b in bots[:2]:
            await wh.send_json({"t": "kick", "id": b["id"]})
        await asyncio.sleep(0.1)
        await wg.send_json({"t": "joinRoom", "id": room["id"]})
        room = (await recv_until(wg, "room"))["room"]
        self.assertEqual(room["botLimit"], 4)
        self.assertEqual(len(room["members"]), 5)
        await wh.send_json({"t": "addBot"})
        room = (await recv_until(wh, "room", pred=lambda d: len(d["room"]["members"]) == 6))["room"]
        self.assertEqual(sum(m["isBot"] for m in room["members"]), 4)
        await wh.send_json({"t": "addBot"})
        await recv_until(wh, "error")

    async def test_full_game_flow(self):
        a = await self.login("Alice")
        b = await self.login("Bob")
        wa = await self.connect(a)
        wb = await self.connect(b)

        await wa.send_json({"t": "createRoom", "name": "测试房", "mapId": "neon", "mode": "ffa", "lives": 1})
        room = (await recv_until(wa, "room"))["room"]
        self.assertEqual(room["hostId"], a["user"]["id"])
        # 乙在大厅列表里看到这个房间并选择加入
        lobby = await recv_until(wb, "lobby", pred=lambda d: any(r["id"] == room["id"] for r in d["rooms"]))
        self.assertTrue(lobby["rooms"])
        await wb.send_json({"t": "joinRoom", "id": room["id"]})
        await recv_until(wb, "room")
        await wa.send_json({"t": "addBot"})
        await wa.send_json({"t": "start"})
        err = await recv_until(wa, "error")
        self.assertEqual(err["code"], "start_not_ready")
        self.assertIn("Bob", err["params"]["names"])

        await wb.send_json({"t": "ready", "v": True})
        await asyncio.sleep(0.1)
        await wa.send_json({"t": "start"})
        start = await recv_until(wa, "start")
        self.assertEqual(start["mapId"], "neon")
        self.assertEqual(len(start["players"]), 3)
        # 开局先等待玩家连接：两名真人都回报加载完成后才开始倒计时
        s = await recv_until(wa, "s", pred=lambda d: d["ph"] == "wait")
        self.assertEqual(sorted(s["wt"]), sorted([a["user"]["id"], b["user"]["id"]]))
        await wa.send_json({"t": "loaded"})
        s = await recv_until(wa, "s", pred=lambda d: d["ph"] == "wait" and d["wt"] == [b["user"]["id"]])
        await wb.send_json({"t": "loaded"})
        await recv_until(wa, "s", pred=lambda d: d["ph"] == "countdown")

        s = await recv_until(wa, "s", timeout=10, pred=lambda d: d["ph"] == "play")
        me0 = next(p for p in s["p"] if p["id"] == a["user"]["id"])
        moved = False
        for d in ("up", "down", "left", "right"):
            await wa.send_json({"t": "in", "d": d})
            for _ in range(10):
                s = await recv_until(wa, "s")
            me1 = next(p for p in s["p"] if p["id"] == a["user"]["id"])
            if (me1["x"], me1["y"]) != (me0["x"], me0["y"]):
                moved = True
                break
        self.assertTrue(moved, "服务器应根据输入移动玩家")

        await wa.send_json({"t": "in", "d": None})
        await wa.send_json({"t": "bomb"})
        await recv_until(wa, "s", pred=lambda d: any(e["k"] == "place" for e in d["e"]))

        await wb.send_json({"t": "chat", "text": "你好"})
        self.assertEqual((await recv_until(wa, "chat"))["text"], "你好")

        # 让机器人和乙出局 → 甲获胜 → 战绩与对局记录写入 PostgreSQL
        lobby_obj = self.client.server.app[LOBBY_KEY]
        g = lobby_obj.rooms[room["id"]].game
        for p in start["players"]:
            if p["id"] != a["user"]["id"]:
                g.die(g.player(p["id"]), None)  # 正常淘汰（不是主动退出）
        end = await recv_until(wa, "end", timeout=10)
        self.assertEqual(end["result"]["players"][0]["id"], a["user"]["id"])
        self.assertTrue(end["result"]["players"][0]["win"])
        me = await recv_until(wa, "me")
        await recv_until(wa, "room", pred=lambda d: d["room"]["state"] == "waiting")
        await asyncio.sleep(0.3)
        con = await asyncpg.connect(TEST_DSN)
        row = await con.fetchrow("SELECT games, wins, exp, points FROM users WHERE id = $1", a["user"]["id"])
        loser = await con.fetchrow("SELECT games, wins, exp, points FROM users WHERE id = $1", b["user"]["id"])
        nm = await con.fetchval("SELECT count(*) FROM matches")
        await con.close()
        self.assertEqual((row["games"], row["wins"]), (1, 1))
        # 获胜奖励：经验和点数写入数据库，结算消息里也带上了奖励
        winner = end["result"]["players"][0]
        self.assertEqual((row["exp"], row["points"]), (winner["exp"], winner["points"]))
        self.assertGreaterEqual(row["exp"], 100)
        self.assertGreaterEqual(row["points"], 10)
        # 失败方有少量经验，点数为胜利算式的 15%–35%
        self.assertEqual((loser["games"], loser["wins"]), (1, 0))
        lp = next(x for x in end["result"]["players"] if x["id"] == b["user"]["id"])
        self.assertTrue(15 <= lp["lossPct"] <= 35)
        self.assertEqual(loser["points"], lp["points"])
        self.assertGreater(loser["exp"], 0)
        self.assertEqual(me["user"]["points"], row["points"])
        self.assertEqual(me["user"]["exp"], row["exp"])
        self.assertEqual(nm, 1)
        con = await asyncpg.connect(TEST_DSN)
        mp = await con.fetch("SELECT user_id, win, exp_gained, points_gained, level_after FROM match_players ORDER BY place")
        lvl = await con.fetchval("SELECT level FROM users WHERE id = $1", a["user"]["id"])
        await con.close()
        self.assertEqual(len(mp), 2)  # 两名真人（AI 不记录）
        self.assertTrue(mp[0]["win"])
        self.assertLess(mp[1]["exp_gained"], mp[0]["exp_gained"] * 0.2)
        self.assertEqual(lvl, mp[0]["level_after"])
        # 对战记录：和谁一起玩、胜负、收益
        await wa.send_json({"t": "history"})
        hist = (await recv_until(wa, "history"))["list"]
        self.assertEqual(len(hist), 1)
        h0 = hist[0]
        self.assertTrue(h0["win"])
        self.assertEqual((h0["exp"], h0["points"]), (winner["exp"], winner["points"]))
        names = {p["name"] for p in h0["players"]}
        self.assertIn(b["user"]["name"], names)
        self.assertTrue(any(p["me"] for p in h0["players"]))
        self.assertTrue(all(p["id"] is None for p in h0["players"] if p["isBot"]))
        await wb.send_json({"t": "history"})
        hb = (await recv_until(wb, "history"))["list"][0]
        self.assertFalse(hb["win"])
        self.assertEqual(hb["points"], lp["points"])  # 失败也有 15%–35% 的点数
        await wa.send_json({"t": "leaderboard"})
        lb = (await recv_until(wa, "leaderboard"))["list"]
        self.assertEqual(lb[0]["id"], a["user"]["id"])
        self.assertIn("avatar", lb[0])  # 排行榜带头像（游客为 null）
        con = await asyncpg.connect(TEST_DSN)
        idx = await con.fetchval("SELECT indexdef FROM pg_indexes WHERE indexname = 'users_leaderboard'")
        plan = "\n".join(r[0] for r in await con.fetch(
            "EXPLAIN SELECT id, name, skin, hat, exp, level, avatar_url, games, wins, kills FROM users "
            "WHERE games > 0 ORDER BY wins DESC, kills DESC, games ASC, id ASC LIMIT 20"))
        await con.close()
        self.assertIn("avatar_url", idx)
        self.assertNotIn("Sort", plan)  # 仍然无需排序（按索引顺序读取）


if __name__ == "__main__":
    unittest.main()
