from flask import Blueprint, request

from server.service.dashboard_service import (
    dashboard_client_info_service,
    dashboard_client_list_service,
    dashboard_instance_card_info_service,
    dashboard_instance_info_service,
    dashboard_raw_json_service,
    dashboard_render_report_service
)
from server.tools.api_response import ApiResponse

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/raw_json", methods=["POST"])
def dashboard_raw_json():
    try:
        request_json = request.get_json()
        json_data = dashboard_raw_json_service(request_json)
        return ApiResponse.success(json_data)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashboard_bp.route("/render_report", methods=["GET"])
def dashboard_render_report():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")
        timestamp = request.args.get("timestamp")

        crash_report_info = dashboard_render_report_service(client_id, pid, timestamp)
        return ApiResponse.success(crash_report_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashboard_bp.route("/client_list", methods=["GET"])
def dashboard_client_list():
    try:
        client_list = dashboard_client_list_service()
        return ApiResponse.success(client_list)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashboard_bp.route("/client_info", methods=["GET"])
def dashboard_client_info():
    try:
        client_id = request.args.get("client_id")

        client_info = dashboard_client_info_service(client_id)
        return ApiResponse.success(client_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashboard_bp.route("/instance_info", methods=["GET"])
def dashboard_instance_info():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")

        instance_info = dashboard_instance_info_service(client_id, pid)

        return ApiResponse.success(instance_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashboard_bp.route("/instance_card_info", methods=["GET"])
def dashboard_instance_card_info():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")
        seconds = request.args.get("seconds")

        instance_card_info = dashboard_instance_card_info_service(
            client_id, pid, seconds
        )

        return ApiResponse.success(instance_card_info)

    except Exception as e:
        return ApiResponse.error(str(e))

