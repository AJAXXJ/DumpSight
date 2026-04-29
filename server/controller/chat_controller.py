from flask import Blueprint, Response, request, stream_with_context
from server.tools.api_response import ApiResponse
from server.service.chat_service import chat, chat_stream

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("", methods=["POST"])
def chat_api():
    body = request.get_json() or {}
    query = body.get("q", "").strip()
    history = body.get("history", [])
    if not query:
        return ApiResponse.bad_request("query is required")
    return ApiResponse.success({"message": chat(query, history)})


@chat_bp.route("/stream", methods=["POST"])
def chat_stream_api():
    body = request.get_json() or {}
    query = body.get("q", "").strip()
    history = body.get("history", [])
    if not query:
        return ApiResponse.bad_request("query is required")

    return Response(
        stream_with_context(chat_stream(query, history)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )