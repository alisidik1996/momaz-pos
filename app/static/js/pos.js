// Momaz POS Cashier Logic (Retail Toko Pakaian)

let currentShift = null;
let currentProducts = [];
let cart = [];
let currentCustomer = null;
let activeMember = null;
let orderDiscount = 0;
let storeTaxRate = 0;
let isTaxEnabled = false;
let html5QrCodeScanner = null;
let isScannerRunning = false;

document.addEventListener("DOMContentLoaded", async () => {
  await initShiftCheck();
  await loadStoreSettings();
  await loadCategories();
  await loadProducts();
  await loadCustomersList();
  setupKeyboardShortcuts();
  setupBarcodeScanner();
});

// 1. Shift Management
async function initShiftCheck() {
  try {
    const shift = await api.get("/api/shifts/current");
    currentShift = shift;
    updateShiftUI();
    if (!currentShift) {
      // Prompt open shift modal
      const modal = new bootstrap.Modal(document.getElementById("openShiftModal"));
      modal.show();
    }
  } catch (e) {
    console.error("Gagal memeriksa shift:", e);
  }
}

function updateShiftUI() {
  const badge = document.getElementById("shift-status-badge");
  if (!badge) return;
  if (currentShift && currentShift.status === "open") {
    badge.className = "badge bg-success";
    badge.innerHTML = `<i class="bi bi-person-check me-1"></i> Shift Aktif (#${currentShift.id}) - Modal: ${formatRupiah(currentShift.starting_cash)}`;
    badge.style.cursor = "pointer";
    badge.onclick = openCloseShiftModal;
  } else {
    badge.className = "badge bg-danger";
    badge.innerHTML = `<i class="bi bi-exclamation-triangle me-1"></i> Shift Belum Buka`;
    badge.style.cursor = "pointer";
    badge.onclick = () => {
      new bootstrap.Modal(document.getElementById("openShiftModal")).show();
    };
  }
}

async function submitOpenShift() {
  const startCashInput = document.getElementById("open-shift-cash");
  const noteInput = document.getElementById("open-shift-note");
  const startingCash = parseFloat(startCashInput.value) || 0;

  try {
    const res = await api.post("/api/shifts/open", {
      starting_cash: startingCash,
      note: noteInput.value
    });
    currentShift = res;
    updateShiftUI();
    bootstrap.Modal.getOrCreateInstance(document.getElementById("openShiftModal")).hide();
    showToast("Shift kasir berhasil dibuka. Selamat bertugas!", "success");
    posSound.success();
  } catch (err) {
    showToast(err.message, "error");
    posSound.error();
  }
}

function openCloseShiftModal() {
  if (!currentShift) return;
  document.getElementById("close-shift-expected").innerText = formatRupiah(currentShift.ending_cash_expected);
  document.getElementById("close-shift-sales-cash").innerText = formatRupiah(currentShift.total_sales_cash);
  document.getElementById("close-shift-sales-noncash").innerText = formatRupiah(currentShift.total_sales_non_cash);
  
  const modal = new bootstrap.Modal(document.getElementById("closeShiftModal"));
  modal.show();
}

async function submitCloseShift() {
  const actualCashInput = document.getElementById("close-shift-actual");
  const noteInput = document.getElementById("close-shift-note");
  const actualCash = parseFloat(actualCashInput.value);

  if (isNaN(actualCash)) {
    showToast("Masukkan jumlah uang tunai fisik di laci kasir.", "warning");
    return;
  }

  try {
    const res = await api.post(`/api/shifts/${currentShift.id}/close`, {
      ending_cash_actual: actualCash,
      note: noteInput.value
    });
    
    bootstrap.Modal.getOrCreateInstance(document.getElementById("closeShiftModal")).hide();
    currentShift = null;
    updateShiftUI();
    
    let diffMsg = `Selisih kas: ${formatRupiah(res.cash_difference)}`;
    if (res.cash_difference === 0) diffMsg += " (Kas Sempurna / Pas)";
    else if (res.cash_difference < 0) diffMsg += " (Kas Kurang)";
    else diffMsg += " (Kas Lebih)";
    
    await showAppAlert(
      `Kas Diharapkan: ${formatRupiah(res.ending_cash_expected)}\nKas Aktual Fisik: ${formatRupiah(res.ending_cash_actual)}\n${diffMsg}`,
      "Shift Kasir Resmi Ditutup!",
      "success"
    );
    window.location.reload();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// 2. Load Store Settings
async function loadStoreSettings() {
  try {
    const s = await api.get("/api/settings");
    if (s.store_name) {
      document.querySelectorAll(".app-store-name").forEach(el => {
        el.innerText = s.store_name;
      });
      document.title = `Kasir - ${s.store_name}`;
    }
    if (s.is_tax_enabled) {
      storeTaxRate = s.tax_rate || 0;
      isTaxEnabled = true;
    }
  } catch (e) {
    console.error(e);
  }
}

// 3. Catalog & Products
async function loadCategories() {
  try {
    const cats = await api.get("/api/catalog/categories");
    const container = document.getElementById("category-filters");
    if (!container) return;
    
    container.innerHTML = `<button class="btn btn-outline-primary active" onclick="filterCategory(null, this)">Semua Pakaian</button>`;
    cats.forEach(c => {
      container.innerHTML += `<button class="btn btn-outline-secondary" onclick="filterCategory(${c.id}, this)">${c.name}</button>`;
    });
  } catch (e) {
    console.error(e);
  }
}

async function loadProducts(query = "", categoryId = null) {
  try {
    let url = "/api/catalog/products?";
    if (query) url += `q=${encodeURIComponent(query)}&`;
    if (categoryId) url += `category_id=${categoryId}&`;
    
    currentProducts = await api.get(url);
    renderProducts(currentProducts);
  } catch (e) {
    console.error(e);
  }
}

function renderProducts(products) {
  const container = document.getElementById("pos-product-grid");
  if (!container) return;

  if (products.length === 0) {
    container.innerHTML = `<div class="col-12 text-center text-muted py-5"><i class="bi bi-inbox fs-1 d-block mb-2"></i>Tidak ada produk ditemukan.</div>`;
    return;
  }

  container.innerHTML = products.map(p => {
    const stock = p.stock !== undefined ? p.stock : (p.total_stock || 0);
    const minStock = p.min_stock !== undefined ? p.min_stock : 5;
    const stockClass = stock <= 0 ? "bg-danger" : (stock <= minStock ? "bg-warning text-dark" : "bg-success");
    const categoryName = p.category ? p.category.name : "Umum";

    const imageHtml = p.image_url
      ? `<img src="${p.image_url}" style="height: 100px; width: 100%; object-fit: cover; border-radius: 8px; margin-bottom: 0.75rem;" alt="${p.name}">`
      : `<div class="img-placeholder"><i class="bi bi-bag-check"></i></div>`;

    let priceDisplay = `<span class="price">${formatRupiah(p.base_price)}</span>`;
    if (p.discount_price && p.discount_price > 0) {
      priceDisplay = `
        <div>
          <span class="price text-danger">${formatRupiah(p.discount_price)}</span>
          <small class="text-muted text-decoration-line-through d-block" style="font-size:0.75rem;">${formatRupiah(p.base_price)}</small>
        </div>
      `;
    }

    return `
      <div class="product-card" onclick="handleProductClick(${p.id})">
        <div>
          ${imageHtml}
          <div class="d-flex justify-content-between align-items-center mb-1">
            <span class="badge bg-light text-secondary border">${categoryName}</span>
            ${p.discount_price > 0 ? '<span class="badge bg-danger">PROMO</span>' : ''}
          </div>
          <h6 class="fw-bold mb-1 text-truncate" title="${p.name}">${p.name}</h6>
          <div class="small text-muted mb-2"><code>${p.sku || p.barcode || '-'}</code></div>
        </div>
        <div class="d-flex justify-content-between align-items-center mt-2 pt-2 border-top">
          ${priceDisplay}
          <span class="badge ${stockClass}">Stok: ${stock}</span>
        </div>
      </div>
    `;
  }).join("");
}

function filterCategory(catId, btnEl) {
  document.querySelectorAll("#category-filters .btn").forEach(b => {
    b.classList.remove("active", "btn-primary");
    b.classList.add("btn-outline-secondary");
  });
  btnEl.classList.add("active", "btn-primary");
  btnEl.classList.remove("btn-outline-secondary");
  loadProducts(document.getElementById("search-input").value, catId);
}

// 4. Product Click -> Direct Add to Cart
function handleProductClick(productId) {
  const product = currentProducts.find(p => p.id === productId);
  if (!product) return;
  addProductToCart(product);
}

function addProductToCart(product) {
  const stock = product.stock !== undefined ? product.stock : (product.total_stock || 0);
  if (stock <= 0) {
    posSound.error();
    showToast(`Stok untuk "${product.name}" telah habis!`, "error");
    return;
  }

  const effectivePrice = (product.discount_price && product.discount_price > 0) ? product.discount_price : product.base_price;
  const existingIndex = cart.findIndex(c => c.product_id === product.id);

  if (existingIndex > -1) {
    if (cart[existingIndex].quantity + 1 > stock) {
      posSound.error();
      showToast(`Maksimal stok tercapai (${stock} pcs).`, "warning");
      return;
    }
    cart[existingIndex].quantity += 1;
    cart[existingIndex].subtotal = (cart[existingIndex].quantity * cart[existingIndex].unit_price) - cart[existingIndex].discount_amount;
  } else {
    cart.push({
      product_id: product.id,
      variant_id: null,
      product_name: product.name,
      variant_info: "",
      sku: product.sku || "-",
      barcode: product.barcode || "-",
      unit_price: effectivePrice,
      cost_price: product.cost_price || 0,
      stock: stock,
      quantity: 1,
      discount_amount: 0,
      subtotal: effectivePrice
    });
  }

  posSound.beep();
  renderCart();
}

// 5. Barcode Scanner Fast Scanning
function setupBarcodeScanner() {
  const barcodeInput = document.getElementById("barcode-scanner-input");
  if (!barcodeInput) return;

  barcodeInput.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const code = barcodeInput.value.trim();
      if (!code) return;

      try {
        const item = await api.get(`/api/catalog/scan/${code}`);
        const effectivePrice = item.sell_price;
        const existingIndex = cart.findIndex(c => (item.product_id && c.product_id === item.product_id) || (item.variant_id && c.variant_id === item.variant_id));

        if (existingIndex > -1) {
          if (cart[existingIndex].quantity + 1 > item.stock) {
            posSound.error();
            showToast(`Maksimal stok tercapai (${item.stock} pcs).`, "warning");
            return;
          }
          cart[existingIndex].quantity += 1;
          cart[existingIndex].subtotal = (cart[existingIndex].quantity * cart[existingIndex].unit_price) - cart[existingIndex].discount_amount;
        } else {
          cart.push({
            product_id: item.product_id,
            variant_id: item.variant_id,
            product_name: item.product_name,
            variant_info: "",
            sku: item.sku,
            barcode: item.barcode,
            unit_price: effectivePrice,
            cost_price: item.cost_price,
            stock: item.stock,
            quantity: 1,
            discount_amount: 0,
            subtotal: effectivePrice
          });
        }

        posSound.beep();
        renderCart();
        barcodeInput.value = "";
        barcodeInput.focus();
      } catch (err) {
        posSound.error();
        showToast(err.message, "error");
        barcodeInput.select();
      }
    }
  });
}

// 6. Cart Management
function updateCartQty(id, delta) {
  const item = cart.find(c => c.product_id === id || c.variant_id === id);
  if (!item) return;

  const newQty = item.quantity + delta;
  if (newQty <= 0) {
    removeCartItem(id);
    return;
  }

  if (newQty > item.stock) {
    posSound.error();
    showToast(`Stok maksimal hanya ${item.stock} pcs!`, "warning");
    return;
  }

  item.quantity = newQty;
  item.subtotal = (item.quantity * item.unit_price) - item.discount_amount;
  renderCart();
}

function removeCartItem(id) {
  cart = cart.filter(c => c.product_id !== id && c.variant_id !== id);
  renderCart();
}

async function clearCart() {
  if (cart.length === 0) return;
  const ok = await showAppConfirm("Apakah Anda yakin ingin mengosongkan seluruh keranjang belanja kasir?", "Kosongkan Keranjang", {
    confirmText: "Ya, Kosongkan",
    confirmBtnClass: "btn-danger"
  });
  if (ok) {
    cart = [];
    orderDiscount = 0;
    renderCart();
  }
}

function renderCart() {
  const container = document.getElementById("cart-items-list");
  const countBadge = document.getElementById("cart-items-count");
  if (!container) return;

  const totalItems = cart.reduce((sum, it) => sum + it.quantity, 0);
  if (countBadge) countBadge.innerText = totalItems;

  if (cart.length === 0) {
    container.innerHTML = `
      <div class="text-center text-muted py-5">
        <i class="bi bi-cart3 fs-1 d-block mb-2"></i>
        Keranjang belanja masih kosong.<br>
        <small>Scan barcode atau klik produk di katalog.</small>
      </div>
    `;
    updateCartTotals(0, 0, 0);
    return;
  }

  container.innerHTML = cart.map(item => {
    const itemId = item.product_id || item.variant_id;
    return `
      <div class="cart-item">
        <div style="flex: 1; padding-right: 0.5rem;">
          <div class="fw-bold text-dark text-truncate" title="${item.product_name}">${item.product_name}</div>
          <div class="small text-muted d-flex gap-2 align-items-center">
            <span>${formatRupiah(item.unit_price)}</span>
            <small class="text-secondary"><code>${item.sku}</code></small>
            ${item.discount_amount > 0 ? `<span class="badge bg-success-subtle text-success border border-success-subtle" style="font-size:0.7rem;">Hemat ${formatRupiah(item.discount_amount)}</span>` : ''}
          </div>
        </div>
        <div class="qty-control me-3">
          <button class="qty-btn" onclick="updateCartQty(${itemId}, -1)">-</button>
          <span class="fw-bold px-2">${item.quantity}</span>
          <button class="qty-btn" onclick="updateCartQty(${itemId}, 1)">+</button>
        </div>
        <div class="text-end" style="min-width: 90px;">
          <div class="fw-bold">${formatRupiah(item.subtotal)}</div>
          <a href="javascript:void(0)" class="text-danger small" onclick="removeCartItem(${itemId})"><i class="bi bi-trash"></i></a>
        </div>
      </div>
    `;
  }).join("");

  const subtotal = cart.reduce((sum, it) => sum + it.subtotal, 0);
  const taxAmount = isTaxEnabled ? Math.round((subtotal - orderDiscount) * (storeTaxRate / 100)) : 0;
  const grandTotal = Math.max(0, subtotal - orderDiscount + taxAmount);

  updateCartTotals(subtotal, taxAmount, grandTotal);
}

function updateCartTotals(subtotal, taxAmount, grandTotal) {
  document.getElementById("cart-subtotal").innerText = formatRupiah(subtotal);
  document.getElementById("cart-discount").innerText = formatRupiah(orderDiscount);
  
  const taxRow = document.getElementById("cart-tax-row");
  if (taxRow) {
    if (isTaxEnabled && taxAmount > 0) {
      taxRow.style.display = "flex";
      document.getElementById("cart-tax").innerText = formatRupiah(taxAmount);
    } else {
      taxRow.style.display = "none";
    }
  }

  document.getElementById("cart-grand-total").innerText = formatRupiah(grandTotal);
  
  // Update checkout button state
  const payBtn = document.getElementById("btn-checkout-pay");
  if (payBtn) payBtn.disabled = cart.length === 0;
}

// 7. Customers / Members
async function loadCustomersList() {
  try {
    const customers = await api.get("/api/customers");
    const select = document.getElementById("customer-select");
    if (!select) return;
    
    select.innerHTML = `<option value="">Pelanggan Umum (Tanpa Member)</option>`;
    customers.forEach(c => {
      select.innerHTML += `<option value="${c.id}">${c.name} (${c.phone || '-'})</option>`;
    });
  } catch (e) {
    console.error(e);
  }
}

function handleCustomerChange(el) {
  const custId = parseInt(el.value);
  currentCustomer = custId ? custId : null;
  if (!currentCustomer) {
    activeMember = null;
    revertCartItemDiscounts();
  }
}

// 8. Member Confirmation & Barcode/Camera Scanner
function initiateCheckoutFlow() {
  if (cart.length === 0) {
    showToast("Keranjang belanja masih kosong.", "warning");
    return;
  }
  if (!currentShift || currentShift.status !== "open") {
    showToast("Harap buka shift kasir terlebih dahulu!", "warning");
    new bootstrap.Modal(document.getElementById("openShiftModal")).show();
    return;
  }

  // Reset inputs
  document.getElementById("member-manual-input").value = "";
  document.getElementById("member-search-results").innerHTML = "";

  if (activeMember) {
    showSelectedMemberUI(activeMember);
  } else {
    document.getElementById("selected-member-card").style.display = "none";
    document.getElementById("btn-proceed-with-member").disabled = true;
  }

  const modal = new bootstrap.Modal(document.getElementById("memberCheckModal"));
  modal.show();

  // If camera tab active, auto start camera scanner
  setTimeout(() => {
    const camTab = document.getElementById("tab-camera-scan");
    if (camTab && camTab.classList.contains("active")) {
      startMemberCameraScanner();
    }
  }, 400);
}

async function startMemberCameraScanner() {
  if (isScannerRunning) return;
  const readerEl = document.getElementById("member-camera-reader");
  if (!readerEl) return;

  if (typeof Html5Qrcode === "undefined") {
    console.warn("Html5Qrcode library not loaded.");
    return;
  }

  try {
    if (!html5QrCodeScanner) {
      html5QrCodeScanner = new Html5Qrcode("member-camera-reader");
    }

    const config = {
      fps: 10,
      qrbox: { width: 280, height: 160 }
    };

    await html5QrCodeScanner.start(
      { facingMode: "environment" },
      config,
      (decodedText) => {
        handleMemberCodeScanned(decodedText);
      },
      (error) => {
        // per-frame scanning, ignore
      }
    );

    isScannerRunning = true;
    const ph = document.getElementById("camera-placeholder");
    if (ph) ph.style.display = "none";
  } catch (err) {
    console.warn("Camera start error:", err);
  }
}

async function stopMemberCameraScanner() {
  if (html5QrCodeScanner && isScannerRunning) {
    try {
      await html5QrCodeScanner.stop();
      isScannerRunning = false;
      const ph = document.getElementById("camera-placeholder");
      if (ph) ph.style.display = "block";
    } catch (e) {
      console.warn("Camera stop error:", e);
    }
  }
}

async function handleMemberCodeScanned(scannedText) {
  posSound.beep();
  await stopMemberCameraScanner();
  showToast(`Barcode terbaca: ${scannedText}`, "info");

  try {
    const member = await api.get(`/api/customers/by-code/${encodeURIComponent(scannedText.trim())}`);
    selectMemberForCheckout(member);
  } catch (err) {
    posSound.error();
    showToast("Member dengan barcode tersebut tidak ditemukan.", "error");
  }
}

async function searchMemberManual() {
  const query = document.getElementById("member-manual-input").value.trim();
  if (!query) {
    showToast("Masukkan nomor HP atau 12 Digit ID Member.", "warning");
    return;
  }

  const resultContainer = document.getElementById("member-search-results");
  resultContainer.innerHTML = `<div class="text-center py-2"><div class="spinner-border spinner-border-sm text-primary"></div> Mencari...</div>`;

  try {
    let member = null;
    try {
      member = await api.get(`/api/customers/by-code/${encodeURIComponent(query)}`);
    } catch (e) {
      const list = await api.get(`/api/customers?q=${encodeURIComponent(query)}`);
      if (list && list.length > 0) member = list[0];
    }

    if (member) {
      resultContainer.innerHTML = `
        <div class="alert alert-success d-flex justify-content-between align-items-center mb-0 p-2">
          <div>
            <strong>${member.name}</strong> (${member.phone || '-'})<br>
            <small class="font-monospace text-muted">ID: ${member.member_id || '-'}</small>
          </div>
          <button type="button" class="btn btn-sm btn-success fw-bold" onclick='selectMemberForCheckout(${JSON.stringify(member)})'>
            <i class="bi bi-check-lg"></i> Pilih Member Ini
          </button>
        </div>
      `;
    } else {
      resultContainer.innerHTML = `<div class="text-danger small py-1"><i class="bi bi-exclamation-circle me-1"></i>Member dengan nomor HP atau ID tersebut tidak ditemukan.</div>`;
    }
  } catch (err) {
    resultContainer.innerHTML = `<div class="text-danger small py-1">${err.message}</div>`;
  }
}

function selectMemberForCheckout(member) {
  activeMember = member;
  currentCustomer = member.id;
  if (document.getElementById("customer-select")) {
    document.getElementById("customer-select").value = member.id;
  }
  showSelectedMemberUI(member);
}

function showSelectedMemberUI(member) {
  const card = document.getElementById("selected-member-card");
  card.style.display = "block";
  document.getElementById("active-member-name").innerText = member.name;
  document.getElementById("active-member-details").innerText = `ID: ${member.member_id || '-'} | HP: ${member.phone || '-'}`;

  const savings = calculateMemberDiscountSavings(member);
  document.getElementById("active-member-discount-total").innerText = formatRupiah(savings);
  document.getElementById("btn-proceed-with-member").disabled = false;
  posSound.success();
}

function cancelSelectedMember() {
  activeMember = null;
  currentCustomer = null;
  if (document.getElementById("customer-select")) {
    document.getElementById("customer-select").value = "";
  }
  document.getElementById("selected-member-card").style.display = "none";
  document.getElementById("btn-proceed-with-member").disabled = true;
  document.getElementById("member-search-results").innerHTML = "";

  revertCartItemDiscounts();
}

function calculateMemberDiscountSavings(member) {
  let totalSavings = 0;
  cart.forEach(item => {
    const prod = currentProducts.find(p => p.id === item.product_id);
    if (prod && prod.member_discount_value > 0) {
      let discPerItem = 0;
      if (prod.member_discount_type === "percent") {
        discPerItem = Math.round(item.unit_price * (prod.member_discount_value / 100));
      } else {
        discPerItem = Math.min(item.unit_price, prod.member_discount_value);
      }
      totalSavings += (discPerItem * item.quantity);
    }
  });
  return totalSavings;
}

function applyMemberDiscountToCart(member) {
  cart.forEach(item => {
    const prod = currentProducts.find(p => p.id === item.product_id);
    if (prod && prod.member_discount_value > 0) {
      let discPerItem = 0;
      if (prod.member_discount_type === "percent") {
        discPerItem = Math.round(item.unit_price * (prod.member_discount_value / 100));
      } else {
        discPerItem = Math.min(item.unit_price, prod.member_discount_value);
      }
      item.discount_amount = discPerItem * item.quantity;
      item.subtotal = (item.unit_price * item.quantity) - item.discount_amount;
    }
  });
  renderCart();
}

function revertCartItemDiscounts() {
  cart.forEach(item => {
    item.discount_amount = 0;
    item.subtotal = item.unit_price * item.quantity;
  });
  renderCart();
}

async function proceedToPaymentWithMember() {
  if (!activeMember) return;
  await stopMemberCameraScanner();
  applyMemberDiscountToCart(activeMember);
  bootstrap.Modal.getOrCreateInstance(document.getElementById("memberCheckModal")).hide();
  openPaymentModal("cash");
}

async function continueWithoutMember() {
  await stopMemberCameraScanner();
  cancelSelectedMember();
  bootstrap.Modal.getOrCreateInstance(document.getElementById("memberCheckModal")).hide();
  openPaymentModal("cash");
}

// 9. Payment Modal & Execution
function openPaymentModal(defaultMethod = "cash") {
  if (cart.length === 0) {
    showToast("Keranjang belanja masih kosong.", "warning");
    return;
  }
  if (!currentShift || currentShift.status !== "open") {
    showToast("Harap buka shift kasir terlebih dahulu!", "warning");
    new bootstrap.Modal(document.getElementById("openShiftModal")).show();
    return;
  }

  const subtotal = cart.reduce((sum, it) => sum + it.subtotal, 0);
  const taxAmount = isTaxEnabled ? Math.round((subtotal - orderDiscount) * (storeTaxRate / 100)) : 0;
  const grandTotal = Math.max(0, subtotal - orderDiscount + taxAmount);

  document.getElementById("pay-modal-total").innerText = formatRupiah(grandTotal);
  document.getElementById("pay-modal-grandtotal-raw").value = grandTotal;

  setPaymentMethod(defaultMethod);
  
  // Set default cash to exact amount
  setQuickCash(grandTotal);

  new bootstrap.Modal(document.getElementById("paymentModal")).show();
}

function setPaymentMethod(method) {
  document.getElementById("selected-payment-method").value = method;
  
  document.querySelectorAll(".pay-method-btn").forEach(b => {
    b.classList.remove("active", "btn-primary");
    b.classList.add("btn-outline-primary");
  });
  
  const activeBtn = document.getElementById(`method-btn-${method}`);
  if (activeBtn) {
    activeBtn.classList.add("active", "btn-primary");
    activeBtn.classList.remove("btn-outline-primary");
  }

  // Toggle dynamic panels
  const cashPanel = document.getElementById("pay-cash-panel");
  const qrisPanel = document.getElementById("pay-qris-panel");
  const cardPanel = document.getElementById("pay-card-panel");

  cashPanel.style.display = method === "cash" ? "block" : "none";
  qrisPanel.style.display = method === "qris" ? "block" : "none";
  cardPanel.style.display = method === "card" ? "block" : "none";

  const grandTotal = parseFloat(document.getElementById("pay-modal-grandtotal-raw").value) || 0;
  if (method === "qris" || method === "card") {
    // Non-cash must be exact
    document.getElementById("pay-amount-paid").value = grandTotal;
    calculateChange();
  }
}

function setQuickCash(amount) {
  document.getElementById("pay-amount-paid").value = amount;
  calculateChange();
}

function calculateChange() {
  const grandTotal = parseFloat(document.getElementById("pay-modal-grandtotal-raw").value) || 0;
  const amountPaid = parseFloat(document.getElementById("pay-amount-paid").value) || 0;
  const change = amountPaid - grandTotal;

  const changeDisplay = document.getElementById("pay-modal-change");
  if (change < 0) {
    changeDisplay.className = "text-danger fw-bold";
    changeDisplay.innerText = `Kurang ${formatRupiah(Math.abs(change))}`;
  } else {
    changeDisplay.className = "text-success fw-bold";
    changeDisplay.innerText = formatRupiah(change);
  }
}

async function executePayment() {
  const grandTotal = parseFloat(document.getElementById("pay-modal-grandtotal-raw").value) || 0;
  const amountPaid = parseFloat(document.getElementById("pay-amount-paid").value) || 0;
  const method = document.getElementById("selected-payment-method").value;
  const notes = document.getElementById("pay-notes").value;

  if (amountPaid < grandTotal) {
    showToast("Nominal pembayaran masih kurang dari total tagihan!", "warning");
    posSound.error();
    return;
  }

  const payload = {
    shift_id: currentShift ? currentShift.id : null,
    customer_id: currentCustomer,
    discount_amount: orderDiscount,
    tax_rate: isTaxEnabled ? storeTaxRate : 0,
    payment_method: method,
    amount_paid: amountPaid,
    notes: notes,
    items: cart.map(c => ({
      product_id: c.product_id,
      variant_id: c.variant_id,
      quantity: c.quantity,
      unit_price: c.unit_price,
      discount_amount: c.discount_amount
    }))
  };

  try {
    const res = await api.post("/api/sales/checkout", payload);
    bootstrap.Modal.getOrCreateInstance(document.getElementById("paymentModal")).hide();
    
    posSound.success();
    showToast(`Transaksi ${res.invoice_number} berhasil diselesaikan!`, "success");
    
    // Clear cart
    cart = [];
    orderDiscount = 0;
    currentCustomer = null;
    activeMember = null;
    document.getElementById("customer-select").value = "";
    renderCart();

    // Show Printable Receipt Modal
    await openReceiptModal(res.id);

    // Refresh products stock in background
    loadProducts(document.getElementById("search-input").value);
    initShiftCheck();
  } catch (err) {
    posSound.error();
    showToast(err.message, "error");
  }
}

// 10. Thermal Receipt Preview & Printing
async function openReceiptModal(orderId) {
  try {
    const receipt = await api.get(`/api/sales/orders/${orderId}/receipt`);
    const container = document.getElementById("thermal-receipt-preview");
    
    container.innerHTML = `
      <div class="receipt-container">
        <div class="receipt-header">
          <h4>${receipt.store_name}</h4>
          <p>${receipt.store_tagline}</p>
          <p>${receipt.store_address}</p>
          <p>Telp: ${receipt.store_phone}</p>
        </div>
        <div class="receipt-divider"></div>
        <div class="receipt-meta">
          <div><span>No: ${receipt.invoice_number}</span><span>${receipt.date_str}</span></div>
          <div><span>Kasir: ${receipt.cashier_name}</span><span>Plg: ${receipt.customer_name || 'Umum'}</span></div>
          ${receipt.customer_member_id ? `<div><span>Member ID:</span><span><code>${receipt.customer_member_id}</code></span></div>` : ''}
        </div>
        <div class="receipt-divider"></div>
        <table class="receipt-table">
          <thead>
            <tr><th>Item</th><th style="text-align:right;">Total</th></tr>
          </thead>
          <tbody>
            ${receipt.items.map(it => `
              <tr>
                <td>
                  <div class="receipt-item-title">${it.product_name}</div>
                  <div class="receipt-item-sub">${it.variant_info} (${it.quantity}x @${formatRupiah(it.unit_price)})</div>
                </td>
                <td style="text-align:right; font-weight:bold;">${formatRupiah(it.subtotal)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        <div class="receipt-divider"></div>
        <div class="receipt-summary">
          <div class="receipt-summary-row"><span>Subtotal:</span><span>${formatRupiah(receipt.subtotal)}</span></div>
          ${receipt.discount_amount > 0 ? `<div class="receipt-summary-row"><span>Diskon:</span><span>-${formatRupiah(receipt.discount_amount)}</span></div>` : ''}
          ${receipt.tax_amount > 0 ? `<div class="receipt-summary-row"><span>PPN:</span><span>${formatRupiah(receipt.tax_amount)}</span></div>` : ''}
          <div class="receipt-summary-row bold"><span>TOTAL:</span><span>${formatRupiah(receipt.total_amount)}</span></div>
          <div class="receipt-summary-row"><span>Bayar (${receipt.payment_method}):</span><span>${formatRupiah(receipt.amount_paid)}</span></div>
          <div class="receipt-summary-row"><span>Kembalian:</span><span>${formatRupiah(receipt.change_amount)}</span></div>
        </div>
        <div class="receipt-divider"></div>
        <div class="receipt-footer">
          ${receipt.receipt_footer}
        </div>
      </div>
    `;

    new bootstrap.Modal(document.getElementById("receiptModal")).show();
  } catch (e) {
    console.error(e);
  }
}

function printReceipt() {
  window.print();
}

// 11. Keyboard Shortcuts
function setupKeyboardShortcuts() {
  window.addEventListener("keydown", (e) => {
    // If inside modal and typing, let it be
    const openModals = document.querySelectorAll(".modal.show");
    
    if (e.key === "F1") {
      e.preventDefault();
      document.getElementById("search-input").focus();
      document.getElementById("search-input").select();
    } else if (e.key === "F2") {
      e.preventDefault();
      document.getElementById("barcode-scanner-input").focus();
      document.getElementById("barcode-scanner-input").select();
    } else if (e.key === "F8") {
      e.preventDefault();
      if (openModals.length === 0) initiateCheckoutFlow();
    } else if (e.key === "F9") {
      e.preventDefault();
      if (openModals.length === 0) initiateCheckoutFlow();
    }
  });

  // Search input live filter
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        loadProducts(e.target.value.trim());
      }, 250);
    });
  }
}
