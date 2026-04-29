import yaml
from flask import Flask
from flask_cors import CORS
from agent.live_monitor import start_sync_thread
from agent.main import fault_handler
from server.controller.client_controller import client_bp
from server.controller.dashboard_controller import dashboard_bp
from server.controller.knowledge_controller import knowledge_bp
from server.controller.case_controller import case_bp
from server.controller.alert_controller import alert_bp
from server.controller.chat_controller import chat_bp
from tools.minio_util import init_minio_util
from tools.mysql_util import get_mysql_util, init_mysql_util
from tools.pgvector_util import init_pgvector_util
from tools.redis_util import init_redis_util
# from server.notification import init_notification
from tools.es_util import init_es_util


def create_app(config_path="server-config.yaml"):
    app = Flask(__name__)

    # 跨域配置
    CORS(app, origins=["http://localhost:5666"], supports_credentials=True)

    with open(config_path, "r") as file:
        config = yaml.safe_load(file)
        app.config.update(config)

    # 初始化 mysql
    init_mysql_util(app.config)

    with app.app_context():
        get_mysql_util().init_db()

    # 初始化 redis
    init_redis_util(app.config)

    # 初始化 minio
    init_minio_util(app.config)

    # 初始化 pgvector
    init_pgvector_util(app.config)

    # 初始化 ES
    init_es_util(app.config)

    # 初始化邮件通知模块
    # init_notification(app.config)

    # 初始化监控
    # start_sync_thread(
    #     alert_handler=lambda alert: alert_service(alert),
    #     fault_handler=lambda result: fault_handler(result),
    #     fast_interval=app.config["FAST_INTERVAL"],
    #     slow_interval=app.config["SLOW_INTERVAL"],
    #     sync_interval=app.config["SYNC_INTERVAL"],
    # )

    # 接口注册
    app.register_blueprint(client_bp, url_prefix="/api/client")
    app.register_blueprint(dashboard_bp, url_prefix="/dpdk/dashboard")
    app.register_blueprint(knowledge_bp, url_prefix="/dpdk/knowledge")
    app.register_blueprint(case_bp, url_prefix="/dpdk/case")
    app.register_blueprint(chat_bp, url_prefix="/dpdk/chat")
    app.register_blueprint(alert_bp, url_prefix="/dpdk/alert")


    return app
