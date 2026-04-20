from agent.live_monitor import start_sync_thread
from agent.main import fault_handler
from server.app import create_app
from server.service.alert_service import alert_service

if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config['DEBUG'], port=app.config['PORT'])

