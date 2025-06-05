from webapp.main import app

if __name__ == "__main__":
    # This is typically not run directly by Gunicorn,
    # but can be useful for some WSGI servers or local testing setup.
    # Gunicorn will usually be pointed to `webapp.wsgi:app` or `webapp.main:app`.
    app.run() 