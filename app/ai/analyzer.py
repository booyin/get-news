"""
AI L1 初筛：对Trend Score筛选后的条目做AI判断，决定是否进入L2深度分析。
对应文档第39节、第64节数据漏斗。
"""
import json
import re
import time
from pathlib import Path
from app.ai.client import gateway_chat
from app.storage.database import get_connection

PROMPT_PATH = Path(__file__).parent / "prompts" / "l1_screening.md"


def load_prompt_template() -> str:
    with open(PROMPT_PATH, "r") as f:
        return f.read()


def _extract_json(text: str) -> dict:
    """从AI返回内容中提取JSON(容错：AI有时会在JSON外面加多余文字)"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"未找到JSON结构: {text[:200]}")
    return json.loads(match.group())


def run_l1_screening(item: dict) -> dict:
    """
    对单条数据做L1初筛，返回 {"success": bool, "keep": bool, "reason": str, "raw_error": str}
    """
    template = load_prompt_template()
    prompt = template.format(title=item["title"], summary=item.get("summary", "")[:300])

    result = gateway_chat(prompt, model="radar-fast")

    if not result["success"]:
        return {"success": False, "keep": None, "reason": "", "raw_error": result["error"]}

    try:
        parsed = _extract_json(result["content"])
        return {
            "success": True,
            "keep": bool(parsed.get("keep", False)),
            "reason": parsed.get("reason", ""),
            "raw_error": "",
            "used_fallback": result.get("used_fallback", False),
        }
    except Exception as e:
        safe_content = str(result.get("content", ""))[:200]
        return {"success": False, "keep": None, "reason": "", "raw_error": f"JSON解析失败: {e}, 原始返回: {safe_content}"}


def process_l1_batch(items: list[dict]) -> dict:
    """
    批量处理，写回数据库。
    ai_status: success(已判断) / failed(调用失败) 
    is_filtered: L1判断keep=false的会被标记为过滤
    """
    stats = {"processed": 0, "kept": 0, "discarded": 0, "failed": 0}

    with get_connection() as conn:
        for idx, item in enumerate(items):
            if idx > 0:
                time.sleep(3.5)  # 控制在20次/分钟限流以内(60s/20=3s,留点余量)
            l1_result = run_l1_screening(item)
            stats["processed"] += 1

            if not l1_result["success"]:
                conn.execute(
                    "UPDATE items SET ai_status = 'failed' WHERE id = ?",
                    (item["id"],)
                )
                stats["failed"] += 1
                print(f"  ❌ [{item['title'][:40]}] AI调用失败: {l1_result['raw_error'][:100]}")
                continue

            is_filtered = 0 if l1_result["keep"] else 1
            conn.execute(
                "UPDATE items SET ai_status = 'success', ai_provider = ?, is_filtered = ? WHERE id = ?",
                ("openrouter", is_filtered, item["id"])
            )
            conn.execute(
                "INSERT INTO analyses (item_id, analysis_type, content) VALUES (?, ?, ?)",
                (item["id"], "l1_screening", json.dumps({"keep": l1_result["keep"], "reason": l1_result["reason"]}))
            )

            if l1_result["keep"]:
                stats["kept"] += 1
                print(f"  ✅ [{item['title'][:40]}] 保留 - {l1_result['reason']}")
            else:
                stats["discarded"] += 1
                print(f"  ⏭️  [{item['title'][:40]}] 淘汰 - {l1_result['reason']}")

        conn.commit()

    return stats


L2_PROMPT_PATH = Path(__file__).parent / "prompts" / "l2_deep_analysis.md"


def load_l2_prompt_template() -> str:
    with open(L2_PROMPT_PATH, "r") as f:
        return f.read()


def run_l2_analysis(item: dict, _retry: bool = True) -> dict:
    """
    对单条数据做L2深度分析，返回 {"success": bool, "analysis": dict, "raw_error": str}
    使用 radar-fast(响应更快)，精简为8个核心维度(原17维度因耗时过长已简化)。
    JSON解析失败时自动重试一次(AI生成的JSON偶发包含未转义特殊字符,重新生成通常能避开)。
    """
    template = load_l2_prompt_template()
    prompt = template.format(
        title=item["title"],
        source=item["source"],
        summary=item.get("summary", "")[:500],
    )

    result = gateway_chat(prompt, model="radar-fast", timeout=25.0)

    if not result["success"]:
        return {"success": False, "analysis": None, "raw_error": result["error"]}

    try:
        parsed = _extract_json(result["content"])
        return {"success": True, "analysis": parsed, "raw_error": "", "used_fallback": result.get("used_fallback", False)}
    except Exception as e:
        if _retry:
            time.sleep(2)
            return run_l2_analysis(item, _retry=False)
        safe_content = str(result.get("content", ""))[:300]
        return {"success": False, "analysis": None, "raw_error": f"JSON解析失败(已重试): {e}, 原始返回: {safe_content}"}


def process_l2_batch(items: list[dict]) -> dict:
    """
    批量L2深度分析，写入analyses表(analysis_type=l2_deep)。
    """
    stats = {"processed": 0, "success": 0, "failed": 0}

    with get_connection() as conn:
        for idx, item in enumerate(items):
            if idx > 0:
                time.sleep(3.5)
            l2_result = run_l2_analysis(item)
            stats["processed"] += 1

            if not l2_result["success"]:
                stats["failed"] += 1
                print(f"  ❌ [{item['title'][:40]}] L2分析失败: {l2_result['raw_error'][:150]}")
                continue

            conn.execute(
                "INSERT INTO analyses (item_id, analysis_type, content) VALUES (?, ?, ?)",
                (item["id"], "l2_deep", json.dumps(l2_result["analysis"], ensure_ascii=False))
            )
            stats["success"] += 1
            print(f"  ✅ [{item['title'][:40]}] L2分析完成 - 商业价值: {l2_result['analysis'].get('commercial_value', '')[:40]}")

        conn.commit()

    return stats


OPP_PROMPT_PATH = Path(__file__).parent / "prompts" / "opportunity_score.md"


def load_opp_prompt_template() -> str:
    with open(OPP_PROMPT_PATH, "r") as f:
        return f.read()


def run_opportunity_scoring(item: dict, l2_analysis: dict, _retry: bool = True) -> dict:
    """
    基于L2深度分析结果，让AI给出综合机会分。对应文档第38节。
    """
    template = load_opp_prompt_template()
    prompt = template.format(
        title=item["title"],
        l2_analysis=json.dumps(l2_analysis, ensure_ascii=False, indent=2),
    )

    result = gateway_chat(prompt, model="radar-fast", timeout=25.0)

    if not result["success"]:
        return {"success": False, "score": None, "raw_error": result["error"]}

    try:
        parsed = _extract_json(result["content"])
        return {"success": True, "score": parsed, "raw_error": ""}
    except Exception as e:
        if _retry:
            time.sleep(2)
            return run_opportunity_scoring(item, l2_analysis, _retry=False)
        safe_content = str(result.get("content", ""))[:300]
        return {"success": False, "score": None, "raw_error": f"JSON解析失败(已重试): {e}, 原始返回: {safe_content}"}


def process_opportunity_batch() -> dict:
    """
    对所有已完成L2分析、尚未打Opportunity Score的条目批量打分。
    写入 items.opportunity_score_overall + analyses表(type=opportunity)。
    """
    stats = {"processed": 0, "success": 0, "failed": 0, "item_ids": []}

    with get_connection() as conn:
        rows = conn.execute('''
            SELECT i.*, a.content as l2_content
            FROM items i
            JOIN analyses a ON i.id = a.item_id AND a.analysis_type = 'l2_deep'
            WHERE i.opportunity_score_overall = 0
        ''').fetchall()
        items = [dict(r) for r in rows]

    for idx, item in enumerate(items):
        if idx > 0:
            time.sleep(3.5)

        l2_analysis = json.loads(item["l2_content"])
        result = run_opportunity_scoring(item, l2_analysis)
        stats["processed"] += 1

        if not result["success"]:
            stats["failed"] += 1
            print(f"  ❌ [{item['title'][:40]}] 机会打分失败: {result['raw_error'][:150]}")
            continue

        score = result["score"]
        overall = score.get("overall", 0)

        with get_connection() as conn:
            conn.execute(
                "UPDATE items SET opportunity_score_overall = ? WHERE id = ?",
                (overall, item["id"])
            )
            conn.execute(
                "INSERT INTO analyses (item_id, analysis_type, content) VALUES (?, ?, ?)",
                (item["id"], "opportunity", json.dumps(score, ensure_ascii=False))
            )
            conn.commit()

        stats["success"] += 1
        stats["item_ids"].append(item["id"])
        print(f"  ✅ [{item['title'][:40]}] 机会分: {overall} - {score.get('verdict', '')}")

    return stats
