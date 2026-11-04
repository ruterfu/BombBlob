"""登录方式开关（LOGIN_GUEST / LOGIN_GITHUB）与 GitHub OAuth 流程测试（用假的 GitHub 客户端，不访问网络）。"""
import asyncio
import os
import re
import unittest
from urllib.parse import parse_qs, urlparse

import asyncpg
from aiohttp.test_utils import TestClient, TestServer

from backend.config import Config
from backend.oauth import GitHubOAuth
from tests.secure_client import TEST_RSA, spost, sws
from backend.server import create_app

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/bombblob_test")


class FakeGitHub(GitHubOAuth):
    def __init__(self):
        super().__init__("cid", "secret")
        self.user = {"id": 424242, "login": "octo-cat", "avatar_url": "https://avatars.githubusercontent.com/u/424242?v=4"}

    async def exchange_code(self, code, redirect_uri):
        assert code == "good-code"
        self.redirect_uri = redirect_uri
        return "gh-access-token"

    async def fetch_user(self, access_token):
        assert access_token == "gh-access-token"
        return dict(self.user)


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        con = await asyncpg.connect(TEST_DSN)
        await con.execute("DROP TABLE IF EXISTS boost_purchases, bomb_purchases, user_items, cosmetics, match_players, login_tokens, matches, levels, meta, users CASCADE")
        await con.close()
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.close()

    async def make(self, guest: bool, github: bool):
        gh = FakeGitHub()
        cfg = Config(login_guest=guest, login_github=github, github_client_id="cid", github_client_secret="secret",
                     public_url="http://bomb.example.com")  # 测试客户端走 http（https 时 state Cookie 带 Secure）
        c = TestClient(TestServer(create_app(TEST_DSN, config=cfg, github=gh, rsa_key=TEST_RSA)))
        await c.start_server()
        self.clients.append(c)
        return c, gh

    async def github_login(self, c):
        r = await c.get("/auth/github", allow_redirects=False)
        self.assertEqual(r.status, 302)
        loc = urlparse(r.headers["Location"])
        self.assertEqual(loc.netloc, "github.com")
        q = parse_qs(loc.query)
        self.assertEqual(q["redirect_uri"][0], "http://bomb.example.com/oauth/callback")
        self.assertNotIn("scope", q)  # 不申请任何权限范围
        state = q["state"][0]
        r = await c.get(f"/oauth/callback?code=good-code&state={state}", allow_redirects=False)
        self.assertEqual(r.status, 302)
        frag = r.headers["Location"].split("#", 1)[1]
        self.assertTrue(frag.startswith("oauth="), frag)
        return frag[len("oauth="):]

    def test_name_rules(self):
        from backend.names import check_name
        ok = ["疾风小队", "Blob01", "夜行者", "Guest1234", "小明 二号", "  前后空格  "]
        for n in ok:
            self.assertIsNone(check_name(n)[1], n)
        bad = {
            "【你妈的】": "name_chars", "[GM]": "name_chars", "a<b>": "name_chars", "哈😀": "name_chars",
            "你妈的": "name_forbidden", "你 妈 的": "name_forbidden", "f-u-c-k": "name_chars", "f u c k": "name_forbidden", "ＦＵＣＫ": "name_forbidden",
            "断开连接": "name_forbidden", "重新連線": "name_forbidden", "系统": "name_forbidden", "Admin": "name_forbidden",
            "仆街": "name_forbidden", "死ね": "name_chars", "  ": "name_invalid", "": "name_invalid",
            "Blob_01": "name_chars", "A·B-C": "name_chars", "hi!": "name_chars", "a.b": "name_chars",
            "ゲスト": "name_chars", "Café": "name_chars", "한글": "name_chars", "，": "name_chars",
        }
        for n, code in bad.items():
            self.assertEqual(check_name(n)[1], code, n)
        self.assertEqual(check_name("一二三四五六七八九十")[0], "一二三四五六七八")  # 最多 8 个字
        self.assertEqual(check_name("  前后空格  ")[0], "前后空格")  # 先 trim
        self.assertEqual(check_name("小明 二号")[0], "小明二号")  # 空格全部去掉

    def test_new_ids_never_contain_4(self):
        from backend.store import is_valid_id, new_user_id
        for _ in range(3000):
            uid = new_user_id()
            self.assertTrue(is_valid_id(uid))
            self.assertNotIn("4", uid)
            self.assertNotEqual(uid[0], "0")

    async def test_character_creation_flow(self):
        c, _ = await self.make(guest=True, github=False)
        d = await (await spost(c, "/api/guest", {})).json()
        self.assertFalse(d["user"]["hasCharacter"])
        self.assertNotIn("4", d["user"]["id"])
        ws = await sws(c, d, create_character=False)
        await ws.receive_json()  # welcome
        # 未创建角色：不能开房 / 匹配
        await ws.send_json({"t": "createRoom", "name": "x"})
        self.assertEqual((await self._reply(ws, "error"))["code"], "character_required")
        await ws.send_json({"t": "createCharacter", "name": "  ", "skin": 1, "hat": 0})
        self.assertEqual((await self._reply(ws, "error"))["code"], "name_invalid")
        await ws.send_json({"t": "createCharacter", "name": "【你妈的】断开连接", "skin": 1, "hat": 0})
        self.assertEqual((await self._reply(ws, "error"))["code"], "text_invalid")  # 全局文本规则先拦下
        await ws.send_json({"t": "createCharacter", "name": "系统公告", "skin": 1, "hat": 0})
        self.assertEqual((await self._reply(ws, "error"))["code"], "name_forbidden")
        await ws.send_json({"t": "createCharacter", "name": "疾风小队", "skin": 3, "hat": 2})  # 王冠未解锁 → 无头饰
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["name"], me["skin"], me["hat"], me["hasCharacter"]), ("疾风小队", 3, 0, True))
        # 只能创建一次（之后改名需要改名卡）
        await ws.send_json({"t": "createCharacter", "name": "再来一次"})
        self.assertEqual((await self._reply(ws, "error"))["code"], "character_exists")
        await ws.send_json({"t": "createRoom", "name": "x"})
        self.assertEqual((await self._reply(ws, "room", "error"))["t"], "room")
        # 重新登录后直接是已有角色
        d2 = await (await spost(c, "/api/login", {"id": d["user"]["id"]})).json()
        self.assertTrue(d2["user"]["hasCharacter"])
        self.assertEqual(d2["user"]["name"], "疾风小队")

    def test_avatar_url_whitelist(self):
        from backend.oauth import safe_avatar
        self.assertEqual(safe_avatar("https://avatars.githubusercontent.com/u/1?v=4"), "https://avatars.githubusercontent.com/u/1?v=4")
        for bad in ("https://evil.example/a.png", "http://avatars.githubusercontent.com/u/1", "javascript:alert(1)",
                    "https://avatars.githubusercontent.com/u/1\" onerror=\"x", None, 123):
            self.assertIsNone(safe_avatar(bad))

    async def test_config_endpoint(self):
        c, _ = await self.make(guest=False, github=True)
        self.assertEqual(await (await c.get("/login-info")).json(), {"guest": False, "github": True, "version": "1.0-beta"})

    async def test_guest_disabled_blocks_guest_and_id_login(self):
        c, _ = await self.make(guest=False, github=True)
        # 游客登录关闭：两个接口直接 404（连解密都不做）
        for path in ("/api/guest", "/api/login"):
            self.assertEqual((await c.post(path, json={})).status, 404, path)

    async def test_no_token_auto_login(self):
        # 不再下发 token；带 token 请求 /api/guest 也只会新建游客账号（token 字段不读取）
        on, _ = await self.make(guest=True, github=True)
        d = await (await spost(on, "/api/guest", {"name": "旧游客"})).json()
        self.assertNotIn("token", d)
        d2 = await (await spost(on, "/api/guest", {"token": "a" * 64})).json()
        self.assertTrue(d2["created"])
        self.assertNotEqual(d2["user"]["id"], d["user"]["id"])
        off, _ = await self.make(guest=False, github=True)
        self.assertEqual((await off.post("/api/guest", json={})).status, 404)

    async def test_github_full_flow(self):
        c, _ = await self.make(guest=False, github=True)
        code = await self.github_login(c)
        r = await spost(c, "/api/oauth/exchange", {"code": code})
        self.assertEqual(r.status, 200)
        d = await r.json()
        self.assertTrue(d["created"])
        self.assertEqual(d["user"]["provider"], "github")
        # 只保存 GitHub 用户 ID 与头像：不保存 GitHub 用户名，默认名字也不取 GitHub 用户名
        avatar = "https://avatars.githubusercontent.com/u/424242?v=4"
        self.assertIsNone(d["user"]["githubLogin"])
        self.assertEqual(d["user"]["avatar"], avatar)
        self.assertNotIn("octo", d["user"]["name"])
        con = await asyncpg.connect(TEST_DSN)
        row = await con.fetchrow("SELECT github_id, github_login, avatar_url FROM users WHERE id = $1", d["user"]["id"])
        await con.close()
        self.assertEqual(tuple(row), (424242, "", avatar))  # 数据库不存 NULL：没有值存 ''
        self.assertRegex(d["user"]["id"], r"^\d{8}$")
        # 交换码只能用一次
        self.assertEqual((await spost(c, "/api/oauth/exchange", {"code": code})).status, 401)
        # 不下发 token：GitHub 账号每次都要重新授权
        self.assertNotIn("token", d)
        # 再授权一次 → 回到同一个账号
        r = await spost(c, "/api/oauth/exchange", {"code": await self.github_login(c)})
        self.assertEqual((await r.json())["user"]["id"], d["user"]["id"])
        # session 可以连 WebSocket
        ws = await sws(c, d)
        msg = await ws.receive_json()
        self.assertEqual(msg["t"], "welcome")
        await ws.close()
        # 再次 GitHub 登录 → 同一个账号
        code2 = await self.github_login(c)
        d2 = await (await spost(c, "/api/oauth/exchange", {"code": code2})).json()
        self.assertFalse(d2["created"])
        self.assertEqual(d2["user"]["id"], d["user"]["id"])

    async def test_github_account_cannot_login_by_id(self):
        c, _ = await self.make(guest=True, github=True)
        code = await self.github_login(c)
        uid = (await (await spost(c, "/api/oauth/exchange", {"code": code})).json())["user"]["id"]
        r = await spost(c, "/api/login", {"id": uid})
        self.assertEqual(r.status, 404)

    async def test_state_is_verified(self):
        c, _ = await self.make(guest=False, github=True)
        r = await c.get("/oauth/callback?code=good-code&state=forged", allow_redirects=False)
        self.assertIn("oauth_error=state", r.headers["Location"])

    async def test_github_disabled(self):
        c, _ = await self.make(guest=True, github=False)
        # GitHub 登录关闭：相关接口直接 404
        self.assertEqual((await c.get("/auth/github", allow_redirects=False)).status, 404)
        self.assertEqual((await c.get("/oauth/callback?code=x&state=y", allow_redirects=False)).status, 404)
        self.assertEqual((await c.post("/api/oauth/exchange", json={})).status, 404)

    async def test_rest_errors_have_code_only(self):
        c, _ = await self.make(guest=True, github=True)
        r = await spost(c, "/api/login", {"id": "12345678"})
        self.assertEqual(await r.json(), {"code": "unknown_id"})
        r = await c.post("/api/login", json={"id": "12345678"})  # 未加密的请求
        self.assertEqual(await r.json(), {"code": "bad_request"})

    async def test_language_saved_on_account(self):
        c, _ = await self.make(guest=True, github=True)
        d = await (await spost(c, "/api/guest", {"lang": "ja"})).json()
        self.assertEqual(d["user"]["lang"], "ja")
        self.assertTrue(d["user"]["name"].startswith("Guest"))  # 名字只允许中文 / 英文字母 / 数字
        # 修改语言 → 写回该账号记录
        ws = await sws(c, d)
        await ws.receive_json()
        await ws.send_json({"t": "profile", "lang": "zh-HK"})  # 含 - ：整条拒绝
        self.assertEqual((await self._reply(ws, "error"))["code"], "text_invalid")
        await ws.send_json({"t": "profile", "lang": "zhHK"})  # 客户端上报用 zhHK
        while (m := await ws.receive_json())["t"] != "me":
            pass
        self.assertEqual(m["user"]["lang"], "zh-HK")
        await ws.send_json({"t": "profile", "lang": "fr"})  # 不支持的语言被忽略
        while (m := await ws.receive_json())["t"] != "me":
            pass
        self.assertEqual(m["user"]["lang"], "zh-HK")
        await ws.close()
        import asyncio
        await asyncio.sleep(0.2)
        con = await asyncpg.connect(TEST_DSN)
        self.assertEqual(await con.fetchval("SELECT lang FROM users WHERE id = $1", d["user"]["id"]), "zh-HK")
        await con.close()
        # 账号已有语言时，登录时客户端的语言不会覆盖它
        d2 = await (await spost(c, "/api/login", {"id": d["user"]["id"], "lang": "en"})).json()
        self.assertEqual(d2["user"]["lang"], "zh-HK")

    async def test_github_lang_from_state(self):
        c, _ = await self.make(guest=False, github=True)
        r = await c.get("/auth/github?lang=en", allow_redirects=False)
        state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
        r = await c.get(f"/oauth/callback?code=good-code&state={state}", allow_redirects=False)
        code = r.headers["Location"].split("#oauth=", 1)[1]
        d = await (await spost(c, "/api/oauth/exchange", {"code": code})).json()
        self.assertEqual(d["user"]["lang"], "en")

    async def test_hat_unlock_by_level(self):
        c, _ = await self.make(guest=True, github=False)
        d = await (await spost(c, "/api/guest", {"hat": 2})).json()  # 王冠需要 Lv12
        self.assertEqual(d["user"]["hat"], 0)
        ws = await sws(c, d)
        await ws.receive_json()
        await ws.send_json({"t": "profile", "hat": 1})  # 头带需要 Lv2，Lv1 不能装备
        while (m := await ws.receive_json())["t"] != "me":
            pass
        self.assertEqual(m["user"]["hat"], 0)
        con = await asyncpg.connect(TEST_DSN)
        await con.execute("UPDATE users SET exp = 150 WHERE id = $1", d["user"]["id"])  # Lv2（100 起）
        await con.close()
        from backend import store
        store._users[d["user"]["id"]]["exp"] = 150
        await ws.send_json({"t": "profile", "hat": 1})
        while (m := await ws.receive_json())["t"] != "me":
            pass
        self.assertEqual(m["user"]["hat"], 1)
        self.assertEqual(m["user"]["level"], 2)
        await ws.close()

    def test_rewards(self):
        from backend.store import reward_for
        win, _ = reward_for(True, 0, 0, 1)
        self.assertEqual(reward_for(True, 2, 1, 1), (100 + 20 + 10, 10 + 8 + 2))
        for kills, rescues in [(0, 0), (3, 2), (8, 4)]:
            lose, points = reward_for(False, kills, rescues, 2)
            full, full_pts = reward_for(True, kills, rescues, 1)
            self.assertLess(lose, full * 0.2, "失败经验应少于胜利的 20%")
            self.assertGreaterEqual(points, round(full_pts * 0.15))
            self.assertLessEqual(points, round(full_pts * 0.35))

    def test_level_curve(self):
        from backend.store import default_level_table, level_of
        t = default_level_table()
        self.assertEqual(len(t), 50)
        self.assertEqual([r[1] for r in t[:5]], [0, 100, 250, 450, 700])
        need = [t[i + 1][1] - t[i][1] for i in range(len(t) - 1)]
        self.assertTrue(all(b > a for a, b in zip(need, need[1:])), "每级所需经验应逐级递增")
        self.assertEqual([level_of(x) for x in (0, 99, 100, 249, 250, 700)], [1, 1, 2, 2, 3, 5])
        # 无上限：50 级之后按同一曲线继续（每级 +50）
        from backend.store import level_exp
        self.assertEqual(level_exp(50), 63700)
        self.assertEqual(level_exp(51), 63700 + 2550)
        self.assertEqual(level_exp(52), 63700 + 2550 + 2600)
        for lv in (50, 51, 52, 60, 100, 300):
            self.assertEqual(level_of(level_exp(lv)), lv)
            self.assertEqual(level_of(level_exp(lv) - 1), lv - 1)
        self.assertGreater(level_of(10 ** 9), 50)

    async def test_bb_level_sql_matches_python(self):
        await self.make(guest=True, github=False)
        from backend.store import level_exp, level_of
        con = await asyncpg.connect(TEST_DSN)
        try:
            for e in [0, 99, 100, 63699, 63700, 66249, 66250, level_exp(77), level_exp(77) - 1, level_exp(250) + 5, 2_000_000_000]:
                self.assertEqual(await con.fetchval("SELECT bb_level($1)", e), level_of(e), e)
        finally:
            await con.close()

    def test_points_formula(self):
        from backend.store import points_for, streak_bonus
        self.assertEqual(points_for(True, 0, 0), 10)
        self.assertEqual(points_for(True, 3, 1), 10 + 12 + 2)
        self.assertEqual(points_for(False, 5, 3, loss_pct=20), round((10 + 20 + 6) * 0.2))
        # 连杀：每人 +5%，最多 +30%，只有获胜才有
        self.assertEqual([streak_bonus(True, n) for n in (0, 1, 2, 3, 6, 9)], [0, 5, 10, 15, 30, 30])
        self.assertEqual(streak_bonus(False, 4), 0)

    async def test_bonus_adds_up_with_card(self):
        """连杀 +30% 与双倍点数卡 +100% 直接相加 = 230%，不是相乘的 260%。"""
        import time as _t
        from backend import store
        c, _ = await self.make(guest=True, github=False)
        uid, ws, _w = await self._shop_user(c, 0, 0)
        store._users[uid]["pointsBoost"], store._users[uid]["pointsBoostUntil"] = 200, int(_t.time() * 1000) + 60_000
        result = {"mode": "ffa", "revive": True, "mapId": "meadow", "draw": False, "winnerTeam": 0, "duration": 60, "players": [
            {"id": uid, "isBot": False, "team": 0, "kills": 6, "rescues": 0, "alive": True, "place": 1, "win": True, "quit": False,
             "streak": 6, "rankBonus": 25},
        ]}
        store.record_match(result)
        await asyncio.gather(*store._bg)
        p = result["players"][0]
        base = store.points_for(True, 6, 0)
        self.assertEqual(p["bonus"], {"streak": 30, "rank": 25, "card": 100})
        self.assertEqual(p["pointsPct"], 255)
        self.assertEqual(p["points"], base * 255 // 100)
        await ws.close()

    async def test_coins_merged_into_points(self):
        """旧库里的金币按 5:1 并入点数，金币列被删除，排行榜索引按新定义重建。"""
        con = await asyncpg.connect(TEST_DSN)
        await con.execute("DROP TABLE IF EXISTS boost_purchases, bomb_purchases, user_items, cosmetics, match_players, login_tokens, matches, levels, meta, users CASCADE")
        await con.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, skin SMALLINT NOT NULL DEFAULT 0, hat SMALLINT NOT NULL DEFAULT 0, "
                          "exp INTEGER NOT NULL DEFAULT 0, coins INTEGER NOT NULL DEFAULT 0, games INTEGER NOT NULL DEFAULT 0, "
                          "wins INTEGER NOT NULL DEFAULT 0, kills INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                          "last_seen TIMESTAMPTZ NOT NULL DEFAULT now())")
        await con.execute("CREATE INDEX users_leaderboard ON users (wins DESC) INCLUDE (coins)")
        await con.execute("INSERT INTO users (id, name, coins, games, wins) VALUES ('12345678', 'old', 420, 3, 2)")
        await con.close()
        await self.make(guest=True, github=False)  # 启动时执行 init.sql 迁移
        con = await asyncpg.connect(TEST_DSN)
        try:
            self.assertEqual(await con.fetchval("SELECT points FROM users WHERE id = '12345678'"), 84)
            self.assertFalse(await con.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'coins')"))
            idx = await con.fetchval("SELECT indexdef FROM pg_indexes WHERE indexname = 'users_leaderboard'")
            self.assertIn("games > 0", idx)
            self.assertNotIn("coins", idx)
        finally:
            await con.close()

    async def test_quitter_gets_no_rewards(self):
        c, _ = await self.make(guest=True, github=False)
        from backend import store
        win = (await (await spost(c, "/api/guest", {})).json())["user"]
        quit_ = (await (await spost(c, "/api/guest", {})).json())["user"]
        result = {"mode": "team", "mapId": "meadow", "draw": False, "winnerTeam": 0, "duration": 60, "players": [
            {"id": win["id"], "isBot": False, "team": 0, "kills": 2, "rescues": 0, "alive": True, "place": 1, "win": True, "quit": False},
            {"id": quit_["id"], "isBot": False, "team": 0, "kills": 3, "rescues": 1, "alive": False, "place": 2, "win": False, "quit": True},
        ]}
        store.record_match(result)
        await asyncio.gather(*store._bg)
        q = result["players"][1]
        self.assertEqual((q["exp"], q["points"]), (0, 0))
        self.assertGreater(result["players"][0]["points"], 0)
        con = await asyncpg.connect(TEST_DSN)
        try:
            row = await con.fetchrow("SELECT games, wins, kills, exp, points FROM users WHERE id = $1", quit_["id"])
            self.assertEqual(tuple(row), (1, 0, 0, 0, 0))  # 只记一局，不计胜场、击倒、经验、点数
            mp = await con.fetchrow("SELECT exp_gained, points_gained FROM match_players WHERE user_id = $1", quit_["id"])
            self.assertEqual(tuple(mp), (0, 0))
        finally:
            await con.close()

    async def test_rename_requires_card(self):
        c, _ = await self.make(guest=True, github=False)
        from backend import store
        uid, ws, welcome = await self._shop_user(c, 0, 250)
        self.assertEqual(welcome["renameCardPrice"], 100)
        old = welcome["user"]["name"]
        # 没有更名卡：改名被拒绝；装扮保存、重新登录都不能改名
        await ws.send_json({"t": "rename", "name": "新名字"})
        self.assertEqual((await self._reply(ws, "error"))["code"], "rename_no_card")
        await ws.send_json({"t": "profile", "name": "偷偷改名", "skin": 2})
        self.assertEqual((await self._reply(ws, "me"))["user"]["name"], old)
        # 买 2 张更名卡（每张 100 点）
        for _ in range(2):
            await ws.send_json({"t": "buy", "item": "rename"})
            self.assertEqual((await self._reply(ws, "bought", "error"))["item"], "rename")
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["renameCards"]), (50, 2))
        await ws.send_json({"t": "buy", "item": "rename"})
        self.assertEqual((await self._reply(ws, "error"))["code"], "item_points")
        # 同名 / 空名不消耗卡
        await ws.send_json({"t": "rename", "name": old})
        self.assertEqual((await self._reply(ws, "error"))["code"], "name_same")
        await ws.send_json({"t": "rename", "name": "   "})
        self.assertEqual((await self._reply(ws, "error"))["code"], "name_invalid")
        # 改名消耗 1 张
        await ws.send_json({"t": "rename", "name": "新名字"})
        self.assertEqual((await self._reply(ws, "renamed"))["name"], "新名字")
        self.assertEqual((await self._reply(ws, "me"))["user"]["renameCards"], 1)
        # 并发两次改名，只剩 1 张卡 → 只能成功一次
        u = store._users[uid]
        res = await asyncio.gather(store.rename(u, "甲"), store.rename(u, "乙"), return_exceptions=True)
        self.assertEqual(sum(not isinstance(r, Exception) for r in res), 1)
        con = await asyncpg.connect(TEST_DSN)
        try:
            row = await con.fetchrow("SELECT name, rename_cards, points FROM users WHERE id = $1", uid)
            self.assertEqual((row["rename_cards"], row["points"]), (0, 50))
            self.assertIn(row["name"], ("甲", "乙"))
            log = await con.fetch("SELECT old_name, new_name FROM name_changes WHERE user_id = $1 ORDER BY id", uid)
            self.assertEqual([(r["old_name"], r["new_name"]) for r in log][0], (old, "新名字"))
            self.assertEqual(len(log), 2)
        finally:
            await con.close()

    async def test_relogin_cannot_rename(self):
        c, _ = await self.make(guest=True, github=False)
        d = await (await spost(c, "/api/guest", {"name": "初始名"})).json()
        self.assertEqual(d["user"]["name"], "初始名")
        d2 = await (await spost(c, "/api/login", {"id": d["user"]["id"], "name": "换个名"})).json()
        self.assertEqual(d2["user"]["name"], "初始名")

    async def _shop_user(self, c, exp, points):
        d = await (await spost(c, "/api/guest", {})).json()
        uid = d["user"]["id"]
        con = await asyncpg.connect(TEST_DSN)
        await con.execute("UPDATE users SET exp = $2, points = $3 WHERE id = $1", uid, exp, points)
        await con.close()
        from backend import store
        store._users[uid]["exp"], store._users[uid]["points"] = exp, points
        ws = await sws(c, d)
        welcome = await ws.receive_json()
        return uid, ws, welcome

    async def _reply(self, ws, *types):
        while (m := await ws.receive_json())["t"] not in types:
            pass
        return m

    async def test_bomb_style_purchase(self):
        import time as _t
        c, _ = await self.make(guest=True, github=False)
        uid, ws, welcome = await self._shop_user(c, 0, 450)
        self.assertEqual(welcome["bombShop"], {"styles": [{"id": st, "price": 200, "days": 7} for st in ("poison", "water", "gold")]})
        self.assertEqual(welcome["user"]["bomb"], {"style": "", "until": 0})
        # 买毒弹：扣 200 点，立即生效 7 天
        await ws.send_json({"t": "buy", "item": "poison"})
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["bomb"]["style"]), (250, "poison"))
        week = 7 * 86400 * 1000
        self.assertLess(abs(me["bomb"]["until"] - (_t.time() * 1000 + week)), 60_000)
        # 再买水弹：覆盖毒弹，有效期从现在重新算 7 天
        await ws.send_json({"t": "buy", "item": "water"})
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["bomb"]["style"]), (50, "water"))
        # 点数不足
        await ws.send_json({"t": "buy", "item": "gold"})
        self.assertEqual((await self._reply(ws, "error"))["code"], "item_points")
        con = await asyncpg.connect(TEST_DSN)
        try:
            row = await con.fetchrow("SELECT points, bomb_style FROM users WHERE id = $1", uid)
            self.assertEqual(tuple(row), (50, "water"))
            self.assertEqual(await con.fetchval("SELECT count(*) FROM bomb_purchases WHERE user_id = $1", uid), 2)
        finally:
            await con.close()
        # 过期：自动恢复普通火焰
        from backend import store
        store._users[uid]["bombUntil"] = int(_t.time() * 1000) - 1
        self.assertEqual(store.public_user(store._users[uid])["bomb"], {"style": "", "until": 0})
        await ws.close()

    async def test_boost_cards(self):
        import time as _t
        from backend import store
        c, _ = await self.make(guest=True, github=False)
        uid, ws, welcome = await self._shop_user(c, 0, 1180)
        self.assertEqual([(x["id"], x["price"], x["hours"]) for x in welcome["boostShop"]["cards"]],
                         [("exp150", 160, 24), ("exp200", 220, 24), ("exp300", 300, 24), ("pts150", 200, 24), ("pts200", 280, 24), ("pts300", 360, 24)])
        self.assertEqual(welcome["user"]["boosts"], {})
        day = 24 * 3600 * 1000
        # 双倍经验卡：220 点，24 小时
        await ws.send_json({"t": "buy", "item": "exp200"})
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["boosts"]["exp"]["pct"]), (960, 200))
        until1 = me["boosts"]["exp"]["until"]
        self.assertLess(abs(until1 - (_t.time() * 1000 + day)), 60_000)
        # 同一倍率再买：顺延 24 小时
        await ws.send_json({"t": "buy", "item": "exp200"})
        me = (await self._reply(ws, "me"))["user"]
        self.assertLess(abs(me["boosts"]["exp"]["until"] - (until1 + day)), 5_000)
        # 不同倍率：立即替换，从现在起 24 小时
        await ws.send_json({"t": "buy", "item": "exp150"})
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["boosts"]["exp"]["pct"]), (580, 150))
        self.assertLess(abs(me["boosts"]["exp"]["until"] - (_t.time() * 1000 + day)), 60_000)
        # 3 倍点数卡（360）：和经验卡互不影响
        await ws.send_json({"t": "buy", "item": "pts300"})
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["boosts"]["points"]["pct"], me["boosts"]["exp"]["pct"]), (220, 300, 150))
        await ws.send_json({"t": "buy", "item": "pts200"})
        self.assertEqual((await self._reply(ws, "error"))["code"], "item_points")
        # 结算：经验 ×1.5，点数 ×3
        result = {"mode": "ffa", "mapId": "meadow", "draw": False, "winnerTeam": None, "duration": 60, "players": [
            {"id": uid, "isBot": False, "team": 0, "kills": 2, "rescues": 0, "alive": True, "place": 1, "win": True, "quit": False},
        ]}
        store.record_match(result)
        await asyncio.gather(*store._bg)
        p = result["players"][0]
        exp0, pts0 = store.reward_for(True, 2, 0)
        self.assertEqual((p["exp"], p["points"], p["expBoost"], p["pointsPct"]), (exp0 * 3 // 2, pts0 * 3, 150, 300))
        self.assertEqual(p["bonus"], {"card": 200})
        con = await asyncpg.connect(TEST_DSN)
        try:
            self.assertEqual(await con.fetchval("SELECT points FROM users WHERE id = $1", uid), 220 + pts0 * 3)
            self.assertEqual(await con.fetchval("SELECT count(*) FROM boost_purchases WHERE user_id = $1", uid), 4)
        finally:
            await con.close()
        # 到期：加成消失
        store._users[uid]["expBoostUntil"] = int(_t.time() * 1000) - 1
        self.assertNotIn("exp", store.public_user(store._users[uid])["boosts"])
        self.assertEqual(store.active_boost(store._users[uid], "exp"), 100)
        await ws.close()

    def test_store_items_availability(self):
        """store_item.json：price = -1、缺少该 ID、内容与 ID 对不上 → 物品不可用；其他物品不受影响。"""
        import json as _json
        import tempfile
        from pathlib import Path as _P
        from backend import store
        good = _json.loads(store.STORE_ITEMS_FILE.read_text(encoding="utf-8"))
        cfg = dict(good)
        cfg["exp150"] = {**good["exp150"], "pct": 200}  # 名字对不上
        cfg["pts300"] = {**good["pts300"], "price": -1}  # 价格 -1
        cfg["rename"] = {"price": "100"}  # 格式不对
        del cfg["water"]  # 缺少
        cfg["mystery"] = {"price": 1}  # 未知商品：忽略
        with tempfile.TemporaryDirectory() as d:
            f = _P(d) / "store_item.json"
            f.write_text(_json.dumps(cfg), encoding="utf-8")
            items = store.load_store_items(f)
            self.assertEqual({k: v["price"] for k, v in items.items()}, {
                "rename": None, "poison": 200, "water": None, "gold": 200,
                "exp150": None, "exp200": 220, "exp300": 300, "pts150": 200, "pts200": 280, "pts300": None})
            f.write_text("{ not json", encoding="utf-8")
            self.assertTrue(all(v["price"] is None for v in store.load_store_items(f).values()))

    async def test_unavailable_item_cannot_be_bought(self):
        from backend import store
        c, _ = await self.make(guest=True, github=False)
        uid, ws, welcome = await self._shop_user(c, 0, 1000)
        old = dict(store.STORE_ITEMS["exp200"])
        store.STORE_ITEMS["exp200"]["price"] = None
        try:
            await ws.send_json({"t": "buy", "item": "exp200"})
            self.assertEqual((await self._reply(ws, "error"))["code"], "item_unavailable")
        finally:
            store.STORE_ITEMS["exp200"] = old
        con = await asyncpg.connect(TEST_DSN)
        try:
            self.assertEqual(await con.fetchval("SELECT points FROM users WHERE id = $1", uid), 1000)
        finally:
            await con.close()
        await ws.close()

    async def test_shop_purchase_rules(self):
        c, _ = await self.make(guest=True, github=False)
        from backend.store import level_exp
        uid, ws, welcome = await self._shop_user(c, level_exp(10), 200)
        shop = {i["id"]: i for i in welcome["shop"]}
        self.assertEqual(len(shop), 12)
        self.assertEqual({lv: sum(1 for i in shop.values() if i["level"] == lv) for lv in (10, 20, 30, 40, 50)},
                         {10: 3, 20: 3, 30: 2, 40: 2, 50: 2})
        # 等级不够
        await ws.send_json({"t": "buy", "item": 9})
        self.assertEqual((await self._reply(ws, "error"))["code"], "item_level")
        # 买 Lv10 的贝雷帽：扣 150 点并自动装备
        await ws.send_json({"t": "buy", "item": 6})
        self.assertEqual((await self._reply(ws, "bought", "error"))["t"], "bought")
        me = (await self._reply(ws, "me"))["user"]
        self.assertEqual((me["points"], me["hat"], me["items"]), (50, 6, [6]))
        # 重复购买 / 点数不足
        await ws.send_json({"t": "buy", "item": 6})
        self.assertEqual((await self._reply(ws, "error"))["code"], "item_owned")
        await ws.send_json({"t": "buy", "item": 7})
        self.assertEqual((await self._reply(ws, "error"))["code"], "item_points")
        # 未购买的装饰不能装备
        await ws.send_json({"t": "profile", "hat": 8})
        self.assertEqual((await self._reply(ws, "me"))["user"]["hat"], 6)
        con = await asyncpg.connect(TEST_DSN)
        row = await con.fetchrow("SELECT points, hat FROM users WHERE id = $1", uid)
        items = await con.fetch("SELECT item_id, price_paid FROM user_items WHERE user_id = $1", uid)
        await con.close()
        self.assertEqual((row["points"], row["hat"]), (50, 6))
        self.assertEqual([(r["item_id"], r["price_paid"]) for r in items], [(6, 150)])

    async def test_shop_concurrent_buys_never_overspend(self):
        c, _ = await self.make(guest=True, github=False)
        from backend import store
        from backend.store import level_exp
        uid, ws, _ = await self._shop_user(c, level_exp(10), 300)  # 只够买 2 件
        u = store._users[uid]
        res = await asyncio.gather(*(store.buy_item(u, i) for i in (6, 7, 8, 6)), return_exceptions=True)
        ok = [r for r in res if not isinstance(r, Exception)]
        self.assertLessEqual(len(ok), 2)
        con = await asyncpg.connect(TEST_DSN)
        pts = await con.fetchval("SELECT points FROM users WHERE id = $1", uid)
        n = await con.fetchval("SELECT count(*) FROM user_items WHERE user_id = $1", uid)
        await con.close()
        self.assertEqual(pts, 300 - 150 * n)
        self.assertGreaterEqual(pts, 0)

    async def test_levels_and_match_rows_in_db(self):
        c, _ = await self.make(guest=True, github=False)
        con = await asyncpg.connect(TEST_DSN)
        rows = await con.fetch("SELECT level, exp_required, tier, unlock_hat FROM levels ORDER BY level")
        self.assertEqual(len(rows), 50)
        self.assertEqual(rows[1]["unlock_hat"], 1)  # Lv2 解锁战术头带
        self.assertEqual(rows[11]["unlock_hat"], 2)  # Lv12 解锁王冠
        self.assertEqual(rows[39]["tier"], 6)  # Lv40 大师
        await con.close()

    def test_init_sql_levels_match_curve(self):
        from backend.store import default_level_table, schema_sql
        sql = schema_sql()
        rows = [tuple(int(x) if x != "NULL" else None for x in m) for m in re.findall(r"\(\s*(\d+),\s*(\d+),\s*(\d+),\s*(NULL|\d+)\)", sql)]
        self.assertEqual(rows, default_level_table())

    async def test_cleanup_tokens_batched(self):
        c, _ = await self.make(guest=True, github=False)
        d = await (await spost(c, "/api/guest", {})).json()
        con = await asyncpg.connect(TEST_DSN)
        await con.execute(
            """INSERT INTO login_tokens (token_hash, user_id, created_at, used_at)
               SELECT md5(g::text), $1, now() - interval '200 days', CASE WHEN g % 2 = 0 THEN now() - interval '40 days' ELSE 'epoch' END
               FROM generate_series(1, 1200) g""", d["user"]["id"])
        await con.close()
        from backend import store
        self.assertEqual(await store.cleanup_tokens(batch=100), 1200)
        # 账号本身不受影响
        self.assertEqual((await spost(c, "/api/login", {"id": d["user"]["id"]})).status, 200)

    def test_env_defaults(self):
        for k in ("LOGIN_GUEST", "LOGIN_GITHUB", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"):
            os.environ.pop(k, None)
        os.environ.update(LOGIN_GITHUB="true", GITHUB_CLIENT_ID="a", GITHUB_CLIENT_SECRET="b")
        try:
            cfg = Config.from_env()
            self.assertTrue(cfg.login_github)
            self.assertFalse(cfg.login_guest, "未设置 LOGIN_GUEST 时不允许游客 / ID 登录")
            os.environ["LOGIN_GUEST"] = "true"
            self.assertTrue(Config.from_env().login_guest)
            # 两个都关闭：无法启动
            os.environ["LOGIN_GUEST"] = "false"
            os.environ["LOGIN_GITHUB"] = "false"
            with self.assertRaises(SystemExit):
                Config.from_env().check()
        finally:
            for k in ("LOGIN_GUEST", "LOGIN_GITHUB", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"):
                os.environ.pop(k, None)


class NoNullTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_columns_not_null(self):
        from backend import store
        con = await asyncpg.connect(TEST_DSN)
        try:
            await con.execute("DROP TABLE IF EXISTS boost_purchases, bomb_purchases, user_items, cosmetics, match_players, login_tokens, matches, levels, meta, users, name_changes CASCADE")
        finally:
            await con.close()
        await store.init(TEST_DSN)
        try:
            con = await asyncpg.connect(TEST_DSN)
            try:
                rows = await con.fetch(
                    """SELECT table_name, column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND is_nullable = 'YES'
                         AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema())""")
                self.assertEqual([tuple(r) for r in rows], [], "所有字段都必须 NOT NULL")
            finally:
                await con.close()
        finally:
            await store.close()

    async def test_old_nullable_schema_migrated(self):
        # 旧库：列可为空且有 NULL 数据 → 启动时自动改成 '' / 0 / 'epoch' / -1 并加 NOT NULL
        from backend import store
        con = await asyncpg.connect(TEST_DSN)
        try:
            await con.execute("DROP TABLE IF EXISTS boost_purchases, bomb_purchases, user_items, cosmetics, match_players, login_tokens, matches, levels, meta, users, name_changes CASCADE")
            await con.execute("""
                CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, skin SMALLINT NOT NULL DEFAULT 0,
                    hat SMALLINT NOT NULL DEFAULT 0, games INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
                    kills INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(), github_id BIGINT, github_login TEXT,
                    avatar_url TEXT, lang TEXT);
                CREATE UNIQUE INDEX users_github_id ON users (github_id) WHERE github_id IS NOT NULL;
                INSERT INTO users (id, name) VALUES ('12345678', 'a'), ('23456789', 'b');
                CREATE TABLE login_tokens (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), used_at TIMESTAMPTZ);
                INSERT INTO login_tokens (token_hash, user_id) VALUES ('h', '12345678');
                CREATE TABLE matches (id BIGSERIAL PRIMARY KEY, map_id TEXT NOT NULL, mode TEXT NOT NULL,
                    duration INTEGER NOT NULL, winner_team INTEGER, result JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), match_key TEXT);
                CREATE UNIQUE INDEX matches_key ON matches (match_key) WHERE match_key IS NOT NULL;
                INSERT INTO matches (map_id, mode, duration, result) VALUES ('meadow', 'ffa', 60, '{}'), ('meadow', 'ffa', 60, '{}');
            """)
        finally:
            await con.close()
        await store.init(TEST_DSN)
        await store.close()
        con = await asyncpg.connect(TEST_DSN)
        try:
            u = await con.fetchrow("SELECT github_id, github_login, avatar_url, lang FROM users WHERE id = '12345678'")
            self.assertEqual(tuple(u), (0, "", "", ""))
            self.assertEqual(str((await con.fetchval("SELECT used_at FROM login_tokens"))).startswith("1970-01-01"), True)
            self.assertEqual(await con.fetchval("SELECT array_agg(DISTINCT winner_team) FROM matches"), [-1])
            self.assertEqual(await con.fetchval("SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() AND is_nullable = 'YES' AND table_name IN ('users', 'login_tokens', 'matches', 'levels')"), 0)
        finally:
            await con.close()


if __name__ == "__main__":
    unittest.main()
