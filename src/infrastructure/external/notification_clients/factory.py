"""
通知客户端工厂
"""
from src.infrastructure.config.settings import NotificationSettings

from .bark_client import BarkClient
from .email_client import EmailClient
from .gotify_client import GotifyClient
from .ntfy_client import NtfyClient
from .telegram_client import TelegramClient
from .wecom_bot_client import WeComBotClient
from .webhook_client import WebhookClient


def build_notification_clients(settings: NotificationSettings):
    pcurl_to_mobile = settings.pcurl_to_mobile
    return [
        NtfyClient(
            settings.ntfy_topic_url,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.ntfy_enabled,
        ),
        BarkClient(
            settings.bark_url,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.bark_enabled,
        ),
        GotifyClient(
            settings.gotify_url,
            settings.gotify_token,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.gotify_enabled,
        ),
        WeComBotClient(
            settings.wx_bot_url,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.wx_bot_enabled,
        ),
        TelegramClient(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            settings.telegram_api_base_url,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.telegram_enabled,
        ),
        WebhookClient(
            settings.webhook_url,
            webhook_method=settings.webhook_method,
            webhook_headers=settings.webhook_headers,
            webhook_content_type=settings.webhook_content_type,
            webhook_query_parameters=settings.webhook_query_parameters,
            webhook_body=settings.webhook_body,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.webhook_enabled,
        ),
        EmailClient(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from_address,
            settings.smtp_to_address,
            use_ssl=settings.smtp_use_ssl,
            pcurl_to_mobile=pcurl_to_mobile,
            channel_enabled=settings.email_enabled,
        ),
    ]
