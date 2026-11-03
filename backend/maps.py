"""地图定义（23 x 19）

每张地图只设计左上象限（12 x 10，最后一列 / 一行是中轴线），再镜像成完整地图，
保证四个出生区域完全对称、公平。

  #  不可破坏的墙            Y  树木 / 装饰物（不可破坏）
  H  塔楼（不可破坏）         x  木箱（一次摧毁）
  *  随机木箱（按 density）    m  钢制货箱（需两次爆炸：先变成木箱）
  e  爆炸油桶（被炸后二次爆炸）  .  空地
  P  出生点                  i  冰面（加速）
  j  冰面 + 随机木箱          ~  水 / 熔岩（不可通行，火焰可越过）
  b  草丛（可藏身，可烧毁）    ^ v < >  传送带（镜像时方向随之翻转）
  1-4  传送门（镜像时左上与右下配对、右上与左下配对）
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

W = 23
H = 19
QW = (W + 1) // 2  # 12
QH = (H + 1) // 2  # 10

FLIP_H = {"<": ">", ">": "<"}
FLIP_V = {"^": "v", "v": "^"}
TELE_ALT = {"1": "5", "2": "6", "3": "7", "4": "8"}


def mirror(quadrant: list[str]) -> list[str]:
    """把左上象限镜像为完整地图。"""
    if len(quadrant) != QH or any(len(r) != QW for r in quadrant):
        raise ValueError("quadrant must be 12 x 10")
    rows: list[list[str]] = [[" "] * W for _ in range(H)]
    for y in range(QH):
        for x in range(QW):
            c = quadrant[y][x]
            for mx in (False, True):
                for my in (False, True):
                    tx = W - 1 - x if mx else x
                    ty = H - 1 - y if my else y
                    ch = c
                    if mx:
                        ch = FLIP_H.get(ch, ch)
                    if my:
                        ch = FLIP_V.get(ch, ch)
                    if ch in TELE_ALT and mx != my:
                        ch = TELE_ALT[ch]  # 右上 / 左下 使用另一组编号
                    rows[ty][tx] = ch
    return ["".join(r) for r in rows]


MAPS: list[dict] = [
    {
        "id": "meadow",
        "name": "遗迹广场",
        "desc": "古老石柱与塔楼构成的经典战场，油桶分布四处，攻守平衡。",
        "theme": "meadow",
        "density": 0.74,
        "quadrant": [
            "############",
            "#P.*****.***",
            "#.#*#H#*#*#*",
            "#**m***e***.",
            "#*#*#*#Y#*#*",
            "#*e****.*m**",
            "#.#*#*#*#*#*",
            "#P**m**b***.",
            "#.#*#Y#*#*#*",
            "#**e**.***..",
        ],
    },
    {
        "id": "frost",
        "name": "冰霜湖",
        "desc": "四片冰封湖面让移动更快，也更难收住脚步。",
        "theme": "frost",
        "density": 0.7,
        "quadrant": [
            "############",
            "#P.*jjj*..j.",
            "#.#j#i#j#*#j",
            "#*jjiiiijj*.",
            "#*#i#~~~#j#j",
            "#j*i~~~~~ijj",
            "#.#i#~~~#j#.",
            "#P*jiiiiijm*",
            "#.#*#j#Y#*#*",
            "#*mjjj.jjj..",
        ],
    },
    {
        "id": "jungle",
        "name": "丛林秘境",
        "desc": "河流把战场一分为二，只有五座桥。草丛可以藏身伏击。",
        "theme": "jungle",
        "density": 0.72,
        "quadrant": [
            "############",
            "#P.bb***Y.bb",
            "#.#b#*#b#*#b",
            "#bb**e**bb*.",
            "#*#*#Y#*#b#*",
            "#*bb***bb**.",
            "#.#*#*#*#*#*",
            "#P*bb*e*Y*bb",
            "#.#b#*#b#*#b",
            "#~~~.~~~~.~.",
        ],
    },
    {
        "id": "neon",
        "name": "霓虹传送站",
        "desc": "四座传送门连通对角，能量塔林立，瞬间换位打乱节奏。",
        "theme": "neon",
        "density": 0.72,
        "quadrant": [
            "############",
            "#P.***.*****",
            "#.#1#*#*#H#*",
            "#**.*m***.*.",
            "#*#*#*#*#*#*",
            "#.*m**H**e*.",
            "#P#*#*#*#*#.",
            "#.***.***m**",
            "#*#*#Y#*#*#*",
            "#*e**.***...",
        ],
    },
    {
        "id": "candy",
        "name": "熔铸工厂",
        "desc": "传送带向中心汇聚，熔岩池与油桶遍布，处处是陷阱。",
        "theme": "foundry",
        "density": 0.7,
        "quadrant": [
            "############",
            "#P.mm***e*..",
            "#.#*#*#*#*#v",
            "#*>>>>>.*e*v",
            "#*#m#~~#*#*v",
            "#e*m*~~*mm*.",
            "#.#*#*#*#*#*",
            "#P*e*<<<<**.",
            "#.#m#*#H#*#*",
            "#*mm**e***..",
        ],
    },
    {
        "id": "canyon",
        "name": "沙暴峡谷",
        "desc": "岩脊把战场切成几条峡道，中央绿洲阻断通行，油桶埋伏其间。",
        "theme": "desert",
        "density": 0.72,
        "quadrant": [
            "############",
            "#P.**e***Y..",
            "#.#*#*#Y#*#*",
            "#*b**Y**b**.",
            "#*#*#*#*#Y#*",
            "#e**Y**e***.",
            "#.#*#*#*#*#~",
            "#P**b*Y**.~~",
            "#.#*#*#*#*#~",
            "#**e*.**.~~~",
        ],
    },
    {
        "id": "harbor",
        "name": "午夜港口",
        "desc": "运河横贯码头，只有几座栈桥可过；钢制货箱要炸两次，传送带把人送向中央。",
        "theme": "harbor",
        "density": 0.7,
        "quadrant": [
            "############",
            "#P.*m**~*m*.",
            "#.#*#*#~#*#*",
            "#**m>>>.*m*.",
            "#*#*#*#~#*#*",
            "#~~.~~~~~.~~",
            "#*#*#m#*#*#*",
            "#P*m*e*.m**.",
            "#.#*#*#H#*#*",
            "#*m*.*~*e*..",
        ],
    },
    {
        "id": "temple",
        "name": "云顶神殿",
        "desc": "两组传送门连通四角，冰面回廊与中央圣坛让进攻路线变化莫测。",
        "theme": "temple",
        "density": 0.7,
        "quadrant": [
            "############",
            "#P.**H**.*..",
            "#.#*#*#*#1#*",
            "#**iii*e**.*",
            "#*#i#*#*#*#*",
            "#.*i**H**m*.",
            "#*#*#*#*#*#*",
            "#P**m*.*Y**.",
            "#.#*#2#*#*#*",
            "#*e*..*..*HH",
        ],
    },
]

for _m in MAPS:
    _m["rows"] = mirror(_m["quadrant"])


def _validate(m: dict) -> None:
    rows = m["rows"]
    if len(rows) != H or any(len(r) != W for r in rows):
        raise ValueError(f"map {m['id']}: bad size")
    tele: dict[str, int] = {}
    spawns = 0
    for r in rows:
        for c in r:
            if c == "P":
                spawns += 1
            if c in "123456789":
                tele[c] = tele.get(c, 0) + 1
    for k, n in tele.items():
        if n != 2:
            raise ValueError(f"map {m['id']}: teleporter {k} must appear exactly twice")
    if spawns < 6:
        raise ValueError(f"map {m['id']}: needs at least 6 spawns")


for _m in MAPS:
    _validate(_m)

MAP_IDS = [m["id"] for m in MAPS]


def get_map(map_id: str) -> dict | None:
    return next((m for m in MAPS if m["id"] == map_id), None)


@dataclass
class BuiltMap:
    id: str
    theme: str
    w: int
    h: int
    floor: list[str]
    blocks: list[str]
    spawns: list[tuple[int, int]]
    tele: dict[int, int] = field(default_factory=dict)


SOLID_STATIC = ("#", "Y", "H")  # 永久障碍
DESTRUCTIBLE = ("x", "m", "e")  # 可被炸毁的方块


def build_map(map_id: str, rng: random.Random | None = None) -> BuiltMap:
    """生成一局游戏使用的地图实例（随机木箱、出生点清场）。"""
    rng = rng or random.Random()
    d = get_map(map_id) or MAPS[0]
    floor = ["."] * (W * H)
    blocks = ["."] * (W * H)
    spawns: list[tuple[int, int]] = []
    tele_pos: dict[str, list[int]] = {}
    for y in range(H):
        for x in range(W):
            c = d["rows"][y][x]
            i = y * W + x
            if c in ("#", "x", "m", "e", "Y", "H", "~", "b"):
                blocks[i] = c
            elif c == "*":
                if rng.random() < d["density"]:
                    blocks[i] = "x"
            elif c == "P":
                spawns.append((x, y))
            elif c == "i":
                floor[i] = "i"
            elif c == "j":
                floor[i] = "i"
                if rng.random() < d["density"]:
                    blocks[i] = "x"
            elif c in "^v<>":
                floor[i] = c
            elif c in "123456789":
                floor[i] = c
                tele_pos.setdefault(c, []).append(i)
    # 出生点周围清理可破坏方块，保证开局有安全空间
    for sx, sy in spawns:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if abs(dx) + abs(dy) > 2:
                    continue
                x, y = sx + dx, sy + dy
                if 0 <= x < W and 0 <= y < H and blocks[y * W + x] in DESTRUCTIBLE:
                    blocks[y * W + x] = "."
    tele: dict[int, int] = {}
    for a, b in tele_pos.values():
        tele[a] = b
        tele[b] = a
    return BuiltMap(d["id"], d["theme"], W, H, floor, blocks, spawns, tele)


MAP_TEXT = {
    "meadow": {
        "names": {"zh": "遗迹广场", "zh-HK": "遺跡廣場", "ja": "遺跡の広場", "en": "Ruins Plaza"},
        "descs": {
            "zh": "古老石柱与塔楼构成的经典战场，油桶分布四处，攻守平衡。",
            "zh-HK": "古老石柱與塔樓構成的經典戰場，油桶散佈四周，攻守皆宜。",
            "ja": "古い石柱と塔が並ぶ定番の戦場。ドラム缶が点在し、攻守のバランスが取れている。",
            "en": "A classic arena of ancient pillars and towers, with barrels scattered around. Balanced for attack and defense.",
        },
    },
    "frost": {
        "names": {"zh": "冰霜湖", "zh-HK": "冰霜湖", "ja": "フロストレイク", "en": "Frost Lake"},
        "descs": {
            "zh": "四片冰封湖面让移动更快，也更难收住脚步。",
            "zh-HK": "四片結冰湖面令移動更快，但亦更難煞停。",
            "ja": "4つの凍った湖面では移動が速くなるが、止まりにくい。",
            "en": "Four frozen ponds make you faster — and harder to stop.",
        },
    },
    "jungle": {
        "names": {"zh": "丛林秘境", "zh-HK": "叢林秘境", "ja": "ジャングル", "en": "Jungle"},
        "descs": {
            "zh": "河流把战场一分为二，只有五座桥。草丛可以藏身伏击。",
            "zh-HK": "河流將戰場一分為二，只有五條橋可以通過。可藏身草叢伏擊對手。",
            "ja": "川が戦場を二分し、橋は5つだけ。茂みに隠れて待ち伏せできる。",
            "en": "A river splits the arena with only five bridges. Hide in the bushes to ambush.",
        },
    },
    "neon": {
        "names": {"zh": "霓虹传送站", "zh-HK": "霓虹傳送站", "ja": "ネオンワープ", "en": "Neon Warp"},
        "descs": {
            "zh": "四座传送门连通对角，能量塔林立，瞬间换位打乱节奏。",
            "zh-HK": "四道傳送門連通對角，能量塔林立，瞬間轉移足以打亂對手節奏。",
            "ja": "4つのワープゲートが対角を結ぶ。エネルギー塔が立ち並び、瞬間移動で流れを乱せる。",
            "en": "Four warp gates link opposite corners among energy towers. Reposition instantly to break the rhythm.",
        },
    },
    "candy": {
        "names": {"zh": "熔铸工厂", "zh-HK": "熔鑄工廠", "ja": "溶鉱工場", "en": "Molten Foundry"},
        "descs": {
            "zh": "传送带向中心汇聚，熔岩池与油桶遍布，处处是陷阱。",
            "zh-HK": "輸送帶湧向中央，熔岩池與油桶遍佈，處處皆是陷阱。",
            "ja": "コンベアが中央に集まり、溶岩とドラム缶だらけ。罠がいたるところに。",
            "en": "Conveyors converge on the center among lava pools and barrels. Traps everywhere.",
        },
    },
}


MAP_TEXT.update({
    "canyon": {
        "names": {"zh": "沙暴峡谷", "zh-HK": "沙暴峽谷", "ja": "砂塵の峡谷", "en": "Dust Canyon"},
        "descs": {
            "zh": "岩脊把战场切成几条峡道，中央绿洲阻断通行，油桶埋伏其间。",
            "zh-HK": "岩脊將戰場分割成數條峽道，中央綠洲阻擋去路，更有油桶伏於其間。",
            "ja": "岩の尾根が戦場をいくつもの峡谷に分断。中央のオアシスが行く手を阻み、ドラム缶が潜む。",
            "en": "Rock ridges cut the arena into narrow canyons. A central oasis blocks the way, and barrels lie in wait.",
        },
    },
    "harbor": {
        "names": {"zh": "午夜港口", "zh-HK": "午夜碼頭", "ja": "ミッドナイトハーバー", "en": "Midnight Harbor"},
        "descs": {
            "zh": "运河横贯码头，只有几座栈桥可过；钢制货箱要炸两次，传送带把人送向中央。",
            "zh-HK": "運河橫越碼頭，只有數條棧橋可以通過；鐵貨櫃須炸兩次才會破開，輸送帶會把玩家送往中央。",
            "ja": "運河が埠頭を横切り、渡れる桟橋はわずか。鋼鉄コンテナは2回爆破が必要で、コンベアが中央へ運ぶ。",
            "en": "Canals cut across the docks with only a few piers to cross. Steel containers take two blasts, and conveyors carry you to the center.",
        },
    },
    "temple": {
        "names": {"zh": "云顶神殿", "zh-HK": "雲頂神殿", "ja": "天空の神殿", "en": "Sky Temple"},
        "descs": {
            "zh": "两组传送门连通四角，冰面回廊与中央圣坛让进攻路线变化莫测。",
            "zh-HK": "兩對傳送門連通四角，冰面走廊加上中央祭壇，進攻路線難以捉摸。",
            "ja": "2組のワープゲートが四隅を結ぶ。氷の回廊と中央の祭壇が攻め筋を読みにくくする。",
            "en": "Two pairs of warp gates link all four corners. Icy corridors and a central altar make every route unpredictable.",
        },
    },
})


def map_summaries() -> list[dict]:
    return [
        {**{k: m[k] for k in ("id", "name", "desc", "theme", "rows")}, **MAP_TEXT.get(m["id"], {})}
        for m in MAPS
    ]
