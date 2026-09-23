"""
账号策略辅助函数
"""
from typing import Optional


ACCOUNT_STRATEGIES = {"auto", "fixed", "rotate"}


def clean_account_state_file(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"null", "undefined"}:
        return None
    return text


def normalize_account_strategy(
    strategy: Optional[str],
    account_state_file: Optional[str] = None,
) -> str:
    raw = str(strategy or "").strip().lower()
    if raw in ACCOUNT_STRATEGIES:
        return raw
    if clean_account_state_file(account_state_file):
        return "fixed"
    return "auto"


def resolve_account_runtime_plan(
    *,
    strategy: Optional[str],
    account_state_file: Optional[str],
    has_root_state_file: bool,
    available_account_files: list[str],
    rotation_enabled: bool = False,
) -> dict:
    normalized_strategy = normalize_account_strategy(strategy, account_state_file)
    cleaned_account = clean_account_state_file(account_state_file)
    has_account_pool = len(available_account_files) > 0

    # 显式开启账号轮换时，优先使用账号池（需存在可用账号文件），
    # 即使根登录态存在或策略为 auto/fixed，也以用户意图为准。
    if rotation_enabled and has_account_pool:
        return {
            "strategy": normalized_strategy,
            "forced_account": None,
            "use_account_pool": True,
            "prefer_root_state": False,
        }

    if normalized_strategy == "fixed":
        return {
            "strategy": normalized_strategy,
            "forced_account": cleaned_account,
            "use_account_pool": False,
            "prefer_root_state": False,
        }

    if normalized_strategy == "rotate":
        return {
            "strategy": normalized_strategy,
            "forced_account": None,
            "use_account_pool": has_account_pool,
            "prefer_root_state": False,
        }

    return {
        "strategy": normalized_strategy,
        "forced_account": None,
        "use_account_pool": (not has_root_state_file) and has_account_pool,
        "prefer_root_state": has_root_state_file,
    }
