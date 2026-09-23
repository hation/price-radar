"""
Email (SMTP) 通知客户端
"""
import asyncio
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Dict

from src.infrastructure.config.settings import DEFAULT_SMTP_PORT

from .base import NotificationClient


class EmailClient(NotificationClient):
    """Email (SMTP) 通知客户端"""

    channel_key = "email"
    display_name = "邮件"

    def __init__(
        self,
        host: str = None,
        port: int = DEFAULT_SMTP_PORT,
        username: str = None,
        password: str = None,
        from_address: str = None,
        to_address: str = None,
        use_ssl: bool = True,
        pcurl_to_mobile: bool = True,
        channel_enabled: bool = True,
    ):
        to_addresses = [
            addr.strip() for addr in (to_address or "").split(",") if addr.strip()
        ]
        super().__init__(
            enabled=bool(host and username and password and to_addresses) and channel_enabled,
            pcurl_to_mobile=pcurl_to_mobile,
        )
        self.host = host
        self.port = port or DEFAULT_SMTP_PORT
        self.username = username
        self.password = password
        self.from_address = from_address or username
        self.to_addresses = to_addresses
        self.use_ssl = use_ssl

    async def send(self, product_data: Dict, reason: str) -> None:
        """发送邮件通知"""
        if not self.is_enabled():
            raise RuntimeError("邮件通知未启用")

        message = self._build_message(product_data, reason)

        body_lines = [
            f"价格: {message.price}",
            f"原因: {message.reason}",
        ]
        if message.mobile_link:
            body_lines.append(f"手机端链接: {message.mobile_link}")
        body_lines.append(f"电脑端链接: {message.desktop_link}")
        if message.image_url:
            body_lines.append(f"商品图片: {message.image_url}")

        email_message = MIMEText("\n".join(body_lines), "plain", "utf-8")
        email_message["Subject"] = Header(message.notification_title, "utf-8")
        email_message["From"] = formataddr(
            (str(Header("闲鱼监控机器人", "utf-8")), self.from_address)
        )
        email_message["To"] = ", ".join(self.to_addresses)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_sync, email_message.as_string())

    def _send_sync(self, message_text: str) -> None:
        smtp_cls = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_cls(self.host, self.port, timeout=10) as server:
            if not self.use_ssl:
                server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.from_address, self.to_addresses, message_text)
