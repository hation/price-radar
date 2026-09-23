"""
通知配置读写与校验服务
"""
import json
from urllib.parse import urlparse

from src.infrastructure.config.env_manager import env_manager
from src.infrastructure.config.settings import (
    DEFAULT_SMTP_PORT,
    DEFAULT_TELEGRAM_API_BASE_URL,
    NotificationSettings,
)


NOTIFICATION_FIELD_MAP = {
    "NTFY_TOPIC_URL": "ntfy_topic_url",
    "NTFY_ENABLED": "ntfy_enabled",
    "GOTIFY_URL": "gotify_url",
    "GOTIFY_TOKEN": "gotify_token",
    "GOTIFY_ENABLED": "gotify_enabled",
    "BARK_URL": "bark_url",
    "BARK_ENABLED": "bark_enabled",
    "WX_BOT_URL": "wx_bot_url",
    "WX_BOT_ENABLED": "wx_bot_enabled",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "TELEGRAM_API_BASE_URL": "telegram_api_base_url",
    "TELEGRAM_ENABLED": "telegram_enabled",
    "WEBHOOK_URL": "webhook_url",
    "WEBHOOK_METHOD": "webhook_method",
    "WEBHOOK_HEADERS": "webhook_headers",
    "WEBHOOK_CONTENT_TYPE": "webhook_content_type",
    "WEBHOOK_QUERY_PARAMETERS": "webhook_query_parameters",
    "WEBHOOK_BODY": "webhook_body",
    "WEBHOOK_ENABLED": "webhook_enabled",
    "SMTP_HOST": "smtp_host",
    "SMTP_PORT": "smtp_port",
    "SMTP_USERNAME": "smtp_username",
    "SMTP_PASSWORD": "smtp_password",
    "SMTP_FROM_ADDRESS": "smtp_from_address",
    "SMTP_TO_ADDRESS": "smtp_to_address",
    "SMTP_USE_SSL": "smtp_use_ssl",
    "EMAIL_ENABLED": "email_enabled",
    "PCURL_TO_MOBILE": "pcurl_to_mobile",
}

CHANNEL_NOTIFICATION_FIELDS = {
    "ntfy": {"NTFY_TOPIC_URL", "NTFY_ENABLED"},
    "bark": {"BARK_URL", "BARK_ENABLED"},
    "gotify": {"GOTIFY_URL", "GOTIFY_TOKEN", "GOTIFY_ENABLED"},
    "wecom": {"WX_BOT_URL", "WX_BOT_ENABLED"},
    "telegram": {
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_API_BASE_URL",
        "TELEGRAM_ENABLED",
    },
    "webhook": {
        "WEBHOOK_URL",
        "WEBHOOK_METHOD",
        "WEBHOOK_HEADERS",
        "WEBHOOK_CONTENT_TYPE",
        "WEBHOOK_QUERY_PARAMETERS",
        "WEBHOOK_BODY",
        "WEBHOOK_ENABLED",
    },
    "email": {
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_ADDRESS",
        "SMTP_TO_ADDRESS",
        "SMTP_USE_SSL",
        "EMAIL_ENABLED",
    },
}

SECRET_NOTIFICATION_FIELDS = {
    "BARK_URL",
    "GOTIFY_TOKEN",
    "WX_BOT_URL",
    "TELEGRAM_BOT_TOKEN",
    "WEBHOOK_URL",
    "WEBHOOK_HEADERS",
    "SMTP_PASSWORD",
}

ENABLED_ATTR_NAMES = {
    "ntfy_enabled",
    "gotify_enabled",
    "bark_enabled",
    "wx_bot_enabled",
    "telegram_enabled",
    "webhook_enabled",
    "email_enabled",
}

INT_NOTIFICATION_FIELDS = {"SMTP_PORT"}
BOOL_NOTIFICATION_FIELDS = {
    "PCURL_TO_MOBILE",
    "SMTP_USE_SSL",
    "NTFY_ENABLED",
    "GOTIFY_ENABLED",
    "BARK_ENABLED",
    "WX_BOT_ENABLED",
    "TELEGRAM_ENABLED",
    "WEBHOOK_ENABLED",
    "EMAIL_ENABLED",
}

JSON_NOTIFICATION_FIELDS = {
    "WEBHOOK_HEADERS": True,
    "WEBHOOK_QUERY_PARAMETERS": True,
    "WEBHOOK_BODY": False,
}

URL_FIELDS = {
    "NTFY_TOPIC_URL",
    "GOTIFY_URL",
    "BARK_URL",
    "WX_BOT_URL",
    "TELEGRAM_API_BASE_URL",
    "WEBHOOK_URL",
}

ALLOWED_WEBHOOK_METHODS = {"GET", "POST"}
ALLOWED_WEBHOOK_CONTENT_TYPES = {"JSON", "FORM"}

URL_FIELD_ENABLED_ATTR = {
    "NTFY_TOPIC_URL": "ntfy_enabled",
    "GOTIFY_URL": "gotify_enabled",
    "BARK_URL": "bark_enabled",
    "WX_BOT_URL": "wx_bot_enabled",
    "TELEGRAM_API_BASE_URL": "telegram_enabled",
    "WEBHOOK_URL": "webhook_enabled",
}


class NotificationSettingsValidationError(ValueError):
    """通知配置校验错误"""


def model_dump(model, *, exclude_unset: bool = False) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def build_notification_settings_response(
    settings: NotificationSettings | None = None,
) -> dict:
    notification_settings = settings or load_notification_settings()
    response = {
        "NTFY_TOPIC_URL": notification_settings.ntfy_topic_url or "",
        "NTFY_ENABLED": notification_settings.ntfy_enabled,
        "GOTIFY_URL": notification_settings.gotify_url or "",
        "GOTIFY_TOKEN": "",
        "GOTIFY_ENABLED": notification_settings.gotify_enabled,
        "BARK_URL": "",
        "BARK_ENABLED": notification_settings.bark_enabled,
        "WX_BOT_URL": "",
        "WX_BOT_ENABLED": notification_settings.wx_bot_enabled,
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": notification_settings.telegram_chat_id or "",
        "TELEGRAM_API_BASE_URL": (
            notification_settings.telegram_api_base_url
            or DEFAULT_TELEGRAM_API_BASE_URL
        ),
        "TELEGRAM_ENABLED": notification_settings.telegram_enabled,
        "WEBHOOK_URL": "",
        "WEBHOOK_METHOD": notification_settings.webhook_method,
        "WEBHOOK_HEADERS": "",
        "WEBHOOK_CONTENT_TYPE": notification_settings.webhook_content_type,
        "WEBHOOK_QUERY_PARAMETERS": notification_settings.webhook_query_parameters or "",
        "WEBHOOK_BODY": notification_settings.webhook_body or "",
        "WEBHOOK_ENABLED": notification_settings.webhook_enabled,
        "SMTP_HOST": notification_settings.smtp_host or "",
        "SMTP_PORT": notification_settings.smtp_port or DEFAULT_SMTP_PORT,
        "SMTP_USERNAME": notification_settings.smtp_username or "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM_ADDRESS": notification_settings.smtp_from_address or "",
        "SMTP_TO_ADDRESS": notification_settings.smtp_to_address or "",
        "SMTP_USE_SSL": notification_settings.smtp_use_ssl,
        "EMAIL_ENABLED": notification_settings.email_enabled,
        "PCURL_TO_MOBILE": notification_settings.pcurl_to_mobile,
    }
    for field in SECRET_NOTIFICATION_FIELDS:
        attr_name = NOTIFICATION_FIELD_MAP[field]
        response[f"{field}_SET"] = bool(getattr(notification_settings, attr_name))
    response["CONFIGURED_CHANNELS"] = build_configured_channels(notification_settings)
    return response


def build_notification_status_flags(
    settings: NotificationSettings | None = None,
) -> dict:
    notification_settings = settings or load_notification_settings()
    return {
        "ntfy_topic_url_set": bool(notification_settings.ntfy_topic_url),
        "gotify_url_set": bool(notification_settings.gotify_url),
        "gotify_token_set": bool(notification_settings.gotify_token),
        "bark_url_set": bool(notification_settings.bark_url),
        "wx_bot_url_set": bool(notification_settings.wx_bot_url),
        "telegram_bot_token_set": bool(notification_settings.telegram_bot_token),
        "telegram_chat_id_set": bool(notification_settings.telegram_chat_id),
        "webhook_url_set": bool(notification_settings.webhook_url),
        "webhook_headers_set": bool(notification_settings.webhook_headers),
        "smtp_host_set": bool(notification_settings.smtp_host),
        "smtp_username_set": bool(notification_settings.smtp_username),
        "smtp_password_set": bool(notification_settings.smtp_password),
        "smtp_to_address_set": bool(notification_settings.smtp_to_address),
    }


def build_configured_channels(
    settings: NotificationSettings | None = None,
) -> list[str]:
    notification_settings = settings or load_notification_settings()
    channels = []
    if notification_settings.ntfy_topic_url and notification_settings.ntfy_enabled:
        channels.append("ntfy")
    if notification_settings.bark_url and notification_settings.bark_enabled:
        channels.append("bark")
    if (
        notification_settings.gotify_url
        and notification_settings.gotify_token
        and notification_settings.gotify_enabled
    ):
        channels.append("gotify")
    if notification_settings.wx_bot_url and notification_settings.wx_bot_enabled:
        channels.append("wecom")
    if (
        notification_settings.telegram_bot_token
        and notification_settings.telegram_chat_id
        and notification_settings.telegram_enabled
    ):
        channels.append("telegram")
    if notification_settings.webhook_url and notification_settings.webhook_enabled:
        channels.append("webhook")
    if (
        notification_settings.smtp_host
        and notification_settings.smtp_username
        and notification_settings.smtp_password
        and notification_settings.smtp_to_address
        and notification_settings.email_enabled
    ):
        channels.append("email")
    return channels


def prepare_notification_settings_update(
    patch_payload: dict,
    existing_settings: NotificationSettings | None = None,
) -> tuple[dict[str, str], list[str], NotificationSettings]:
    current_settings = existing_settings or load_notification_settings()
    merged_values = _notification_settings_to_values(current_settings)

    for env_name, raw_value in patch_payload.items():
        attr_name = NOTIFICATION_FIELD_MAP.get(env_name)
        if attr_name is None:
            continue
        merged_values[attr_name] = _normalize_patch_value(env_name, raw_value)

    normalized_values = _normalize_notification_values(merged_values)
    candidate_settings = _build_notification_settings_model(normalized_values)
    _validate_notification_settings(candidate_settings)

    updates = {}
    deletions = []
    for env_name, raw_value in patch_payload.items():
        attr_name = NOTIFICATION_FIELD_MAP.get(env_name)
        if attr_name is None:
            continue
        value = normalized_values[attr_name]
        if isinstance(value, bool):
            updates[env_name] = "true" if value else "false"
            continue
        if value is None:
            deletions.append(env_name)
            continue
        updates[env_name] = value
    return updates, deletions, candidate_settings


def prepare_notification_test_settings(
    patch_payload: dict,
    existing_settings: NotificationSettings | None = None,
    *,
    channel: str | None = None,
) -> NotificationSettings:
    if channel is None:
        _, _, merged_settings = prepare_notification_settings_update(
            patch_payload,
            existing_settings,
        )
        return _force_all_enabled(merged_settings)

    if channel not in CHANNEL_NOTIFICATION_FIELDS:
        raise NotificationSettingsValidationError(f"不支持的通知渠道: {channel}")

    current_settings = existing_settings or load_notification_settings()
    included_env_fields = set(CHANNEL_NOTIFICATION_FIELDS[channel])
    included_env_fields.add("PCURL_TO_MOBILE")
    merged_values = _build_channel_test_values(current_settings, included_env_fields)

    for env_name, raw_value in patch_payload.items():
        if env_name not in included_env_fields:
            continue
        attr_name = NOTIFICATION_FIELD_MAP[env_name]
        merged_values[attr_name] = _normalize_patch_value(env_name, raw_value)

    normalized_values = _normalize_notification_values(merged_values)
    candidate_settings = _build_notification_settings_model(normalized_values)
    _validate_notification_settings(candidate_settings)
    return _force_all_enabled(candidate_settings)


def _force_all_enabled(settings: NotificationSettings) -> NotificationSettings:
    """测试通知时忽略渠道开关状态，只要凭据配置正确即可测试。"""
    values = _notification_settings_to_values(settings)
    for attr_name in ENABLED_ATTR_NAMES:
        values[attr_name] = True
    return _build_notification_settings_model(values)


def _notification_settings_to_values(settings: NotificationSettings) -> dict:
    return {
        attr_name: getattr(settings, attr_name)
        for attr_name in NOTIFICATION_FIELD_MAP.values()
    }


def _build_channel_test_values(
    settings: NotificationSettings,
    included_env_fields: set[str],
) -> dict:
    values = {
        attr_name: None
        for attr_name in NOTIFICATION_FIELD_MAP.values()
    }
    values["telegram_api_base_url"] = DEFAULT_TELEGRAM_API_BASE_URL
    values["webhook_method"] = "POST"
    values["webhook_content_type"] = "JSON"
    values["smtp_port"] = DEFAULT_SMTP_PORT
    values["smtp_use_ssl"] = True
    values["pcurl_to_mobile"] = True
    values["ntfy_enabled"] = True
    values["gotify_enabled"] = True
    values["bark_enabled"] = True
    values["wx_bot_enabled"] = True
    values["telegram_enabled"] = True
    values["webhook_enabled"] = True
    values["email_enabled"] = True

    for env_name in included_env_fields:
        attr_name = NOTIFICATION_FIELD_MAP[env_name]
        values[attr_name] = getattr(settings, attr_name)

    return values


def load_notification_settings() -> NotificationSettings:
    return _build_notification_settings_model(
        {
            "ntfy_topic_url": _normalize_existing_text(env_manager.get_value("NTFY_TOPIC_URL")),
            "ntfy_enabled": _env_bool(env_manager.get_value("NTFY_ENABLED"), True),
            "gotify_url": _normalize_existing_text(env_manager.get_value("GOTIFY_URL")),
            "gotify_token": _normalize_existing_text(env_manager.get_value("GOTIFY_TOKEN")),
            "gotify_enabled": _env_bool(env_manager.get_value("GOTIFY_ENABLED"), True),
            "bark_url": _normalize_existing_text(env_manager.get_value("BARK_URL")),
            "bark_enabled": _env_bool(env_manager.get_value("BARK_ENABLED"), True),
            "wx_bot_url": _normalize_existing_text(env_manager.get_value("WX_BOT_URL")),
            "wx_bot_enabled": _env_bool(env_manager.get_value("WX_BOT_ENABLED"), True),
            "telegram_bot_token": _normalize_existing_text(env_manager.get_value("TELEGRAM_BOT_TOKEN")),
            "telegram_chat_id": _normalize_existing_text(env_manager.get_value("TELEGRAM_CHAT_ID")),
            "telegram_api_base_url": (
                _normalize_existing_text(env_manager.get_value("TELEGRAM_API_BASE_URL"))
                or DEFAULT_TELEGRAM_API_BASE_URL
            ),
            "telegram_enabled": _env_bool(env_manager.get_value("TELEGRAM_ENABLED"), True),
            "webhook_url": _normalize_existing_text(env_manager.get_value("WEBHOOK_URL")),
            "webhook_method": _normalize_existing_text(env_manager.get_value("WEBHOOK_METHOD")) or "POST",
            "webhook_headers": _normalize_existing_text(env_manager.get_value("WEBHOOK_HEADERS")),
            "webhook_content_type": _normalize_existing_text(env_manager.get_value("WEBHOOK_CONTENT_TYPE")) or "JSON",
            "webhook_query_parameters": _normalize_existing_text(env_manager.get_value("WEBHOOK_QUERY_PARAMETERS")),
            "webhook_body": _normalize_existing_text(env_manager.get_value("WEBHOOK_BODY")),
            "webhook_enabled": _env_bool(env_manager.get_value("WEBHOOK_ENABLED"), True),
            "smtp_host": _normalize_existing_text(env_manager.get_value("SMTP_HOST")),
            "smtp_port": _env_int(env_manager.get_value("SMTP_PORT"), DEFAULT_SMTP_PORT),
            "smtp_username": _normalize_existing_text(env_manager.get_value("SMTP_USERNAME")),
            "smtp_password": _normalize_existing_text(env_manager.get_value("SMTP_PASSWORD")),
            "smtp_from_address": _normalize_existing_text(env_manager.get_value("SMTP_FROM_ADDRESS")),
            "smtp_to_address": _normalize_existing_text(env_manager.get_value("SMTP_TO_ADDRESS")),
            "smtp_use_ssl": _env_bool(env_manager.get_value("SMTP_USE_SSL"), True),
            "email_enabled": _env_bool(env_manager.get_value("EMAIL_ENABLED"), True),
            "pcurl_to_mobile": _env_bool(env_manager.get_value("PCURL_TO_MOBILE"), True),
        }
    )


def _build_notification_settings_model(values: dict) -> NotificationSettings:
    if hasattr(NotificationSettings, "model_construct"):
        return NotificationSettings.model_construct(**values)
    return NotificationSettings.construct(**values)


def _normalize_patch_value(env_name: str, value):
    if env_name in BOOL_NOTIFICATION_FIELDS:
        return bool(value)
    if env_name in INT_NOTIFICATION_FIELDS:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise NotificationSettingsValidationError(
                f"{env_name} 必须是整数"
            ) from exc
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_existing_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(value: str | None, default: int) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def _normalize_notification_values(values: dict) -> dict:
    normalized = dict(values)
    normalized["webhook_method"] = (
        (normalized.get("webhook_method") or "POST").strip().upper()
    )
    normalized["webhook_content_type"] = (
        (normalized.get("webhook_content_type") or "JSON").strip().upper()
    )

    for env_name, expect_dict in JSON_NOTIFICATION_FIELDS.items():
        attr_name = NOTIFICATION_FIELD_MAP[env_name]
        raw_value = normalized.get(attr_name)
        if raw_value is None:
            continue
        parsed = _parse_json_field(env_name, raw_value, expect_dict=expect_dict)
        normalized[attr_name] = json.dumps(
            parsed,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return normalized


def _validate_notification_settings(settings: NotificationSettings) -> None:
    for field_name in URL_FIELDS:
        enabled_attr = URL_FIELD_ENABLED_ATTR.get(field_name)
        if enabled_attr and not getattr(settings, enabled_attr):
            continue
        value = getattr(settings, NOTIFICATION_FIELD_MAP[field_name])
        if value is not None:
            _validate_http_url(field_name, value)

    if settings.gotify_enabled:
        _validate_pair(
            "GOTIFY_URL",
            settings.gotify_url,
            "GOTIFY_TOKEN",
            settings.gotify_token,
        )
    if settings.telegram_enabled:
        _validate_pair(
            "TELEGRAM_BOT_TOKEN",
            settings.telegram_bot_token,
            "TELEGRAM_CHAT_ID",
            settings.telegram_chat_id,
        )

    if settings.email_enabled:
        _validate_smtp_settings(settings)

    if not settings.webhook_enabled:
        return

    if settings.webhook_method not in ALLOWED_WEBHOOK_METHODS:
        allowed = ", ".join(sorted(ALLOWED_WEBHOOK_METHODS))
        raise NotificationSettingsValidationError(
            f"WEBHOOK_METHOD 仅支持: {allowed}"
        )
    if settings.webhook_content_type not in ALLOWED_WEBHOOK_CONTENT_TYPES:
        allowed = ", ".join(sorted(ALLOWED_WEBHOOK_CONTENT_TYPES))
        raise NotificationSettingsValidationError(
            f"WEBHOOK_CONTENT_TYPE 仅支持: {allowed}"
        )

    has_webhook_extras = any(
        [
            settings.webhook_headers,
            settings.webhook_query_parameters,
            settings.webhook_body,
        ]
    )
    if has_webhook_extras and not settings.webhook_url:
        raise NotificationSettingsValidationError(
            "配置 Webhook 高级参数前必须先填写 WEBHOOK_URL"
        )

    if settings.webhook_content_type == "FORM" and settings.webhook_body:
        parsed_body = json.loads(settings.webhook_body)
        if not isinstance(parsed_body, dict):
            raise NotificationSettingsValidationError(
                "WEBHOOK_BODY 在 FORM 模式下必须是 JSON 对象"
            )


def _validate_http_url(field_name: str, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise NotificationSettingsValidationError(
            f"{field_name} 必须是合法的 HTTP/HTTPS URL"
        )


def _validate_pair(
    left_name: str,
    left_value: str | None,
    right_name: str,
    right_value: str | None,
) -> None:
    if bool(left_value) == bool(right_value):
        return
    raise NotificationSettingsValidationError(
        f"{left_name} 与 {right_name} 必须成对配置"
    )


def _validate_smtp_settings(settings: NotificationSettings) -> None:
    required = {
        "SMTP_HOST": settings.smtp_host,
        "SMTP_USERNAME": settings.smtp_username,
        "SMTP_PASSWORD": settings.smtp_password,
        "SMTP_TO_ADDRESS": settings.smtp_to_address,
    }
    present = [bool(value) for value in required.values()]
    if any(present) and not all(present):
        names = ", ".join(required.keys())
        raise NotificationSettingsValidationError(f"{names} 必须同时配置")

    if settings.smtp_port is not None and not (1 <= settings.smtp_port <= 65535):
        raise NotificationSettingsValidationError("SMTP_PORT 必须在 1-65535 之间")

    if settings.smtp_to_address:
        _validate_email_field("SMTP_TO_ADDRESS", settings.smtp_to_address)
    if settings.smtp_from_address:
        _validate_email_field("SMTP_FROM_ADDRESS", settings.smtp_from_address)


def _validate_email_field(field_name: str, value: str) -> None:
    for candidate in value.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        if "@" not in candidate or candidate.startswith("@") or candidate.endswith("@"):
            raise NotificationSettingsValidationError(
                f"{field_name} 包含无效的邮箱地址: {candidate}"
            )


def _parse_json_field(
    field_name: str,
    raw_value: str,
    expect_dict: bool,
):
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise NotificationSettingsValidationError(
            f"{field_name} 不是合法 JSON: {exc.msg}"
        ) from exc
    if expect_dict and not isinstance(parsed, dict):
        raise NotificationSettingsValidationError(
            f"{field_name} 必须是 JSON 对象"
        )
    return parsed
