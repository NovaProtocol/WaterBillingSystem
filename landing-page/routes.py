from __future__ import annotations

from data import MODELS
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from templating import templates

router = APIRouter()

MODEL_TEMPLATES: dict[str, str] = {
    "aspen": "landing/models/aspen.html",
    "birch": "landing/models/birch.html",
    "cedar": "landing/models/cedar.html",
    "dogwood": "landing/models/dogwood.html",
    "elm": "landing/models/elm.html",
    "fern": "landing/models/fern.html",
    "hazel": "landing/models/hazel.html",
    "iris": "landing/models/iris.html",
    "juniper": "landing/models/juniper.html",
}

for _slug in MODELS:
    MODELS[_slug]["photos"] = []


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
