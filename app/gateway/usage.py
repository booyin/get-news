"""
每日用量统计，简单 JSON 文件持久化。
对应文档第七十九节：gateway_usage 是长期数据资产之一，
这里先用文件实现，阶段16接入SQLite后迁移。
"""
import json
import os
from datetime import date
from pathlib import Path

USAGE_FILE = Path(__file__).parent.parent.parent / "data" / "gateway_usage.json"


def _load() -> dict:
    if not USAGE_FILE.exists():
        return {}
    try:
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save(data: dict):
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_usage(provider: str, client: str, success: bool):
    today = str(date.today())
    data = _load()
    data.setdefault(today, {})
    data[today].setdefault(provider, {"success": 0, "fail": 0})
    data[today].setdefault("_by_client", {})
    data[today]["_by_client"].setdefault(client, 0)

    if success:
        data[today][provider]["success"] += 1
    else:
        data[today][provider]["fail"] += 1
    data[today]["_by_client"][client] += 1

    _save(data)


def get_today_usage() -> dict:
    today = str(date.today())
    return _load().get(today, {})
