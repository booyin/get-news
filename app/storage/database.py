"""
SQLite 数据库连接与建表。
对应文档第42-44节：sources / items / analyses / ai_usage / gateway_usage / daily_runs
对应文档第80节：SQLite历史数据库是项目真正的长期资产。
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent.parent / "data" / "radar.db"

SCHEMA = """
-- 数据源表：记录每个采集源的元信息
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,              -- rss / github / web
    url TEXT NOT NULL,
    category TEXT,
    enabled INTEGER DEFAULT 1,
    last_fetched_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 采集条目表：对应文档第41节统一数据结构
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,             -- URL哈希，阶段17去重用
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TEXT,
    category TEXT,
    tags TEXT,                       -- JSON数组存成文本
    summary TEXT,
    trend_score_overall REAL DEFAULT 0,
    opportunity_score_overall REAL DEFAULT 0,
    ai_status TEXT DEFAULT 'pending',  -- pending/success/failed/skipped
    ai_provider TEXT,
    ai_model TEXT,
    is_filtered INTEGER DEFAULT 0,   -- 阶段18规则筛选是否被淘汰
    created_at TEXT DEFAULT (datetime('now'))
);

-- AI深度分析结果表：对应文档第39节AI深度分析的字段
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    analysis_type TEXT NOT NULL,     -- l1_screening / l2_deep / opportunity
    content TEXT,                    -- AI返回的完整分析内容(JSON文本)
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (item_id) REFERENCES items(id)
);

-- AI调用统计：对应文档第43节
CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0,
    latency_ms INTEGER,
    fallback_used INTEGER DEFAULT 0,
    error_code TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Gateway用量统计：对应文档第44节(阶段10已有JSON版本，这里是SQLite正式版)
CREATE TABLE IF NOT EXISTS gateway_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    model_alias TEXT,
    provider TEXT,
    actual_model TEXT,
    status TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER,
    fallback_used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 每日运行记录：对应文档第79节长期数据资产之一
CREATE TABLE IF NOT EXISTS daily_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL UNIQUE,
    total_collected INTEGER DEFAULT 0,
    total_after_filter INTEGER DEFAULT 0,
    total_ai_l1 INTEGER DEFAULT 0,
    total_ai_l2 INTEGER DEFAULT 0,
    top3_item_ids TEXT,               -- JSON数组存成文本
    status TEXT DEFAULT 'running',    -- running/success/failed
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at);
CREATE INDEX IF NOT EXISTS idx_items_ai_status ON items(ai_status);
CREATE INDEX IF NOT EXISTS idx_analyses_item_id ON analyses(item_id);
"""


def init_db():
    """建表，幂等操作(重复执行不会报错或重建)"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection():
    """统一的数据库连接上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
