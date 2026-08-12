'''Create the database schema.

Run once against a deployment's DATABASE_URL. This is deliberately kept out of
create_app(): gunicorn boots several workers, and they would race each other
creating the same tables. create_all() only adds missing tables, so re-running
this is safe, but it never alters an existing table -- schema changes still need
a migration tool.
'''
from app import create_app, db

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
        print('schema created on %s' % app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1])
