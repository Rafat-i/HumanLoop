import json
import logging

from starlette.requests import Request

from app.main import unexpected


async def test_unexpected_error_logs_locations_without_private_exception_text(caplog):
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/workers", "headers": []})
    request.state.request_id = "fictional-request-id"
    with caplog.at_level(logging.ERROR, logger="humanloop"):
        try:
            raise RuntimeError("private-password-and-query-parameters")
        except RuntimeError as exc:
            response = await unexpected(request, exc)
    assert response.status_code == 500
    record = json.loads(caplog.records[-1].message)
    assert record["request_id"] == "fictional-request-id"
    assert record["exception_type"] == "RuntimeError"
    assert (
        record["frames"][-1]["function"]
        == "test_unexpected_error_logs_locations_without_private_exception_text"
    )
    assert "private-password" not in caplog.text
    assert "private-password" not in response.body.decode()
