"""道具玩法：道具栏、五种道具的效果、AI 捡 / 用道具、房间设置（道具开关、时间限制）。"""
import random
import unittest

from backend import bot
from backend.game import (BASE_SPEED, FLAME_TIME, BOOTS_SPEED_LV, SPEED_STEP, TICK_RATE, Bomb, Flame, Game,
                          pick_powerup)


def game(players=None, seed=1, **kw):
    players = players or [{"id": "a", "name": "a", "skin": 0, "hat": 0, "is_bot": False},
                          {"id": "b", "name": "b", "skin": 1, "hat": 0, "is_bot": False}]
    g = Game("meadow", "ffa", 1, players, rng=random.Random(seed), **kw)
    g.phase = "play"
    g.shrink = False
    for i in range(g.W * g.H):  # 空地，外圈是墙
        x, y = i % g.W, i // g.W
        g.blocks[i] = "#" if x in (0, g.W - 1) or y in (0, g.H - 1) else "."
    g.tele = {}
    for p in g.players:
        p.invuln = 0
    g.players[0].x, g.players[0].y = 3.0, 3.0
    if len(g.players) > 1:
        g.players[1].x, g.players[1].y = 15.0, 15.0
    return g


def drop(g, x, y, kind):
    g.powerups[y * g.W + x] = kind


def step(g, n=1):
    for _ in range(n):
        g.update(1 / TICK_RATE)


class InventoryTests(unittest.TestCase):
    def test_first_empty_slot_and_full(self):
        g = game()
        a = g.players[0]
        drop(g, 3, 3, "needle")
        step(g)
        drop(g, 3, 3, "boots")
        step(g)
        self.assertEqual(a.items[:3], ["needle", "boots", ""])
        # 用掉第 1 格，下次捡到的放回第 1 格
        a.trapped = 5.0
        self.assertTrue(g.use_item("a", 0))
        self.assertEqual(a.items[0], "")
        a.invuln = 0
        drop(g, 3, 3, "ghost")
        step(g)
        self.assertEqual(a.items[:2], ["ghost", "boots"])
        # 6 格满了：捡不起来，道具留在地上
        a.items = ["wings"] * 6
        drop(g, 3, 3, "ishield")
        step(g)
        self.assertEqual(g.powerups.get(3 * g.W + 3), "ishield")

    def test_needle_only_when_trapped(self):
        g = game()
        a = g.players[0]
        a.items[0] = "needle"
        self.assertFalse(g.use_item("a", 0))  # 没被困：不能用，道具保留
        self.assertEqual(a.items[0], "needle")
        a.trapped = 6.0
        self.assertTrue(g.use_item("a", 0))
        self.assertEqual(a.trapped, 0)
        self.assertTrue(a.alive)

    def test_other_items_not_usable_when_trapped(self):
        g = game()
        a = g.players[0]
        a.items[0] = "ishield"
        a.trapped = 6.0
        self.assertFalse(g.use_item("a", 0))
        self.assertEqual(a.items[0], "ishield")

    def test_invincible_shield_blocks_for_3s(self):
        g = game()
        a = g.players[0]
        a.items[0] = "ishield"
        self.assertTrue(g.use_item("a", 0))
        g.flames = {3 * g.W + 3: Flame(FLAME_TIME, 16, "b")}
        step(g, 5)
        self.assertEqual(a.trapped, 0)  # 3 秒内被炸到：什么都不会发生
        step(g, int(3.2 * TICK_RATE))
        g.flames = {3 * g.W + 3: Flame(FLAME_TIME, 16, "b")}
        step(g, 2)
        self.assertGreater(a.trapped, 0)  # 3 秒后照常被困

    def test_boots_speed(self):
        g = game()
        a = g.players[0]
        a.items[0] = "boots"
        base = g.player_speed(a)
        self.assertTrue(g.use_item("a", 0))
        self.assertAlmostEqual(g.player_speed(a), BASE_SPEED * (1 + SPEED_STEP * BOOTS_SPEED_LV))
        self.assertGreater(g.player_speed(a), base)
        step(g, int(5.2 * TICK_RATE))
        self.assertAlmostEqual(g.player_speed(a), base)

    def test_wings_pass_bombs_but_flames_still_hit(self):
        g = game()
        a = g.players[0]
        g.bombs = [Bomb(1, "b", 1, 4, 3, 4.0, 3.0, 9.0, 1)]
        a.move_budget = 5
        self.assertFalse(g.client_move("a", 4.5, 3.0, epoch=a.fix))  # 没有翅膀：被炸弹挡住
        a.items[0] = "wings"
        g.use_item("a", 0)
        a.move_budget = 5
        self.assertTrue(g.client_move("a", 4.5, 3.0, epoch=a.fix))
        a.x, a.y = 5.0, 3.0
        g.flames = {3 * g.W + 5: Flame(FLAME_TIME, 16, "b")}
        step(g, 12)  # 客户端移动的玩家：命中要等延迟补偿窗口结束才确认
        self.assertGreater(a.trapped, 0)

    def test_snapshot_fields(self):
        g = game()
        a = g.players[0]
        a.items[1] = "ghost"
        g.use_item("a", 1)
        me = next(p for p in g.snapshot()["p"] if p["id"] == "a")
        self.assertEqual(me["it"], ",,,,,")
        self.assertGreater(me["gh"], 9)

    def test_items_off(self):
        rng = random.Random(1)
        kinds = {pick_powerup(rng, items=False) for _ in range(3000)}
        self.assertFalse(kinds & {"needle", "ishield", "boots", "ghost", "wings"})
        rng = random.Random(1)
        self.assertTrue({pick_powerup(rng) for _ in range(3000)} >= {"needle", "ishield", "boots", "ghost", "wings"})


class BotItemTests(unittest.TestCase):
    def bots(self, *levels):
        players = [{"id": f"p{i}", "name": "x", "skin": i, "hat": 0, "is_bot": True, "ai": lv} for i, lv in enumerate(levels)]
        return game(players)

    def test_easy_picks_up_on_contact_but_never_uses(self):
        g = self.bots("easy", "easy")
        e = g.players[0]
        drop(g, 3, 3, "boots")
        step(g)
        self.assertEqual(e.items[0], "boots")  # 碰到就捡起来
        g._claim_item(3 * g.W + 5)
        self.assertNotIn(3 * g.W + 5, g.item_claims)  # 但不会专门去捡
        e.items = ["needle", "ishield", "boots", "ghost", "wings", ""]
        e.trapped = 6.0
        for _ in range(3 * TICK_RATE):
            bot.think(g, e, 1 / TICK_RATE)
        self.assertEqual(e.items, ["needle", "ishield", "boots", "ghost", "wings", ""])  # 也不会用

    def test_normal_rolls_50_percent(self):
        hits = 0
        for seed in range(400):
            g = self.bots("normal", "easy")
            g.rng = random.Random(seed)
            g._claim_item(5 * g.W + 3)  # 离 p0（3,3）最近
            hits += g.item_claims.get(5 * g.W + 3) == "p0"
        self.assertTrue(150 < hits < 250, hits)

    def test_hard_uses_needle_when_trapped(self):
        g = self.bots("hard", "easy")
        h = g.players[0]
        h.items[0] = "needle"
        h.trapped = 6.0
        bot.think(g, h, 1 / TICK_RATE)
        self.assertEqual(h.trapped, 0)
        self.assertEqual(h.items[0], "")

    def test_normal_never_uses_needle(self):
        g = self.bots("normal", "easy")
        n = g.players[0]
        n.items[0] = "needle"
        n.trapped = 6.0
        bot.think(g, n, 1 / TICK_RATE)
        self.assertGreater(n.trapped, 0)

    def test_ghost_vision(self):
        g = self.bots("normal", "hard")
        target = {"id": "t", "name": "t", "skin": 2, "hat": 0, "is_bot": False}
        g = game([{"id": "n", "name": "n", "skin": 0, "hat": 0, "is_bot": True, "ai": "normal"},
                  {"id": "h", "name": "h", "skin": 1, "hat": 0, "is_bot": True, "ai": "hard"}, target])
        n, h, t = g.players
        t.ghost_t = 10
        self.assertFalse(bot._sees(g, n.ai, t))  # 中等：看不见
        seen = []
        for k in range(300):  # 难：每 3 秒掷一次骰子，约 30%
            g.elapsed = k * 3.0
            seen.append(bot._sees(g, h.ai, t))
        self.assertTrue(60 < sum(seen) < 120, sum(seen))
        t.ghost_t = -1
        self.assertTrue(bot._sees(g, n.ai, t))


class RoomSettingTests(unittest.TestCase):
    def test_items_and_time(self):
        from backend.lobby import Lobby, Room
        room = Room(Lobby(), "1", "r", {"mapId": "meadow", "mode": "team", "items": False, "time": 3, "shrink": False})
        self.assertEqual((room.settings["items"], room.settings["time"], room.settings["mode"]), (False, 3, "team"))
        room.apply_settings({"time": 7})  # 只能选 3 / 5 / 10
        self.assertEqual(room.settings["time"], 3)
        room.apply_settings({"time": 5, "items": True})
        self.assertEqual((room.settings["items"], room.settings["time"]), (True, 5))


if __name__ == "__main__":
    unittest.main()
