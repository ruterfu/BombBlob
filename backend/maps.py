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
  g  金色宝箱（一次摧毁，必出道具）
  w  冰墙闸门（开局升起）     u  冰墙闸门（开局落下）——两组每隔几秒轮流升降
  s  补给台（定时空投道具）    f  火焰喷口（定时向四周喷火）

地图还可以带 "mech"：regrow（被烧掉的草丛会重新长出来）/ meteor（火山陨石）
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
        "desc": "十字林荫大道通向中央广场，四个街区是坍塌的古城残垣，油桶藏在废墟里。",
        "theme": "meadow",
        "density": 0.74,
        "quadrant": [
            "############",
            "#P.**e*#*Y..",
            "#.##**#**.*.",
            "#*#m*b**#Y.*",
            "#**#*##*m.*.",
            "#e*b*#*b*Y..",
            "#.#**m*#*.*.",
            "#P*#*Y*Y.H..",
            "#.*.*.*.....",
            "#**e*.*.*...",
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
            "#P.jj*Y*jj.j",
            "#.YjjiiijjYj",
            "#jjii~~~iijj",
            "#*ji~~~~~ij*",
            "#jji~~~~~ijj",
            "#*jjii~iijm.",
            "#Pj*jiiijj*.",
            "#.YYjjjj*Y..",
            "#jj*j.ij*...",
        ],
    },
    {
        "id": "jungle",
        "name": "丛林秘境",
        "desc": "蜿蜒的河流中间夹着一条沙洲，只有几处浅滩能过河；草丛可以藏身伏击。",
        "theme": "jungle",
        "density": 0.72,
        "quadrant": [
            "############",
            "#P.bb**Y.bb*",
            "#.Yb*bb*Y*b*",
            "#bb*YY*bb*b.",
            "#*b*b**Y*bb*",
            "#.bbY*b*b*Y.",
            "#*b*b*bb*b**",
            "#P*bbY*b*YY.",
            "#~~~.~~~bb*.",
            "#b*b*b*~~.~~",
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
            "#P.**.*****.",
            "#.####*##*#.",
            "#*#1.*m*#**.",
            "#*#*###*#*##",
            "#.**.*e*..*.",
            "####*#*####*",
            "#P*.*#*m*.*.",
            "#.#*##**#*..",
            "#**H*.*.....",
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
            "#P.>>>v.m*e*",
            "#.mm*.v#H#*.",
            "#*m*e.v*.**.",
            "#.*##.>>>>v.",
            "#e*##*m*..v.",
            "#.*.*e**H.v.",
            "#P*^<<<*...~",
            "#.m*mm*e*.~~",
            "#*e*..*..~~~",
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
            "#P.**Y**e*..",
            "#.*Y**Y**b*.",
            "#*Y**Y**Y*.*",
            "#Y**Y**Y**b.",
            "#**Y**Y**Y*.",
            "#e*b*Y**Y*~~",
            "#P***bY**.~Y",
            "#.*e**bY*.~~",
            "#**.*..*Y...",
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
            "#P.mm*.*mm*.",
            "#.*mm*H*mm*.",
            "#*..*.*.*..*",
            "#mm*.mm*.mm*",
            "#mm*.mm*.mm*",
            "#.*..*e*>>*.",
            "#P*H*.*.*H*.",
            "#.e**.*.*e*.",
            "#~~.~~~~.~~~",
        ],
    },
    {
        "id": "temple",
        "name": "云顶神殿",
        "desc": "两层回字形环墙围住中央圣坛，每层只留几道门；两组传送门与冰面回廊让进攻路线变化莫测。",
        "theme": "temple",
        "density": 0.7,
        "quadrant": [
            "############",
            "#P.**e***1*.",
            "#.*i*****.*.",
            "#**i*##.####",
            "#*.i*#*****.",
            "#**i*#*e*.*.",
            "#.*i*.*####.",
            "#P*i*#*#*.*.",
            "#.*i*#2#....",
            "#*e*.#*.....",
        ],
    },
    {
        "id": "sakura",
        "name": "樱花庭院",
        "desc": "樱花林里遍布草丛与锦鲤池；被烧掉的草丛过一会儿会重新长出来，适合埋伏。",
        "theme": "sakura",
        "density": 0.68,
        "mech": "regrow",
        "quadrant": [
            "############",
            "#P.bb*b*bb*.",
            "#.~~*b*Y*b**",
            "#.~~b*b*b*bb",
            "#b*b*Y*bb*b*",
            "#*b*b*b###..",
            "#b*Y*b*#bb*.",
            "#P*b*b*#b*..",
            "#.b*b*b.b...",
            "#b*bb*b.b...",
        ],
    },
    {
        "id": "mine",
        "name": "雷鸣矿坑",
        "desc": "坑道里塞满油桶，金色宝箱炸开必出道具，一颗炸弹就能引发连环爆破。",
        "theme": "mine",
        "density": 0.72,
        "quadrant": [
            "############",
            "#P.*e*##*g*.",
            "#.##*m##*e**",
            "#*##e*..*##.",
            "#*e*g*##*##*",
            "##*m*e##e*..",
            "##g*##*e*m*.",
            "#P*e##*g*##.",
            "#.*m**e*##..",
            "#*e*g*.*....",
        ],
    },
    {
        "id": "glacier",
        "name": "极光冰川",
        "desc": "冰墙闸门每隔几秒轮流升降，迷宫随时改变；冰面上一旦起步就很难停下。",
        "theme": "glacier",
        "density": 0.66,
        "quadrant": [
            "############",
            "#P.jjj#jjj.j",
            "#.jj#jwjj#jj",
            "#jj#jjijj#ij",
            "#j#jjiiiu#ii",
            "#jwjiiiiiiiw",
            "#jj#iiu#iiii",
            "#Pjj#jii#iii",
            "#.jjj>>iiiii",
            "#jjwjjiiiiii",
        ],
    },
    {
        "id": "starport",
        "name": "星际空港",
        "desc": "十二座传送门组成迷阵，补给台定时空投道具，抢补给还是守传送门？",
        "theme": "starport",
        "density": 0.7,
        "quadrant": [
            "############",
            "#P.**1*###*.",
            "#.*m***###*s",
            "#**###*****.",
            "#**###*m*2*.",
            "#.*****###*.",
            "#*m*3**###**",
            "#P****......",
            "#.**###.s...",
            "#*e*###.....",
        ],
    },
    {
        "id": "arena",
        "name": "烈日斗兽场",
        "desc": "中央是空旷的竞技场，地面的火焰喷口会定时喷火，正面硬碰硬。",
        "theme": "arena",
        "density": 0.6,
        "quadrant": [
            "############",
            "#P.***Y***..",
            "#.*m******m*",
            "#**.*m*****.",
            "#**m***HHH..",
            "#*m***H.....",
            "#**m*H..f...",
            "#P**.H......",
            "#.*m........",
            "#**m*.....f.",
        ],
    },
    {
        "id": "volcano",
        "name": "火山孤岛",
        "desc": "熔岩把战场分成四座孤岛，只有八座窄桥相连；火山不时喷出陨石砸向地面。",
        "theme": "volcano",
        "density": 0.7,
        "mech": "meteor",
        "quadrant": [
            "############",
            "#P.***e**.*~",
            "#.*YY**m**.~",
            "#**Y**.**e..",
            "#*m***YY*.*~",
            "#e**.*Y**m*~",
            "#.*m***.**.~",
            "#P**YY*e**..",
            "#.**Y**.*.*~",
            "#~~.~~~~~.~~",
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
    mech: str = ""


SOLID_STATIC = ("#", "Y", "H")  # 永久障碍
DESTRUCTIBLE = ("x", "m", "e", "g")  # 可被炸毁的方块


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
            if c in ("#", "x", "m", "e", "g", "Y", "H", "~", "b"):
                blocks[i] = c
            elif c == "w":  # 冰墙闸门（开局升起）：地板记下位置，方块随时间升降
                floor[i] = "w"
                blocks[i] = "w"
            elif c in ("u", "s", "f"):
                floor[i] = c
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
    # 补给台 / 火焰喷口 / 闸门本身不放木箱
    for i, f in enumerate(floor):
        if f in ("s", "f", "u") and blocks[i] in DESTRUCTIBLE:
            blocks[i] = "."
    # 传送门四周不放木箱：传送过去后一定能走开（否则落在被木箱围住的格子里，传送锁解不开就永远出不来）
    for cells in tele_pos.values():
        for i in cells:
            x, y = i % W, i // W
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and blocks[ny * W + nx] in DESTRUCTIBLE:
                    blocks[ny * W + nx] = "."
    tele: dict[int, int] = {}
    for a, b in tele_pos.values():
        tele[a] = b
        tele[b] = a
    return BuiltMap(d["id"], d["theme"], W, H, floor, blocks, spawns, tele, d.get("mech", ""))


MAP_TEXT = {
    "meadow": {
        "names": {"zh": "遗迹广场", "zh-HK": "遺跡廣場", "ja": "遺跡の広場", "en": "Ruins Plaza"},
        "descs": {
            "zh": "十字林荫大道通向中央广场，四个街区是坍塌的古城残垣，油桶藏在废墟里。",
            "zh-HK": "十字林蔭大道通往中央廣場，四個街區是倒塌的古城殘垣，油桶藏在廢墟之中。",
            "ja": "十字の並木道が中央広場へ続き、四つの街区は崩れた古城の廃墟。ドラム缶が瓦礫に潜む。",
            "en": "Tree-lined avenues cross at a central plaza, surrounded by four blocks of crumbling ruins with barrels hidden in the rubble.",
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
            "zh": "蜿蜒的河流中间夹着一条沙洲，只有几处浅滩能过河；草丛可以藏身伏击。",
            "zh-HK": "蜿蜒的河流中間夾着一條沙洲，只有幾處淺灘可以過河；可藏身草叢伏擊對手。",
            "ja": "蛇行する川の中ほどに中州があり、渡れる浅瀬はわずか。茂みに隠れて待ち伏せできる。",
            "en": "A winding river wraps around a sandbar with only a few fords to cross. Hide in the bushes to ambush.",
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
            "zh": "两层回字形环墙围住中央圣坛，每层只留几道门；两组传送门与冰面回廊让进攻路线变化莫测。",
            "zh-HK": "兩層回字形環牆圍住中央祭壇，每層只留數道門；兩對傳送門加上冰面走廊，進攻路線難以捉摸。",
            "ja": "二重の回廊壁が中央の祭壇を囲み、門は数か所だけ。2組のワープゲートと氷の回廊が攻め筋を読みにくくする。",
            "en": "Two rings of temple walls guard the central altar with only a few gates. Warp gates and icy corridors make every route unpredictable.",
        },
    },
    "sakura": {
        "names": {"zh": "樱花庭院", "zh-HK": "櫻花庭園", "ja": "桜の庭園", "en": "Sakura Garden"},
        "descs": {
            "zh": "樱花林里遍布草丛与锦鲤池；被烧掉的草丛过一会儿会重新长出来，适合埋伏。",
            "zh-HK": "櫻花林內遍佈草叢與錦鯉池；燒掉的草叢過一陣子會重新長出來，最適合埋伏。",
            "ja": "桜の林に茂みと鯉の池が広がる。燃えた茂みはしばらくすると生え戻り、待ち伏せに最適。",
            "en": "Bushes and koi ponds fill the cherry grove. Burnt bushes grow back after a while, perfect for ambushes.",
        },
    },
    "mine": {
        "names": {"zh": "雷鸣矿坑", "zh-HK": "雷鳴礦坑", "ja": "雷鳴の鉱山", "en": "Thunder Mine"},
        "descs": {
            "zh": "坑道里塞满油桶，金色宝箱炸开必出道具，一颗炸弹就能引发连环爆破。",
            "zh-HK": "坑道塞滿油桶，金色寶箱炸開必定有道具，一個炸彈就能引發連環爆炸。",
            "ja": "坑道はドラム缶だらけ。金の宝箱を壊すと必ずアイテムが出る。爆弾ひとつで大連鎖。",
            "en": "Tunnels packed with barrels. Golden chests always drop a power-up, and one bomb can set off a chain reaction.",
        },
    },
    "glacier": {
        "names": {"zh": "极光冰川", "zh-HK": "極光冰川", "ja": "オーロラ氷河", "en": "Aurora Glacier"},
        "descs": {
            "zh": "冰墙闸门每隔几秒轮流升降，迷宫随时改变；冰面上一旦起步就很难停下。",
            "zh-HK": "冰牆閘門每隔數秒輪流升降，迷宮隨時改變；冰面上一起步就難以煞停。",
            "ja": "氷の壁ゲートが数秒ごとに交互に上下し、迷路が刻々と変わる。氷の上では止まりにくい。",
            "en": "Ice gates rise and fall in turns every few seconds, reshaping the maze. Once you slide, it's hard to stop.",
        },
    },
    "starport": {
        "names": {"zh": "星际空港", "zh-HK": "星際空港", "ja": "スターポート", "en": "Starport"},
        "descs": {
            "zh": "十二座传送门组成迷阵，补给台定时空投道具，抢补给还是守传送门？",
            "zh-HK": "十二道傳送門組成迷陣，補給台定時空投道具，搶補給定守傳送門？",
            "ja": "12基のワープゲートが迷宮をつくる。補給台には定期的にアイテムが届く。補給を奪うか、ゲートを守るか。",
            "en": "Twelve warp gates form a maze, and supply pads get regular air drops. Grab the loot or guard the gates?",
        },
    },
    "arena": {
        "names": {"zh": "烈日斗兽场", "zh-HK": "烈日鬥獸場", "ja": "灼熱の闘技場", "en": "Sun Arena"},
        "descs": {
            "zh": "中央是空旷的竞技场，地面的火焰喷口会定时喷火，正面硬碰硬。",
            "zh-HK": "中央是空曠的競技場，地上的火焰噴口會定時噴火，正面硬碰硬。",
            "ja": "中央は見通しのいい闘技場。床の噴射口から定期的に炎が噴き出す。真っ向勝負だ。",
            "en": "A wide-open arena in the middle. Floor vents erupt with fire on a timer. Fight head-on.",
        },
    },
    "volcano": {
        "names": {"zh": "火山孤岛", "zh-HK": "火山孤島", "ja": "火山の孤島", "en": "Volcano Isles"},
        "descs": {
            "zh": "熔岩把战场分成四座孤岛，只有八座窄桥相连；火山不时喷出陨石砸向地面。",
            "zh-HK": "熔岩將戰場分成四座孤島，只靠八條窄橋相連；火山不時噴出隕石砸向地面。",
            "ja": "溶岩が戦場を4つの島に分け、つなぐのは8本の細い橋だけ。火山からときどき隕石が降ってくる。",
            "en": "Lava splits the arena into four islands joined by eight narrow bridges, and the volcano keeps raining meteors.",
        },
    },
})


def map_summaries() -> list[dict]:
    return [
        {**{k: m[k] for k in ("id", "name", "desc", "theme", "rows")}, **MAP_TEXT.get(m["id"], {})}
        for m in MAPS
    ]
