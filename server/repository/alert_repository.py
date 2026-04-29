from server.models.email.smtp_config import SmtpConfig
from server.models.email.alert_mail_log import AlertMailLog
from server.models.email.alert_rule import AlertRule
from server.models.email.alert_rule_recipient import AlertRuleRecipient
from server.models.email.alert_mail_template import AlertMailTemplate

CRASH_TYPE = "crash_event"
CRASH_FIXED_TEMPLATE_NAME = "崩溃告警标准模板"


def _format_smtp_config(data):
    if not data:
        return None

    return {
        "id": data.get("id"),
        "host": data.get("host", ""),
        "port": int(data.get("port") or 465),
        "ssl": bool(data.get("use_ssl", 0)),
        "sender": data.get("sender", ""),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
        "enabled": bool(data.get("enabled", 1)),
        "create_time": data.get("create_time"),
        "update_time": data.get("update_time"),
    }


def get_smtp_config():
    """
    获取 SMTP 配置。
    默认读取 smtp_config 表中 id=1 且 enabled=1 的记录，对外统一使用 ssl 字段。
    """
    data = SmtpConfig.get(id=1, enabled=1)
    return _format_smtp_config(data)


def save_smtp_config(config: dict):
    """
    保存 SMTP 配置。
    - 如果 id=1 存在则更新，不存在则插入
    - 数据库存 use_ssl，对外统一使用 ssl
    """
    if not isinstance(config, dict):
        raise ValueError("SMTP 配置保存失败，参数格式错误")

    params = {
        "id": 1,
        "host": str(config.get("host", "")).strip(),
        "port": int(config.get("port", 465)),
        "use_ssl": 1 if bool(config.get("ssl", True)) else 0,
        "sender": str(config.get("sender", "")).strip(),
        "username": str(config.get("username", "")).strip(),
        "password": str(config.get("password", "") or ""),
        "enabled": 1,
    }

    existing = SmtpConfig.get(id=1)

    if existing:
        SmtpConfig.update(filters={"id": 1}, updates=params)
    else:
        SmtpConfig.create(**params)

    return get_smtp_config()


def create_mail_log(data: dict):
    """
    新增邮件发送历史记录。
    """
    if not isinstance(data, dict):
        raise ValueError("邮件发送历史记录保存失败，参数格式错误")

    params = {
        "sent_at": data.get("sent_at"),
        "sender": str(data.get("sender", "")).strip(),
        "receivers": str(data.get("receivers", "")).strip(),
        "subject": str(data.get("subject", "")).strip(),
        "alert_level": data.get("alert_level") or "P3",
        "status": data.get("status") or "failed",
        "error_message": str(data.get("error_message", "") or ""),
    }

    AlertMailLog.create(**params)

    return True


def get_mail_logs(
    start_time: str | None = None,
    end_time: str | None = None,
    status: str | None = None,
):
    """
    获取邮件发送历史记录列表。
    支持按发送时间范围和发送状态筛选。
    """
    rows = AlertMailLog.all()

    # 按发送状态筛选
    if status:
        rows = [
            item for item in rows
            if item.get("status") == status
        ]

    # 按开始时间筛选
    if start_time:
        rows = [
            item for item in rows
            if (item.get("sent_at") or "") >= start_time
        ]

    # 按结束时间筛选
    if end_time:
        rows = [
            item for item in rows
            if (item.get("sent_at") or "") <= end_time
        ]

    rows.sort(
        key=lambda x: (x.get("sent_at") or "", x.get("id") or 0),
        reverse=True,
    )

    items = []
    for data in rows:
        items.append({
            "id": data.get("id"),
            "sent_at": data.get("sent_at", ""),
            "sender": data.get("sender", ""),
            "receivers": data.get("receivers", ""),
            "subject": data.get("subject", ""),
            "alert_level": data.get("alert_level", ""),
            "status": data.get("status", ""),
            "error_message": data.get("error_message", ""),
        })

    return {
        "items": items,
        "total": len(items),
    }




def get_alert_rules():
    """
    获取告警规则列表。

    说明：
    - 只返回 deleted=0 的规则
    - 补齐收件人 emails 与模板名称
    - 按 id 倒序排列（最新优先）
    """
    rows = AlertRule.filter(deleted=0)

    rows.sort(
        key=lambda x: x.get("id") or 0,
        reverse=True,
    )

    # 收集 rule_id，便于批量查询收件人
    rule_ids = [row.get("id") for row in rows if row.get("id")]

    # 查询收件人
    recipients = AlertRuleRecipient.in_filter("rule_id", rule_ids) if rule_ids else []

    email_map = {}
    for item in recipients:
        rule_id = item.get("rule_id")
        email = item.get("email")
        if not rule_id or not email:
            continue

        email_map.setdefault(rule_id, []).append(email)

    # 查询模板名称
    template_ids = [
        row.get("template_id")
        for row in rows
        if row.get("template_id")
    ]

    templates = (
        AlertMailTemplate.in_filter("id", template_ids)
        if template_ids else []
    )

    template_map = {
        item.get("id"): item.get("name")
        for item in templates
        if item.get("id")
    }

    # 组装返回数据
    items = []
    for data in rows:
        rule_id = data.get("id")
        template_id = data.get("template_id")
        alert_type = data.get("alert_type", "")

        # crash_event 使用固定模板名，其他类型回退模板表或历史字段
        if alert_type == CRASH_TYPE:
            template_name = CRASH_FIXED_TEMPLATE_NAME
        else:
            template_name = template_map.get(template_id) or data.get("template_name")

        items.append({
            "id": rule_id,
            "name": data.get("name", ""),
            "alert_type": alert_type,
            "severity": data.get("severity", ""),
            "emails": email_map.get(rule_id, []),
            "template_id": template_id,
            "template_name": template_name,
            "enabled": bool(data.get("enabled", 1)),
            "remark": data.get("remark"),
            "create_time": data.get("create_time"),
            "update_time": data.get("update_time"),
        })

    return {
        "items": items,
        "total": len(items),
    }

def get_alert_rule_by_id(rule_id):
    """
    根据 ID 获取规则（未删除）。
    """
    if not rule_id:
        return None

    return AlertRule.get(id=rule_id, deleted=0)

def create_alert_rule(data: dict):
    if not isinstance(data, dict):
        raise ValueError("新增规则失败，参数格式错误")

    data = dict(data)
    emails = data.pop("emails", [])

    params = {
        "name": str(data.get("name", "")).strip(),
        "alert_type": str(data.get("alert_type") or data.get("type") or "").strip(),
        "severity": str(data.get("severity") or "info").strip(),
        "template_id": data.get("template_id"),
        "template_name": data.get("template_name"),
        "enabled": 1 if bool(data.get("enabled", True)) else 0,
        "remark": str(data.get("remark", "") or ""),
        "deleted": 0,  # 新增默认未删除
    }

    rule = AlertRule.create(**params)

    rule_id = rule.get("id") if isinstance(rule, dict) else None
    if not rule_id:
        raise ValueError("规则创建失败")

    for email in emails:
        AlertRuleRecipient.create(
            rule_id=rule_id,
            email=email,
        )

    return get_alert_rule_by_id(rule_id)


def update_alert_rule(rule_id, data: dict):
    if not rule_id:
        raise ValueError("rule_id 不能为空")

    data = dict(data)
    emails = data.pop("emails", None)

    if data:
        AlertRule.update(
            filters={"id": rule_id},
            updates=data,
        )

    if emails is not None:
        old_items = AlertRuleRecipient.filter(rule_id=rule_id)

        for item in old_items:
            AlertRuleRecipient.delete(id=item.get("id"))

        for email in emails:
            AlertRuleRecipient.create(
                rule_id=rule_id,
                email=email,
            )

    return get_alert_rule_by_id(rule_id)


def delete_alert_rule(rule_id):
    if not rule_id:
        raise ValueError("rule_id 不能为空")

    AlertRule.update(
        filters={"id": rule_id},
        updates={"deleted": 1},
    )

    old_items = AlertRuleRecipient.filter(rule_id=rule_id)

    for item in old_items:
        AlertRuleRecipient.delete(id=item.get("id"))

    return {"ok": True}

def _format_alert_mail_template(data):
    if not data:
        return None

    return {
        "id": data.get("id"),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "alert_type": data.get("alert_type", "callback_event"),
        "subject_template": data.get("subject_template", ""),
        "field_order": data.get("field_order") or [],
        "enabled": bool(data.get("enabled", 1)),
        "deleted": bool(data.get("deleted", 0)),
        "create_time": data.get("create_time"),
        "update_time": data.get("update_time"),
    }


def get_alert_mail_templates():
    """
    获取邮件模板列表。
    """
    rows = AlertMailTemplate.filter(deleted=0)

    rows.sort(
        key=lambda x: x.get("id") or 0,
        reverse=True,
    )

    items = [_format_alert_mail_template(row) for row in rows]

    return {
        "items": items,
        "total": len(items),
    }


def get_alert_mail_template_by_id(template_id):
    """
    根据 ID 获取邮件模板。
    """
    if not template_id:
        return None

    data = AlertMailTemplate.get(id=template_id, deleted=0)
    return _format_alert_mail_template(data)


def create_alert_mail_template(data: dict):
    """
    新增邮件模板。
    """
    if not isinstance(data, dict):
        raise ValueError("新增邮件模板失败，参数格式错误")

    params = {
        "name": str(data.get("name", "")).strip(),
        "description": str(data.get("description", "") or "").strip(),
        "alert_type": str(data.get("alert_type") or "callback_event").strip(),
        "subject_template": str(data.get("subject_template", "")).strip(),
        "field_order": data.get("field_order") or [],
        "enabled": 1 if bool(data.get("enabled", True)) else 0,
        "deleted": 0,
    }

    template = AlertMailTemplate.create(**params)
    return _format_alert_mail_template(template)


def update_alert_mail_template(template_id, data: dict):
    """
    更新邮件模板。
    """
    if not template_id:
        raise ValueError("template_id 不能为空")

    if not isinstance(data, dict):
        raise ValueError("更新邮件模板失败，参数格式错误")

    params = {}

    if "name" in data:
        params["name"] = str(data.get("name", "")).strip()

    if "description" in data:
        params["description"] = str(data.get("description", "") or "").strip()

    if "alert_type" in data:
        params["alert_type"] = str(data.get("alert_type") or "callback_event").strip()

    if "subject_template" in data:
        params["subject_template"] = str(data.get("subject_template", "")).strip()

    if "field_order" in data:
        params["field_order"] = data.get("field_order") or []

    if "enabled" in data:
        params["enabled"] = 1 if bool(data.get("enabled", True)) else 0

    if not params:
        return get_alert_mail_template_by_id(template_id)

    AlertMailTemplate.update(
        filters={"id": template_id, "deleted": 0},
        updates=params,
    )

    return get_alert_mail_template_by_id(template_id)


def delete_alert_mail_template(template_id):
    """
    删除邮件模板（逻辑删除）。
    """
    if not template_id:
        raise ValueError("template_id 不能为空")

    AlertMailTemplate.update(
        filters={"id": template_id},
        updates={"deleted": 1},
    )

    return {"ok": True}
