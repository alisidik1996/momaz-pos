import os
import uuid
from pathlib import Path
from fastapi import UploadFile

# Local uploads directory fallback
LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "products"

async def upload_file_to_blob_or_local(file: UploadFile, folder: str = "products") -> str:
    """
    Uploads file to Vercel Blob if BLOB_READ_WRITE_TOKEN is configured.
    Otherwise, gracefully saves to local disk in app/static/uploads/products.
    
    Returns:
        The URL string to access the uploaded image (e.g. https://...vercel-storage.com/... or /static/uploads/products/...)
    """
    token = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()
    clean_filename = Path(file.filename).name.replace(" ", "_")
    unique_name = f"{uuid.uuid4().hex[:10]}_{clean_filename}"
    file_bytes = await file.read()

    # 1. Cloud Storage: Vercel Blob REST API
    if token:
        try:
            import httpx
            pathname = f"{folder}/{unique_name}"
            # Vercel Blob Put API endpoint
            blob_url = f"https://blob.vercel-storage.com/{pathname}?access=public"
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.put(
                    blob_url,
                    content=file_bytes,
                    headers={
                        "authorization": f"Bearer {token}",
                        "x-api-version": "13",
                        "content-type": file.content_type or "application/octet-stream",
                        "x-vercel-blob-access": "public"
                    }
                )
                if res.status_code in [200, 201]:
                    data = res.json()
                    if data.get("url"):
                        return data["url"]
                else:
                    print(f"Vercel Blob upload response status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Vercel Blob upload failed (falling back to local if possible): {e}")

    # 2. Local Fallback (Local Development & Unit Tests)
    try:
        LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target_path = LOCAL_UPLOAD_DIR / unique_name
        with open(target_path, "wb") as f:
            f.write(file_bytes)
        return f"/static/uploads/{folder}/{unique_name}"
    except Exception as e:
        # In serverless environments where local filesystem might be read-only,
        # return a simulated data URI or placeholder if both fail
        import base64
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        mime = file.content_type or "image/jpeg"
        return f"data:{mime};base64,{b64}"
