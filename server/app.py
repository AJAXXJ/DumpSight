import yaml
from flask import Flask
from agent.live_monitor import start_sync_thread
from agent.main import fault_handler
from server.controller.client_controller import client_bp
from server.controller.dashborad_controller import dashborad_bp
from server.service import alert_service
from tools.mysql_util import get_mysql_util, init_mysql_util


def create_app(config_path="server-config.yaml"):
    app = Flask(__name__)

    with open(config_path, "r") as file:
        config = yaml.safe_load(file)
        app.config.update(config)

    # 初始化 mysql
    init_mysql_util(app.config)

    with app.app_context():
        get_mysql_util().init_db()

    # 初始化监控
    start_sync_thread(
        alert_handler=lambda alert: alert_service(alert),
        fault_handler=lambda result: fault_handler(result),
        fast_interval=app.config["FAST_INTERVAL"],
        slow_interval=app.config["SLOW_INTERVAL"],
        sync_interval=app.config["SYNC_INTERVAL"],
    )

    # 接口注册
    app.register_blueprint(client_bp, url_prefix="/api/client")
    app.register_blueprint(dashborad_bp, url_prefix="/api/dasgborad")

    return app
