"""
导出结构化JSON：完整的当日分析结果。
对应文档第35节数据流：SQLite → JSON
"""
import json
from datetime import date
from pathlib import Path
from app.storage.database import get_connection

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "json"


def export_daily_json(run_date: str = None, item_ids: list = None) -> str:
    """
    导出条目为JSON文件。
    item_ids: 若提供，只导出这些ID(本次运行新产生的)，避免历史数据累积混入。
    若不提供，则导出全部(兼容旧用法)。
    返回文件路径。
    """
    if run_date is None:
        run_date = str(date.today())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    id_filter = ""
    params = []
    if item_ids:
        placeholders = ",".join("?" * len(item_ids))
        id_filter = f"AND i.id IN ({placeholders})"
        params = item_ids

    with get_connection() as conn:
        items = conn.execute(f'''
            SELECT i.*,
                   l1.content as l1_content,
                   l2.content as l2_content,
                   opp.content as opp_content
            FROM items i
            LEFT JOIN analyses l1 ON i.id = l1.item_id AND l1.analysis_type = 'l1_screening'
            LEFT JOIN analyses l2 ON i.id = l2.item_id AND l2.analysis_type = 'l2_deep'
            LEFT JOIN analyses opp ON i.id = opp.item_id AND opp.analysis_type = 'opportunity'
            WHERE i.opportunity_score_overall > 0 {id_filter}
            ORDER BY i.opportunity_score_overall DESC
        ''', params).fetchall()

        output_items = []
        for item in items:
            item = dict(item)
            output_items.append({
                "id": item["id"],
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "published_at": item["published_at"],
                "trend_score": item["trend_score_overall"],
                "opportunity_score": item["opportunity_score_overall"],
                "l1_screening": json.loads(item["l1_content"]) if item["l1_content"] else None,
                "l2_analysis": json.loads(item["l2_content"]) if item["l2_content"] else None,
                "opportunity_detail": json.loads(item["opp_content"]) if item["opp_content"] else None,
            })

    output = {
        "run_date": run_date,
        "total_items": len(output_items),
        "top3_ids": [item["id"] for item in output_items[:3]],
        "items": output_items,
    }

    output_path = OUTPUT_DIR / f"{run_date}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return str(output_path)
