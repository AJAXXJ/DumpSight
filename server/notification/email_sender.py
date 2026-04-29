import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from server.models.email.smtp_config import SmtpConfig
from server.repository.alert_repository import create_mail_log


class SmtpMailSender:
    def __init__(
        self,
        host: str = None,
        port: int = None,
        ssl: bool = None,
        sender: str = None,
        username: str = None,
        password: str = None,
        timeout: int = 10,
    ):
        self.timeout = timeout

        # 未提供完整配置时，从数据库读取启用配置
        if not all([host, port, sender, username, password]) or ssl is None:
            config = self._load_smtp_config_from_db()
            self.host = config["host"]
            self.port = int(config["port"])
            self.ssl = bool(config["use_ssl"])
            self.sender = config["sender"]
            self.username = config["username"]
            self.password = config["password"]
        else:
            self.host = host
            self.port = int(port)
            self.ssl = bool(ssl)
            self.sender = sender
            self.username = username
            self.password = password

    def _load_smtp_config_from_db(self):
        """
        读取启用中的 SMTP 配置。
        """
        data = SmtpConfig.get(id=1, enabled=1)

        if not data:
            raise ValueError("未找到启用中的 SMTP 配置，请先配置并启用 SMTP")

        return {
            "id": data.get("id"),
            "host": data.get("host"),
            "port": data.get("port"),
            "use_ssl": data.get("use_ssl"),
            "sender": data.get("sender"),
            "username": data.get("username"),
            "password": data.get("password"),
            "enabled": data.get("enabled"),
        }

    def _create_client(self):
        """
        创建 SMTP 客户端，优先使用 SSL，再回退 STARTTLS。
        """
        if self.ssl:
            client = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            client.ehlo()
            return client

        client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        client.ehlo()

        # 非 SSL 模式下优先尝试 STARTTLS
        try:
            client.starttls()
            client.ehlo()
        except Exception:
            pass

        return client

    def test_connection(self):
        """
        测试 SMTP 连接并验证认证信息。
        """
        client = None
        try:
            client = self._create_client()
            client.login(self.username, self.password)
            return True

        except smtplib.SMTPAuthenticationError as e:
            raise ValueError("SMTP 认证失败，请检查用户名和密码/授权码") from e

        except smtplib.SMTPConnectError as e:
            raise ValueError("SMTP 连接失败，请检查服务器地址和端口") from e

        except smtplib.SMTPServerDisconnected as e:
            raise ValueError("SMTP 服务器断开连接，请检查 SSL/端口配置") from e

        except TimeoutError as e:
            raise ValueError("SMTP 连接超时") from e

        except Exception as e:
            raise ValueError(f"SMTP 测试失败: {str(e)}") from e

        finally:
            if client:
                try:
                    client.quit()
                except Exception:
                    pass

    def _save_mail_log(
        self,
        receivers: list[str],
        subject: str,
        alert_level: str,
        status: str,
        error_message: str = "",
    ):
        """
        保存邮件发送日志，失败时不影响主流程。
        """
        try:
            create_mail_log({
                "sent_at": datetime.now(),
                "sender": self.sender,
                "receivers": ",".join(receivers),
                "subject": subject,
                "alert_level": alert_level,
                "status": status,
                "error_message": error_message,
            })
        except Exception:
            pass

    def send_mail(
        self,
        to_addrs: list[str],
        subject: str,
        body: str,
        cc_addrs: list[str] | None = None,
        content_type: str = "plain",
        alert_level: str = "P3",
    ):
        """
        发送邮件并记录发送结果。

        Args:
            to_addrs: 收件人
            subject: 邮件标题
            body: 邮件正文
            cc_addrs: 抄送人
            content_type: plain / html
            alert_level: P1 / P2 / P3

        Returns:
            bool: 发送成功返回 True
        """
        if not to_addrs:
            raise ValueError("收件人不能为空")

        cc_addrs = cc_addrs or []
        receivers = list(to_addrs) + list(cc_addrs)

        client = None

        try:
            client = self._create_client()
            client.login(self.username, self.password)

            msg = MIMEMultipart()
            msg["From"] = self.sender
            msg["To"] = ",".join(to_addrs)
            msg["Subject"] = subject

            if cc_addrs:
                msg["Cc"] = ",".join(cc_addrs)

            msg.attach(MIMEText(body, content_type, "utf-8"))

            client.sendmail(self.sender, receivers, msg.as_string())

            self._save_mail_log(
                receivers=receivers,
                subject=subject,
                alert_level=alert_level,
                status="success",
                error_message="",
            )

            return True

        except smtplib.SMTPAuthenticationError as e:
            error_message = "SMTP 认证失败，邮件发送失败"
            self._save_mail_log(receivers, subject, alert_level, "failed", error_message)
            raise ValueError(error_message) from e

        except smtplib.SMTPRecipientsRefused as e:
            error_message = f"收件人地址被拒绝: {str(e)}"
            self._save_mail_log(receivers, subject, alert_level, "failed", error_message)
            raise ValueError(error_message) from e

        except smtplib.SMTPDataError as e:
            error_message = f"SMTP 数据发送失败: {str(e)}"
            self._save_mail_log(receivers, subject, alert_level, "failed", error_message)
            raise ValueError(error_message) from e

        except Exception as e:
            error_message = f"邮件发送失败: {str(e)}"
            self._save_mail_log(receivers, subject, alert_level, "failed", error_message)
            raise ValueError(error_message) from e

        finally:
            if client:
                try:
                    client.quit()
                except Exception:
                    pass
