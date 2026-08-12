import requests
from flask import request
from flask_restx import Resource, Namespace, fields, abort
from sqlalchemy import or_
from app.models import Book
from app.resources.book import book_model

ns = Namespace('search', description='Book search')

OPEN_LIBRARY_URL = 'https://openlibrary.org/search.json'
OPEN_LIBRARY_FIELDS = 'key,title,author_name,first_publish_year,cover_i,subject'
MAX_RESULTS = 40

external_book_model = ns.model('ExternalBook', {
    'external_id': fields.String(readonly=True, description='Open Library work key, e.g. /works/OL45804W'),
    'title': fields.String(readonly=True),
    'author': fields.String(readonly=True),
    'genre': fields.String(readonly=True),
    'year': fields.Integer(readonly=True),
    'cover_url': fields.String(readonly=True)
})

def from_open_library(doc):
    '''Map one Open Library search hit onto our own book shape.

    Fields are truncated to the Book column widths: Postgres rejects overlong
    values outright, where SQLite would have silently accepted them.
    '''
    authors = doc.get('author_name') or []
    subjects = doc.get('subject') or []
    cover_id = doc.get('cover_i')
    return {
        'external_id': doc.get('key'),
        'title': (doc.get('title') or 'Untitled')[:100],
        'author': (', '.join(authors) or 'Unknown')[:100],
        'genre': subjects[0][:50] if subjects else None,
        'year': doc.get('first_publish_year'),
        'cover_url': 'https://covers.openlibrary.org/b/id/%s-M.jpg' % cover_id if cover_id else None
    }

@ns.route('')
class BookSearch(Resource):
    @ns.doc('search_books', params={
        'q': 'Substring matched against both title and author',
        'title': 'Substring matched against the title',
        'author': 'Substring matched against the author',
        'genre': 'Exact genre'
    })
    @ns.marshal_list_with(book_model)
    def get(self):
        '''Search books already in the catalogue; with no parameters this returns every book'''
        query = Book.query

        q = request.args.get('q')
        if q:
            pattern = '%{}%'.format(q)
            query = query.filter(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))

        title = request.args.get('title')
        if title:
            query = query.filter(Book.title.ilike('%{}%'.format(title)))

        author = request.args.get('author')
        if author:
            query = query.filter(Book.author.ilike('%{}%'.format(author)))

        genre = request.args.get('genre')
        if genre:
            query = query.filter(Book.genre == genre)

        return query.all()

@ns.route('/external')
class ExternalBookSearch(Resource):
    @ns.doc('search_external_books', params={
        'q': 'Search terms',
        'limit': 'Maximum results, capped at %d (default 10)' % MAX_RESULTS
    })
    @ns.response(400, 'Missing q')
    @ns.response(502, 'Open Library is unreachable')
    @ns.marshal_list_with(external_book_model)
    def get(self):
        '''Search Open Library; nothing is stored until POST /books/import'''
        q = request.args.get('q')
        if not q:
            abort(400, 'q is required')
        limit = min(request.args.get('limit', default=10, type=int) or 10, MAX_RESULTS)
        try:
            response = requests.get(
                OPEN_LIBRARY_URL,
                params={'q': q, 'limit': limit, 'fields': OPEN_LIBRARY_FIELDS},
                timeout=10
            )
            response.raise_for_status()
            docs = response.json().get('docs', [])
        except (requests.RequestException, ValueError):
            abort(502, 'Could not reach Open Library')
        return [from_open_library(doc) for doc in docs]
