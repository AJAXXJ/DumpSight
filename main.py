from server.app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config['DEBUG'], port=app.config['PORT'])