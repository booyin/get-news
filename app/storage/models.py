"""
数据存取操作封装。
"""
import json
from app.storage.database import get_connection


def save_items(items: list[dict]) -> dict:
    """
    批量保存采集条目。用 INSERT OR IGNORE 实现天然去重
    (id是URL哈希，阶段17正式去重逻辑会在这基础上扩展)。
    返回 {inserted: N, skipped: N}
    """
    inserted = 0
    skipped = 0
    with get_connection() as conn:
        for item in items:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO items
                (id, title, url, source, published_at, category, tags, summary,
                 trend_score_overall, opportunity_score_overall, ai_status, ai_provider, ai_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"], item["title"], item["url"], item["source"],
                    item["published_at"], item["category"], json.dumps(item.get("tags", [])),
                    item["summary"], item["trend_score"]["overall"], item["opportunity_score"]["overall"],
                    item["ai_status"], item.get("ai_provider"), item.get("ai_model"),
                )
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    return {"inserted": inserted, "skipped": skipped}


def get_item_count() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM items").fetchone()
        return row["cnt"]


def get_recent_items(limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM items ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
