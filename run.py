import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print(">> MOMAZ POS - RETAIL APPAREL (MULTI-TENANT MONOLITH)")
    print(">> Port              : 8181")
    print(">> URL Login/Daftar  : http://localhost:8181/login")
    print(">> URL POS Kasir     : http://localhost:8181/pos")
    print(">> URL Backoffice    : http://localhost:8181/backoffice/dashboard")
    print(">> Master Database   : master.db")
    print(">> Tenants Directory : tenants/")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8181, reload=True)
