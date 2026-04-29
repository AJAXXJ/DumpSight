from server.models.email.alert_rule import AlertRule
from server.models.email.alert_rule_recipient import AlertRuleRecipient
from server.notification.email_sender import SmtpMailSender
from server.notification.mail_builder import build_crash_mail_payload

DEFAULT_RULE_ID = 1
DEFAULT_SUBJECT_PREFIX = "[DumpSight] Crash Alert"


def _severity_to_alert_level(severity: str):
    """
    将规则中的 severity 映射为邮件日志使用的 P1/P2/P3。
    """
    mapping = {
        "critical": "P1",
        "warning": "P2",
        "info": "P3",
    }
    return mapping.get(severity or "", "P3")


def send_crash_notification(
    client_id=None,
    pid=None,
    crash_time=None,
    description=None,
    root_cause=None,
    crash_type="crash",
    rule_id=1,
    sender=None,
):
    """
    发送崩溃告警邮件通知。

    处理步骤：
    1) 读取内置崩溃规则与收件人
    2) 组装崩溃数据与邮件内容
    3) 交由 SmtpMailSender 发送并落库日志

    Args:
        client_id: 客户端 ID
        pid: 进程 PID
        crash_time: 崩溃时间
        description: 崩溃描述
        root_cause: 根因分析
        crash_type: 崩溃类型，目前主要处理 crash
        rule_id: 告警规则 ID，目前固定使用内置规则
        sender: 可注入自定义 sender，默认使用 SmtpMailSender

    Returns:
        dict: 发送结果
    """

    # 崩溃告警目前固定使用内置规则
    rule_id = DEFAULT_RULE_ID

    rule = AlertRule.get(id=rule_id, deleted=0)
    if not rule:
        return {
            "ok": False,
            "message": "alert rule not found",
            "rule_id": rule_id,
        }

    if not bool(rule.get("enabled", 0)):
        return {
            "ok": True,
            "message": "alert rule disabled",
            "rule_id": rule_id,
        }

    recipients = AlertRuleRecipient.filter(rule_id=rule_id)
    to_addrs = [
        item.get("email")
        for item in recipients
        if item.get("email")
    ]

    if not to_addrs:
        return {
            "ok": False,
            "message": "no recipients configured",
            "rule_id": rule_id,
        }

    crash_info = {
        "client_id": client_id,
        "pid": pid,
        "crash_time": crash_time,
        "description": description,
        "root_cause": root_cause,
    }

    payload = build_crash_mail_payload({
        "crash_type": crash_type,
        "rule": rule,
        "crash_info": crash_info,
        "to_addrs": to_addrs,
        "cc_addrs": [],
        "subject_prefix": DEFAULT_SUBJECT_PREFIX,
    })

    mail_sender = sender or SmtpMailSender()
    alert_level = _severity_to_alert_level(rule.get("severity"))

    try:
        mail_sender.send_mail(
            to_addrs=payload["to_addrs"],
            cc_addrs=payload.get("cc_addrs", []),
            subject=payload["subject"],
            body=payload["body"],
            content_type=payload.get("content_type", "plain"),
            alert_level=alert_level,
        )

        return {
            "ok": True,
            "message": "crash notification sent",
        }

    except Exception as e:
        return {
            "ok": False,
            "message": "crash notification failed",
            "error": str(e),
        }
