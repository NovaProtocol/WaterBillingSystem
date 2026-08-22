from __future__ import annotations

import os

from data import MODELS
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from templating import templates

from shared.config import shared_static_dir

router = APIRouter()

MODEL_TEMPLATES: dict[str, str] = {
    "catherine-4": "landing/models/catherine-4.html",
    "bernice-4": "landing/models/bernice-4.html",
    "tristen": "landing/models/tristen.html",
    "sophia": "landing/models/sophia.html",
    "margarette-2": "landing/models/margarette-2.html",
    "claire-2": "landing/models/claire-2.html",
    "amelia-3": "landing/models/amelia-3.html",
    "scarlet": "landing/models/scarlet.html",
    "lucia": "landing/models/lucia.html",
}

_IMAGE_DIR = os.path.join(shared_static_dir(), "landing", "img")

_FOLDERS = {
    "catherine-4": "catherine",
    "bernice-4": "bernice",
    "tristen": "tristen",
    "sophia": "sophia",
    "margarette-2": "margarette",
    "claire-2": "claire",
    "amelia-3": "amelia",
    "scarlet": "scarlet",
    "lucia": "lucia",
}


def _scan_photos(slug: str) -> list[str]:
    """List photos for a model folder; 1.jpg first, then the rest sorted."""
    folder = os.path.join(_IMAGE_DIR, _FOLDERS.get(slug, slug))
    if not os.path.isdir(folder):
        return []
    photos = sorted(
        f
        for f in os.listdir(folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png")) and not f.startswith(".")
    )
    photos.sort(key=lambda f: (f != "1.jpg", f))
    return [f"{_FOLDERS.get(slug, slug)}/{f}" for f in photos]


for _slug in MODELS:
    MODELS[_slug]["photos"] = _scan_photos(_slug)


@router.get("/offerings")
async def offerings(request: Request):
    return templates.TemplateResponse(request, "landing/offerings.html", {"models": MODELS})


@router.get("/offerings/{slug}")
async def model_detail(slug: str, request: Request):
    template = MODEL_TEMPLATES.get(slug)
    model = MODELS.get(slug)
    if not template or not model:
        raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse(
        request,
        template,
        {
            "models": MODELS,
            "current_slug": slug,
            "model": model,
        },
    )


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "landing/index.html", {"models": MODELS})


@router.post("/")
async def index_post(request: Request):
    try:
        form = await request.form()
    except Exception:
        form = {}
    customer_number = str(form.get("customer_number", "") or "").strip()
    last_receipt = str(form.get("last_receipt", "") or "").strip()

    if not customer_number:
        return templates.TemplateResponse(
            request,
            "landing/index.html",
            {"models": MODELS, "modal_error": "Customer number is required."},
        )

    try:
        return RedirectResponse(
            f"/customer/login?account_number={int(customer_number)}", status_code=302
        )
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            request,
            "landing/index.html",
            {"models": MODELS, "modal_error": "Customer number is required."},
        )
