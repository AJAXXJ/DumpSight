from flask import Blueprint, request
from server.service.knowledge_service import (
    knowledge_delete_service,
    knowledge_handle_minio_event_service,
    knowledge_page_service,
    knowledge_upload_service,
)
from server.tools.api_response import ApiResponse


knowledge_bp = Blueprint("knowledge", __name__)


@knowledge_bp.route("/upload", methods=["POST"])
def knowledge_upload():
    try:
        request_json = request.get_json()
        upload_info = knowledge_upload_service(request_json["filename"])
        return ApiResponse.success(upload_info)

    except Exception as e:
        return ApiResponse.error(str(e))


@knowledge_bp.route("/minio/event", methods=["POST"])
def knowledge_handle_minio_event():
    minio_event_info = request.get_json(silent=True)
    knowledge_handle_minio_event_service(minio_event_info)
    return ApiResponse.success()


@knowledge_bp.route("/delete/<int:file_id>", methods=["DELETE"])
def knowledge_delete(file_id):
    try:
        knowledge_delete_service(file_id)
        return ApiResponse.success()

    except Exception as e:
        return ApiResponse.error(str(e))


@knowledge_bp.route("/page", methods=["GET"])
def knowledge_page():
    try:
        page_index = request.args.get("page_index")
        page_size = request.args.get("page_size")

        knowledge_page = knowledge_page_service(page_index, page_size)

        return ApiResponse.success(knowledge_page)
    except Exception as e:
        return ApiResponse.error(str(e))