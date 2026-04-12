import os
import sys
import yaml
from flask import Flask
from server.controller.client_controller import client_bp


def get_exe_dir() -> str:
    """Get the directory of the current executable or script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

EXE_DIR = get_exe_dir()

def create_app():
    app = Flask(__name__)

    config_path = os.path.join(EXE_DIR, 'server-config.yaml')

    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
        app.config.update(config)

    app.register_blueprint(client_bp, url_prefix="/api/client")

    return app