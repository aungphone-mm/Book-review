from flask import request
from flask_restx import Resource, Namespace, fields, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Book, Review
from app import db

ns = Namespace('reviews', description='Review operations')

RATING_MIN = 1
RATING_MAX = 5

review_model = ns.model('Review', {
    'id': fields.Integer(readonly=True),
    'content': fields.String(required=True),
    'rating': fields.Integer(required=True, min=RATING_MIN, max=RATING_MAX),
    'book_id': fields.Integer(required=True),
    'user_id': fields.Integer(readonly=True)
})

def check_rating(rating):
    '''Reject anything outside the 1-5 range before it reaches the database'''
    if not isinstance(rating, int) or isinstance(rating, bool) or not RATING_MIN <= rating <= RATING_MAX:
        abort(400, 'rating must be an integer between %d and %d' % (RATING_MIN, RATING_MAX))
    return rating

def owned_review_or_403(id):
    review = Review.query.get_or_404(id)
    if review.user_id != int(get_jwt_identity()):
        abort(403, 'Not the author of this review')
    return review

@ns.route('')
class ReviewList(Resource):
    @ns.doc('list_reviews', params={'book_id': 'Only return reviews of this book'})
    @ns.marshal_list_with(review_model)
    def get(self):
        '''List all reviews, optionally filtered to a single book'''
        book_id = request.args.get('book_id', type=int)
        if book_id is not None:
            return Book.query.get_or_404(book_id).reviews.all()
        return Review.query.all()

    @ns.doc('create_review')
    @ns.expect(review_model)
    @ns.response(400, 'Invalid rating')
    @ns.response(404, 'Book not found')
    @ns.marshal_with(review_model, code=201)
    @jwt_required()
    def post(self):
        '''Review a book as the authenticated user'''
        book = Book.query.get_or_404(ns.payload['book_id'])
        review = Review(
            content=ns.payload['content'],
            rating=check_rating(ns.payload['rating']),
            book_id=book.id,
            user_id=int(get_jwt_identity())
        )
        db.session.add(review)
        db.session.commit()
        return review, 201

@ns.route('/<int:id>')
@ns.response(404, 'Review not found')
@ns.param('id', 'The review identifier')
class ReviewResource(Resource):
    @ns.doc('get_review')
    @ns.marshal_with(review_model)
    def get(self, id):
        '''Fetch a review given its identifier'''
        return Review.query.get_or_404(id)

    @ns.doc('update_review')
    @ns.expect(review_model)
    @ns.response(400, 'Invalid rating')
    @ns.response(403, 'Not the author of this review')
    @ns.marshal_with(review_model)
    @jwt_required()
    def put(self, id):
        '''Update a review; only its author may do so'''
        review = owned_review_or_403(id)
        review.content = ns.payload['content']
        review.rating = check_rating(ns.payload['rating'])
        db.session.commit()
        return review

    @ns.doc('delete_review')
    @ns.response(204, 'Review deleted')
    @ns.response(403, 'Not the author of this review')
    @jwt_required()
    def delete(self, id):
        '''Delete a review; only its author may do so'''
        review = owned_review_or_403(id)
        db.session.delete(review)
        db.session.commit()
        return '', 204
