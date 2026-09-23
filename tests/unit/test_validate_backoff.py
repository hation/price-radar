import pytest

from src.scraper import (
    VALIDATE_BACKOFF_BASE_SECONDS,
    VALIDATE_BACKOFF_MAX_SECONDS,
    _validation_should_rotate,
    compute_validate_backoff_delay,
)


def test_backoff_starts_at_base():
    assert compute_validate_backoff_delay(1) == VALIDATE_BACKOFF_BASE_SECONDS


def test_backoff_grows_exponentially():
    assert compute_validate_backoff_delay(1) == 5
    assert compute_validate_backoff_delay(2) == 10
    assert compute_validate_backoff_delay(3) == 20
    assert compute_validate_backoff_delay(4) == 40
    assert compute_validate_backoff_delay(5) == 80
    assert compute_validate_backoff_delay(6) == 160


def test_backoff_is_capped():
    huge = compute_validate_backoff_delay(20)
    assert huge == VALIDATE_BACKOFF_MAX_SECONDS
    assert huge < VALIDATE_BACKOFF_BASE_SECONDS * (2 ** 19)


def test_backoff_handles_zero_attempt():
    assert compute_validate_backoff_delay(0) == VALIDATE_BACKOFF_BASE_SECONDS


def test_validation_should_rotate_first_attempt_with_other_account():
    # 首次触发 + 开启轮换 + 有其他账号可切换 -> 应轮换
    assert _validation_should_rotate(1, True, True, "a.json", "b.json") is True


def test_validation_should_rotate_not_on_later_attempts():
    # 非首次触发（已轮换过一次）-> 走指数退避，不再轮换
    assert _validation_should_rotate(2, True, True, "a.json", "b.json") is False


def test_validation_should_rotate_disabled():
    assert _validation_should_rotate(1, False, True, "a.json", "b.json") is False
    assert _validation_should_rotate(1, True, False, "a.json", "b.json") is False


def test_validation_should_rotate_no_other_account():
    # 只有一个账号（候选与当前相同）-> 无法轮换，走退避
    assert _validation_should_rotate(1, True, True, "a.json", "a.json") is False
    assert _validation_should_rotate(1, True, True, "a.json", None) is False

