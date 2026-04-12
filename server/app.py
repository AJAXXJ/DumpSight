import yaml
from flask import Flask
from server.controller.client_controller import client_bp
from tools.mysql_util import get_mysql_util, init_mysql_util

def create_app(config_path="server-config.yaml"):
    app = Flask(__name__)

    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
        app.config.update(config)

    init_mysql_util(app.config)

    with app.app_context():
        get_mysql_util().init_db()

    app.register_blueprint(client_bp, url_prefix="/api/client")

    return app