// Backoffice Management Script

// 1. Dashboard Analytics
async function loadDashboard() {
  try {
    const data = await api.get("/api/reports/dashboard");
    
    document.getElementById("stat-today-revenue").innerText = formatRupiah(data.today_revenue);
    document.getElementById("stat-today-orders").innerText = data.today_orders_count;
    document.getElementById("stat-today-profit").innerText = formatRupiah(data.today_gross_profit);
    document.getElementById("stat-low-stock").innerText = data.low_stock_count;

    // Payment methods breakdown
    const pContainer = document.getElementById("payment-breakdown-list");
    if (pContainer) {
      if (Object.keys(data.payment_breakdown).length === 0) {
        pContainer.innerHTML = `<div class="text-muted small text-center py-3">Belum ada transaksi hari ini.</div>`;
      } else {
        pContainer.innerHTML = Object.entries(data.payment_breakdown).map(([method, val]) => `
          <div class="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
            <span class="text-uppercase fw-bold">${method}</span>
            <span class="fw-bold text-primary">${formatRupiah(val)}</span>
          </div>
        `).join("");
      }
    }

    // Top selling items
    const topContainer = document.getElementById("top-items-list");
    if (topContainer) {
      if (data.top_items.length === 0) {
        topContainer.innerHTML = `<div class="text-muted small text-center py-3">Belum ada data penjualan item.</div>`;
      } else {
        topContainer.innerHTML = data.top_items.map((it, idx) => `
          <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
            <div>
              <span class="badge bg-secondary me-2">#${idx + 1}</span>
              <span class="fw-medium">${it.name}</span>
            </div>
            <div>
              <span class="badge bg-primary me-2">${it.qty_sold} pcs</span>
              <span class="text-muted small">${formatRupiah(it.revenue)}</span>
            </div>
          </div>
        `).join("");
      }
    }
  } catch (err) {
    console.error(err);
  }
}

// 2. Products & Matrix Variant Management
let backofficeProductsCache = [];

async function loadBackofficeProducts() {
  try {
    const products = await api.get("/api/catalog/products");
    backofficeProductsCache = products || [];
    const tbody = document.getElementById("products-table-body");
    if (!tbody) return;

    if (products.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">Belum ada produk terdaftar.</td></tr>`;
      return;
    }

    tbody.innerHTML = products.map(p => {
      const catName = p.category ? p.category.name : "-";
      const brandName = p.brand ? p.brand.name : "-";
      const stock = p.stock !== undefined ? p.stock : (p.total_stock || 0);
      const minStock = p.min_stock !== undefined ? p.min_stock : 5;
      const stockBadge = stock <= 0 ? "bg-danger" : (stock <= minStock ? "bg-warning text-dark" : "bg-success");

      const photoHtml = p.image_url
        ? `<img src="${p.image_url}" class="rounded border shadow-sm" style="width: 48px; height: 48px; object-fit: cover;" alt="${p.name}">`
        : `<div class="bg-light border rounded text-center text-muted d-flex align-items-center justify-content-center" style="width: 48px; height: 48px;"><i class="bi bi-box-seam text-secondary fs-5"></i></div>`;

      let priceHtml = `<span class="fw-bold text-dark">${formatRupiah(p.base_price)}</span>`;
      if (p.discount_price && p.discount_price > 0) {
        priceHtml = `
          <div><span class="fw-bold text-danger">${formatRupiah(p.discount_price)}</span></div>
          <small class="text-muted text-decoration-line-through" style="font-size:0.75rem;">${formatRupiah(p.base_price)}</small>
        `;
      }

      return `
        <tr>
          <td>${photoHtml}</td>
          <td>
            <div class="fw-bold">${p.name}</div>
            ${p.discount_price > 0 ? '<span class="badge bg-danger-subtle text-danger" style="font-size:0.7rem;">PROMO</span>' : ''}
          </td>
          <td><code>${p.sku || '-'}</code></td>
          <td><code>${p.barcode || '-'}</code></td>
          <td>
            <span class="badge bg-light text-dark border">${catName}</span>
            <small class="text-muted d-block mt-1">${brandName}</small>
          </td>
          <td>${formatRupiah(p.cost_price || 0)}</td>
          <td>${priceHtml}</td>
          <td><span class="badge ${stockBadge}">${stock} pcs</span></td>
          <td>
            <div class="d-flex flex-wrap gap-1">
              <button class="btn btn-sm btn-outline-success" onclick="openRestockModal(${p.id})" title="Tambah Stok Produk">
                <i class="bi bi-box-arrow-in-down me-1"></i>+ Stok
              </button>
              <button class="btn btn-sm btn-outline-warning" onclick="openEditProductModal(${p.id})" title="Edit Detail Produk">
                <i class="bi bi-pencil me-1"></i>Edit
              </button>
              <button class="btn btn-sm btn-outline-danger" onclick="deleteProduct(${p.id})" title="Hapus Produk">
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    if (typeof TableManager !== "undefined") {
      TableManager.bind(tbody.closest("table"));
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteProduct(productId) {
  const ok = await showAppConfirm("Apakah Anda yakin ingin menghapus produk pakaian ini dari katalog?", "Konfirmasi Hapus Produk", {
    confirmText: "Ya, Hapus Produk",
    confirmBtnClass: "btn-danger"
  });
  if (!ok) return;
  try {
    await api.delete(`/api/catalog/products/${productId}`);
    showToast("Produk berhasil dihapus.", "success");
    loadBackofficeProducts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// 3. Inventory & Stock In
async function loadInventoryData() {
  try {
    // Low stock
    const lowStock = await api.get("/api/inventory/low-stock");
    const lowTbody = document.getElementById("low-stock-table-body");
    if (lowTbody) {
      if (lowStock.length === 0) {
        lowTbody.innerHTML = `<tr><td colspan="6" class="text-center text-success py-3"><i class="bi bi-check-circle me-1"></i> Semua stok pakaian aman.</td></tr>`;
      } else {
        lowTbody.innerHTML = lowStock.map(it => `
          <tr>
            <td class="fw-bold">${it.product_name}</td>
            <td><span class="badge bg-light text-dark border">${it.category_name || '-'}</span></td>
            <td><code>${it.sku || '-'}</code></td>
            <td><small class="text-muted">${it.barcode || '-'}</small></td>
            <td class="fw-bold text-danger">${it.stock} pcs</td>
            <td>Min: ${it.min_stock} pcs</td>
          </tr>
        `).join("");
      }
      if (typeof TableManager !== "undefined") TableManager.bind(lowTbody.closest("table"));
    }

    // Movements ledger
    const movements = await api.get("/api/inventory/movements?limit=100");
    const movTbody = document.getElementById("movements-table-body");
    if (movTbody) {
      if (movements.length === 0) {
        movTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-3">Belum ada mutasi stok.</td></tr>`;
      } else {
        movTbody.innerHTML = movements.map(m => {
          const typeBadge = {
            sale: "bg-danger",
            return: "bg-info",
            restock: "bg-success",
            adjustment: "bg-warning text-dark"
          }[m.movement_type] || "bg-secondary";

          const changeColor = m.change_qty > 0 ? "text-success fw-bold" : "text-danger fw-bold";
          const changePrefix = m.change_qty > 0 ? "+" : "";
          const variantText = m.variant_info ? ` (${m.variant_info})` : "";

          return `
            <tr>
              <td><small>${formatDate(m.created_at)}</small></td>
              <td class="fw-medium">${m.product_name || 'Produk'}${variantText}</td>
              <td><span class="badge ${typeBadge}">${m.movement_type.toUpperCase()}</span></td>
              <td class="${changeColor}">${changePrefix}${m.change_qty}</td>
              <td class="fw-bold">${m.current_stock}</td>
              <td><small>${m.reference || '-'}</small></td>
              <td><small class="text-muted">${m.note || '-'}</small></td>
            </tr>
          `;
        }).join("");
      }
      if (typeof TableManager !== "undefined") TableManager.bind(movTbody.closest("table"));
    }
  } catch (err) {
    console.error(err);
  }
}

// 4. Sales History & Return
async function loadSalesHistory() {
  try {
    const orders = await api.get("/api/sales/orders?limit=100");
    const tbody = document.getElementById("sales-table-body");
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">Belum ada transaksi penjualan.</td></tr>`;
      return;
    }

    tbody.innerHTML = orders.map(o => `
      <tr>
        <td class="fw-bold"><code>${o.invoice_number}</code></td>
        <td>${formatDate(o.created_at)}</td>
        <td>${o.cashier_name || '-'}</td>
        <td>${o.customer_name || 'Umum'}</td>
        <td><span class="badge bg-light text-dark border">${o.payment_method.toUpperCase()}</span></td>
        <td class="fw-bold text-primary">${formatRupiah(o.total_amount)}</td>
        <td>
          <button class="btn btn-sm btn-outline-primary me-1" onclick="viewReceipt(${o.id})">
            <i class="bi bi-printer me-1"></i> Struk
          </button>
        </td>
      </tr>
    `).join("");

    if (typeof TableManager !== "undefined") TableManager.bind(tbody.closest("table"));
  } catch (err) {
    console.error(err);
  }
}

// 5. Returns / Exchanges
async function loadReturnsHistory() {
  try {
    const returns = await api.get("/api/returns?limit=50");
    const tbody = document.getElementById("returns-table-body");
    if (!tbody) return;

    if (returns.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">Belum ada riwayat retur/tukar pakaian.</td></tr>`;
      return;
    }

    tbody.innerHTML = returns.map(r => `
      <tr>
        <td class="fw-bold"><code>${r.return_number}</code></td>
        <td><code>${r.invoice_number}</code></td>
        <td>${formatDate(r.created_at)}</td>
        <td><span class="badge bg-warning text-dark">${r.reason.replace('_', ' ').toUpperCase()}</span></td>
        <td>${r.exchange_variant_info ? `<span class="badge bg-success">Tukar: ${r.exchange_variant_info}</span>` : '<span class="text-muted">Retur Saja</span>'}</td>
        <td>${formatRupiah(r.total_refund_amount)}</td>
        <td><small class="text-muted">${r.notes || '-'}</small></td>
      </tr>
    `).join("");

    if (typeof TableManager !== "undefined") TableManager.bind(tbody.closest("table"));
  } catch (err) {
    console.error(err);
  }
}

// 6. Settings
async function loadSettingsForm() {
  try {
    const s = await api.get("/api/settings");
    document.getElementById("set-store-name").value = s.store_name || "";
    document.getElementById("set-tagline").value = s.tagline || "";
    document.getElementById("set-address").value = s.address || "";
    document.getElementById("set-phone").value = s.phone || "";
    document.getElementById("set-email").value = s.email || "";
    document.getElementById("set-footer").value = s.receipt_footer || "";
    document.getElementById("set-return-days").value = s.return_policy_days || 3;
    document.getElementById("set-tax-rate").value = s.tax_rate || 11;
    document.getElementById("set-tax-enabled").checked = s.is_tax_enabled || false;
  } catch (err) {
    console.error(err);
  }
}

async function submitSettings() {
  const payload = {
    store_name: document.getElementById("set-store-name").value,
    tagline: document.getElementById("set-tagline").value,
    address: document.getElementById("set-address").value,
    phone: document.getElementById("set-phone").value,
    email: document.getElementById("set-email").value,
    receipt_footer: document.getElementById("set-footer").value,
    return_policy_days: parseInt(document.getElementById("set-return-days").value) || 3,
    tax_rate: parseFloat(document.getElementById("set-tax-rate").value) || 0,
    is_tax_enabled: document.getElementById("set-tax-enabled").checked
  };

  try {
    await api.put("/api/settings", payload);
    if (payload.store_name) {
      document.querySelectorAll(".app-store-name").forEach(el => {
        el.innerText = payload.store_name;
      });
    }
    showToast("Pengaturan toko berhasil disimpan!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}
