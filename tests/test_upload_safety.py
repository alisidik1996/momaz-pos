import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.core import storage

PNG = bytes.fromhex("89504e470d0a1a0a") + b"review-image"


def image_file(content=PNG, filename="review.png", content_type="image/png"):
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


def test_upload_rejects_oversized_images(monkeypatch):
    monkeypatch.setattr(storage, "MAX_IMAGE_BYTES", 10, raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.save_uploaded_image(image_file(content=PNG + b"x" * 20)))
    assert error.value.status_code == 413


def test_upload_rejects_html_disguised_as_an_image():
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.save_uploaded_image(image_file(b"<html>not an image</html>")))
    assert error.value.status_code == 400


def test_failed_storage_does_not_return_a_fake_data_uri(monkeypatch):
    class UnwritablePath:
        def mkdir(self, *args, **kwargs):
            raise OSError("Simulated read-only filesystem")

    monkeypatch.setattr(storage, "LOCAL_UPLOAD_DIR", UnwritablePath())
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.save_uploaded_image(image_file()))
    assert error.value.status_code == 503
