from flask import Blueprint, app, jsonify, request

client_bp = Blueprint("client", __name__)

@client_bp.route('/status', methods=['GET'])
def client_status():
    client_id = request.args.get("client_id")
    if client_id:
        # TODO
        return jsonify(None), 200
    else:
        return jsonify({"error": "client_id is required"}), 400


@client_bp.route('/register', methods=['POST'])
def client_register():
    try:
        client_register_info = request.get_json()
        # TODO 

        return jsonify({"message": "Client registered successfully"}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to register client: {str(e)}"}), 500


@client_bp.route('/heartbeat', methods=['POST'])
def client_heartbeat():
    try:
        heartbeat_info = request.get_json()
        # TODO
        
        return jsonify({"message": "Heartbeat received successfully"}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to process heartbeat: {str(e)}"}), 500


@client_bp.route('/report_crash', methods=['POST'])
def client_core_analyse():
    try:
        crash_info = request.get_json()
        # TODO
        
        return jsonify({"message": "Heartbeat received successfully"}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to process heartbeat: {str(e)}"}), 500