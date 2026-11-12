import logging
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import master_engine, MasterBase, get_request_identity, _get_master_unpooled_engine

# Import Routers
from app.modules.tenants.router import router as tenants_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.inventory.router import router as inventory_router
from app.modules.customers.router import router as customers_router
from app.modules.shifts.router import router as shifts_router
from app.modules.sales.router import router as sales_router
from app.modules.returns.router import router as returns_router
from app.modules.reports.router import router as reports_router

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure master database tables exist
    # Di PostgreSQL pakai UNPOOLED engine untuk DDL (CREATE TABLE)
    # Neon pooler tidak mendukung DDL statements
    if settings.DATABASE_URL:
        ddl_engine = _get_master_unpooled_engine()
    else:
        ddl_engine = master_engine
    MasterBase.metadata.create_all(bind=ddl_engine)
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

@app.middleware("http")
async def protect_cookie_mutations(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get("access_token"):
        origin = request.headers.get("Origin")
        if origin and not request.headers.get("Authorization"):
            origin_host = urlsplit(origin).hostname
            request_host = request.url.hostname
            if not origin_host or not request_host or origin_host.lower() != request_host.lower():
                return JSONResponse(status_code=403, content={"detail": "Asal permintaan tidak diizinkan."})
    return await call_next(request)

# Static & Templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Include API Routers
app.include_router(tenants_router)
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(inventory_router)
app.include_router(customers_router)
app.include_router(shifts_router)
app.include_router(sales_router)
app.include_router(returns_router)
app.include_router(reports_router)

# Helper to inspect user from cookie
def get_user_from_cookie(request: Request):
    try:
        identity = get_request_identity(request).copy()
        if identity["tenant_slug"]:
            from app.database import TenantManager
            from app.modules.auth.service import get_user_by_username

            with TenantManager.get_session(identity["tenant_slug"]) as db:
                user = get_user_by_username(db, identity["sub"])
                if user is None or not user.is_active:
                    return None
                identity["role"] = user.role
        return identity
    except HTTPException:
        return None

def get_template_context(request: Request, extra: dict = None) -> dict:
    from app.core.cache import get_cache, set_cache

    ctx = extra.copy() if extra else {}
    user = get_user_from_cookie(request)
    ctx["user"] = user
    store_name = "POS"

    if user and user.get("tenant_slug"):
        # Cache store name per tenant to avoid DB query on every page load
        cache_key = f"store_name:{user['tenant_slug']}"
        cached_name = get_cache(cache_key)

        if cached_name:
            store_name = cached_name
        else:
            try:
                from app.database import TenantManager
                from app.core.models import StoreSettings
                db = TenantManager.get_session(user["tenant_slug"])
                try:
                    s = db.query(StoreSettings).first()
                    if s and s.store_name:
                        store_name = s.store_name
                        set_cache(cache_key, store_name, ttl=600)  # Cache 10 minutes
                finally:
                    db.close()
            except Exception:
                logging.getLogger(__name__).warning("Store name could not be loaded for page context")

    ctx["store_name"] = store_name
    return ctx

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content=b"", media_type="image/x-icon")

# ----------------- Web UI Page Routes -----------------

def check_backoffice_access(request: Request):
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login")
    if not user.get("tenant_slug"):
        return RedirectResponse(url="/setup")
    if user.get("role") == "cashier":
        return RedirectResponse(url="/pos")
    return None

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user = get_user_from_cookie(request)
    if user and user.get("tenant_slug"):
        if user.get("role") == "cashier":
            return RedirectResponse(url="/pos")
        return RedirectResponse(url="/backoffice/dashboard")
    return templates.TemplateResponse(request=request, name="login.html", context={"title": "Login Kasir & Backoffice"})

@app.get("/setup", response_class=HTMLResponse)
def setup_wizard_page(request: Request):
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login")
    if user.get("tenant_slug"):
        return RedirectResponse(url="/backoffice/dashboard")
    return templates.TemplateResponse(request=request, name="setup.html", context={
        "title": "Setup Toko Retail Pakaian",
        "user": user
    })

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login")
    if not user.get("tenant_slug"):
        return RedirectResponse(url="/setup")
    if user.get("role") == "cashier":
        return RedirectResponse(url="/pos")
    return RedirectResponse(url="/pos")

@app.get("/pos", response_class=HTMLResponse)
def pos_interface(request: Request):
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login")
    if not user.get("tenant_slug"):
        return RedirectResponse(url="/setup")
    return templates.TemplateResponse(request=request, name="pos/index.html", context=get_template_context(request))

@app.get("/member-portal", response_class=HTMLResponse)
def member_portal(request: Request):
    """Public member portal - no login required"""
    return templates.TemplateResponse(request=request, name="member_portal.html", context={"title": "Member Portal"})

@app.get("/backoffice", response_class=HTMLResponse)
def backoffice_root(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return RedirectResponse(url="/backoffice/dashboard")

@app.get("/backoffice/dashboard", response_class=HTMLResponse)
def backoffice_dashboard(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/dashboard.html", context=get_template_context(request, {
        "active_page": "dashboard"
    }))

@app.get("/backoffice/products", response_class=HTMLResponse)
def backoffice_products(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/products.html", context=get_template_context(request, {
        "active_page": "products"
    }))

@app.get("/backoffice/inventory", response_class=HTMLResponse)
def backoffice_inventory(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/inventory.html", context=get_template_context(request, {
        "active_page": "inventory"
    }))

@app.get("/backoffice/sales", response_class=HTMLResponse)
def backoffice_sales(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/sales.html", context=get_template_context(request, {
        "active_page": "sales"
    }))

@app.get("/backoffice/shifts", response_class=HTMLResponse)
def backoffice_shifts(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/shifts.html", context=get_template_context(request, {
        "active_page": "shifts"
    }))

@app.get("/backoffice/returns", response_class=HTMLResponse)
def backoffice_returns(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/returns.html", context=get_template_context(request, {
        "active_page": "returns"
    }))

@app.get("/backoffice/members", response_class=HTMLResponse)
@app.get("/backoffice/customers", response_class=HTMLResponse)
def backoffice_members(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/members.html", context=get_template_context(request, {
        "active_page": "members"
    }))

@app.get("/backoffice/reports", response_class=HTMLResponse)
def backoffice_reports(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/reports.html", context=get_template_context(request, {
        "active_page": "reports"
    }))

@app.get("/backoffice/settings", response_class=HTMLResponse)
def backoffice_settings(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/settings.html", context=get_template_context(request, {
        "active_page": "settings"
    }))

@app.get("/backoffice/users", response_class=HTMLResponse)
def backoffice_users(request: Request):
    check = check_backoffice_access(request)
    if check:
        return check
    return templates.TemplateResponse(request=request, name="backoffice/users.html", context=get_template_context(request, {
        "active_page": "users"
    }))
