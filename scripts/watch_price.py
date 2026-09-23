# -*- coding: utf-8 -*-
"""商品盯价 CLI(拼多多/京东/淘宝等全平台,经慢慢买间接价,扫码任务之外的第二条盯价路线)。

用法:
  python scripts/watch_price.py add <商品URL> <目标价> [备注]   # 加盯价
  python scripts/watch_price.py rm <商品URL>                    # 删
  python scripts/watch_price.py list                            # 列表
  python scripts/watch_price.py check                           # 全部查一轮,跌破推飞书
  python scripts/watch_price.py now <商品URL>                   # 立即查某商品历史价

前置:专用 CDP Chrome + 慢慢买微信扫码授权(见 SKILL.md 第 1-2 步)
"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, ".")

from src.services.indirect_price_service import (  # noqa: E402
    lookup_item_history,
    watch_add,
    watch_check,
    watch_list,
    watch_remove,
)

HELP = __doc__


def main():
    args = sys.argv[1:]
    if not args:
        print(HELP)
        return
    cmd = args[0]

    if cmd == "add" and len(args) >= 3:
        entry = watch_add(args[1], float(args[2]), args[3] if len(args) > 3 else "")
        print(f"已加盯价: {entry['url']} 目标 ¥{entry['target_price']}")
    elif cmd == "rm" and len(args) >= 2:
        n = watch_remove(args[1])
        print(f"已删 {n} 条")
    elif cmd == "list":
        items = watch_list()
        if not items:
            print("watchlist 为空")
        for x in items:
            last = f"现价 ¥{x['last_price']}" if x.get("last_price") else "未查过"
            print(f"- {x['url'][:60]} 目标 ¥{x['target_price']} {last} 备注:{x.get('note','')}")
    elif cmd == "check":
        for r in watch_check():
            if not r["ok"]:
                print(f"✗ {r['url'][:60]} {r['reason']}")
            elif r["hit"]:
                print(f"🎯 命中! {r['title']} 现 ¥{r['current']} ≤ 目标 ¥{r['target']}(历史最低 ¥{r['lowest']})")
            else:
                print(f"· 未到: {r['title']} 现 ¥{r['current']} > 目标 ¥{r['target']}")
    elif cmd == "now" and len(args) >= 2:
        trend = lookup_item_history(args[1])
        if not trend:
            print("查询失败(会话凭据?商品未收录?)")
            return
        print(f"站点: {trend['site']} | 商品: {trend['title'][:50]}")
        print(f"当前: ¥{trend['current_price']} | 历史最低 ¥{trend['lowest']} | 最高 ¥{trend['highest']}")
        print(f"现价高于历史最低: {trend.get('current_vs_lowest_pct')}% | 数据点: {len(trend['points'])}")
    else:
        print(HELP)


if __name__ == "__main__":
    main()
