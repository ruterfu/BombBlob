# BombBlob · 美术设计说明（生图用）

> 本文档描述 BombBlob 的玩法、游戏风格与美术风格，用于交给图像生成模型（GPT / DALL·E 等）产出概念图、海报、角色设定、场景图与图标。
> 所有设计均为原创，请勿与任何现有游戏 IP 相似。

---

## 1. 一句话概述

**BombBlob（爆破竞技场）** 是一款面向 20 岁以上玩家的**多人在线实时爆破对战游戏**：最多 6 名玩家在俯视角的网格竞技场中放置炸弹、炸开障碍、收集道具，用十字形爆炸困住对手，最后存活的玩家或队伍获胜。

- 类型：多人实时竞技 · 网格策略动作 · 派对竞技
- 视角：45°~60° 俯视（斜上方俯拍），整张地图同屏
- 目标受众：20+ 玩家，追求**成熟、精致、有质感**的风格，**不是低幼卡通**

---

## 2. 玩法要点（画面里需要体现的元素）

| 机制 | 说明 | 画面表现 |
| --- | --- | --- |
| 放置炸弹 | 炸弹 2.5 秒后爆炸，火焰呈**十字形**延伸 | 深色金属球形炸弹，腰部一圈发光能量环（颜色 = 玩家颜色），顶部引信冒火花 |
| 爆炸威力 | 起始 3×3，最大 11×11 | 十字形发光火焰光束，由蓬松的火团连接而成，带辉光 |
| 被困（核心机制） | 被火焰击中会被**困在透明能量泡**中 10 秒，只能缓慢移动 | 角色被包裹在半透明、带虹彩反光的球形气泡里，头顶有环形倒计时 |
| 救援 / 击破 | 队友碰到 → 救出复活（3 秒无敌）；敌人碰到 → 击破淘汰 | 救援时绿色 / 青色粒子爆发；击破时气泡碎裂 |
| 道具 | 炸弹数量、威力、红色跑鞋（加速）、绿色跑鞋（减速）、护盾、踢弹 | 悬浮的六边形徽章图标，带对应颜色光晕 |
| 可破坏物 | 木箱（一次）、钢制货箱（两次）、爆炸油桶（连锁爆炸） | 见第 5 节 |
| 缩圈 | 最后 60 秒，墙体从外圈向内落下 | 石墙从空中砸落，计时器变红，红色警报横幅 |
| 模式 | 个人混战 / 红队 vs 蓝队团战 | 团战时角色脚下光圈为红 / 蓝；自己头顶有发光箭头 |

---

## 3. 整体游戏风格

- **基调**：成熟、利落、竞技感；像一款精致的独立竞技游戏或电竞化派对游戏
- **关键词**：stylized realism（风格化写实）、premium、cinematic lighting、competitive arena、sleek UI
- **质感**：PBR 材质 + 环境反射；角色有胶质高光；金属、石材、木材都有真实纹理
- **光影**：低角度暖色主光 + 冷色轮廓光，拉出长阴影；发光元素（火焰、能量环、传送门、水晶）带辉光（bloom）；画面四周轻微暗角
- **避免**：
  - 粉嫩糖果色、过度饱和的儿童配色
  - 粗黑描边的卡通、Q 版低龄画风
  - 腮红、星星眼、爱心等可爱元素
  - 圆滚滚的卡通字体、emoji
  - 与任何现有游戏角色或地图相似

---

## 4. 角色设计（Blob）

### 4.1 造型

- **主体**：一个略扁的球体（宽 : 高 ≈ 1 : 0.92），像**有弹性的胶质 / 硅胶球**，表面有清漆般的高光与柔和次表面感
- **眼睛**：两只**竖向胶囊形**的眼睛（白色底 + 黑色胶囊瞳孔 + 一个小高光点），偏冷静、有斗志
- **眉毛**：两条短而粗的**斜眉，内低外高**，表情坚定、带一点挑衅；不要委屈或可爱的表情
- **脚**：两只扁椭圆的小脚，颜色比身体深
- **没有**：嘴巴、手臂、腮红
- **动作**：移动时上下弹跳、挤压拉伸；待机时轻微呼吸起伏

### 4.2 配色（8 种皮肤）

| 名称 | 颜色 |
| --- | --- |
| 赤焰 | `#e5484d` |
| 苍蓝 | `#3d8bff` |
| 翠影 | `#2fb872` |
| 琥珀 | `#f0a33a` |
| 紫晶 | `#8b5cf6` |
| 熔橙 | `#f26b38` |
| 青钢 | `#22b3c4` |
| 绯红 | `#d9467f` |

### 4.3 头饰（6 种基础 + 12 种商店装饰）

| 头饰 | 描述 |
| --- | --- |
| 无 | — |
| 战术头带 | 深炭黑色布质头带环绕头顶，正面一块红色小标签，脑后飘出一截带尾 |
| 王冠 | 抛光**金属金色**小王冠，五个尖角 |
| 耳机 | 深色头戴式耳机，两侧耳罩带**青色发光 LED** |
| 犄角 | 两只骨白色、微弯的短角 |
| 鸭舌帽 | 深炭黑色鸭舌帽，帽檐朝前，帽顶一道皮肤同色细条 |

商店装饰（达到等级后用点数购买）：贝雷帽（暗酒红）、护目镜（琥珀镜片）、头巾（蓝底白点）、牛仔帽（棕色宽檐）、骑士盔（抛光钢 + 红色羽饰）、光环（悬浮金色发光环）、礼帽（黑色高顶 + 红带）、巫师帽（深紫尖顶 + 发光星点）、冰晶冠（半透明冰晶尖刺）、烈焰冠（跳动的火焰）、龙角（暗红弯角 + 金色角尖）、星环（环绕头部旋转的发光星环）。

---

## 5. 场景元素（竞技场）

竞技场为 **23 × 19 格**的方形网格，四周是一圈较矮的外墙，整个场地像一块悬浮的平台，平台外是主题化的远景。

| 元素 | 外观 |
| --- | --- |
| 地面 | 交替深浅的方形地砖，带极细倒角与缝隙 |
| 石墙 / 石柱 | 圆角倒角的方块，侧面是**切割石块砖纹**，顶面为带边框的石板 |
| 塔楼 | 比石柱高一半的方塔，四棱锥顶，腰部一圈发光灯带 |
| 树木 / 装饰 | 低多边形风格（low-poly）的树、雪松、棕榈、水晶或烟囱，随地图主题变化 |
| 木箱 | 圆角木箱：横向木板 + 深色边框 + 斜撑 + 四角金属包角 |
| 钢制货箱 | 拉丝金属货箱，横向加强筋，底部琥珀色警示三角，四角铆钉 |
| 爆炸油桶 | 红色金属圆桶，中间一道黑底黄斜纹警示带 |
| 草丛 | 低多边形灌木，可藏身 |
| 水 / 熔岩 | 低于地面的液体格，熔岩自发光 |
| 冰面 | 半光滑反光的冰蓝色地砖 |
| 传送带 | 深色履带，琥珀色箭头，边缘黄黑警示条纹 |
| 传送门 | 地面上的发光圆盘 + 两层旋转光环 |
| 道具 | 悬浮的**深色六边形徽章**，外框为道具色，内含细线图标，下方有光晕 |

### 道具图标与颜色

| 道具 | 图标 | 颜色 |
| --- | --- | --- |
| 炸弹（可连放 +1） | 炸弹 | `#5b7cff` |
| 火焰（威力 +1） | 火焰 | `#ff7a1f` |
| 威力满级 | 爆裂星 | `#ff3b3b` |
| 红色跑鞋（速度 +5%） | 跑鞋 | `#ff3b3b` |
| 绿色跑鞋（速度 −5%） | 跑鞋 | `#2fd06a` |
| 护盾（免疫一次） | 盾牌 | `#4fb3ff` |
| 踢弹 | 踢腿 | `#c9a04a` |

---

## 6. 八张地图（主题场景）

| 地图 | 时间 / 氛围 | 主色 | 场景描述 |
| --- | --- | --- | --- |
| **遗迹广场** | 黄昏，暖金色斜阳 | 苔绿地砖、灰石、暖木 | 古老石柱阵列与塔楼，平台外是傍晚的海面与低多边形树林，空中漂浮细尘 |
| **冰霜湖** | 清冷白天 | 冰蓝、雪白、钢蓝 | 四片冰封湖面，冰块货箱，平台外是雪原与覆雪雪松，飘雪，火焰为冰蓝色 |
| **丛林秘境** | 潮湿午后 | 深绿、青蓝河水、棕木 | 一条河把场地分成两半，五座桥，大量草丛与棕榈，萤火虫点点 |
| **霓虹传送站** | 夜晚 | 深紫黑地面、霓虹粉、电光青 | 深紫色墙体配发光粉色顶盖，青色货箱，四座传送门，平台外是发光网格地面与漂浮水晶，紫色火焰 |
| **熔铸工厂** | 夜晚，熔炉火光 | 炭灰金属、琥珀、熔岩橙 | 深色金属地面，向中心汇聚的传送带，熔岩池、油桶、钢箱遍布，平台外是熔岩与工业烟囱，飘着火星 |
| **沙暴峡谷** | 沙漠黄昏 | 沙黄地砖、赭石岩壁、青绿水面 | 岩脊切出数条峡道，中央一片十字形绿洲，干枯灌木与棕榈，平台外是沙地，空中飘着沙尘 |
| **午夜港口** | 深夜码头 | 炭灰地面、黄黑警示、集装箱蓝 | 运河横贯码头只留几座栈桥，蓝色集装箱与钢制货箱密集，墙顶为黄色警示涂装，平台外是夜海与吊机管道 |
| **云顶神殿** | 云海之上的晴天 | 象牙白石、浅金、冰蓝 | 白色石砌神殿，冰面回廊，金色传送门，中央圣坛塔楼，平台外是云海与漂浮水晶 |

---

## 7. UI 风格

- **面板**：深色半透明玻璃面板（`rgba(16,20,30,0.86)` + 背景模糊），1px 细边框，**切角（左上 / 右下斜切）**，顶部一条琥珀色渐隐细线
- **主色**：底色 `#0b0e16`，琥珀点缀 `#ffb547`（主按钮渐变到 `#ff8a1f`），青色点缀 `#36d6ff`，危险红 `#ff4d5e`，成功绿 `#3ee08f`
- **字体**：标题和数字用窄体粗无衬线（类似 DIN Condensed），字间距加宽；中文用干净的黑体
- **按钮**：切角平行四边形感，主按钮为琥珀渐变配深色文字，悬停时有光泽扫过
- **图标**：统一的细线描边图标（2px 线宽，圆角端点），不用 emoji
- **Logo**：「**BOMB**」白色 + 「**BLOB**」琥珀渐变（`#ffd27a → #ff8a1f`）并带橙色光晕，窄体粗字，字间距宽；副标题「爆破竞技场 · 多人实时对战」，前面一条琥珀短线
- **菜单场景**：暗色**角色展示台**——反光的深色金属地面、发光的六边形台座、聚光灯光柱、背景一排竖向青色 / 琥珀灯条、漂浮微尘
- **结算**：大字「VICTORY / DEFEAT / DRAW」（窄体，金色渐变）配中文副标题，三颗星评分，一条横向金色光线

---

## 8. 构图与镜头参考

- **游戏画面**：斜上方约 60° 俯视，整张竞技场同屏，四周可见主题远景
- **海报 / 主视觉**：低角度仰拍或 3/4 俯视；中心是一个角色正在跳跃闪避，身后十字形爆炸光束炸开，前景木箱碎片飞溅，背景是竞技场与主题环境
- **角色设定图**：中性灰或深色背景，正面、3/4 侧面、背面三视图，外加 6 种头饰的变体

---

## 9. 可直接使用的提示词

> 用法：复制下方提示词，把【】里的内容替换成需要的选项。英文提示词通常出图更稳定。

### 9.1 游戏主视觉 / 海报

**中文**
```
原创多人竞技游戏《BombBlob》主视觉海报。风格化写实 3D 渲染，成熟精致，电影级光影，面向成年玩家。
画面中心：一个【苍蓝色】的胶质球形角色（略扁的球体，清漆高光，竖向胶囊形眼睛，内低外高的坚定斜眉，没有嘴和手臂，两只深色小脚），戴着【带青色 LED 的头戴式耳机】，正在跃起闪避。
身后：十字形的橙色发光爆炸光束炸开，带强烈辉光；前景木箱碎片和火星飞溅；地上有一颗深色金属炸弹，腰部一圈发光能量环。
背景：黄昏时分的网格竞技场，切割石块的石柱与塔楼，远处海面与低多边形树林，暖金色低角度阳光，长阴影，空气中漂浮微尘。
画面顶部 Logo「BOMB BLOB」：BOMB 为白色，BLOB 为琥珀橙渐变并带光晕，窄体粗无衬线字体。
避免：儿童卡通、粗黑描边、腮红、糖果配色、与现有游戏相似的设计。
```

**English**
```
Key art poster for an original multiplayer arena game "BombBlob". Stylized-realistic 3D render, premium and mature, cinematic lighting, aimed at adult players.
Center: a glossy jelly-like spherical character in [cobalt blue #3d8bff] (slightly squashed sphere, clear-coat highlights, two vertical capsule-shaped eyes, short thick angled eyebrows lower on the inside for a determined look, no mouth, no arms, two small dark feet), wearing [dark over-ear headphones with glowing cyan LED cups], leaping to dodge.
Behind it: a cross-shaped orange explosion beam bursting with strong bloom; wooden crate debris and sparks flying in the foreground; a dark metallic bomb on the ground with a glowing energy ring around its waist.
Background: a grid arena at golden-hour dusk, beveled cut-stone pillars and towers, distant sea and low-poly trees, warm low-angle sunlight, long shadows, floating dust particles.
Logo at top: "BOMB" in white and "BLOB" in amber-orange gradient with glow, bold condensed sans-serif, wide letter spacing.
Avoid: childish cartoon style, thick black outlines, blush cheeks, candy pastel colors, resemblance to any existing game franchise.
```

### 9.2 角色设定图（三视图）

```
Character design sheet for an original game character "Blob": a glossy, slightly squashed jelly sphere with clear-coat highlights and subtle subsurface glow, two vertical capsule eyes with small highlights, short thick angled determined eyebrows, no mouth, no arms, two small flattened darker feet.
Show front view, 3/4 view and back view on a dark neutral background (#0b0e16), studio lighting with warm key light and cyan rim light.
Below: six headgear variants on the same character — none, tactical charcoal headband with red tag and trailing tail, polished gold metal crown with five points, dark headphones with glowing cyan LEDs, two short bone-white horns, charcoal baseball cap.
Color swatches of 8 skins: #e5484d, #3d8bff, #2fb872, #f0a33a, #8b5cf6, #f26b38, #22b3c4, #d9467f.
Style: stylized realism, premium, mature, clean; not childish, no thick outlines, no blush.
```

### 9.3 地图场景（替换【】）

```
Top-down 60-degree view of a square grid battle arena (23x19 tiles) for an original multiplayer bomb game, the whole arena visible, floating platform with themed surroundings.
Theme: 【Frost Lake — four frozen ponds, icy blue reflective tiles, ice-blue crate blocks, snowfield and snow-capped pine trees outside the arena, falling snow, cold daylight】
Arena elements: beveled cut-stone wall blocks and pillars, taller towers with pyramid caps and a glowing band, wooden crates with metal corner brackets, brushed-steel cargo crates with amber warning triangles, red explosive barrels with black-and-yellow hazard stripe, low-poly bushes, small glossy jelly sphere characters with capsule eyes, dark metallic bombs with glowing rings, a cross-shaped glowing explosion beam.
Style: stylized-realistic PBR 3D, cinematic lighting with long shadows, bloom on emissive elements, subtle vignette, mature and premium, not childish.
```

其他主题替换文本：

- **遗迹广场**：`Ruins Plaza — mossy green tiles, grey cut-stone pillars and towers, golden-hour dusk sunlight, distant sea and low-poly trees, floating dust`
- **丛林秘境**：`Jungle — a river splitting the arena with five bridges, many low-poly bushes and palm trees, humid afternoon light, fireflies`
- **霓虹传送站**：`Neon Warp Station — night, dark purple-black floor tiles, deep purple walls with glowing magenta caps, cyan crates, four glowing teleport rings on the floor, glowing grid ground and floating crystals outside, purple explosion flames`
- **熔铸工厂**：`Molten Foundry — night, dark metal floor plates, conveyor belts with amber arrows and hazard-striped edges converging to the center, lava pools, red explosive barrels, steel crates, industrial chimneys and lava outside, embers in the air`

### 9.4 道具图标

```
Set of 7 game item icons for an original arena game, each a dark hexagon badge (#10131b to #2a2f3d gradient) with a thin colored outer rim and a clean 2px line icon in the same color, soft glow behind: 
bomb (#5b7cff), flame (#ff7a1f), starburst "max power" (#ff3b3b), red running shoe (#ff3b3b), green running shoe (#2fd06a), shield (#4fb3ff), kicking foot (#c9a04a).
Flat front view, consistent style, transparent background, premium game UI, no emoji, no cartoon outlines.
```

### 9.5 UI 界面概念（大厅）

```
Game lobby UI concept for an original competitive arena game "BombBlob". Dark sleek interface: semi-transparent dark glass panels (#0b0e16 base) with 1px subtle borders, chamfered corners, a thin amber (#ffb547) accent line at the top of each panel, amber gradient primary buttons with dark text, cyan (#36d6ff) secondary accents, condensed bold sans-serif headings with wide letter spacing, thin line icons.
Layout: player badge with level and ID at top-left, purple points counter (shop), ping indicator with signal bars, settings icons at top-right; two big buttons "快速匹配 QUICK MATCH" and "创建房间 CUSTOM" at bottom-left; a tabbed room list panel on the right.
Background: a dark 3D character showcase stage — reflective dark metal floor, a glowing cyan hexagonal podium with a glossy jelly sphere character on it, spotlight cone, row of vertical cyan and amber light bars, floating dust.
Mature, premium, esports-inspired, not childish.
```

### 9.6 被困泡泡特写

```
Close-up of a glossy cobalt-blue jelly sphere character (capsule eyes, angled determined eyebrows) trapped inside a translucent iridescent energy bubble, floating slightly above a stone-tiled arena floor, a circular countdown ring badge above its head showing "7", cyan glow, soft reflections, cinematic lighting, stylized-realistic 3D, mature and premium.
```
