from flask import jsonify


class ApiResponse:

    @staticmethod
    def success(data=None, message="success", code=0):
        return jsonify({
            "code": code,
            "message": message,
            "data": data
        }), 200

    @staticmethod
    def error(message="error", code=500, data=None):
        return jsonify({
            "code": code,
            "message": message,
            "data": data
        }), 200

    @staticmethod
    def bad_request(message="bad request", data=None):
        return ApiResponse.error(message, code=400, data=data)

    @staticmethod
    def unauthorized(message="unauthorized"):
        return ApiResponse.error(message, code=401)

    @staticmethod
    def forbidden(message="forbidden"):
        return ApiResponse.error(message, code=403)

    @staticmethod
    def not_found(message="not found"):
        return ApiResponse.error(message, code=404)