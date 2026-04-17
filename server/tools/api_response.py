from flask import jsonify


class ApiResponse:
    @staticmethod
    def success(data=None, message="success", code=200):
        return jsonify({
            "code": code,
            "message": message,
            "data": data
        }), code

    @staticmethod
    def error(message="error", code=500, data=None):
        return jsonify({
            "code": code,
            "message": message,
            "data": data
        }), code