# -*- coding: utf-8 -*-
"""比价 CLI:丢关键词出全网对比报告。
用法: python scripts/compare_price.py "vivo X Fold5" [平台1,平台2]
平台缺省=全部;示例: python scripts/compare_price.py "iPhone 15" goofish,jd
"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, ".")

from src.services.price_compare_engine import compare_keyword, format_compare_report  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('用法: python scripts/compare_price.py "关键词" [平台列表(逗号分隔)]')
    keyword = sys.argv[1]
    platforms = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    result = compare_keyword(keyword, platforms)
    print(format_compare_report(result))
