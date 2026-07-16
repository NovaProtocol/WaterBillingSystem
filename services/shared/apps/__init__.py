from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
csrf = CSRFProtect()
