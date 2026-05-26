-- Supabase 迁移脚本
-- 在 Supabase SQL Editor 中执行: https://ajilnckhmjmrhcbncvgo.supabase.com → SQL Editor → New Query
-- 粘贴全部内容 → Run

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER DEFAULT 1,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    zhu_gua_name TEXT,
    zhu_gua_full TEXT,
    bian_gua_name TEXT,
    bian_gua_full TEXT,
    changing_lines TEXT,
    dong_yao_details TEXT,
    ti_yong_analysis TEXT,
    ai_prediction TEXT,
    ai_confidence REAL,
    ai_analysis TEXT,
    ai_model TEXT,
    retry_count INTEGER DEFAULT 0,
    predicted_at TIMESTAMPTZ DEFAULT NOW(),
    predicted_price REAL,
    target_date DATE,
    actual_result TEXT,
    actual_price REAL,
    actual_change_pct REAL,
    accuracy_checked INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    yingqi_date DATE
);

CREATE TABLE IF NOT EXISTS stock_picks (
    id BIGSERIAL PRIMARY KEY,
    strategy TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    score REAL,
    analysis_json TEXT,
    picked_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quality_logs (
    id BIGSERIAL PRIMARY KEY,
    call_type TEXT NOT NULL,
    input_summary TEXT,
    retry_count INTEGER DEFAULT 0,
    quality_passed INTEGER DEFAULT 0,
    fail_reason TEXT,
    response_length INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: 单用户应用, 允许所有操作
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_all_users" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_predictions" ON predictions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_stock_picks" ON stock_picks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_quality_logs" ON quality_logs FOR ALL USING (true) WITH CHECK (true);

-- 序列修复: 从 SQLite 迁移带 id 插入后必须执行，否则新插入会与已有 ID 冲突
-- 每次从外部导入数据后也需重新执行一次
SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1));
SELECT setval(pg_get_serial_sequence('predictions', 'id'), COALESCE((SELECT MAX(id) FROM predictions), 1));
SELECT setval(pg_get_serial_sequence('stock_picks', 'id'), COALESCE((SELECT MAX(id) FROM stock_picks), 1));
SELECT setval(pg_get_serial_sequence('quality_logs', 'id'), COALESCE((SELECT MAX(id) FROM quality_logs), 1));
