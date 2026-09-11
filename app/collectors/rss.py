"""
RSS 采集器。
对应文档第33节：数据来源之一。
使用 feedparser（阶段3已安装），只读公开RSS，不绕过任何访问控制。
"""
import feedparser
import hashlib
from datetime import datetime, timezone


def _make_id(url: str) -> str:
    """用URL生成稳定唯一ID，供后续去重使用（阶段17）"""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def fetch_rss(source_name: str, url: str, category: str) -> list[dict]:
    """
    抓取单个RSS源，返回统一数据结构的列表。
    对应文档第41节：统一数据结构。
    """
    items = []
    try:
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            # bozo=1 且没有任何条目，说明解析彻底失败
            print(f"[RSS] {source_name} 解析失败: {feed.bozo_exception}")
            return items

        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue

            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                published_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
            else:
                published_at = datetime.now(timezone.utc).isoformat()

            items.append({
                "id": _make_id(link),
                "title": entry.get("title", "").strip(),
                "url": link,
                "source": source_name,
                "published_at": published_at,
                "category": category,
                "tags": [],
                "summary": entry.get("summary", "")[:500],  # 先截断,AI摘要在L1/L2阶段生成
                "trend_score": {"overall": 0},
                "opportunity_score": {"overall": 0},
                "ai_status": "pending",
                "ai_provider": None,
                "ai_model": None,
                "ai_analysis": {},
            })
    except Exception as e:
        print(f"[RSS] {source_name} 采集异常: {e}")

    return items
