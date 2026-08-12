import requests
from flask import request
from flask_restx import Resource, Namespace, fields, abort
from sqlalchemy import or_
from app.models import Book
from app.resources.book import book_model

ns = Namespace('search', description='Book search')

OPEN_LIBRARY_URL = 'https://openlibrary.org/search.json'
OPEN_LIBRARY_FIELDS = 'key,title,author_name,first_publish_year,cover_i,subject'
GUTENDEX_URL = 'https://gutendex.com/books'
# ordered by how pleasant the format is to read; the first hit wins
DOWNLOAD_FORMATS = ('application/epub+zip', 'text/html', 'text/plain')
DEFAULT_SOURCE = 'gutendex'
MAX_RESULTS = 40

external_book_model = ns.model('ExternalBook', {
    'external_id': fields.String(readonly=True, description='"<source>:<id>", unique across both sources'),
    'source': fields.String(readonly=True),
    'title': fields.String(readonly=True),
    'author': fields.String(readonly=True),
    'genre': fields.String(readonly=True),
    'year': fields.Integer(readonly=True),
    'cover_url': fields.String(readonly=True),
    'download_url': fields.String(readonly=True, description='Null unless the book is public domain')
})

def fetch_json(url, params):
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        abort(502, 'Could not reach %s' % url)

def pick_download(formats):
    '''Choose the nicest available download.

    Matching is by prefix because Gutendex appends a charset to some keys,
    e.g. "text/plain; charset=utf-8".
    '''
    for wanted in DOWNLOAD_FORMATS:
        for mime, url in formats.items():
            if mime.startswith(wanted):
                return url
    return None

def flip_name(name):
    '''Gutendex stores authors as "Dickens, Charles"'''
    if ', ' in name:
        family, _, given = name.partition(', ')
        return '%s %s' % (given, family)
    return name

def from_gutendex(doc):
    authors = [flip_name(a.get('name', '')) for a in doc.get('authors') or []]
    subjects = doc.get('subjects') or []
    formats = doc.get('formats') or {}
    return {
        'external_id': 'gutendex:%s' % doc.get('id'),
        'source': 'gutendex',
        'title': (doc.get('title') or 'Untitled')[:100],
        'author': (', '.join(a for a in authors if a) or 'Unknown')[:100],
        'genre': subjects[0][:50] if subjects else None,
        'year': None,
        'cover_url': (formats.get('image/jpeg') or '')[:255] or None,
        'download_url': (pick_download(formats) or '')[:255] or None
    }

def from_open_library(doc):
    authors = doc.get('author_name') or []
    subjects = doc.get('subject') or []
    cover_id = doc.get('cover_i')
    return {
        'external_id': ('openlibrary:%s' % doc.get('key'))[:64],
        'source': 'openlibrary',
        'title': (doc.get('title') or 'Untitled')[:100],
        'author': (', '.join(authors) or 'Unknown')[:100],
        'genre': subjects[0][:50] if subjects else None,
        'year': doc.get('first_publish_year'),
        'cover_url': 'https://covers.openlibrary.org/b/id/%s-M.jpg' % cover_id if cover_id else None,
        # Open Library indexes books it cannot hand out; only Gutenberg downloads
        'download_url': None
    }

def search_gutendex(q, limit):
    # Gutendex has no page-size parameter, it always returns 32 per page
    payload = fetch_json(GUTENDEX_URL, {'search': q})
    return [from_gutendex(doc) for doc in (payload.get('results') or [])[:limit]]

def search_open_library(q, limit):
    payload = fetch_json(OPEN_LIBRARY_URL, {'q': q, 'limit': limit, 'fields': OPEN_LIBRARY_FIELDS})
    return [from_open_library(doc) for doc in payload.get('docs') or []]

SOURCES = {'gutendex': search_gutendex, 'openlibrary': search_open_library}

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
        'source': 'gutendex (downloadable public domain, the default) or openlibrary (metadata only)',
        'limit': 'Maximum results, capped at %d (default 10)' % MAX_RESULTS
    })
    @ns.response(400, 'Missing q, or unknown source')
    @ns.response(502, 'The upstream catalogue is unreachable')
    @ns.marshal_list_with(external_book_model)
    def get(self):
        '''Search a public book catalogue; nothing is stored until POST /books/import'''
        q = request.args.get('q')
        if not q:
            abort(400, 'q is required')
        source = request.args.get('source', DEFAULT_SOURCE)
        if source not in SOURCES:
            abort(400, 'source must be one of: %s' % ', '.join(sorted(SOURCES)))
        limit = min(request.args.get('limit', default=10, type=int) or 10, MAX_RESULTS)
        return SOURCES[source](q, limit)
