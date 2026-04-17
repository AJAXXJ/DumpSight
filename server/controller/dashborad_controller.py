from flask import Blueprint, request

from server.service.dashborad_service import (
    dashborad_client_info_service,
    dashborad_instance_card_info_service,
    dashborad_instance_info_service,
    dashborad_raw_json_service,
    dashborad_render_report_service,
    dashborad_timeseries_metrics_service,
)
from server.tools.api_response import ApiResponse

dashborad_bp = Blueprint("dashborad", __name__)


@dashborad_bp.route("/raw_json", methods=["POST"])
def dashborad_raw_json():
    try:
        request_json = request.get_json()
        json_data = dashborad_raw_json_service(request_json)
        return ApiResponse.success(json_data)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashborad_bp.route("/render_report", methods=["GET"])
def dashborad_render_report():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")
        timestamp = request.args.get("timestamp")

        crash_report_info = dashborad_render_report_service(client_id, pid, timestamp)
        return ApiResponse.success(crash_report_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashborad_bp.route("/client_info", methods=["GET"])
def dashborad_cilent_info():
    try:
        client_id = request.args.get("client_id")

        client_info = dashborad_client_info_service(client_id)
        return ApiResponse.success(client_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashborad_bp.route("/instance_info", methods=["GET"])
def dashborad_instance_card_info():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")

        instance_info = dashborad_instance_info_service(client_id, pid)

        return ApiResponse.success(instance_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashborad_bp.route("/instance_card_info", methods=["GET"])
def dashborad_instance_card_info():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")
        seconds = request.args.get("seconds")

        instance_card_info = dashborad_instance_card_info_service(
            client_id, pid, seconds
        )

        return ApiResponse.success(instance_card_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@dashborad_bp.route("/instance_timeseries_metrics", methods=["GET"])
def dashborad_timeseries_metrics():
    try:
        client_id = request.args.get("client_id")
        pid = request.args.get("pid")
        seconds = request.args.get("seconds")

        timeseries_metrics = dashborad_timeseries_metrics_service(
            client_id, pid, seconds
        )

        return ApiResponse.success(timeseries_metrics)

    except Exception as e:
        return ApiResponse.error(str(e))
