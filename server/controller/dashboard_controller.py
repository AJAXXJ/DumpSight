from flask import Blueprint, request

from server.service.dashboard_service import (
    dashboard_client_info_service,
    dashboard_client_list_service,
    dashboard_instance_timeseries_info_service,
    dashboard_instance_info_service,
    dashboard_instance_list_service,
    dashboard_raw_json_service,
    dashboard_render_report_service,
    dashboard_report_list_service,
    dashboard_statics_service,
)
from server.tools.api_response import ApiResponse
from tools.minio_util import get_minio_util

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/report_list", methods=["GET"])
def dashboard_report_list():
    try:
        page_index = request.args.get("page_index")
        page_size = request.args.get("page_size")
        report_list = dashboard_report_list_service(page_index, page_size)
        return ApiResponse.success(report_list)
    except Exception as e:
        return ApiResponse.error(str(e))


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


@dashboard_bp.route("/instance_list", methods=["GET"])
def dashboard_instance_list():
    try:
        client_id = request.args.get("client_id")

        instance_list = dashboard_instance_list_service(client_id)
        return ApiResponse.success(instance_list)

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


@dashboard_bp.route("/instance_timeseries_info", methods=["GET"])
def dashboard_instance_timeseries_info():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")
        seconds = int(request.args.get("seconds"))

        instance_timeseries_info = dashboard_instance_timeseries_info_service(
            client_id, pid, seconds
        )

        return ApiResponse.success(instance_timeseries_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashboard_bp.route("/dashboard_statics", methods=["GET"])
def dashboard_statics():
    try:
        statics_info = dashboard_statics_service()
        return ApiResponse.success(statics_info)

    except Exception as e:
        return ApiResponse.error(str(e))


