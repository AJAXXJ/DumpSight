from flask import jsonify
from werkzeug.exceptions import HTTPException

from server.tools.api_response import ApiResponse


class BusinessException(Exception):
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)


def register_error_handlers(app):

    # 处理业务异常
    @app.errorhandler(BusinessException)
    def handle_business_error(e):
        return ApiResponse.error(code=e.code, message=e.message)

    # 处理 HTTPException（404/405 等）
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        return ApiResponse.error(code=e.code, message=e.description)

    # 处理所有未捕获异常
    @app.errorhandler(Exception)
    def handle_exception(e):
        return ApiResponse.error(code=500, message=str(e))
