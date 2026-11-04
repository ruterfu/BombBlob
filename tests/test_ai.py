"""AI 难度与命中规则：46% 身体覆盖判定、按时间规划躲避、难度形象、房间内修改难度。"""
import random
import unittest

from backend import bot, store
from backend.game import FLAME_TIME, TICK_RATE, Bomb, Flame, Game


def corridor_game(level: str) -> Game:
    """横向走廊 y=5（x=1..9）+ 在 x=7 向下的一条小岔路 (7,6)(7,7)，其余都是墙。
    炸弹 A (1,5) 0.8 秒后爆炸，火焰覆盖整条走廊；炸弹 B (7,8) 2.0 秒后爆炸，只覆盖岔路。
    唯一的活路：先躲进岔路，等 A 的火灭了，在 B 爆炸前回到走廊。"""
    players = [
        {"id": "ai", "name": "ai", "skin": 0, "hat": 0, "is_bot": True, "ai": level},
        {"id": "far", "name": "far", "skin": 1, "hat": 0, "is_bot": False},
    ]
    g = Game("meadow", "ffa", 1, players, rng=random.Random(3))
    g.phase = "play"
    g.shrink = False
    g.tele = {}
    for i in range(g.W * g.H):
        g.blocks[i] = "#"
        g.floor[i] = "."
    for x in range(1, 10):
        g.blocks[5 * g.W + x] = "."
    for y in (6, 7, 8):
        g.blocks[y * g.W + 7] = "."
    g.blocks[15 * g.W + 15] = "."  # 另一名玩家被关在远处的一格里
    ai, far = g.players
    ai.x, ai.y = 6.0, 5.0
    far.x, far.y = 15.0, 15.0
    ai.max_bombs = 0  # 这个测试只看躲避
    ai.invuln = far.invuln = 0
    g.bombs = [Bomb(1, "far", 1, 1, 5, 1.0, 5.0, 0.8, 9), Bomb(2, "far", 1, 7, 8, 7.0, 8.0, 2.0, 2)]
    g.next_bomb_id = 3
    return g


def run(g: Game, seconds: float) -> None:
    for _ in range(int(seconds * TICK_RATE)):
        g.tick()


class HitRuleTests(unittest.TestCase):
    def setUp(self):
        players = [{"id": "a", "name": "a", "skin": 0, "hat": 0, "is_bot": False}]
        self.g = Game("meadow", "ffa", 1, players, rng=random.Random(1))
        self.g.flames = {}
        self.p = self.g.players[0]

    def flame(self, x, y):
        self.g.flames = {y * self.g.W + x: Flame(FLAME_TIME, 0, "z")}

    def test_46_percent_threshold(self):
        # 身体宽 0.6：在 x=3.46 时覆盖 (4,y) 约 43%（不算），x=3.49 时约 48%（算）
        self.flame(4, 3)
        self.p.x, self.p.y = 3.46, 3.0
        self.assertIsNone(self.g._flame_on_body(self.p))
        self.p.x = 3.49
        self.assertIsNotNone(self.g._flame_on_body(self.p))

    def test_four_cell_corner_is_safe(self):
        # 站在四格交点：每格只占 25%，都不到 46%
        self.p.x, self.p.y = 3.5, 3.5
        for x, y in ((3, 3), (4, 3), (3, 4), (4, 4)):
            self.flame(x, y)
            self.assertIsNone(self.g._flame_on_body(self.p), (x, y))


class BombStyleTests(unittest.TestCase):
    def test_style_is_visual_only(self):
        # 特效炸弹与普通炸弹：爆炸范围、火焰格子、时间完全一样，只多了 style 字段
        def play(style):
            players = [{"id": "a", "name": "a", "skin": 0, "hat": 0, "is_bot": False, "bomb": style}]
            g = Game("meadow", "ffa", 1, players, rng=random.Random(5))
            g.phase = "play"
            p = g.players[0]
            g.place_bomb(p)
            booms = []
            for _ in range(int(3 * TICK_RATE)):
                g.update(1 / TICK_RATE)
                booms += [e for e in g.events if e["k"] == "boom"]
                if g.flames:
                    break
            return g, booms
        g1, b1 = play("")
        g2, b2 = play("gold")
        self.assertEqual(sorted(g1.flames), sorted(g2.flames))
        self.assertEqual([(e["x"], e["y"], e["r"]) for e in b1], [(e["x"], e["y"], e["r"]) for e in b2])
        self.assertEqual(b2[0]["st"], "gold")
        self.assertTrue(all(f.style == "gold" for f in g2.flames.values()))
        snap = g2.snapshot()
        self.assertTrue(all(len(f) == 3 and f[2] == "gold" for f in snap["f"]))

    def test_unknown_style_ignored(self):
        players = [{"id": "a", "name": "a", "skin": 0, "hat": 0, "is_bot": False, "bomb": "nuke"}]
        g = Game("meadow", "ffa", 1, players, rng=random.Random(5))
        self.assertEqual(g.players[0].bomb_style, "")


class DodgeTests(unittest.TestCase):
    def test_hard_uses_timing_gap(self):
        g = corridor_game("hard")
        ai = g.players[0]
        seen_spur = False
        y_at_b = None  # B 爆炸那一刻 AI 所在的行
        for _ in range(int(3.2 * TICK_RATE)):
            b_alive = any(b.id == 2 for b in g.bombs)
            g.tick()
            seen_spur = seen_spur or round(ai.y) >= 6
            if b_alive and not any(b.id == 2 for b in g.bombs):
                y_at_b = round(ai.y)
        self.assertTrue(seen_spur, "应先躲进岔路")
        self.assertTrue(ai.alive and ai.trapped <= 0, f"难：应利用时间差躲过两颗炸弹，结果在 ({ai.x:.2f},{ai.y:.2f})")
        self.assertEqual(y_at_b, 5, "B 爆炸前应回到走廊")

    def test_plain_search_cannot_solve_it(self):
        # 普通的「找最近的安全格」搜不到出路（所有格子迟早都会着火）→ 简单会被炸到
        g = corridor_game("easy")
        ai = g.players[0]
        ai.ai.react = 0.0
        run(g, 3.2)
        self.assertTrue(ai.trapped > 0 or not ai.alive)

    def test_hard_speed_bonus(self):
        players = [{"id": f"b{i}", "name": "b", "skin": i, "hat": 0, "is_bot": True, "ai": lv}
                   for i, lv in enumerate(("easy", "normal", "hard"))]
        g = Game("meadow", "ffa", 1, players, rng=random.Random(1))
        easy, normal, hard = g.players
        self.assertEqual(g.player_speed(easy), g.player_speed(normal))
        self.assertAlmostEqual(g.player_speed(hard) / g.player_speed(easy), 1.03)


class LevelTests(unittest.TestCase):
    def test_profiles_and_defaults(self):
        self.assertEqual(bot.LEVELS, ("easy", "normal", "hard"))
        self.assertEqual(bot.level_of("bogus"), "normal")
        self.assertEqual(bot.create(random.Random(1), "hard").prof.speed_bonus, 0.03)
        self.assertEqual(bot.PROFILES["easy"].blunder, 0.2)

    def test_hats_follow_difficulty(self):
        old_shop, old_unlock = dict(store.SHOP), dict(store.HAT_UNLOCK)
        try:
            store.SHOP = {6: {"code": "beret", "level": 10, "price": 1}, 9: {"code": "cowboy", "level": 20, "price": 1},
                          12: {"code": "tophat", "level": 30, "price": 1}, 14: {"code": "ice", "level": 40, "price": 1},
                          16: {"code": "dragon", "level": 50, "price": 1}}
            store.HAT_UNLOCK = {0: 1, 1: 2, 2: 12, 3: 3}
            self.assertEqual(store.hats_in_levels(*bot.LEVEL_BAND["easy"]), [0, 1, 2, 3, 6])
            self.assertEqual(store.hats_in_levels(*bot.LEVEL_BAND["normal"]), [9, 12])
            self.assertEqual(store.hats_in_levels(*bot.LEVEL_BAND["hard"]), [14, 16])
        finally:
            store.SHOP, store.HAT_UNLOCK = old_shop, old_unlock

    def test_room_add_and_change_level(self):
        from backend.lobby import Lobby, Room
        lobby = Lobby()
        room = Room(lobby, "1", "r", {"mapId": "meadow", "mode": "ffa", "lives": 1, "shrink": True, "maxPlayers": 6})
        room.members.append({"id": "h", "name": "h", "skin": 0, "hat": 0, "isBot": False, "ready": True, "team": 0, "connected": True})
        self.assertTrue(room.add_bot("hard"))
        b = room.members[-1]
        self.assertEqual(b["ai"], "hard")
        self.assertTrue(room.add_bot("nonsense"))
        self.assertEqual(room.members[-1]["ai"], "normal")
        self.assertTrue(room.set_bot_level(b["id"], "easy"))
        self.assertEqual(b["ai"], "easy")
        self.assertFalse(room.set_bot_level("h", "easy"))  # 真人不能改


if __name__ == "__main__":
    unittest.main()
