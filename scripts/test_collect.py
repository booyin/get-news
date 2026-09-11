"""
阶段15手动测试脚本：验证采集器能真实拉到数据。
"""
import sys
sys.path.insert(0, "/opt/ai-radar")

from app.collectors.sources import collect_all

if __name__ == "__main__":
    items = collect_all()
    print(f"\n===== 总计采集 {len(items)} 条 =====")
    print("\n===== 前3条样本 =====")
    for item in items[:3]:
        print(f"- [{item['source']}] {item['title']}")
        print(f"  URL: {item['url']}")
        print(f"  发布时间: {item['published_at']}")
        print()
