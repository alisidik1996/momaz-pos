import os
import uuid
from pathlib import Path

import aiofiles
import httpx
from fastapi import HTTPException, UploadFile

from app.config import settings

LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "products"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CSV_BYTES = 10 * 1024 * 1024


async def read_bounded_upload(file: UploadFile, limit: int) -> bytes:
    chunks = []
    size = 0
    while True:
        chunk = await file.read(min(64 * 1024, limit + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"Ukuran file melebihi batas {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def _image_content_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(status_code=400, detail="Isi file bukan gambar PNG, JPEG, GIF, atau WEBP.")


async def upload_file_to_blob_or_local(file: UploadFile, folder: str = "products") -> str:
    extension = Path(file.filename or "").suffix.lower()
    expected_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    if extension not in expected_types or folder != "products":
        raise HTTPException(status_code=400, detail="Format atau folder unggahan tidak didukung.")
    content = await read_bounded_upload(file, MAX_IMAGE_BYTES)
    content_type = _image_content_type(content)
    supplied_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if expected_types[extension] != content_type or supplied_type not in {content_type, "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Tipe gambar tidak sesuai dengan isi file.")
    unique_name = f"{uuid.uuid4().hex}{extension}"
    token = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()
    if token:
        headers = {
            "authorization": f"Bearer {token}", "x-api-version": "13",
            "x-vercel-blob-access": "public", "x-content-type": content_type,
            "content-type": content_type,
        }
        store_id = os.getenv("BLOB_STORE_ID", "").strip()
        if store_id:
            headers["x-vercel-blob-store-id"] = store_id
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(
                    "https://blob.vercel-storage.com/",
                    params={"pathname": f"{folder}/{unique_name}"},
                    content=content,
                    headers=headers,
                )
                response.raise_for_status()
                url = response.json().get("url")
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError("Invalid Blob response")
                return url
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="Unggah gambar ke penyimpanan cloud gagal. Silakan coba kembali.") from exc
    if settings.IS_VERCEL:
        raise HTTPException(status_code=503, detail="Penyimpanan gambar cloud belum dikonfigurasi.")
    try:
        LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(LOCAL_UPLOAD_DIR / unique_name, "wb") as output:
            await output.write(content)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Penyimpanan gambar tidak tersedia.") from exc
    return f"/static/uploads/products/{unique_name}"
