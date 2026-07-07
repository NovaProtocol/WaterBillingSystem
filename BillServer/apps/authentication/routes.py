from __future__ import annotations

from flask import Response, redirect, url_for

from apps.authentication import blueprint


@blueprint.route("/login")
def login_redirect() -> Response:
    return redirect(url_for("staff_blueprint.login"))


@blueprint.route("/logout")
def logout_redirect() -> Response:
    return redirect(url_for("staff_blueprint.logout"))
