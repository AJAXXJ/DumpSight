from flask import Blueprint, request
from server.tools.api_response import ApiResponse
from server.service.case_service import (
    case_get_service,
    case_insert_service,
    case_update_service,
    search_cases_es_pg,
    case_delete_service,
    case_page_service,
)

case_bp = Blueprint("case", __name__)


@case_bp.route("/insert", methods=["POST"])
def create_case():
    try:
        data = request.get_json()
        case_id = case_insert_service(data)
        return ApiResponse.success({"case_id": case_id})
    except Exception as e:
        return ApiResponse.error(str(e))


@case_bp.route("/get/<string:case_id>", methods=["GET"])
def get_case(case_id):
    try:
        case_info = case_get_service(case_id)
        return ApiResponse.success(case_info)
    except Exception as e:
        return ApiResponse.error(str(e))


@case_bp.route("/update/<string:case_id>", methods=["PUT"])
def update_case(case_id):
    try:
        updates = request.get_json()
        case_update_service(case_id, updates)
        return ApiResponse.success()
    except Exception as e:
        return ApiResponse.error(str(e))


@case_bp.route("/delete/<string:id>", methods=["DELETE"])
def delete_case(id):
    try:
        case_delete_service(id)
        return ApiResponse.success()
    except Exception as e:
        return ApiResponse.error(str(e))


@case_bp.route("/page", methods=["GET"])
def page_case():
    try:
        page_index = int(request.args.get("page_index", 1))
        page_size = int(request.args.get("page_size", 10))

        result = case_page_service(page_index, page_size)
        return ApiResponse.success(result)

    except Exception as e:
        return ApiResponse.error(str(e))


@case_bp.route("/search", methods=["POST"])
def search_case():
    try:
        data = request.get_json()
        query = data.get("query", "")

        results = search_cases_es_pg(query)
        return ApiResponse.success(results)

    except Exception as e:
        return ApiResponse.error(str(e))
