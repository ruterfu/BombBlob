-- =====================================================================
-- BombBlob 数据库初始化脚本（PostgreSQL 13+）
--
-- 用法：psql "$DATABASE_URL" -f db/init.sql
-- 服务器启动时也会自动执行本文件（在咨询锁保护的事务中），因此可以重复执行：
--   * 表 / 列 / 索引均使用 IF NOT EXISTS
--   * 约束使用 DO 块，已存在时跳过
--   * 等级数据使用 ON CONFLICT DO NOTHING，不会覆盖线上调整过的数值
--   * 所有列都是 NOT NULL：没有值时文本存 ''，数字存 0（时间存 'epoch'，即 1970-01-01）
--     例外：matches.winner_team 没有获胜队伍时存 -1（0 是红队）
-- =====================================================================
SET client_min_messages = warning;

-- ========== 表 ==========
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,                 -- 8 位数字 ID
    name        TEXT NOT NULL,
    skin        SMALLINT NOT NULL DEFAULT 0,
    hat         SMALLINT NOT NULL DEFAULT 0,
    exp         INTEGER NOT NULL DEFAULT 0,
    points      INTEGER NOT NULL DEFAULT 0,      -- 点数：获胜获得，用于购买装饰
    games       INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    kills       INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS exp INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'guest';
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_id BIGINT NOT NULL DEFAULT 0;      -- 0 = 不是 GitHub 账号
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_login TEXT NOT NULL DEFAULT '';    -- 已停用，始终为 ''
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT NOT NULL DEFAULT '';      -- '' = 没有头像
ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT NOT NULL DEFAULT '';            -- '' = 尚未设置语言

CREATE TABLE IF NOT EXISTS login_tokens (
    token_hash  TEXT PRIMARY KEY,                 -- SHA-256（不存明文）
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    used_at     TIMESTAMPTZ NOT NULL DEFAULT 'epoch'  -- 'epoch'（1970-01-01）= 尚未使用
);

CREATE TABLE IF NOT EXISTS matches (
    id           BIGSERIAL PRIMARY KEY,
    map_id       TEXT NOT NULL,
    mode         TEXT NOT NULL,
    duration     INTEGER NOT NULL,
    winner_team  INTEGER NOT NULL DEFAULT -1,         -- -1 = 没有获胜队伍（个人战 / 平局）
    result       JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS match_key TEXT NOT NULL DEFAULT '';  -- 幂等写入键（重试不会重复结算）

CREATE TABLE IF NOT EXISTS levels (
    level         INTEGER PRIMARY KEY CHECK (level >= 1),
    exp_required  INTEGER NOT NULL CHECK (exp_required >= 0),   -- 达到该等级所需的累计经验
    tier          SMALLINT NOT NULL CHECK (tier BETWEEN 0 AND 6), -- 0 新兵 … 6 大师
    unlock_hat    SMALLINT NOT NULL DEFAULT 0                   -- 达到该等级时解锁的头饰（0 = 不解锁）
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id     BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    place        SMALLINT NOT NULL,
    win          BOOLEAN NOT NULL,
    kills        INTEGER NOT NULL,
    rescues      INTEGER NOT NULL,
    exp_gained   INTEGER NOT NULL,
    points_gained INTEGER NOT NULL DEFAULT 0,
    level_after  INTEGER NOT NULL,
    PRIMARY KEY (match_id, user_id)
);

-- 旧版本的「金币」并入「点数」（一次性迁移）：
--   旧金币 = 50 + 10×击倒，新点数 = 10 + 2×击倒，因此按 5:1 折算；之后删除金币列
--   （DROP COLUMN … CASCADE 会连带删除引用它的排行榜索引与约束，下方会按新定义重建）
ALTER TABLE match_players ADD COLUMN IF NOT EXISTS points_gained INTEGER NOT NULL DEFAULT 0;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'coins') THEN
        UPDATE users SET points = points + coins / 5 WHERE coins > 0;
        ALTER TABLE users DROP COLUMN coins CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'match_players' AND column_name = 'coins_gained') THEN
        UPDATE match_players SET points_gained = coins_gained / 5 WHERE points_gained = 0 AND coins_gained > 0;
        ALTER TABLE match_players DROP COLUMN coins_gained;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- ========== 旧库迁移：可为空的列改为 NOT NULL（只在列仍可为空时执行一次） ==========
-- 先删掉依赖 IS NULL / IS NOT NULL 的部分索引和约束，把 NULL 改成 '' / 0 / 'epoch' / -1，再加 NOT NULL；
-- 索引和约束在下面按新定义重建。
DO $$
DECLARE
    nullable BOOLEAN;
BEGIN
    SELECT is_nullable = 'YES' INTO nullable FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'github_id';
    IF nullable THEN
        DROP INDEX IF EXISTS users_github_id;
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_github_chk;
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_lang_chk;
        UPDATE users SET github_id = COALESCE(github_id, 0), github_login = COALESCE(github_login, ''),
                         avatar_url = COALESCE(avatar_url, ''), lang = COALESCE(lang, '')
            WHERE github_id IS NULL OR github_login IS NULL OR avatar_url IS NULL OR lang IS NULL;
        ALTER TABLE users ALTER COLUMN github_id SET DEFAULT 0, ALTER COLUMN github_id SET NOT NULL,
                          ALTER COLUMN github_login SET DEFAULT '', ALTER COLUMN github_login SET NOT NULL,
                          ALTER COLUMN avatar_url SET DEFAULT '', ALTER COLUMN avatar_url SET NOT NULL,
                          ALTER COLUMN lang SET DEFAULT '', ALTER COLUMN lang SET NOT NULL;
    END IF;

    SELECT is_nullable = 'YES' INTO nullable FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'login_tokens' AND column_name = 'used_at';
    IF nullable THEN
        DROP INDEX IF EXISTS login_tokens_used;
        DROP INDEX IF EXISTS login_tokens_unused;
        UPDATE login_tokens SET used_at = 'epoch' WHERE used_at IS NULL;
        ALTER TABLE login_tokens ALTER COLUMN used_at SET DEFAULT 'epoch', ALTER COLUMN used_at SET NOT NULL;
    END IF;

    SELECT is_nullable = 'YES' INTO nullable FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'matches' AND column_name = 'match_key';
    IF nullable THEN
        DROP INDEX IF EXISTS matches_key;
        UPDATE matches SET match_key = COALESCE(match_key, ''), winner_team = COALESCE(winner_team, -1)
            WHERE match_key IS NULL OR winner_team IS NULL;
        ALTER TABLE matches ALTER COLUMN match_key SET DEFAULT '', ALTER COLUMN match_key SET NOT NULL,
                            ALTER COLUMN winner_team SET DEFAULT -1, ALTER COLUMN winner_team SET NOT NULL;
    END IF;

    SELECT is_nullable = 'YES' INTO nullable FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'levels' AND column_name = 'unlock_hat';
    IF nullable THEN
        UPDATE levels SET unlock_hat = 0 WHERE unlock_hat IS NULL;
        ALTER TABLE levels ALTER COLUMN unlock_hat SET DEFAULT 0, ALTER COLUMN unlock_hat SET NOT NULL;
    END IF;
END $$;

-- ========== 索引（每条都对应一个实际查询） ==========
-- GitHub 登录：按 github_id 查账号
CREATE UNIQUE INDEX IF NOT EXISTS users_github_id ON users (github_id) WHERE github_id <> 0;
-- 排行榜：ORDER BY wins DESC, kills DESC, games ASC, id ASC LIMIT n（WHERE games > 0）
--   列顺序与排序完全一致 → 无需排序；INCLUDE 展示列 → 仅索引扫描
DROP INDEX IF EXISTS users_rank;
-- 旧版本的排行榜索引不含头像列：重建（只在定义不同时执行一次）
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'users_leaderboard' AND indexdef NOT LIKE '%avatar_url%') THEN
        DROP INDEX users_leaderboard;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS users_leaderboard ON users (wins DESC, kills DESC, games ASC, id ASC)
    INCLUDE (name, skin, hat, exp, level, avatar_url) WHERE games > 0;
-- 删除用户时级联删除 token；清理已用 / 长期未用的 token
CREATE INDEX IF NOT EXISTS login_tokens_user ON login_tokens (user_id);
CREATE INDEX IF NOT EXISTS login_tokens_used ON login_tokens (used_at) WHERE used_at > 'epoch';
CREATE INDEX IF NOT EXISTS login_tokens_unused ON login_tokens (created_at) WHERE used_at = 'epoch';
-- 经验 → 等级：WHERE exp_required <= $x ORDER BY exp_required DESC LIMIT 1
CREATE UNIQUE INDEX IF NOT EXISTS levels_exp ON levels (exp_required);
-- 个人战绩：WHERE user_id = $1 ORDER BY match_id DESC LIMIT n
DROP INDEX IF EXISTS match_players_user;
CREATE INDEX IF NOT EXISTS match_players_user_recent ON match_players (user_id, match_id DESC);
-- 对局幂等键；按时间查询对局
CREATE UNIQUE INDEX IF NOT EXISTS matches_key ON matches (match_key) WHERE match_key <> '';
CREATE INDEX IF NOT EXISTS matches_created ON matches (created_at DESC);

-- ========== 约束（重复执行安全） ==========
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_provider_chk CHECK (provider IN ('guest', 'github'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_lang_chk CHECK (lang IN ('', 'zh', 'zh-HK', 'ja', 'en'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_nonneg_chk
        CHECK (exp >= 0 AND points >= 0 AND games >= 0 AND wins >= 0 AND kills >= 0 AND wins <= games AND level >= 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_github_chk CHECK (provider <> 'github' OR github_id <> 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ========== 等级数据（1–50 级） ==========
-- 第 n 级升到 n+1 级需要 100 + 50*(n-1) 经验；
-- 段位：0 新兵(1-4) 1 青铜(5-9) 2 白银(10-14) 3 黄金(15-19) 4 铂金(20-29) 5 钻石(30-39) 6 大师(40-50)
-- 头饰：1 战术头带 / 2 王冠 / 3 耳机 / 4 犄角 / 5 鸭舌帽（0 无，Lv1 即可使用）
INSERT INTO levels (level, exp_required, tier, unlock_hat) VALUES
    ( 1,      0, 0, 0),  -- 新兵
    ( 2,    100, 0,    1),  -- 新兵，解锁战术头带
    ( 3,    250, 0,    3),  -- 新兵，解锁耳机
    ( 4,    450, 0, 0),  -- 新兵
    ( 5,    700, 1,    4),  -- 青铜，解锁犄角
    ( 6,   1000, 1, 0),  -- 青铜
    ( 7,   1350, 1, 0),  -- 青铜
    ( 8,   1750, 1,    5),  -- 青铜，解锁鸭舌帽
    ( 9,   2200, 1, 0),  -- 青铜
    (10,   2700, 2, 0),  -- 白银
    (11,   3250, 2, 0),  -- 白银
    (12,   3850, 2,    2),  -- 白银，解锁王冠
    (13,   4500, 2, 0),  -- 白银
    (14,   5200, 2, 0),  -- 白银
    (15,   5950, 3, 0),  -- 黄金
    (16,   6750, 3, 0),  -- 黄金
    (17,   7600, 3, 0),  -- 黄金
    (18,   8500, 3, 0),  -- 黄金
    (19,   9450, 3, 0),  -- 黄金
    (20,  10450, 4, 0),  -- 铂金
    (21,  11500, 4, 0),  -- 铂金
    (22,  12600, 4, 0),  -- 铂金
    (23,  13750, 4, 0),  -- 铂金
    (24,  14950, 4, 0),  -- 铂金
    (25,  16200, 4, 0),  -- 铂金
    (26,  17500, 4, 0),  -- 铂金
    (27,  18850, 4, 0),  -- 铂金
    (28,  20250, 4, 0),  -- 铂金
    (29,  21700, 4, 0),  -- 铂金
    (30,  23200, 5, 0),  -- 钻石
    (31,  24750, 5, 0),  -- 钻石
    (32,  26350, 5, 0),  -- 钻石
    (33,  28000, 5, 0),  -- 钻石
    (34,  29700, 5, 0),  -- 钻石
    (35,  31450, 5, 0),  -- 钻石
    (36,  33250, 5, 0),  -- 钻石
    (37,  35100, 5, 0),  -- 钻石
    (38,  37000, 5, 0),  -- 钻石
    (39,  38950, 5, 0),  -- 钻石
    (40,  40950, 6, 0),  -- 大师
    (41,  43000, 6, 0),  -- 大师
    (42,  45100, 6, 0),  -- 大师
    (43,  47250, 6, 0),  -- 大师
    (44,  49450, 6, 0),  -- 大师
    (45,  51700, 6, 0),  -- 大师
    (46,  54000, 6, 0),  -- 大师
    (47,  56350, 6, 0),  -- 大师
    (48,  58750, 6, 0),  -- 大师
    (49,  61200, 6, 0),  -- 大师
    (50,  63700, 6, 0)   -- 大师
ON CONFLICT (level) DO NOTHING;

-- ========== 等级无上限 ==========
-- 超过 levels 表最后一级后按同一曲线继续：每级所需经验在上一级的基础上 +50。
-- 例：Lv50 累计 63,700，Lv51 需要 66,250，Lv60 需要 92,950 ……
-- 计算：levels 表内用 levels_exp 索引单行查找；超出部分解一元二次方程 25m² + (d−25)m ≤ 剩余经验。
CREATE OR REPLACE FUNCTION bb_level(e INTEGER) RETURNS INTEGER
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    lv INTEGER; base INTEGER; prev INTEGER; d BIGINT; rest BIGINT; m BIGINT;
BEGIN
    SELECT level, exp_required INTO lv, base FROM levels WHERE exp_required <= e ORDER BY exp_required DESC LIMIT 1;
    IF lv IS NULL THEN RETURN 1; END IF;
    IF EXISTS (SELECT 1 FROM levels WHERE level = lv + 1) THEN RETURN lv; END IF;
    SELECT exp_required INTO prev FROM levels WHERE level = lv - 1;
    d := COALESCE(base - prev, 50) + 50;            -- lv → lv+1 所需经验
    rest := e - base;
    m := floor((-(d - 25) + sqrt(((d - 25) * (d - 25) + 100 * rest)::float8)) / 50);
    WHILE 25 * (m + 1) * (m + 1) + (d - 25) * (m + 1) <= rest LOOP m := m + 1; END LOOP;  -- 浮点误差修正
    WHILE m > 0 AND 25 * m * m + (d - 25) * m > rest LOOP m := m - 1; END LOOP;
    RETURN lv + m::INTEGER;
END $$;

-- ========== 点数与装饰商店 ==========
-- 点数：只有获胜才获得（10 + 2×击倒 + 2×救援），用于购买装饰；失败没有点数（列定义见 users 表）。
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_points_chk CHECK (points >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 装饰目录：达到 min_level 后才能用 price 点购买（id 与客户端头饰编号一致）
CREATE TABLE IF NOT EXISTS cosmetics (
    id         SMALLINT PRIMARY KEY CHECK (id >= 6),     -- 0–5 为按等级免费解锁的基础头饰
    slot       TEXT NOT NULL DEFAULT 'hat' CHECK (slot IN ('hat')),
    code       TEXT NOT NULL UNIQUE,
    min_level  INTEGER NOT NULL CHECK (min_level >= 1),
    price      INTEGER NOT NULL CHECK (price >= 0)
);

-- 已拥有的装饰：主键 (user_id, item_id) 同时满足「查某人拥有什么」和「防止重复购买」
CREATE TABLE IF NOT EXISTS user_items (
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id      SMALLINT NOT NULL REFERENCES cosmetics(id),
    price_paid   INTEGER NOT NULL CHECK (price_paid >= 0),
    acquired_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, item_id)
);

-- 价格依据（平均每胜约 14 点、约 130 经验）：
--   Lv10 约 20 胜 → 累计约 280 点，可买 1 件 150 点的装饰；
--   Lv50 约 490 胜 → 累计约 6,900 点；全部 12 件共 6,350 点，正好可以全部收齐。
INSERT INTO cosmetics (id, code, min_level, price) VALUES
    ( 6, 'beret',        10,  150),
    ( 7, 'goggles',      10,  150),
    ( 8, 'bandana',      10,  150),
    ( 9, 'cowboy',       20,  300),
    (10, 'knight',       20,  300),
    (11, 'halo',         20,  300),
    (12, 'tophat',       30,  500),
    (13, 'wizard',       30,  500),
    (14, 'ice_crown',    40,  800),
    (15, 'flame_crown',  40,  800),
    (16, 'dragon_horns', 50, 1200),
    (17, 'star_ring',    50, 1200)
ON CONFLICT (id) DO NOTHING;

-- ========== 更名卡 ==========
-- 在商店用点数购买（可叠加），每次改名消耗 1 张；没有更名卡不能改名。
ALTER TABLE users ADD COLUMN IF NOT EXISTS rename_cards INTEGER NOT NULL DEFAULT 0;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_rename_cards_chk CHECK (rename_cards >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 改名记录（审计 / 客服查询）：按用户倒序查询命中 name_changes_user 索引
CREATE TABLE IF NOT EXISTS name_changes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    old_name    TEXT NOT NULL,
    new_name    TEXT NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS name_changes_user ON name_changes (user_id, changed_at DESC);

-- ========== GitHub 只保存用户 ID 与头像 ==========
-- 登录不申请任何 scope；只保存 GitHub 用户 ID 和头像地址，不保存 GitHub 用户名（清除旧版本保存过的，重复执行无影响）
UPDATE users SET github_login = '' WHERE github_login <> '';

-- ========== 角色创建 ==========
-- 新账号（游客 / GitHub）登录后先进入「创建角色」流程（取名、颜色、头饰），完成后才能进入大厅。
-- 已有账号默认视为已创建角色。
ALTER TABLE users ADD COLUMN IF NOT EXISTS has_character BOOLEAN NOT NULL DEFAULT TRUE;

-- ========== 炸弹特效（商店） ==========
-- 纯画面效果：毒弹（紫色毒气）/ 水弹（水波）/ 金弹（金光），范围、威力、爆炸时间与普通炸弹完全一样。
-- 每次 200 点，有效 7 天；同一时间只有一种生效，再次购买会覆盖之前的（有效期从购买时重新算）。
ALTER TABLE users ADD COLUMN IF NOT EXISTS bomb_style TEXT NOT NULL DEFAULT '';               -- '' = 普通火焰
ALTER TABLE users ADD COLUMN IF NOT EXISTS bomb_until TIMESTAMPTZ NOT NULL DEFAULT 'epoch';   -- 到期时间
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_bomb_style_chk CHECK (bomb_style IN ('', 'poison', 'water', 'gold'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- 购买记录（审计 / 客服查询）
CREATE TABLE IF NOT EXISTS bomb_purchases (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    style       TEXT NOT NULL,
    price_paid  INTEGER NOT NULL CHECK (price_paid >= 0),
    bought_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS bomb_purchases_user ON bomb_purchases (user_id, id DESC);

-- ========== 加成卡（商店） ==========
-- 经验卡 / 点数卡：×1.5 / ×2 / ×3，有效 24 小时，期间对局获得的经验 / 点数按倍率加成。
-- 经验和点数各占一个位置：再买同一倍率 → 在当前到期时间上再加 24 小时；买不同倍率 → 立即替换，从现在起 24 小时。
-- 倍率按百分比存（100 = 没有加成）。
ALTER TABLE users ADD COLUMN IF NOT EXISTS exp_boost INTEGER NOT NULL DEFAULT 100;
ALTER TABLE users ADD COLUMN IF NOT EXISTS exp_boost_until TIMESTAMPTZ NOT NULL DEFAULT 'epoch';
ALTER TABLE users ADD COLUMN IF NOT EXISTS points_boost INTEGER NOT NULL DEFAULT 100;
ALTER TABLE users ADD COLUMN IF NOT EXISTS points_boost_until TIMESTAMPTZ NOT NULL DEFAULT 'epoch';
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_exp_boost_chk CHECK (exp_boost = ANY (ARRAY[100, 150, 200, 300]));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_points_boost_chk CHECK (points_boost = ANY (ARRAY[100, 150, 200, 300]));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- 购买记录（审计 / 客服查询）
CREATE TABLE IF NOT EXISTS boost_purchases (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('exp', 'points')),
    pct         INTEGER NOT NULL CHECK (pct IN (150, 200, 300)),
    price_paid  INTEGER NOT NULL CHECK (price_paid >= 0),
    bought_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS boost_purchases_user ON boost_purchases (user_id, id DESC);
