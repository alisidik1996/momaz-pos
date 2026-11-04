import asyncio
import io

import pytest
import httpx
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.core import storage

PNG = bytes.fromhex("89504e470d0a1a0a") + b"review-image"


def image_file(content=PNG, filename="review.png", content_type="image/png"):
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


def test_upload_rejects_oversized_images(monkeypatch):
    monkeypatch.setattr(storage, "MAX_IMAGE_BYTES", 10, raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.upload_file_to_blob_or_local(image_file(content=PNG + b"x" * 20)))
    assert error.value.status_code == 413


def test_upload_rejects_html_disguised_as_an_image():
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.upload_file_to_blob_or_local(image_file(b"<html>not an image</html>")))
    assert error.value.status_code == 400


def test_failed_storage_does_not_return_a_fake_data_uri(monkeypatch):
    class UnwritablePath:
        def mkdir(self, *args, **kwargs):
            raise OSError("Simulated read-only filesystem")

    monkeypatch.setattr(storage, "LOCAL_UPLOAD_DIR", UnwritablePath())
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.upload_file_to_blob_or_local(image_file()))
    assert error.value.status_code == 503


def test_blob_upload_uses_the_v13_pathname_and_content_type_contract(monkeypatch):
    real_client = httpx.AsyncClient
    received = {}

    def handler(request):
        received["path"] = request.url.path
        received["pathname"] = request.url.params.get("pathname")
        received["content_type"] = request.headers.get("x-content-type")
        return httpx.Response(200, json={"url": "https://review.public.blob.vercel-storage.com/products/review.png"})

    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "review-only-placeholder")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(storage.upload_file_to_blob_or_local(image_file()))
    assert result.startswith("https://review.public.blob.vercel-storage.com/")
    assert received["path"] == "/"
    assert received["pathname"].startswith("products/")
    assert received["content_type"] == "image/png"


def test_blob_failure_returns_an_error_instead_of_local_success(monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"error": "private details"}))
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "review-only-placeholder")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.upload_file_to_blob_or_local(image_file()))
    assert error.value.status_code == 502
