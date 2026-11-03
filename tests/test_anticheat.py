"""异常行为观察：10 秒观察期内累计 3 次提醒。"""
import random
import unittest

from backend import anticheat
from backend.anticheat import Watch
from backend.game import Game


class WatchTests(unittest.TestCase):
    def test_three_in_window_warns_then_resets(self):
        w = Watch()
        self.assertFalse(w.report(0))
        self.assertFalse(w.report(2))
        self.assertTrue(w.report(5))  # 10 秒内第 3 次 → 提醒
        self.assertEqual(w.count, 0)
        self.assertFalse(w.report(6))
        self.assertEqual(w.count, 1)

    def test_window_expires(self):
        w = Watch()
        w.report(0)
        w.report(9)
        self.assertFalse(w.report(10))  # 10 秒到期 → 重新从 1 开始
        self.assertEqual(w.count, 1)
        self.assertEqual(w.until, 20)

    def test_watcher_map(self):
        m = anticheat.Watcher()
        self.assertFalse(m.report("a", 0))
        self.assertFalse(m.report("b", 0))
        self.assertFalse(m.report("a", 1))
        self.assertTrue(m.report("a", 2))
        self.assertFalse(m.report("b", 3))


class GameHookTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
        players = [{"id": f"p{i}", "name": f"p{i}", "skin": i, "hat": 0, "team": 0, "is_bot": False} for i in range(2)]
        self.g = Game("meadow", "ffa", 1, players, rng=random.Random(1),
                      on_anomaly=lambda pid, kind: self.seen.append((pid, kind)))
        self.g.phase = "play"

    def test_bad_move_reported(self):
        a = self.g.players[0]
        self.assertFalse(self.g.client_move(a.id, a.x + 5, a.y, epoch=a.fix))
        self.assertEqual(self.seen, [(a.id, "move")])

    def test_bomb_spam_reported(self):
        a = self.g.players[0]
        for _ in range(4):  # 突发额度内：正常
            self.g.set_input(a.id, bomb=True)
        self.assertEqual(self.seen, [])
        self.g.set_input(a.id, bomb=True)
        self.assertEqual(self.seen, [(a.id, "bomb")])

    def test_normal_bomb_pace_ok(self):
        a = self.g.players[0]
        for _ in range(30):  # 每 6 帧（0.1 秒）一次
            self.g.set_input(a.id, bomb=True)
            for _ in range(6):
                self.g.tick()
        self.assertEqual(self.seen, [])


class TextRuleTests(unittest.TestCase):
    def test_clean(self):
        from backend.textrule import TextError, clean
        self.assertEqual(clean("小明 二号"), "小明二号")
        self.assertEqual(clean(" Ａｂ１\t中\n"), "Ab1中")  # 全角转半角，所有空白去掉
        for bad in ("hi!", "a-b", "zh-HK", "【系统】", "ゲスト", "한글", "Café", "😀", "a_b", "你好，"):
            with self.assertRaises(TextError, msg=bad):
                clean(bad)

    def test_read_ws_takes_only_known_fields(self):
        from backend.textrule import TextError, read_ws
        m = read_ws({"t": "mv", "x": 1.5, "y": "2", "f": "up", "m": 1, "k": [3, 4], "evil": "a-b", "q": 7})
        self.assertEqual(m, {"t": "mv", "x": 1.5, "y": None, "f": "up", "m": None, "k": [3, 4],
                             "q": 7, "e": None, "p": None})  # 类型不对 → None；未约定字段不看
        self.assertIsNone(read_ws({"t": "hack"}))  # 不认识的类型
        self.assertEqual(read_ws({"t": "chat", "text": "  你 好\t\thi "})["text"], "你 好 hi")
        # 聊天不限制字符：标点、符号、表情、HTML 都原样保留（只当纯文本显示）
        self.assertEqual(read_ws({"t": "chat", "text": "你好！<b>gg</b> 😀 ゲーム"})["text"], "你好！<b>gg</b> 😀 ゲーム")
        # 不可见的控制 / 双向文本字符被去掉，最多 120 字
        self.assertEqual(read_ws({"t": "chat", "text": "ab\u202ecd\u0000e\u200b"})["text"], "abcde")
        self.assertEqual(len(read_ws({"t": "chat", "text": "x" * 500})["text"]), 120)
        with self.assertRaises(TextError):
            read_ws({"t": "in", "d": "up;drop"})
