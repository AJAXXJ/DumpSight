import yaml
from flask import Flask
from server.controller.client_controller import client_bp

def create_app(config_path="server-config.yaml"):
    app = Flask(__name__)

    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
        app.config.update(config)

    app.register_blueprint(client_bp, url_prefix="/api/client")

    return app

app = create_app()