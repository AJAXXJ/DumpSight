from flask import Blueprint, request
from server.tools.api_response import ApiResponse
from server.service.alert_service import (
    get_smtp_config_service,
    save_smtp_config_service,
    test_smtp_connection_service,
    get_mail_logs_service,
    get_alert_rules_service,
    create_alert_rule_service,
    update_alert_rule_service,
    delete_alert_rule_service,

    get_alert_mail_templates_service,
    get_alert_mail_template_by_id_service,
    create_alert_mail_template_service,
    update_alert_mail_template_service,
    delete_alert_mail_template_service,
)


alert_bp = Blueprint("alert", __name__)

# --- 原有接口 ---
@alert_bp.get("/smtp-config")
def get_smtp_config_api():
    try:
        return ApiResponse.success(get_smtp_config_service())
    except Exception as e:
        return ApiResponse.error(str(e))


@alert_bp.post("/smtp-config")
def save_smtp_config_api():
    try:
        data = request.get_json() or {}
        return ApiResponse.success(save_smtp_config_service(data))
    except Exception as e:
        return ApiResponse.error(str(e))


@alert_bp.post("/smtp-config/test")
def test_smtp_connection_api():
    try:
        data = request.get_json() or {}
        return ApiResponse.success(test_smtp_connection_service(data))
    except Exception as e:
        return ApiResponse.error(str(e))


@alert_bp.get("/mail-logs")
def get_mail_logs_api():
    try:
        start_time = request.args.get("start_time")
        end_time = request.args.get("end_time")
        status = request.args.get("status")

        return ApiResponse.success(
            get_mail_logs_service(
                start_time=start_time,
                end_time=end_time,
                status=status,
            )
        )
    except Exception as e:
        return ApiResponse.error(str(e))



@alert_bp.get("/alert-rules")
def get_alert_rules_api():
    try:
        return ApiResponse.success(get_alert_rules_service())
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 新增规则（只能回调告警） ---
@alert_bp.post("/alert-rules")
def create_alert_rule_api():
    try:
        data = request.get_json() or {}
        # 后端 Service 会检查 type，确保只能是 callback_event
        return ApiResponse.success(create_alert_rule_service(data))
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 修改规则（崩溃告警只能修改 emails，其余规则可全部修改） ---
@alert_bp.put("/alert-rules/<rule_id>")
def update_alert_rule_api(rule_id: str):
    try:
        data = request.get_json() or {}
        return ApiResponse.success(update_alert_rule_service(rule_id, data))
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 删除规则（只能删除回调告警） ---
@alert_bp.delete("/alert-rules/<rule_id>")
def delete_alert_rule_api(rule_id: str):
    try:
        return ApiResponse.success(delete_alert_rule_service(rule_id))
    except Exception as e:
        return ApiResponse.error(str(e))

# --- 邮件模板列表 ---
@alert_bp.get("/templates")
def get_alert_mail_templates_api():
    try:
        return ApiResponse.success(get_alert_mail_templates_service())
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 邮件模板详情 ---
@alert_bp.get("/templates/<template_id>")
def get_alert_mail_template_by_id_api(template_id: str):
    try:
        return ApiResponse.success(get_alert_mail_template_by_id_service(template_id))
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 新增邮件模板 ---
@alert_bp.post("/templates")
def create_alert_mail_template_api():
    try:
        data = request.get_json() or {}
        return ApiResponse.success(create_alert_mail_template_service(data))
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 修改邮件模板 ---
@alert_bp.put("/templates/<template_id>")
def update_alert_mail_template_api(template_id: str):
    try:
        data = request.get_json() or {}
        return ApiResponse.success(update_alert_mail_template_service(template_id, data))
    except Exception as e:
        return ApiResponse.error(str(e))


# --- 删除邮件模板 ---
@alert_bp.delete("/templates/<template_id>")
def delete_alert_mail_template_api(template_id: str):
    try:
        return ApiResponse.success(delete_alert_mail_template_service(template_id))
    except Exception as e:
        return ApiResponse.error(str(e))
