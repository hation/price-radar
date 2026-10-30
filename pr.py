#!/usr/bin/env python3
"""price-radar 命令行入口：按关键词爬取 / 任务管理 / 历史走势查询。"""
import argparse
import asyncio
import csv
import json
import os


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="price-radar CLI：按关键词爬取、任务管理、历史走势查询",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例:
  python pr.py --crawl "三星/SK 64G5600" --pages 3
  python pr.py --task list
  python pr.py --task start --id 0
  python pr.py --task create --name "xxx" --keyword "xxx" --pages 3
  python pr.py --trend "三星/SK 64G5600" --days 30 --json
""",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--crawl", metavar="KEYWORD", help="按关键词爬取并落库")
    action.add_argument("--task", metavar="ACTION", help="任务管理动作: list|create|start|stop|delete")
    action.add_argument("--trend", metavar="KEYWORD", help="查询关键词历史价格走势")
    parser.add_argument("--platform", default="goofish", help="平台: goofish|jd|taobao|1688 (默认 goofish)")
    parser.add_argument("--pages", type=int, default=3, help="爬取页数 (默认 3)")
    parser.add_argument("--mode", choices=["ai", "keyword"], default="keyword", help="crawl 模式 (默认 keyword)")
    parser.add_argument("--json", action="store_true", help="结构化 JSON 输出")
    parser.add_argument("--days", type=int, default=30, help="走势窗口天数 (默认 30)")
    parser.add_argument("--export", metavar="PATH", help="trend 导出 CSV 路径")
    parser.add_argument("--name", help="task create 的任务名")
    parser.add_argument("--keyword", help="task create 的关键词")
    parser.add_argument("--id", type=int, help="task start/stop/delete 的任务 ID")
    return parser.parse_args(argv)


async def main(argv=None):
    args = _parse_args(argv)
    if args.crawl:
        from pr import cmd_crawl
        await cmd_crawl(args)
    elif args.task:
        from pr import cmd_task
        await cmd_task(args)
    elif args.trend:
        from pr import cmd_trend
        cmd_trend(args)


if __name__ == "__main__":
    asyncio.run(main())


def _render_table(headers, rows):
    """标准库文本对齐表格；rows 为空时打印 (无数据)。"""
    if not rows:
        print("(无数据)")
        return
    widths = [len(str(header)) for header in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(str(value)))
    print("  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))


def _print_json(obj):
    """JSON 结构化输出（机器可解析）。"""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_trend(args):
    """查询关键词历史价格走势（每日 min/avg/max）。"""
    from src.services.price_history_service import (
        build_price_history_insights,
        load_price_snapshots,
    )

    snapshots = load_price_snapshots(args.trend)
    if not snapshots:
        print(f"关键词 '{args.trend}' 暂无价格快照。请先 --crawl 或运行任务积累数据。")
        return

    insights = build_price_history_insights(args.trend, window_days=args.days)
    if args.json:
        _print_json(insights)
        return

    print(f"关键词: {args.trend}（近 {args.days} 天）  最新快照: {insights['latest_snapshot_at']}")
    market = insights["market_summary"]
    print(
        f"市场样本: {market['sample_count']} 条 | 均价 ¥{market['avg_price']} | "
        f"最低 ¥{market['min_price']} | 最高 ¥{market['max_price']}"
    )
    trend = insights["daily_trend"]
    _render_table(
        ["日期", "样本", "最低价", "均价", "最高价"],
        [
            [p["day"], p["sample_count"], p["min_price"], p["avg_price"], p["max_price"]]
            for p in trend
        ],
    )
    if args.export:
        _export_trend_csv(args.export, trend)
        print(f"已导出: {args.export}")


def _export_trend_csv(path, trend):
    """导出每日走势为 CSV。"""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "sample_count", "min_price", "avg_price", "max_price"])
        for p in trend:
            writer.writerow(
                [p["day"], p["sample_count"], p["min_price"], p["avg_price"], p["max_price"]]
            )
