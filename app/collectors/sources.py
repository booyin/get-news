"""
数据源调度器：读取 config/sources.yaml，依次调用各采集器。
对应文档第54节目录结构。
"""
import yaml
from pathlib import Path
from app.collectors.rss import fetch_rss

SOURCES_CONFIG = Path(__file__).parent.parent.parent / "config" / "sources.yaml"


def load_sources_config() -> dict:
    with open(SOURCES_CONFIG, "r") as f:
        return yaml.safe_load(f)


def collect_all() -> list[dict]:
    """
    执行全部启用的数据源采集，返回合并后的原始数据列表。
    这一步只负责采集，不做清洗/去重/筛选（那是阶段16-18的事）。
    """
    config = load_sources_config()
    all_items = []

    for src in config.get("rss_sources", []):
        if not src.get("enabled", True):
            continue
        print(f"[Collector] 正在采集: {src['name']} ({src['url']})")
        items = fetch_rss(src["name"], src["url"], src["category"])
        print(f"[Collector] {src['name']} 采集到 {len(items)} 条")
        all_items.extend(items)

    return all_items
