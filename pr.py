#!/usr/bin/env python3
"""price-radar 命令行入口：按关键词爬取 / 任务管理 / 历史走势查询。"""
import argparse
import asyncio
import csv
import json
import os

from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository


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
        cmd_crawl(args)
    elif args.task:
        from pr import cmd_task
        cmd_task(args)
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


def cmd_task(args):
    """任务管理: list / create / start / stop / delete（复用 Web 同一 SQLite）。"""
    from src.domain.models.task import Task
    from src.platforms import normalize_platform_key

    repo = SqliteTaskRepository()
    action = args.task

    if action == "list":
        tasks = asyncio.run(repo.find_all())
        _render_table(
            ["ID", "名称", "关键词", "平台", "启用", "运行中", "定时"],
            [
                [t.id, t.task_name, t.keyword, t.platform, t.enabled, t.is_running, t.cron or ""]
                for t in tasks
            ],
        )
        return

    if action == "create":
        if not args.name or not args.keyword:
            print("create 需要 --name 和 --keyword。示例: --task create --name x --keyword x")
            return
        task = Task(
            task_name=args.name,
            keyword=args.keyword,
            enabled=True,
            max_pages=args.pages,
            personal_only=True,
            platform=normalize_platform_key(args.platform),
            decision_mode="keyword",
            ai_prompt_base_file="prompts/base_prompt.txt",
            ai_prompt_criteria_file="",
        )
        saved = asyncio.run(repo.save(task))
        print(f"已创建任务 #{saved.id}: {saved.task_name}（keyword 模式，不依赖 AI）")
        return

    if action == "delete":
        if args.id is None:
            print("delete 需要 --id")
            return
        ok = asyncio.run(repo.delete(args.id))
        print(f"已删除任务 #{args.id}" if ok else f"任务 #{args.id} 不存在")
        return

    if action in ("start", "stop"):
        _cmd_task_start_stop(args, repo)
        return

    print(f"未知 task 动作: {action}（可选 list/create/start/stop/delete）")


def _cmd_task_start_stop(args, repo):
    """start: 终端前台运行任务（Ctrl+C 中断）；stop: 清理任务运行状态标记。"""
    from src.platforms import get_scraper, platform_display_name

    task = asyncio.run(repo.find_by_id(args.id))
    if task is None:
        print(f"任务 #{args.id} 不存在")
        return

    if args.task == "stop":
        if not task.is_running:
            print(f"任务 #{args.id} 未在运行")
            return
        cleaned = task.model_copy(
            update={"is_running": False, "execution_status": "idle"}
        )
        asyncio.run(repo.save(cleaned))
        print(
            f"已清理任务 #{args.id} 运行状态；若该任务由 Web 服务进程启动，"
            f"请到 Web UI 停止对应进程"
        )
        return

    # start
    if not task.enabled:
        print(f"任务 #{args.id} 已被禁用，跳过执行")
        return
    from pr import _check_platform_ready
    if not _check_platform_ready(task.platform):
        return
    task_config = task.model_dump()
    plat = task_config.get("platform") or "goofish"
    print(f"-> 任务 '{task.task_name}' [{platform_display_name(plat)}] 开始运行（Ctrl+C 中断）")
    try:
        count = asyncio.run(
            get_scraper(plat)(task_config=task_config, debug_limit=0)
        )
    except KeyboardInterrupt:
        print("\n已中断")
        return
    print(f"任务 '{task.task_name}' 结束，本次新增 {count} 个商品")


def cmd_crawl(args):
    """按关键词爬取并落库（默认 keyword 模式，纯采集）。"""
    from src.platforms import get_scraper, normalize_platform_key, platform_display_name
    from src.services.result_storage_service import query_result_records
    from src.services.task_generation_runner import build_criteria_filename
    from src.infrastructure.persistence.storage_names import build_result_filename

    platform = normalize_platform_key(args.platform)
    if not _check_platform_ready(platform):
        return

    if args.mode == "ai":
        criteria = build_criteria_filename(args.crawl)
        if not os.path.exists(criteria):
            print(f"关键词 '{args.crawl}' 尚无分析标准文件: {criteria}")
            print("请先在 Web UI 用 AI 生成任务，或改用 --mode keyword 纯采集。")
            return
        print(f"[info] 将采用分析标准: {criteria}（当前采集管线为纯抓取，AI 分析由任务管线执行）")

    task_config = {
        "task_name": args.crawl,
        "keyword": args.crawl,
        "platform": platform,
        "max_pages": args.pages,
        "decision_mode": args.mode,
    }
    print(f"开始爬取: {args.crawl} [{platform_display_name(platform)}] {args.pages} 页")
    count = asyncio.run(get_scraper(platform)(task_config=task_config, debug_limit=0))
    print(f"本次新增 {count} 个商品")
    if count <= 0:
        return

    total, items = asyncio.run(
        query_result_records(
            build_result_filename(args.crawl),
            sort_by="crawl_time",
            sort_order="desc",
            page=1,
            limit=min(count, 50),
        )
    )
    _print_items(items, json_out=args.json)


def _print_items(items, json_out=False):
    """输出商品结果：JSON 或表格。"""
    if json_out:
        _print_json(items)
        return
    rows = []
    for record in items:
        item = record.get("商品信息", {})
        analysis = record.get("ai_analysis", {}) or {}
        rows.append(
            [
                str(item.get("商品标题") or "")[:30],
                str(item.get("当前售价") or ""),
                "推荐" if analysis.get("is_recommended") else "-",
                str(item.get("商品链接") or ""),
            ]
        )
    _render_table(["标题", "价格", "AI推荐", "链接"], rows)


def _check_platform_ready(platform):
    """平台前置检查：闲鱼需 CDP 专用 Chrome(9222)，其余平台由平台函数内部处理登录态。"""
    if platform != "goofish":
        return True
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3)
        return True
    except Exception:
        from src.platforms._web import CDP_PROFILE_DIR
        print("闲鱼需要 CDP 专用 Chrome（端口 9222），当前未启动。启动命令：")
        print(
            f'  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
            f"--remote-debugging-port=9222 --user-data-dir={CDP_PROFILE_DIR}"
        )
        print("启动后需在 Chrome 里登录闲鱼一次（登录态持久化）。")
        return False
