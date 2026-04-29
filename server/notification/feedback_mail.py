from datetime import datetime
from html import escape

from server.notification.email_sender import SmtpMailSender
from server.repository.alert_repository import (
    get_alert_mail_template_by_id,
    get_alert_rules,
)


CALLBACK_TYPE = "callback_event"

DEFAULT_SUBJECT_TEMPLATE = "【{{severity}}】{{title}}"
SEVERITY_LEVEL_MAP = {
    "critical": "P1",
    "warning": "P2",
    "info": "P3",
}


FIELD_LABELS = {
    "alert_id": "告警 ID",
    "client_id": "客户端 ID",
    "severity": "告警级别",
    "title": "告警标题",
    "description": "告警描述",
    "triggered_at": "触发时间",
}


def _severity_to_alert_level(severity: str):
    return SEVERITY_LEVEL_MAP.get(severity or "", "P3")


def _severity_meta(severity: str):
    severity = (severity or "warning").lower()

    if severity == "critical":
        return {
            "label": "CRITICAL",
            "color": "#d93025",
            "bg": "#fce8e6",
            "border": "#f4b8b3",
        }

    if severity == "warning":
        return {
            "label": "WARNING",
            "color": "#b06000",
            "bg": "#fff4e5",
            "border": "#ffd699",
        }

    return {
        "label": "INFO",
        "color": "#1677ff",
        "bg": "#e6f4ff",
        "border": "#91caff",
    }


def _format_triggered_at(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _normalize_callback_alert(alert: dict) -> dict:
    return {
        "alert_id": str(alert.get("alert_id", "")),
        "client_id": str(alert.get("client_id", "")),
        "severity": str(alert.get("severity", "")),
        "title": str(alert.get("title", "")),
        "description": str(alert.get("description", "")),
        "triggered_at": _format_triggered_at(alert.get("triggered_at")),
    }


def _render_subject(template_text: str, context: dict) -> str:
    subject = template_text or DEFAULT_SUBJECT_TEMPLATE

    for key, value in context.items():
        subject = subject.replace("{{" + key + "}}", str(value))
        subject = subject.replace("{{ " + key + " }}", str(value))

    return subject


def _get_template_field_order(template: dict) -> list[str]:
    """
     兼容两种模板配置方式：
     1) field_order: ["alert_id", "client_id", "severity"]
     2) 布尔字段: {"alert_id": true, "client_id": true}
    """
    field_order = template.get("field_order") or template.get("fieldOrder")

    if isinstance(field_order, list):
        return [
            field_key
            for field_key in field_order
            if field_key in FIELD_LABELS
        ]

    selected = []
    for field_key in FIELD_LABELS:
        if bool(template.get(field_key, False)):
            selected.append(field_key)

    return selected


def build_callback_mail_payload(data: dict):
    """
    构建回调告警邮件内容。

    data 中必须包含：rule、template、callback_info、to_addrs、cc_addrs。
    """
    if not data:
        raise ValueError("data is required")

    rule = data.get("rule") or {}
    template = data.get("template") or {}
    callback_info = data.get("callback_info") or {}

    severity = str(callback_info.get("severity") or rule.get("severity") or "warning").lower()
    meta = _severity_meta(severity)

    rule_id = escape(str(rule.get("id") or ""))
    rule_name = escape(str(rule.get("name") or "回调告警规则"))

    context = {
        key: str(value or "")
        for key, value in callback_info.items()
    }

    subject_template = (
        template.get("subject_template")
        or template.get("subjectTemplate")
        or DEFAULT_SUBJECT_TEMPLATE
    )
    subject = _render_subject(subject_template, context)

    field_order = _get_template_field_order(template)

    rows = []
    for field_key in field_order:
        label = escape(FIELD_LABELS[field_key])
        value = escape(str(context.get(field_key, "")))

        rows.append(
            f"""
          <tr>
            <td style="width:34%; padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">{label}</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{value}</td>
          </tr>
            """.strip()
        )

    if not rows:
        rows.append(
            """
          <tr>
            <td style="padding:10px 12px; border:1px solid #e5e7eb; color:#6b7280;">提示</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">当前模板未选择任何展示字段</td>
          </tr>
            """.strip()
        )

    rows_html = "\n".join(rows)

    body = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(subject)}</title>
</head>
<body style="margin:0; padding:0; background:#f5f7fa; font-family:Arial,'Microsoft YaHei',sans-serif; color:#1f2937;">
  <div style="max-width:760px; margin:0 auto; padding:24px 12px;">
    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:10px; overflow:hidden;">

      <div style="background:#111827; padding:22px 28px;">
        <div style="font-size:13px; color:#9ca3af; letter-spacing:0.08em;">DUMPSIGHT 告警系统</div>
        <div style="margin-top:8px; font-size:24px; font-weight:700; color:#ffffff;">
          回调告警通知
        </div>
      </div>

      <div style="padding:24px 28px;">
        <div style="margin-bottom:22px; padding:14px 16px; background:{meta["bg"]}; border:1px solid {meta["border"]}; border-radius:8px;">
          <span style="display:inline-block; padding:4px 10px; border-radius:999px; background:{meta["color"]}; color:#ffffff; font-size:12px; font-weight:700;">
            {meta["label"]}
          </span>
          <span style="margin-left:10px; font-size:14px; color:{meta["color"]}; font-weight:600;">
            实时监控触发回调告警
          </span>
        </div>

        <table style="width:100%; border-collapse:collapse; margin-bottom:22px;">
          <tr>
            <td style="width:34%; padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">规则 ID</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{rule_id}</td>
          </tr>
          <tr>
            <td style="padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">规则名称</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{rule_name}</td>
          </tr>
          {rows_html}
        </table>

        <div style="padding:14px 16px; background:#f0f7ff; border-left:4px solid #1677ff; border-radius:6px; font-size:13px; line-height:1.7; color:#1d4ed8;">
          建议操作：请关注该客户端实时监控指标，结合告警描述检查 DPDK 内存池、队列、错误计数及 CPU 使用情况。
        </div>
      </div>

      <div style="padding:16px 28px; background:#f9fafb; border-top:1px solid #e5e7eb; color:#9ca3af; font-size:12px; line-height:1.6;">
        本邮件由 DumpSight 自动生成，请勿直接回复。
      </div>
    </div>
  </div>
</body>
</html>
""".strip()

    return {
        "to_addrs": data.get("to_addrs") or [],
        "cc_addrs": data.get("cc_addrs") or [],
        "subject": subject,
        "body": body,
        "content_type": "html",
    }


def send_callback_notification(alert: dict, sender=None):
    """
    根据回调告警规则发送通知邮件。
    """
    print("\n========== send_callback_notification start ==========")
    print("[DEBUG] raw alert =", alert)

    if not isinstance(alert, dict) or not alert:
        print("[DEBUG] empty callback alert")
        return {
            "ok": False,
            "message": "empty callback alert",
        }

    callback_info = _normalize_callback_alert(alert)
    severity = (callback_info.get("severity") or "").lower()

    print("[DEBUG] normalized callback_info =", callback_info)
    print("[DEBUG] alert severity =", severity)

    result = get_alert_rules()
    print("[DEBUG] get_alert_rules result =", result)

    items = result.get("items", []) if isinstance(result, dict) else []
    print("[DEBUG] all rule count =", len(items))

    rules = [
        item
        for item in items
        if item
        and item.get("alert_type") == CALLBACK_TYPE
        and bool(item.get("enabled", False))
    ]

    print("[DEBUG] enabled callback_event rule count =", len(rules))
    print("[DEBUG] enabled callback_event rules =", rules)

    if not rules:
        print("[DEBUG] no callback alert rule configured")
        return {
            "ok": True,
            "message": "no callback alert rule configured",
            "alert_id": callback_info.get("alert_id"),
        }

    mail_sender = sender or SmtpMailSender()

    sent_count = 0
    skipped_count = 0

    for idx, rule in enumerate(rules, start=1):
        print(f"\n[DEBUG] ---- processing rule #{idx} ----")
        print("[DEBUG] rule =", rule)

        rule_severity = (rule.get("severity") or "").lower()
        print("[DEBUG] rule severity =", rule_severity)
        print("[DEBUG] alert severity =", severity)

        if rule_severity and rule_severity != severity:
            skipped_count += 1
            print("[SKIP] severity not match")
            print("[SKIP] rule_severity =", rule_severity, ", alert_severity =", severity)
            continue

        template_id = rule.get("template_id")
        print("[DEBUG] template_id =", template_id)

        to_addrs = [
            email
            for email in (rule.get("emails") or [])
            if email
        ]

        print("[DEBUG] to_addrs =", to_addrs)

        if not to_addrs:
            skipped_count += 1
            print("[SKIP] no recipient emails")
            continue

        if not template_id:
            skipped_count += 1
            print("[SKIP] no template_id")
            continue

        template = get_alert_mail_template_by_id(template_id)
        print("[DEBUG] template =", template)

        if not template:
            skipped_count += 1
            print("[SKIP] template not found")
            continue

        if not bool(template.get("enabled", True)):
            skipped_count += 1
            print("[SKIP] template disabled")
            continue

        field_order = _get_template_field_order(template)
        print("[DEBUG] template field_order =", field_order)

        payload = build_callback_mail_payload({
            "rule": rule,
            "template": template,
            "callback_info": callback_info,
            "to_addrs": to_addrs,
            "cc_addrs": [],
            "subject_prefix": "[DumpSight] Callback Alert",
        })

        print("[DEBUG] mail payload subject =", payload["subject"])
        print("[DEBUG] mail payload to_addrs =", payload["to_addrs"])
        print("[DEBUG] mail payload content_type =", payload.get("content_type"))

        alert_level = _severity_to_alert_level(rule.get("severity"))
        print("[DEBUG] alert_level =", alert_level)

        print("[DEBUG] sending mail...")

        mail_sender.send_mail(
            to_addrs=payload["to_addrs"],
            cc_addrs=payload.get("cc_addrs", []),
            subject=payload["subject"],
            body=payload["body"],
            content_type=payload.get("content_type", "html"),
            alert_level=alert_level,
        )

        sent_count += len(to_addrs)
        print("[DEBUG] mail sent success, sent_count =", sent_count)

    final_result = {
        "ok": True,
        "message": "callback notification sent",
        "alert_id": callback_info.get("alert_id"),
        "sent_count": sent_count,
        "skipped_count": skipped_count,
    }

    print("\n[DEBUG] final result =", final_result)
    print("========== send_callback_notification end ==========\n")

    return final_result

