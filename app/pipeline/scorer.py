"""
Trend Score 规则打分器。
对应文档第36节：100分制，六维度。
对应文档第35节数据流位置：在AI Gateway之前，不调用AI，纯规则粗筛。
"""
import yaml
import re
from datetime import datetime, timezone
from pathlib import Path
from app.storage.database import get_connection

RULES_PATH = Path(__file__).parent.parent.parent / "config" / "scoring_rules.yaml"


def load_rules() -> dict:
    with open(RULES_PATH, "r") as f:
        return yaml.safe_load(f)


def _score_freshness(published_at: str, max_hours: int) -> float:
    """越新分越高，线性衰减，超过max_hours归零。返回0~1的比例。"""
    try:
        pub_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours_ago = (now - pub_time).total_seconds() / 3600
        if hours_ago < 0:
            hours_ago = 0
        ratio = max(0.0, 1.0 - (hours_ago / max_hours))
        return ratio
    except Exception:
        return 0.5  # 解析失败给中性分,不因为脏数据直接清零


def _score_keywords(text: str, keywords: list[str]) -> float:
    """命中关键词比例(命中1个给0.5，命中2个及以上给1.0，命中0个给0)。"""
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    if hits == 0:
        return 0.0
    elif hits == 1:
        return 0.5
    else:
        return 1.0


def _score_spread(duplicate_count: int) -> float:
    """被多少其他条目指向自己(即被几个信源报道)，作为传播度代理。"""
    if duplicate_count == 0:
        return 0.5  # 单一信源(数据源数量少时的正常情况)，给中性基础分
    elif duplicate_count == 1:
        return 0.7
    else:
        return 1.0


def calculate_trend_score(item: dict, rules: dict, duplicate_count: int = 0) -> dict:
    """
    返回 {"overall": 0-100, "grade": "S/A/B/C/Filter", "breakdown": {...}}
    """
    w = rules["weights"]
    text = f"{item['title']} {item.get('summary', '')}"

    freshness_ratio = _score_freshness(item["published_at"], rules["freshness_max_hours"])
    spread_ratio = _score_spread(duplicate_count)
    growth_ratio = 0.5  # 第一版无时序数据，固定中性分
    commercial_ratio = _score_keywords(text, rules["commercial_keywords"])
    replicability_ratio = _score_keywords(text, rules["replicability_keywords"])
    novelty_ratio = _score_keywords(text, rules["novelty_keywords"])

    breakdown = {
        "freshness": round(freshness_ratio * w["freshness"], 1),
        "spread": round(spread_ratio * w["spread"], 1),
        "growth": round(growth_ratio * w["growth"], 1),
        "commercial": round(commercial_ratio * w["commercial_keywords"], 1),
        "replicability": round(replicability_ratio * w["replicability_keywords"], 1),
        "novelty": round(novelty_ratio * w["novelty_keywords"], 1),
    }
    overall = round(sum(breakdown.values()), 1)

    thresholds = rules["grade_thresholds"]
    if overall >= thresholds["S"]:
        grade = "S"
    elif overall >= thresholds["A"]:
        grade = "A"
    elif overall >= thresholds["B"]:
        grade = "B"
    elif overall >= thresholds["C"]:
        grade = "C"
    else:
        grade = "Filter"

    return {"overall": overall, "grade": grade, "breakdown": breakdown}


def run_scoring() -> dict:
    """
    对所有未打分(trend_score_overall=0)且非重复(duplicate_of为空)的条目打分。
    分数<60的自动标记 is_filtered=1(对应文档第37节Rule Filter)。
    """
    rules = load_rules()

    with get_connection() as conn:
        # 先统计每条"正本"被多少条重复指向(传播度代理)
        dup_counts = {}
        for row in conn.execute("SELECT duplicate_of, COUNT(*) as cnt FROM items WHERE duplicate_of IS NOT NULL GROUP BY duplicate_of"):
            dup_counts[row["duplicate_of"]] = row["cnt"]

        rows = conn.execute(
            "SELECT * FROM items WHERE duplicate_of IS NULL AND trend_score_overall = 0"
        ).fetchall()

        items = [dict(r) for r in rows]
        graded_counts = {"S": 0, "A": 0, "B": 0, "C": 0, "Filter": 0}

        for item in items:
            dup_count = dup_counts.get(item["id"], 0)
            score = calculate_trend_score(item, rules, dup_count)
            graded_counts[score["grade"]] += 1

            is_filtered = 1 if score["grade"] == "Filter" else 0
            conn.execute(
                "UPDATE items SET trend_score_overall = ?, is_filtered = ? WHERE id = ?",
                (score["overall"], is_filtered, item["id"])
            )

        conn.commit()

    return {"total_scored": len(items), "grades": graded_counts}
