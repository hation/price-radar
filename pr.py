#!/usr/bin/env python3
"""price-radar 命令行入口：按关键词爬取 / 任务管理 / 历史走势查询。"""
import argparse
import asyncio


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
        await cmd_trend(args)


if __name__ == "__main__":
    asyncio.run(main())
