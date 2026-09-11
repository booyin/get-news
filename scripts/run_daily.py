"""
每日情报采集汇总脚本：手动触发一次完整流程。
Collector → SQLite → Dedup → Trend Score → AI L1 → AI L2 → Opportunity Score → 导出
在Termius里连上服务器后，跑：python3 scripts/run_daily.py
"""
import sys
sys.path.insert(0, "/opt/ai-radar")

from datetime import date
from app.collectors.sources import collect_all
from app.storage.database import init_db, get_connection
from app.storage.models import save_items
from app.pipeline.dedup import run_dedup
from app.pipeline.scorer import run_scoring
from app.ai.analyzer import process_l1_batch, process_l2_batch, process_opportunity_batch
from app.exporter.json_export import export_daily_json
from app.exporter.markdown_export import export_daily_markdown


def step(title):
    print()
    print(f"{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def main():
    run_date = str(date.today())
    print(f"🚀 开始每日情报采集流程 — {run_date}")

    init_db()

    # 1. 采集
    step("阶段1/7: 采集数据源")
    items = collect_all()
    print(f"采集到 {len(items)} 条原始数据")

    # 2. 存储(天然URL去重)
    step("阶段2/7: 存入数据库")
    save_result = save_items(items)
    print(f"新插入 {save_result['inserted']} 条，重复跳过 {save_result['skipped']} 条")

    # 3. 语义去重
    step("阶段3/7: 语义去重")
    dedup_result = run_dedup()
    print(f"检查 {dedup_result['total_checked']} 条，发现重复 {dedup_result['duplicates_found']} 条")

    # 4. 规则打分
    step("阶段4/7: Trend Score规则打分")
    score_result = run_scoring()
    print(f"打分 {score_result['total_scored']} 条，分级: {score_result['grades']}")

    # 5. AI L1初筛
    step("阶段5/7: AI L1初筛")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM items WHERE is_filtered = 0 AND duplicate_of IS NULL AND ai_status = 'pending' ORDER BY trend_score_overall DESC"
        ).fetchall()
        l1_items = [dict(r) for r in rows]
    print(f"待L1初筛: {len(l1_items)} 条")
    if l1_items:
        l1_result = process_l1_batch(l1_items)
        print(f"L1结果: 保留{l1_result['kept']} / 淘汰{l1_result['discarded']} / 失败{l1_result['failed']}")
    else:
        print("无待处理条目，跳过")

    # 6. AI L2深度分析
    step("阶段6/7: AI L2深度分析")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM items WHERE is_filtered = 0 AND duplicate_of IS NULL AND ai_status = 'success' "
            "AND id NOT IN (SELECT item_id FROM analyses WHERE analysis_type = 'l2_deep') "
            "ORDER BY trend_score_overall DESC"
        ).fetchall()
        l2_items = [dict(r) for r in rows]
    print(f"待L2深度分析: {len(l2_items)} 条")
    if l2_items:
        l2_result = process_l2_batch(l2_items)
        print(f"L2结果: 成功{l2_result['success']} / 失败{l2_result['failed']}")
    else:
        print("无待处理条目，跳过")

    # 7. Opportunity Score + 导出
    step("阶段7/7: 机会打分 + 导出")
    opp_result = process_opportunity_batch()
    print(f"机会打分: 成功{opp_result['success']} / 失败{opp_result['failed']}")

    if opp_result["item_ids"]:
        json_path = export_daily_json(run_date, item_ids=opp_result["item_ids"])
        md_path = export_daily_markdown(run_date, item_ids=opp_result["item_ids"])
        print(f"✅ JSON导出: {json_path}")
        print(f"✅ Markdown导出: {md_path}")
    else:
        print("⚠️ 本次没有新的机会分析结果，跳过导出")

    print()
    print(f"🎉 本次运行完成 — {run_date}")


if __name__ == "__main__":
    main()
