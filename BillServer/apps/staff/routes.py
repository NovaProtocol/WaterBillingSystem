from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable

from flask import Response, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from apps import cache
from apps.authentication.forms import LoginForm
from apps.authentication.util import verify_pass
from apps.models import Staff
from apps.staff import api as staff_api  # noqa: F401
from apps.staff import (
    bills,  # noqa: F401
    blueprint,
    customers,  # noqa: F401
    payments,  # noqa: F401
    readings,  # noqa: F401
    staff_mgmt,  # noqa: F401
)
from apps.staff import (
    debug as staff_debug,  # noqa: F401
)


def rate_limit(
    max_attempts: int = 10, window: int = 60
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ip = request.remote_addr or "unknown"
            cache_key = f"rl:login:{ip}"
            attempts: list[float] = cache.get(cache_key) or []
            now = time.time()
            attempts = [t for t in attempts if now - t < window]
            if len(attempts) >= max_attempts:
                return (
                    render_template(
                        "staff/login.html",
                        msg="Too many attempts. Try again in 60 seconds.",
                        form=LoginForm(),
                    ),
                    429,
                )
            attempts.append(now)
            cache.set(cache_key, attempts, timeout=window + 30)
            return f(*args, **kwargs)

        return wrapper

    return decorator


@blueprint.route("/")
def index() -> str:
    return render_template("staff/index.html")


@blueprint.route("/login", methods=["GET", "POST"])
@rate_limit(max_attempts=10, window=60)
def login() -> Response | str:
    login_form = LoginForm()
    if login_form.validate_on_submit():
        staff = Staff.query.filter_by(username=login_form.username.data).first()
        if staff and verify_pass(login_form.password.data, staff.password):
            login_user(staff)
            return redirect(url_for("staff_blueprint.dashboard"))
        return render_template(
            "staff/login.html", msg="Wrong user or password", form=login_form
        )
    if current_user.is_authenticated:
        return redirect(url_for("staff_blueprint.dashboard"))
    return render_template("staff/login.html", form=login_form)


@blueprint.route("/logout")
def logout() -> Response:
    logout_user()
    return redirect(url_for("staff_blueprint.index"))


@blueprint.route("/dashboard")
def dashboard() -> Response | str:
    if not current_user.is_authenticated:
        return redirect(url_for("staff_blueprint.login"))
    return render_template("staff/dashboard.html")
