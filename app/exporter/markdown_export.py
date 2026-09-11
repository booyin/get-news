"""
导出可读的Markdown每日商业情报简报。
对应文档第35节：JSON → Markdown/YAML
"""
import json
from datetime import date
from pathlib import Path
from app.storage.database import get_connection

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "markdown"


def _format_item(item: dict, rank: int = None) -> str:
    l2 = json.loads(item["l2_content"]) if item["l2_content"] else {}
    opp = json.loads(item["opp_content"]) if item["opp_content"] else {}

    header = f"### {'🏆 ' if rank else ''}{item['title']}" if not rank else f"### 🏆 TOP{rank}: {item['title']}"

    lines = [
        header,
        "",
        f"**来源**: {item['source']} | **发布**: {item['published_at'][:10]} | "
        f"**Trend Score**: {item['trend_score_overall']:.1f} | **机会分**: {item['opportunity_score_overall']}",
        "",
        f"🔗 {item['url']}",
        "",
    ]

    if opp.get("verdict"):
        lines.append(f"> **一句话判断**: {opp['verdict']}")
        lines.append("")

    if l2:
        lines.extend([
            f"- **发生了什么**: {l2.get('what_happened', 'N/A')}",
            f"- **商业价值**: {l2.get('commercial_value', 'N/A')}",
            f"- **能否复制**: {l2.get('replicable', 'N/A')}",
            f"- **怎么做**: {l2.get('how_to_replicate', 'N/A')}",
            f"- **怎么赚钱**: {l2.get('monetization', 'N/A')}",
            f"- **技术难度**: {l2.get('technical_difficulty', 'N/A')} | **成本**: {l2.get('estimated_cost', 'N/A')}",
            f"- **风险**: 版权-{l2.get('copyright_risk', 'N/A')} / 政策-{l2.get('policy_risk', 'N/A')}",
        ])

    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def export_daily_markdown(run_date: str = None) -> str:
    if run_date is None:
        run_date = str(date.today())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        items = conn.execute('''
            SELECT i.*,
                   l2.content as l2_content,
                   opp.content as opp_content
            FROM items i
            LEFT JOIN analyses l2 ON i.id = l2.item_id AND l2.analysis_type = 'l2_deep'
            LEFT JOIN analyses opp ON i.id = opp.item_id AND opp.analysis_type = 'opportunity'
            WHERE i.opportunity_score_overall > 0
            ORDER BY i.opportunity_score_overall DESC
        ''').fetchall()
        items = [dict(r) for r in items]

    top3 = items[:3]
    rest = items[3:]

    lines = [
        f"# 📡 每日商业情报雷达 — {run_date}",
        "",
        f"今日共分析 {len(items)} 条机会，以下是完整排行。",
        "",
        "## 🏆 TOP 3 机会",
        "",
    ]
    for i, item in enumerate(top3, 1):
        lines.append(_format_item(item, rank=i))

    if rest:
        lines.append("## 📋 其余机会")
        lines.append("")
        for item in rest:
            lines.append(_format_item(item))

    content = "\n".join(lines)

    output_path = OUTPUT_DIR / f"{run_date}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(output_path)
