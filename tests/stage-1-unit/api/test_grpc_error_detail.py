"""Regression: the gRPC error path must not destroy its own exception.

``grpc.aio.ServicerContext.set_code`` / ``set_details`` are plain synchronous
methods returning ``None``.  Awaiting them raised
``TypeError: object NoneType can't be used in 'await' expression`` *inside* the
``except`` block, so the client received that TypeError text instead of the real
failure — which is why the live log showed nonsense rather than the underlying
``MissingGreenlet``.

This test drives the real servicer through an in-process ``grpc.aio`` server.  On
the pre-fix code the assertion fails with the TypeError detail; after the fix the
marker reaches the client.
"""
import os
import sys

import pytest

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "..")
for _p in (BASE, os.path.join(BASE, "api"), os.path.join(BASE, "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MARKER = "marker: the real cause"


@pytest.mark.asyncio
async def test_error_detail_survives(monkeypatch):
    import grpc
    import grpc.aio as grpc_aio

    import db_async
    import grpc_server
    from shared.proto_gen import billing_pb2, billing_pb2_grpc

    def _boom():
        raise RuntimeError(MARKER)

    monkeypatch.setattr(db_async, "session_factory", _boom)

    server = grpc_aio.server()
    billing_pb2_grpc.add_BillingServiceServicer_to_server(
        grpc_server.BillingServicer(), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc_aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = billing_pb2_grpc.BillingServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as excinfo:
                await stub.GetBillingHistory(
                    billing_pb2.GetBillingHistoryRequest(customer_number=1),
                    metadata=(("x-internal-api-key", os.environ["INTERNAL_API_KEY"]),),
                )
        details = excinfo.value.details()
        assert "await" not in details, (
            "the error path destroyed the real exception: " f"{details!r}"
        )
        assert MARKER in details, f"real cause missing from details: {details!r}"
    finally:
        await server.stop(grace=0)
