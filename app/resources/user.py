from flask_restx import Resource, Namespace, fields, abort
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app.models import User
from app import db

ns = Namespace('users', description='User registration and authentication')

credentials_model = ns.model('Credentials', {
    'username': fields.String(required=True),
    'password': fields.String(required=True)
})

user_model = ns.model('User', {
    'id': fields.Integer(readonly=True),
    'username': fields.String(readonly=True)
})

token_model = ns.model('Token', {
    'access_token': fields.String(readonly=True)
})

@ns.route('/register')
class UserRegister(Resource):
    @ns.doc('register_user')
    @ns.expect(credentials_model)
    @ns.response(409, 'Username already taken')
    @ns.marshal_with(user_model, code=201)
    def post(self):
        '''Register a new user'''
        username = ns.payload['username']
        if User.query.filter_by(username=username).first():
            abort(409, 'Username already taken')
        user = User(username=username)
        user.set_password(ns.payload['password'])
        db.session.add(user)
        db.session.commit()
        return user, 201

@ns.route('/login')
class UserLogin(Resource):
    @ns.doc('login_user')
    @ns.expect(credentials_model)
    @ns.response(401, 'Invalid username or password')
    @ns.marshal_with(token_model)
    def post(self):
        '''Exchange credentials for a JWT access token'''
        user = User.query.filter_by(username=ns.payload['username']).first()
        if user is None or not user.check_password(ns.payload['password']):
            abort(401, 'Invalid username or password')
        # the identity is stored as a string: flask-jwt-extended rejects a
        # non-string `sub` claim from 4.6 onwards
        return {'access_token': create_access_token(identity=str(user.id))}

@ns.route('/me')
class UserMe(Resource):
    @ns.doc('get_current_user')
    @ns.marshal_with(user_model)
    @jwt_required()
    def get(self):
        '''Fetch the currently authenticated user'''
        return User.query.get_or_404(int(get_jwt_identity()))
