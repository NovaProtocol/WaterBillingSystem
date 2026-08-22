import logging
import os

from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from shared.config import shared_templates_dir

logger = logging.getLogger("developer-portal")

DEBUG_ENABLED = os.environ["DEBUG"].lower() in ("true", "1", "yes")


def _reverse_url(name: str, **params) -> str:
    import routes as _routes_module

    for route in _routes_module.router.routes:
        if getattr(route, "name", None) == name:
            path = route.path_format
            for k, v in params.items():
                path = path.replace("{" + k + "}", str(v))
            return path
    raise RuntimeError(f"url_for: unknown endpoint {name!r} (typo or unregistered route)")


templates_env = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
            FileSystemLoader(shared_templates_dir()),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
)
templates_env.globals["url_for"] = _reverse_url
templates_env.globals["config"] = {"DEBUG_ENABLED": DEBUG_ENABLED}
templates = Jinja2Templates(env=templates_env)
