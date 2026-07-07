# Authentication Blueprint

Handles staff login/logout and password hashing.

- `routes.py` — Login/logout view redirects
- `forms.py` — Login form
- `util.py` — Password hashing (Werkzeug PBKDF2 + legacy fallback)
