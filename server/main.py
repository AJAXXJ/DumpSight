import yaml
from flask import Flask, current_app
from controller.client_controller import client_bp

app = Flask(__name__)

def load_config_from_yaml(app):
    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)
        app.config.update(config)

load_config_from_yaml(app)

app.register_blueprint(client_bp, url_prefix="/api/client")


if __name__ == '__main__':
    app.run(debug=current_app.config['DEBUG'], port=current_app.config['PORT'])