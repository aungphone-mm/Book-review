# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Flask + Flask-RESTX JSON API for books, reviews, users, and search. `render.yaml` is the intended API deployment path — as of 2026-08-12 nothing answers at `book-review-api.onrender.com`, so treat that hostname as unconfirmed rather than live. Despite living under a directory named `node/`, there is no JavaScript build — `web/index.html` is a single standalone browser client, served by the API itself at `/app`.

## Endpoints

All four namespaces from `app/__init__.py` now exist under `app/resources/`. Reads are public; writes require `Authorization: Bearer <token>`.

- `books` — `GET/POST /books`, `GET/PUT/DELETE /books/<id>`, `POST /books/import` (saves an Open Library result; returns 200 with the existing row instead of 201 when `external_id` is already present)
- `reviews` — `GET/POST /reviews`, `GET/PUT/DELETE /reviews/<id>`. `GET` takes an optional `?book_id=` filter; `rating` is validated to 1-5; `user_id` is taken from the JWT and never from the payload; `PUT`/`DELETE` return 403 unless the caller authored the review.
- `users` — `POST /users/register` (409 on duplicate username), `POST /users/login` → `{access_token}`, `GET /users/me`
- `search` — `GET /search?q=&title=&author=&genre=` over the local catalogue (no parameters means all books), and `GET /search/external?q=&source=&limit=` which proxies a public catalogue

**External catalogues.** Two sources, dispatched through the `SOURCES` dict in `app/resources/search.py`, both keyless:

- `gutendex` (default) — `https://gutendex.com/books`, Project Gutenberg. Public domain, so results carry a real `download_url`. It has no page-size parameter (always 32 per page), hence the client-side `[:limit]` slice. Authors arrive as `"Dickens, Charles"` and are flipped by `flip_name`; `pick_download` matches format keys by *prefix* because some carry a charset suffix (`"text/plain; charset=utf-8"`).
- `openlibrary` — `https://openlibrary.org/search.json`. Far more titles but metadata only, so `download_url` is always None.

Both mappers truncate to the `Book` column widths: Postgres rejects overlong values where SQLite silently accepted them. `external_id` is namespaced `"<source>:<id>"` so the two catalogues cannot collide. Nothing persists until `POST /books/import`, which dedupes on `Book.external_id` (nullable + unique, so hand-entered books coexist). Upstream failures return 502 rather than hanging — every call has a 10s timeout.

JWT identity is stored as `str(user.id)` and read back with `int(get_jwt_identity())`, because flask-jwt-extended rejects a non-string `sub` claim from 4.6 onwards.

## Commands

No virtualenv, test suite, or linter is configured in this repo. On this machine `python`/`python -m pip` are both Python 3.10 (a bare `pip` may resolve to a different 3.12 Store install — always use `python -m pip`).

```bash
python -m pip install -r requirements.txt
python run.py                               # local dev server on :5000, debug=True
python init_db.py                           # create tables against $DATABASE_URL
gunicorn run:app                            # production entrypoint (what Render runs)
```

Swagger UI is served at `/` by Flask-RESTX once the app boots; the browser client is at `/app`.

Dependencies were bumped to Flask 3 / Flask-SQLAlchemy 3.1 / flask-restx 1.3 for deployment. `Flask-RESTful` was dropped — nothing imported it and it blocked the Flask 3 upgrade.

## Architecture

**App factory + module-level extension singletons.** `db`, `jwt`, and `api` are constructed at import time in `app/__init__.py` and bound to the app inside `create_app()`. Models import `db` from `app`, resources import `db` from `app` and models from `app.models` — so nothing may import `create_app` at module scope or you get a cycle.

**Adding a resource** follows the pattern in `app/resources/book.py`: declare `ns = Namespace('<name>', ...)`, define an `ns.model(...)` for marshalling, decorate `Resource` methods with `@ns.marshal_with` / `@ns.expect`, then register the namespace in `create_app()`. Registration is manual — a new file alone does nothing.

**Auth** is JWT via `flask_jwt_extended`, issued by `POST /users/login`. Convention throughout: reads are public, writes are `@jwt_required()`, and the decorator sits *innermost* (below `@ns.expect`/`@ns.marshal_with`) so authorization runs before marshalling. `User` in `app/models.py` provides `set_password`/`check_password` over werkzeug hashes.

**Schema creation is deliberately out of the app.** `db.create_all()` runs in `run.py`'s `__main__` guard (local only) and in `init_db.py` (deployments). It is kept out of `create_app()` on purpose — gunicorn boots several workers and they would race creating the same tables. There are no migrations (no Flask-Migrate/Alembic), so `create_all()` adds missing tables but never alters existing ones.

**Database** is `DATABASE_URL`, falling back to SQLite only for local dev. `config.py` rewrites the `postgres://` prefix Render hands out to `postgresql://`, which SQLAlchemy 1.4+ requires. When `RENDER=true`, a missing `DATABASE_URL`, `SECRET_KEY`, or `JWT_SECRET_KEY` raises at startup rather than silently using a dev fallback.

**`web/index.html`** is served at `/app` by a plain `@app.route` in `create_app()` — Flask-RESTX owns `/` for Swagger, so the client cannot live there. `WEB_DIR` is built from `__file__` because `web/` sits beside `app/`, and `send_from_directory` resolves relative paths against the package directory instead. The page has register, login, add-book, external-search-with-import, and a book list.

`API_URL` at the top of its script block is `''` — same-origin, so the page follows the API to whatever host it lands on. Set it to an absolute URL only to open the file straight from disk. CORS stays open app-wide via `flask_cors` even though same-origin no longer needs it.

Every request goes through the `apiFetch` wrapper, which reveals a "still working" banner after 2s. Two separate things trigger it: a free-tier host waking from idle, and an ordinary `/search/external` call — Gutendex and Open Library both routinely take several seconds. Failures render into a per-form `.status` element; there are no `alert()` boxes.

## Deployment (Render)

`render.yaml` is a Render blueprint: free Postgres, free web service, `init_db.py` in the build command, `gunicorn run:app` as the start command, and `SECRET_KEY`/`JWT_SECRET_KEY` generated by Render rather than stored here.

`app.yaml` is the older Google App Engine config and is no longer the deployment path. **Its committed `SECRET_KEY`/`JWT_SECRET_KEY` values are burned — never reuse them.**

## Configuration

`config.py` reads `SECRET_KEY`, `DATABASE_URL`, and `JWT_SECRET_KEY` from the environment with insecure literal fallbacks. `app.yaml` hardcodes real-looking `SECRET_KEY` and `JWT_SECRET_KEY` values in `env_variables` — these are committed in plaintext and should be rotated and moved to Secret Manager rather than propagated.
