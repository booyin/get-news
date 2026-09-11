"""
语义级去重：基于标题相似度识别"同一事件不同信源报道"。
对应文档第17节 / 第35节 Dedup。
硬件约束(文档第九节)：不用向量数据库/ML库，用标准库做轻量相似度比对。

v2修复：改用"词级Jaccard相似度"代替字符级SequenceMatcher。
原因：字符级比对对短标题(如Product Hunt的产品名)极不可靠，
"OpenMarket" vs "Speechmark" 这类无关词会因字符片段重叠被误判为重复。
词级比对要求"共享的独立单词"比例，短标题下更不容易假阳性。
"""
import re
from app.storage.database import get_connection

SIMILARITY_THRESHOLD = 0.6
MIN_TITLE_WORDS = 3  # 标题少于3个词时，不参与相似度去重(短产品名太容易误判)


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def get_word_set(title: str) -> set:
    normalized = normalize_title(title)
    # 过滤掉太短的停用词(a/the/is等对相似度判断没有意义的高频词)
    stopwords = {"a", "an", "the", "is", "are", "to", "of", "in", "on", "for", "and", "with"}
    words = {w for w in normalized.split() if w not in stopwords and len(w) > 1}
    return words


def title_similarity(a: str, b: str) -> float:
    """词级Jaccard相似度：交集/并集"""
    words_a = get_word_set(a)
    words_b = get_word_set(b)

    if len(words_a) < MIN_TITLE_WORDS or len(words_b) < MIN_TITLE_WORDS:
        # 任一标题词数太少，字符串完全相等才算重复，否则一律不判定
        return 1.0 if normalize_title(a) == normalize_title(b) else 0.0

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def run_dedup() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, published_at FROM items "
            "WHERE duplicate_of IS NULL AND is_filtered = 0 "
            "ORDER BY published_at ASC"
        ).fetchall()

        items = [dict(r) for r in rows]
        canonical_items = []
        duplicate_count = 0

        for item in items:
            is_dup = False
            for canonical in canonical_items:
                sim = title_similarity(item["title"], canonical["title"])
                if sim >= SIMILARITY_THRESHOLD:
                    conn.execute(
                        "UPDATE items SET duplicate_of = ? WHERE id = ?",
                        (canonical["id"], item["id"])
                    )
                    duplicate_count += 1
                    is_dup = True
                    break
            if not is_dup:
                canonical_items.append(item)

        conn.commit()

    return {
        "total_checked": len(items),
        "canonical": len(canonical_items),
        "duplicates_found": duplicate_count,
    }
