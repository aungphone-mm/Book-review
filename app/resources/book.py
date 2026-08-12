from flask_restx import Resource, Namespace, fields
from flask_jwt_extended import jwt_required
from app.models import Book
from app import db

ns = Namespace('books', description='Book operations')

book_model = ns.model('Book', {
    'id': fields.Integer(readonly=True),
    'title': fields.String(required=True),
    'author': fields.String(required=True),
    'genre': fields.String(),
    'external_id': fields.String(readonly=True)
})

import_model = ns.model('BookImport', {
    'external_id': fields.String(required=True, description='Open Library work key from /search/external'),
    'title': fields.String(required=True),
    'author': fields.String(required=True),
    'genre': fields.String()
})

@ns.route('')
class BookList(Resource):
    @ns.doc('list_books')
    @ns.marshal_list_with(book_model)
    def get(self):
        '''List all books'''
        return Book.query.all()

    @ns.doc('create_book')
    @ns.expect(book_model)
    @ns.marshal_with(book_model, code=201)
    @jwt_required()
    def post(self):
        '''Create a new book'''
        book = Book(title=ns.payload['title'], author=ns.payload['author'], genre=ns.payload['genre'])
        db.session.add(book)
        db.session.commit()
        return book, 201

@ns.route('/import')
class BookImport(Resource):
    @ns.doc('import_book')
    @ns.expect(import_model)
    @ns.response(200, 'Book had already been imported')
    @ns.marshal_with(book_model, code=201)
    @jwt_required()
    def post(self):
        '''Save a result from /search/external into the catalogue'''
        external_id = ns.payload['external_id']
        existing = Book.query.filter_by(external_id=external_id).first()
        if existing:
            return existing, 200
        genre = ns.payload.get('genre')
        book = Book(
            title=ns.payload['title'][:100],
            author=ns.payload['author'][:100],
            genre=genre[:50] if genre else None,
            external_id=external_id[:64]
        )
        db.session.add(book)
        db.session.commit()
        return book, 201

@ns.route('/<int:id>')
@ns.response(404, 'Book not found')
@ns.param('id', 'The book identifier')
class BookResource(Resource):
    @ns.doc('get_book')
    @ns.marshal_with(book_model)
    def get(self, id):
        '''Fetch a book given its identifier'''
        return Book.query.get_or_404(id)

    @ns.doc('update_book')
    @ns.expect(book_model)
    @ns.marshal_with(book_model)
    @jwt_required()
    def put(self, id):
        '''Update a book given its identifier'''
        book = Book.query.get_or_404(id)
        book.title = ns.payload['title']
        book.author = ns.payload['author']
        book.genre = ns.payload['genre']
        db.session.commit()
        return book

    @ns.doc('delete_book')
    @ns.response(204, 'Book deleted')
    @jwt_required()
    def delete(self, id):
        '''Delete a book given its identifier'''
        book = Book.query.get_or_404(id)
        db.session.delete(book)
        db.session.commit()
        return '', 204