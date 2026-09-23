"""平台注册表:多平台适配器的唯一登记入口。

新增平台三步:
1. 在本包新建 <platform>.py,实现 `async def scrape_<platform>(task_config: dict, debug_limit: int = 0) -> int`
   (签名与 scrape_xianyu 一致:入参任务配置 dict,返回本次处理的新商品数)
2. 解析输出统一中文键字段:商品标题/当前售价/商品链接/商品ID/卖家昵称/商品标签/发货地区/发布时间
3. 在 SCRAPER_REGISTRY 注册,PLATFORMS 加入 key

相关铁律见项目 CLAUDE.md:登录态文件制、headless 必被拦(有头+屏外窗口)、key 不落盘。
"""
from __future__ import annotations

from typing import Callable, Coroutine

# 平台标识 -> 爬虫协程函数
SCRAPER_REGISTRY: dict[str, Callable[..., Coroutine]] = {}

# 平台显示名(WebUI/通知文案用)
PLATFORM_DISPLAY_NAMES: dict[str, str] = {
    "goofish": "闲鱼",
    "jd": "京东",
    "taobao": "淘宝",
    "1688": "1688",
}

# 实测结论(2026-09-18 spike):京东 PC 搜索接口 pc_search_searchWare 无登录 403、
# 移动端直接 risk_handler 拦截;淘宝 mtop 同需登录态。当前所有平台都需要登录态,
# LOGIN_FREE_PLATFORMS 留空,未来若某个平台放开再把 key 加进来。
LOGIN_FREE_PLATFORMS: set[str] = set()

DEFAULT_PLATFORM = "goofish"


def normalize_platform_key(value) -> str:
    """清洗任务里的 platform 字段:未知/空值回落到闲鱼,保证旧数据零迁移可用。"""
    key = str(value or DEFAULT_PLATFORM).strip().lower()
    if key not in PLATFORM_DISPLAY_NAMES:
        return DEFAULT_PLATFORM
    return key


def register_platform(key: str, scraper: Callable[..., Coroutine]) -> None:
    SCRAPER_REGISTRY[key] = scraper


def get_scraper(platform: str) -> Callable[..., Coroutine]:
    key = normalize_platform_key(platform)
    return SCRAPER_REGISTRY.get(key) or SCRAPER_REGISTRY[DEFAULT_PLATFORM]


def platform_requires_login(platform: str) -> bool:
    return normalize_platform_key(platform) not in LOGIN_FREE_PLATFORMS


def platform_display_name(platform: str) -> str:
    return PLATFORM_DISPLAY_NAMES.get(normalize_platform_key(platform), "闲鱼")


# ---- 注册各平台爬虫( import 放底部避免循环依赖) ----
from src.platforms.ali1688 import scrape_ali1688  # noqa: E402
from src.platforms.goofish_cdp import scrape_goofish  # noqa: E402
from src.platforms.jd import scrape_jd  # noqa: E402
from src.platforms.taobao import scrape_taobao  # noqa: E402
from src.scraper import scrape_xianyu  # noqa: E402

# 闲鱼走 CDP 版(原生 scrape_xianyu 因自动化指纹不可用,保留作 AI 打分管线参考)
register_platform("goofish", scrape_goofish)
register_platform("jd", scrape_jd)
register_platform("taobao", scrape_taobao)
register_platform("1688", scrape_ali1688)
