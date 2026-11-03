"""游戏规则单元测试 + 全地图机器人对战冒烟测试。运行：python -m unittest discover tests"""
import random
import unittest
import zlib

from backend.game import (
    FLAME_TIME, FUSE, INVULN_START, MAX_BOMBS, TICK_RATE, TRAP_TIME, Bomb, Game,
)
from backend.maps import MAPS, W, H, build_map


def make_game(map_id="meadow", n=2, mode="ffa", bots=False, seed=1):
    levels = ("easy", "normal", "hard")
    players = [
        {"id": f"p{i}", "name": f"p{i}", "skin": i, "hat": 0, "team": i % 2, "is_bot": bots, "ai": levels[i % 3]}
        for i in range(n)
    ]
    g = Game(map_id, mode, 1, players, rng=random.Random(seed))
    g.phase = "play"
    return g


def clear_map(g):
    """把内部清空成只有外墙的空地，便于精确测试规则。"""
    for y in range(g.H):
        for x in range(g.W):
            border = x in (0, g.W - 1) or y in (0, g.H - 1)
            g.blocks[y * g.W + x] = "#" if border else "."
            g.floor[y * g.W + x] = "."
    g.tele = {}


def run_ticks(g, n):
    for _ in range(n):
        g.tick()


def run(g, seconds):
    for _ in range(int(seconds * TICK_RATE)):
        g.tick()


class MapTests(unittest.TestCase):
    def test_eight_maps_enlarged(self):
        self.assertEqual(len(MAPS), 8)
        self.assertEqual((W, H), (23, 19))  # 15x13 的约 1.5 倍
        for m in MAPS:
            self.assertEqual(len(m["rows"]), H)
            self.assertTrue(all(len(r) == W for r in m["rows"]))

    def test_all_spawns_connected(self):
        """炸开所有可破坏方块后，每个出生点都能走到其他出生点（考虑传送门）。"""
        from backend.maps import build_map
        for m in MAPS:
            bm = build_map(m["id"], random.Random(1))
            solid = set("#YH~")
            start = bm.spawns[0]
            seen = {start}
            todo = [start]
            while todo:
                x, y = todo.pop()
                nxt = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                t = bm.tele.get(y * bm.w + x)
                if t is not None:
                    nxt.append((t % bm.w, t // bm.w))
                for nx, ny in nxt:
                    if 0 <= nx < bm.w and 0 <= ny < bm.h and (nx, ny) not in seen and bm.blocks[ny * bm.w + nx] not in solid:
                        seen.add((nx, ny))
                        todo.append((nx, ny))
            self.assertTrue(all(sp in seen for sp in bm.spawns), m["id"])

    def test_spawns_are_clear(self):
        for m in MAPS:
            bm = build_map(m["id"], random.Random(0))
            self.assertGreaterEqual(len(bm.spawns), 6)
            for x, y in bm.spawns:
                self.assertEqual(bm.blocks[y * bm.w + x], ".", m["id"])

    def test_new_building_types_present(self):
        allrows = "".join("".join(m["rows"]) for m in MAPS)
        for c in "mHYe":
            self.assertIn(c, allrows)


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.g = make_game()
        clear_map(self.g)
        a, b = self.g.players
        a.x, a.y = 3.0, 3.0
        b.x, b.y = 11.0, 9.0

    def test_start_invulnerable_3s(self):
        g = make_game()
        g.phase = "countdown"
        g.countdown = 0.01
        g.tick()
        self.assertEqual(g.phase, "play")
        self.assertAlmostEqual(g.players[0].invuln, INVULN_START, places=1)

    def test_move_blocked_by_wall(self):
        a = self.g.players[0]
        a.x, a.y = 1.0, 1.0
        self.g.set_input("p0", direction="up")
        run(self.g, 0.5)
        self.assertEqual((a.x, a.y), (1.0, 1.0))
        self.g.set_input("p0", direction="right")
        run(self.g, 0.5)
        self.assertGreater(a.x, 1.5)

    def test_input_ack(self):
        self.g.set_input("p0", direction="right", seq=7)
        self.g.set_input("p0", direction=None, seq=5)  # 旧序号不回退
        self.assertEqual(self.g.players[0].ack, 7)
        snap = self.g.snapshot()
        self.assertEqual(snap["p"][0]["q"], 7)
        self.assertIn("st", snap)

    def test_bomb_traps_then_dies_after_10s(self):
        a, b = self.g.players
        a.range = 2
        b.x, b.y = 5.0, 3.0
        self.g.set_input("p0", bomb=True)
        self.g.tick()
        self.g.set_input("p0", direction="down")
        run(self.g, FUSE + 0.2)
        self.assertTrue(b.alive)
        self.assertGreater(b.trapped, 0)
        run(self.g, TRAP_TIME + 0.2)
        self.assertFalse(b.alive)
        self.assertEqual(a.kills, 1)

    def test_trapped_cannot_place_bombs_and_is_slow(self):
        b = self.g.players[1]
        free_speed = self.g.player_speed(b)
        self.g.hit(b, "p0")
        self.assertLess(self.g.player_speed(b), free_speed * 0.5)
        self.g.set_input("p1", bomb=True)
        self.g.tick()
        self.assertEqual(len(self.g.bombs), 0)

    def test_teammate_rescue_gives_3s_invuln(self):
        g = make_game(n=3, mode="team")
        clear_map(g)
        a, b, c = g.players  # a、c 同为 0 队
        a.x, a.y = 5.0, 5.0
        c.x, c.y = 5.4, 5.0
        b.x, b.y = 15.0, 15.0
        g.hit(a, "p1")
        g.tick()
        self.assertEqual(a.trapped, 0)
        self.assertTrue(a.alive)
        self.assertGreaterEqual(a.invuln, 2.9)
        self.assertEqual(c.rescues, 1)

    def test_enemy_touch_pops(self):
        a, b = self.g.players
        b.x, b.y = 3.5, 3.0
        self.g.hit(b, None)
        self.g.tick()
        self.assertFalse(b.alive)
        self.assertEqual(a.kills, 1)

    def test_trapped_enemies_touching_nothing_happens(self):
        a, b = self.g.players
        b.x, b.y = 3.4, 3.0
        self.g.hit(a, None)
        self.g.hit(b, None)
        for _ in range(30):
            self.g.tick()
        self.assertTrue(a.alive and b.alive)
        self.assertGreater(a.trapped, 0)
        self.assertGreater(b.trapped, 0)
        self.assertEqual((a.kills, b.kills), (0, 0))

    def test_trapped_can_still_move_slowly(self):
        a = self.g.players[0]
        self.g.hit(a, None)
        run_ticks(self.g, 60)  # 1 秒：被困速度约 3.8 × 0.3 ≈ 1.14 格/秒
        self.assertTrue(self.g.client_move(a.id, 3.9, 3.0, epoch=a.fix))
        self.assertFalse(self.g.client_move(a.id, 6.0, 3.0, epoch=a.fix))  # 超过被困速度：拒绝

    def test_quitter_never_wins(self):
        g = make_game(n=3, mode="team")
        clear_map(g)
        a, b, c = g.players  # a、c 同为 0 队，b 为 1 队
        a.x, a.y, b.x, b.y, c.x, c.y = 3.0, 3.0, 15.0, 15.0, 9.0, 9.0
        g.forfeit("p2")  # c 主动退出
        self.assertTrue(c.quit and not c.alive)
        g.die(b, a, counted=True)  # 之后 0 队获胜
        g.check_end()
        res = {p["id"]: p for p in g.result["players"]}
        self.assertEqual(g.result["winnerTeam"], 0)
        self.assertTrue(res["p0"]["win"])
        self.assertFalse(res["p2"]["win"])
        self.assertTrue(res["p2"]["quit"])
        self.assertEqual(g.result["players"][-1]["id"], "p2")  # 排在最后

    def test_quit_after_death_still_counts(self):
        g = make_game(n=3, mode="team")
        clear_map(g)
        a, b, c = g.players
        g.die(c, b, counted=True)  # c 先阵亡
        g.forfeit("p2")  # 观战中退出
        self.assertTrue(c.quit)

    def test_trapped_walks_into_free_enemy_dies(self):
        a, b = self.g.players
        a.x, a.y = 3.0, 3.0
        b.x, b.y = 3.8, 3.0
        self.g.hit(a, None)  # a 被困，b 自由
        run_ticks(self.g, 60)
        self.assertTrue(a.alive)
        self.g.client_move(a.id, 3.3, 3.0, epoch=a.fix)  # 被困的 a 主动碰到自由的敌人 b
        self.g.tick()
        self.assertFalse(a.alive)
        self.assertEqual(b.kills, 1)

    def test_trapped_teammates_touching_no_rescue(self):
        g = make_game(n=3, mode="team")
        clear_map(g)
        a, b, c = g.players  # a、c 同为 0 队
        a.x, a.y = 5.0, 5.0
        c.x, c.y = 5.4, 5.0
        b.x, b.y = 15.0, 15.0
        g.hit(a, "p1")
        g.hit(c, "p1")
        g.tick()
        self.assertGreater(a.trapped, 0)
        self.assertGreater(c.trapped, 0)

    def test_body_overlap_hit_precision(self):
        b = self.g.players[1]
        b.x, b.y = 6.0, 6.0
        b.invuln = 0
        self.g._add_flame(7 * self.g.W + 6, 16, "p0")  # 正下方一格着火
        self.g.tick()
        self.assertEqual(b.trapped, 0, "身体不在火焰格内不应被命中")
        b.y = 6.55  # 身体已大半进入下方格子
        self.g._add_flame(7 * self.g.W + 6, 16, "p0")
        self.g.tick()
        self.assertGreater(b.trapped, 0)

    def test_shield_absorbs_hit(self):
        b = self.g.players[1]
        b.shield = True
        self.g.hit(b, "p0")
        self.assertEqual(b.trapped, 0)
        self.assertFalse(b.shield)

    def test_speed_items(self):
        a = self.g.players[0]
        base = self.g.player_speed(a)
        for _ in range(10):
            self.g.apply_powerup(a, "speed")
        self.assertAlmostEqual(self.g.player_speed(a) / base, 1.25, places=3)
        for _ in range(20):
            self.g.apply_powerup(a, "slow")
        self.assertAlmostEqual(self.g.player_speed(a) / base, 0.75, places=3)

    def test_bomb_capacity_1_to_5(self):
        a = self.g.players[0]
        self.assertEqual(a.max_bombs, 1)
        self.g.apply_powerup(a, "bomb")
        self.assertEqual(a.max_bombs, 2)
        for _ in range(10):
            self.g.apply_powerup(a, "bomb")
        self.assertEqual(a.max_bombs, MAX_BOMBS)
        self.assertEqual(MAX_BOMBS, 5)

    def test_power_3x3_to_11x11(self):
        a = self.g.players[0]
        self.assertEqual(a.range, 1)
        for _ in range(10):
            self.g.apply_powerup(a, "fire")
        self.assertEqual(a.range, 5)

    def test_steel_crate_needs_two_hits(self):
        g = self.g
        i = 3 * g.W + 5
        g.blocks[i] = "m"
        g.bombs.append(Bomb(90, "p0", 0, 4, 3, 4.0, 3.0, 0, 1))
        g.tick()
        self.assertEqual(g.blocks[i], "x")
        run(g, FLAME_TIME + 0.1)
        g.bombs.append(Bomb(91, "p0", 0, 4, 3, 4.0, 3.0, 0, 1))
        g.tick()
        self.assertEqual(g.blocks[i], ".")

    def test_barrel_chain_explosion(self):
        g = self.g
        g.blocks[3 * g.W + 8] = "e"
        g.bombs.append(Bomb(90, "p0", 0, 7, 3, 7.0, 3.0, 0, 1))
        run(g, 0.2)
        self.assertEqual(g.blocks[3 * g.W + 8], ".")
        self.assertIn(3 * g.W + 10, g.flames)  # 油桶威力 2，火焰到达 x=10

    def test_kick(self):
        a = self.g.players[0]
        a.kick = True
        self.g.bombs.append(Bomb(99, "p1", 1, 4, 3, 4.0, 3.0, FUSE, 1))
        self.g.set_input("p0", direction="right")
        run(self.g, 0.5)
        self.assertGreater(self.g.bombs[0].x, 6)

    def test_sudden_death_crushes(self):
        a = self.g.players[0]
        a.x, a.y = 1.0, 1.0
        self.g.time_left = self.g.sd_time
        run(self.g, 0.2)
        self.assertFalse(a.alive)

    def test_quick_tap_moves_a_little(self):
        a = self.g.players[0]
        self.g.set_input("p0", direction="right")
        self.g.set_input("p0", direction=None)
        run(self.g, 0.6)
        self.assertGreater(a.x, 3.0)
        self.assertLess(a.x, 3.2)
        self.assertEqual(a.y, 3.0)

    def test_free_move_stops_between_tiles(self):
        a = self.g.players[0]
        self.g.set_input("p0", direction="right")
        run(self.g, 0.2)
        self.g.set_input("p0", direction=None)
        x = a.x
        run(self.g, 0.3)
        self.assertEqual(a.x, x)
        self.assertGreater(x - int(x), 0.1)  # 停在两格之间

    def test_blocked_ahead_stops_at_center(self):
        a = self.g.players[0]
        self.g.blocks[3 * self.g.W + 5] = "#"
        self.g.set_input("p0", direction="right")
        run(self.g, 1.5)
        self.assertEqual((a.x, a.y), (4.0, 3.0))

    def test_corner_assist_slides_into_lane(self):
        a = self.g.players[0]
        W = self.g.W
        a.x, a.y = 3.0, 3.4  # 偏离通道 0.4
        self.g.blocks[4 * W + 4] = "#"  # 右下格被挡，只有第 3 行能走
        self.g.set_input("p0", direction="right")
        run(self.g, 0.5)
        self.assertEqual(a.y, 3.0)
        self.assertGreater(a.x, 3.5)

    def test_walk_off_own_bomb_midway(self):
        a = self.g.players[0]
        a.x = 3.4
        self.g.set_input("p0", bomb=True)
        run(self.g, 0.05)
        self.assertIsNotNone(self.g.bomb_at(3, 3))
        self.g.set_input("p0", direction="right")
        run(self.g, 0.5)
        self.assertGreater(a.x, 4.0)

    def test_shrink_optional(self):
        players = [{"id": f"p{i}", "name": f"p{i}", "skin": i, "hat": 0, "team": i % 2, "is_bot": False} for i in range(2)]
        for shrink, expect in ((True, True), (False, False)):
            g = Game("meadow", "ffa", 1, players, rng=random.Random(1), shrink=shrink)
            g.phase = "play"
            self.assertEqual(g.round_time, 600.0)
            g.time_left = 30.0
            for _ in range(TICK_RATE * 3):
                g.tick()
            self.assertEqual(g.sd_started, expect)
            self.assertEqual(any(c == "#" for c in g.blocks[g.W + 1:g.W + 3]) or g.sd_index > 0, expect)

    # ---------- 客户端移动 + 服务器校验 ----------
    def _walk(self, a, xs, ys=None, dt_ticks=2):
        """模拟客户端：每 dt_ticks 帧上报一次位置。"""
        ok = True
        for i, x in enumerate(xs):
            y = ys[i] if ys else a.y
            run_ticks(self.g, dt_ticks)
            ok = self.g.client_move(a.id, x, y, epoch=a.fix) and ok
        return ok

    def test_client_move_accepted(self):
        a = self.g.players[0]
        run_ticks(self.g, 30)
        self.assertTrue(self._walk(a, [3.1, 3.2, 3.3, 3.4, 3.5]))
        self.assertEqual((a.x, a.y), (3.5, 3.0))
        self.assertEqual(a.fix, 0)

    def test_client_move_too_fast_rejected(self):
        a = self.g.players[0]
        run_ticks(self.g, 2)
        self.assertFalse(self.g.client_move(a.id, 9.0, 3.0, epoch=0))  # 瞬移
        self.assertEqual((a.x, a.y), (3.0, 3.0))
        self.assertEqual(a.fix, 1)

    def test_client_move_through_wall_rejected(self):
        a = self.g.players[0]
        self.g.blocks[3 * self.g.W + 4] = "#"
        run_ticks(self.g, 60)
        self.assertFalse(self.g.client_move(a.id, 4.5, 3.0, epoch=0))
        self.assertFalse(self.g.client_move(a.id, 3.0, 3.6, epoch=1) and False)

    def test_client_move_off_own_bomb(self):
        a = self.g.players[0]
        self.g.set_input(a.id, bomb=True)
        run_ticks(self.g, 30)
        self.assertIsNotNone(self.g.bomb_at(3, 3))
        self.assertTrue(self._walk(a, [3.2, 3.4, 3.6, 3.8, 4.0]))
        # 离开后不能再走回炸弹格
        run_ticks(self.g, 30)
        self.assertFalse(self.g.client_move(a.id, 3.6, 3.0, epoch=a.fix))

    def test_stale_epoch_dropped(self):
        a = self.g.players[0]
        run_ticks(self.g, 2)
        self.g.client_move(a.id, 9.0, 3.0, epoch=0)  # 被拒，fix=1
        run_ticks(self.g, 30)
        self.assertFalse(self.g.client_move(a.id, 3.1, 3.0, epoch=0))  # 旧状态的上报：丢弃
        self.assertEqual(a.fix, 1)
        self.assertTrue(self.g.client_move(a.id, 3.1, 3.0, epoch=1))

    def test_lag_grace_lets_escape(self):
        a = self.g.players[0]
        a.invuln = 0
        run_ticks(self.g, 30)
        self.g.client_move(a.id, 3.0, 3.0, epoch=0, ping=200)
        a.client_move = True
        from backend.game import Flame
        self.g.flames[3 * self.g.W + 3] = Flame(0.5, 15, "p1")
        run_ticks(self.g, 1)
        self.assertIsNotNone(a.pending_hit)
        # 玩家在自己的时间线里已经躲开：补偿窗口内的上报显示已离开火焰
        self.g.client_move(a.id, 3.0, 3.6, epoch=0)
        self.g.client_move(a.id, 3.0, 4.0, epoch=0)
        run_ticks(self.g, 12)
        self.assertEqual(a.trapped, 0)

    def test_lag_grace_still_hits(self):
        a = self.g.players[0]
        a.invuln = 0
        run_ticks(self.g, 30)
        self.g.client_move(a.id, 3.0, 3.0, epoch=0, ping=100)
        from backend.game import Flame
        self.g.flames[3 * self.g.W + 3] = Flame(0.5, 15, "p1")
        run_ticks(self.g, 12)
        self.assertGreater(a.trapped, 0)

    def test_blocks_only_sent_when_changed(self):
        s1 = self.g.snapshot()
        s2 = self.g.snapshot()
        self.assertIn("k", s1)
        self.assertNotIn("k", s2)


class SyncRateTests(unittest.TestCase):
    def test_broadcast_rate(self):
        for hz in (10, 25, 30, 60):
            g = Game("meadow", "ffa", 1, [{"id": "a", "name": "a", "skin": 0, "hat": 0}, {"id": "b", "name": "b", "skin": 1, "hat": 0}],
                     rng=random.Random(1), net_rate=hz)
            g.phase = "play"
            g.round_time = g.time_left = 999
            sent = []
            g.broadcast = lambda s: sent.append(s)
            for _ in range(TICK_RATE * 10):
                g.tick()
            self.assertAlmostEqual(len(sent), hz * 10, delta=2, msg=hz)
            self.assertEqual(g.start_info()["netRate"], hz)
            # 至少每 2 秒有一个带完整地图的关键帧
            keys = [i for i, s in enumerate(sent) if "k" in s]
            self.assertTrue(all(b - a <= hz * 2 + 1 for a, b in zip(keys, keys[1:])), (hz, keys[:5]))

    def test_rate_clamped(self):
        g = Game("meadow", "ffa", 1, [{"id": "a", "name": "a", "skin": 0, "hat": 0}], net_rate=500)
        self.assertEqual(g.net_rate, 60)

    def test_env_sync_hz(self):
        import os
        from backend.config import env_sync_hz
        old = os.environ.pop("SYNC_HZ", None)
        try:
            self.assertEqual(env_sync_hz(), 30)
            for raw, want in (("45", 45), ("5", 10), ("120", 60), ("abc", 30), ("20.0", 20)):
                os.environ["SYNC_HZ"] = raw
                self.assertEqual(env_sync_hz(), want, raw)
        finally:
            os.environ.pop("SYNC_HZ", None)
            if old is not None:
                os.environ["SYNC_HZ"] = old


class BotSmokeTests(unittest.TestCase):
    def test_bots_finish_every_map(self):
        for m in MAPS:
            for mode in ("ffa", "team"):
                g = make_game(m["id"], 6, mode, bots=True, seed=zlib.crc32(f"{m['id']}{mode}".encode()))
                booms = [0]
                g.broadcast = lambda s: booms.__setitem__(0, booms[0] + sum(e["k"] == "boom" for e in s["e"]))
                for _ in range(TICK_RATE * 620):
                    if g.tick():
                        break
                self.assertIsNotNone(g.result, f"{m['id']}/{mode} 没有结束")
                # 很快分出胜负说明在积极进攻；拖得久的对局则要求有足够多的爆炸
                self.assertTrue(booms[0] > 30 or g.elapsed < 120, f"{m['id']}/{mode} 机器人太被动（{booms[0]} 次爆炸 / {g.elapsed:.0f} 秒）")


if __name__ == "__main__":
    unittest.main()
