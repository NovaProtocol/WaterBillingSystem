from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from db_async import sync_session

logger = logging.getLogger('api')


def _run_sync(fn, *args, **kwargs):
    def _call():
        s = sync_session()
        try:
            return fn(*args, session=s, **kwargs)
        finally:
            s.close()

    return run_in_threadpool(_call)


__all__ = ["_run_sync", "logger"]
