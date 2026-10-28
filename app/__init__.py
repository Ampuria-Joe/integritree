from flask import Flask

from config import Config


def create_app(db_path=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if db_path:
        app.config["DB_PATH"] = str(db_path)

    from .db import init_db
    init_db(app.config["DB_PATH"])

    from .routes import bp
    from .cli import register
    app.register_blueprint(bp)
    register(app)
    return app
