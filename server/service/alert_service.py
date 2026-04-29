from typing import Any

from server.notification.email_sender import SmtpMailSender
from server.notification.feedback_mail import send_callback_notification
from server.repository.alert_repository import (
    get_smtp_config,
    save_smtp_config,
    get_mail_logs,
    create_mail_log,
    get_alert_rules,
    get_alert_rule_by_id,
    create_alert_rule,
    update_alert_rule,
    delete_alert_rule,
    get_alert_mail_templates,
    get_alert_mail_template_by_id,
    create_alert_mail_template,
    update_alert_mail_template,
    delete_alert_mail_template,
)

CRASH_TYPE = "crash_event"
CALLBACK_TYPE = "callback_event"
ALLOWED_TEMPLATE_FIELDS = {
    "alert_id",
    "client_id",
    "severity",
    "title",
    "description",
    "triggered_at",
}
ALLOWED_SEVERITIES = {"critical", "warning", "info"}


def alert_service(alert: dict):
    """
    实时监控回调告警入口。
    alert 来自 agent live monitor 的 alert_handler(alert)。

    当前 alert 可用字段：
    - alert_id
    - client_id
    - severity
    - title
    - description
    - triggered_at
    """
    return send_callback_notification(alert)


def _normalize_smtp_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("SMTP 配置格式错误")

    return {
        "host": str(data.get("host", "")).strip(),
        "port": int(data.get("port", 0) or 0),
        "ssl": bool(data.get("ssl", False)),
        "sender": str(data.get("sender", "")).strip(),
        "username": str(data.get("username", "")).strip(),
        "password": str(data.get("password", "") or ""),
    }


def _validate_email(value: str, field_name: str):
    if not value:
        raise ValueError(f"{field_name} 不能为空")

    if "@" not in value:
        raise ValueError(f"{field_name} 格式不合法")


def _validate_smtp_payload(data: dict, allow_empty_password: bool = False):
    if not data.get("host"):
        raise ValueError("SMTP 服务器地址不能为空")

    port = data.get("port")
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError("SMTP 端口不合法")

    _validate_email(data.get("sender", ""), "发件人邮箱")

    if not data.get("username"):
        raise ValueError("用户名不能为空")

    if not allow_empty_password and not data.get("password"):
        raise ValueError("密码或授权码不能为空")


def get_smtp_config_service():
    """
    获取 SMTP 配置。
    注意：不返回真实密码，仅返回空字符串占位。
    """
    config = get_smtp_config()

    if not config:
        return {
            "host": "",
            "port": 465,
            "ssl": True,
            "sender": "",
            "username": "",
            "password": "",
        }

    return {
        "host": config.get("host", ""),
        "port": int(config.get("port", 465)),
        "ssl": bool(config.get("ssl", True)),
        "sender": config.get("sender", ""),
        "username": config.get("username", ""),
        "password": "",
    }


def save_smtp_config_service(data: dict):
    """
    保存 SMTP 配置。
    - password 为空时沿用旧密码
    - password 非空时更新新密码
    """
    payload = _normalize_smtp_payload(data)
    _validate_smtp_payload(payload, allow_empty_password=True)

    old = get_smtp_config() or {}

    password = payload.get("password", "")
    if not password:
        password = old.get("password", "")
        if not password:
            raise ValueError("请填写密码或授权码")

    save_smtp_config(
        {
            "host": payload["host"],
            "port": payload["port"],
            "ssl": payload["ssl"],
            "sender": payload["sender"],
            "username": payload["username"],
            "password": password,
        }
    )

    return {"ok": True}


def test_smtp_connection_service(data: dict):
    """
    测试 SMTP 连接。
    使用前端表单传入的配置测试，不依赖已保存配置。
    """
    payload = _normalize_smtp_payload(data)
    _validate_smtp_payload(payload, allow_empty_password=False)

    sender = SmtpMailSender(
        host=payload["host"],
        port=payload["port"],
        ssl=payload["ssl"],
        sender=payload["sender"],
        username=payload["username"],
        password=payload["password"],
    )
    sender.test_connection()

    return {"ok": True}


def create_mail_log_service(data: dict):
    """
    新增邮件发送历史记录。
    """
    return create_mail_log(data)


def get_mail_logs_service(
    start_time: str | None = None,
    end_time: str | None = None,
    status: str | None = None,
):
    """
    获取邮件发送历史记录列表。
    支持按发送时间范围和发送状态筛选。
    """
    if status and status not in {"success", "failed"}:
        raise ValueError("发送状态不合法")

    return get_mail_logs(
        start_time=start_time,
        end_time=end_time,
        status=status,
    )


def get_alert_rules_service():
    """
    获取告警规则列表。
    """
    return get_alert_rules()


def _normalize_template_field_order(values):
    if not isinstance(values, list):
        raise ValueError("模板字段顺序格式错误")

    field_order = []
    for item in values:
        field_key = str(item).strip()
        if not field_key:
            continue
        if field_key not in ALLOWED_TEMPLATE_FIELDS:
            raise ValueError(f"不支持的模板字段：{field_key}")
        if field_key not in field_order:
            field_order.append(field_key)

    if not field_order:
        raise ValueError("请至少选择一个邮件内容字段")

    return field_order


def _normalize_alert_mail_template_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("邮件模板格式错误")

    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("模板名称不能为空")

    subject_template = str(
        data.get("subjectTemplate") or data.get("subject_template") or ""
    ).strip()
    if not subject_template:
        raise ValueError("邮件主题模板不能为空")

    field_order = _normalize_template_field_order(
        data.get("fieldOrder") or data.get("field_order") or []
    )

    return {
        "name": name,
        "description": str(data.get("description", "") or "").strip(),
        "alert_type": CALLBACK_TYPE,
        "subject_template": subject_template,
        "field_order": field_order,
        "enabled": bool(data.get("enabled", True)),
    }


def _format_alert_mail_template_for_frontend(template: dict[str, Any] | None):
    if not template:
        return None

    return {
        "id": template.get("id"),
        "name": template.get("name", ""),
        "description": template.get("description", ""),
        "alertTypes": [template.get("alert_type") or CALLBACK_TYPE],
        "subjectTemplate": template.get("subject_template", ""),
        "fieldOrder": template.get("field_order") or [],
        "enabled": bool(template.get("enabled", True)),
        "createdAt": template.get("create_time"),
        "updatedAt": template.get("update_time"),
    }

def get_alert_mail_templates_service():
    """
    获取邮件模板列表。
    """
    result = get_alert_mail_templates()
    items = result.get("items", []) if isinstance(result, dict) else []

    return [
        _format_alert_mail_template_for_frontend(item)
        for item in items
        if item
    ]


def get_alert_mail_template_by_id_service(template_id):
    """
    根据 ID 获取邮件模板。
    """
    template = get_alert_mail_template_by_id(template_id)
    return _format_alert_mail_template_for_frontend(template)


def create_alert_mail_template_service(data: dict):
    """
    新增邮件模板。
    """
    payload = _normalize_alert_mail_template_payload(data)
    template = create_alert_mail_template(payload)
    return _format_alert_mail_template_for_frontend(template)


def update_alert_mail_template_service(template_id, data: dict):
    """
    更新邮件模板。
    """
    old = get_alert_mail_template_by_id(template_id)
    if not old:
        raise ValueError("邮件模板不存在")

    payload = _normalize_alert_mail_template_payload(data)
    template = update_alert_mail_template(template_id, payload)
    return _format_alert_mail_template_for_frontend(template)


def delete_alert_mail_template_service(template_id):
    """
    删除邮件模板。
    """
    old = get_alert_mail_template_by_id(template_id)
    if not old:
        raise ValueError("邮件模板不存在")

    return delete_alert_mail_template(template_id)


def _normalize_emails(values):
    if not isinstance(values, list):
        raise ValueError("通知邮箱格式错误")

    emails = []
    for item in values:
        email = str(item).strip()
        if not email:
            continue
        if "@" not in email:
            raise ValueError(f"通知邮箱格式不合法：{email}")
        if email not in emails:
            emails.append(email)

    if not emails:
        raise ValueError("请至少填写一个通知邮箱")

    return emails


def _normalize_alert_rule_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("告警规则格式错误")

    return {
        "name": str(data.get("name", "")).strip(),
        "alert_type": str(data.get("type") or data.get("alert_type") or "").strip(),
        "severity": str(data.get("severity", "")).strip(),
        "emails": _normalize_emails(data.get("emails", [])),
        "template_id": data.get("templateId") or data.get("template_id"),
        "enabled": bool(data.get("enabled", True)),
        "remark": str(data.get("condition") or data.get("remark") or "").strip(),
    }


def _validate_callback_rule_payload(payload: dict):
    if payload["alert_type"] != CALLBACK_TYPE:
        raise ValueError("只能新增回调告警规则")

    if not payload["name"]:
        raise ValueError("规则名称不能为空")

    if payload["severity"] not in ALLOWED_SEVERITIES:
        raise ValueError("告警级别不合法")

    if not payload.get("template_id"):
        raise ValueError("请选择通知模板")


def create_alert_rule_service(data: dict):
    """
    新增告警规则。
    只允许新增 callback_event，不允许新增 crash_event。
    """
    payload = _normalize_alert_rule_payload(data)
    _validate_callback_rule_payload(payload)

    return create_alert_rule(payload)


def update_alert_rule_service(rule_id, data: dict):
    """
    修改告警规则。
    - crash_event: 只能修改 emails，并强制 enabled=True
    - callback_event: 允许正常修改
    """
    rule = get_alert_rule_by_id(rule_id)
    if not rule:
        raise ValueError("告警规则不存在")

    payload = _normalize_alert_rule_payload(data)

    rule_type = rule.get("alert_type") or rule.get("type")

    if rule_type == CRASH_TYPE:
        return update_alert_rule(
            rule_id,
            {
                "emails": payload["emails"],
                "enabled": True,
            },
        )

    _validate_callback_rule_payload(payload)
    return update_alert_rule(rule_id, payload)


def delete_alert_rule_service(rule_id):
    """
    删除告警规则。
    只允许删除 callback_event，禁止删除 crash_event。
    """
    rule = get_alert_rule_by_id(rule_id)
    if not rule:
        raise ValueError("告警规则不存在")

    rule_type = rule.get("alert_type") or rule.get("type")

    if rule_type == CRASH_TYPE:
        raise ValueError("崩溃告警为系统内置规则，不允许删除")

    return delete_alert_rule(rule_id)

