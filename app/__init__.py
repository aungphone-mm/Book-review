from flask import Flask
from flask_restx import Api
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS  # Add this import

from config import Config

db = SQLAlchemy()
jwt = JWTManager()
api = Api(title='Book Review API', version='1.0', description='A simple book review API')

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)  # Add this line to enable CORS

    db.init_app(app)
    jwt.init_app(app)
    api.init_app(app)

    from app.resources.book import ns as book_ns
    from app.resources.review import ns as review_ns
    from app.resources.user import ns as user_ns
    from app.resources.search import ns as search_ns

    api.add_namespace(book_ns)
    api.add_namespace(review_ns)
    api.add_namespace(user_ns)
    api.add_namespace(search_ns)

    return app