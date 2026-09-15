from pathlib import Path

from dotenv import load_dotenv

# Load .env before anything reads os.environ (config, services, scripts).
# Variables already present in the environment win, so containers and CI
# are unaffected.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from flask import Flask  # noqa: E402

from .config import Config  # noqa: E402
from .extensions import db, migrate
from .routes import main_bp
from .api_v1 import api_v1_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError(
            "DATABASE_URL is not set. Export it in your shell or set it in a .env file."
        )

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(main_bp)
    app.register_blueprint(api_v1_bp)

    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        app.config["APP_VERSION"] = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        app.config["APP_VERSION"] = "unknown"

    @app.context_processor
    def inject_app_globals():
        return {
            "app_version": app.config.get("APP_VERSION", "unknown"),
            "app_name": app.config.get("APP_NAME", "Ant Air"),
            "home_city": app.config.get("HOME_CITY"),
            "home_country": app.config.get("HOME_COUNTRY"),
            "home_airports": app.config.get("HOME_AIRPORTS", []),
        }

    return app
