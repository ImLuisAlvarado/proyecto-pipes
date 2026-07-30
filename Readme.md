# Restaurante POS Backend

This project is a Flask API for a restaurant POS backend.

## Render deployment

A Render deployment configuration is included in [render.yaml](render.yaml).

### What it deploys
- One web service for the Flask API
- One managed PostgreSQL database
- A health check at /health
- A printer simulator UI exposed at the service root `/`

### Deploy steps
1. Create a new Render Blueprint from this repository.
2. Render will create the PostgreSQL database and wire DATABASE_URL automatically.
3. The service uses `gunicorn --workers 1 --bind 0.0.0.0:$PORT wsgi:app` as the startup command.
4. Set `JWT_SECRET` in Render if you want to override the default development token secret.

The app will create its database tables on startup when connected to Postgres.
