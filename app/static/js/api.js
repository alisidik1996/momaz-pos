// Momaz POS Central API Client & Utilities

const api = {
  getToken() {
    const match = document.cookie.match(new RegExp('(^| )access_token=([^;]+)'));
    if (match) {
      let val = decodeURIComponent(match[2]).trim().replace(/^["']|["']$/g, '');
      while (val.toLowerCase().startsWith("bearer ")) {
        val = val.substring(7).trim().replace(/^["']|["']$/g, '');
      }
      return val ? "Bearer " + val : null;
    }
    return null;
  },

  async request(url, options = {}) {
    const headers = options.headers || {};
    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const token = this.getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = token;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (response.status === 401) {
        // If not authenticated, redirect to login unless already on login page
        if (!window.location.pathname.includes("/login")) {
          window.location.href = "/login";
        }
      }

      const contentType = response.headers.get("content-type");
      let data = null;
      if (contentType && contentType.includes("application/json")) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      if (!response.ok) {
        const errorMsg = (data && data.detail) ? data.detail : "Terjadi kesalahan pada sistem.";
        throw new Error(errorMsg);
      }

      return data;
    } catch (err) {
      console.error(`API Error [${url}]:`, err);
      throw err;
    }
  },

  get(url) {
    return this.request(url, { method: "GET" });
  },

  post(url, body) {
    return this.request(url, {
      method: "POST",
      body: JSON.stringify(body)
    });
  },

  put(url, body) {
    return this.request(url, {
      method: "PUT",
      body: JSON.stringify(body)
    });
  },

  delete(url) {
    return this.request(url, { method: "DELETE" });
  }
};

// Formatting Utilities
function formatRupiah(amount) {
  if (amount === undefined || amount === null || isNaN(amount)) return "Rp 0";
  return "Rp " + Math.round(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function formatDate(isoString) {
  if (!isoString) return "-";
  const d = new Date(isoString);
  return d.toLocaleString("id-ID", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

// Toast Notification
function showToast(message, type = "info") {
  let toastContainer = document.getElementById("toast-container");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toast-container";
    toastContainer.style.position = "fixed";
    toastContainer.style.top = "20px";
    toastContainer.style.right = "20px";
    toastContainer.style.zIndex = "9999";
    document.body.appendChild(toastContainer);
  }

  const bgClasses = {
    success: "bg-success text-white",
    error: "bg-danger text-white",
    warning: "bg-warning text-dark",
    info: "bg-primary text-white"
  };

  const toastEl = document.createElement("div");
  toastEl.className = `toast align-items-center show shadow-lg mb-2 ${bgClasses[type] || bgClasses.info}`;
  toastEl.setAttribute("role", "alert");
  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body fw-medium py-2 px-3">
        ${message}
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.parentElement.parentElement.remove()"></button>
    </div>
  `;

  toastContainer.appendChild(toastEl);
  setTimeout(() => {
    if (toastEl.parentElement) toastEl.remove();
  }, 4000);
}

// =========================================================================
// Universal Popup Modal System (Ganti window.alert & window.confirm)
// Semua modal dikunci: hanya bisa ditutup lewat tanda 'X' / tombol aksi
// =========================================================================

function ensureAlertConfirmModalInDOM() {
  let modalEl = document.getElementById("appUniversalAlertConfirmModal");
  if (!modalEl) {
    modalEl = document.createElement("div");
    modalEl.id = "appUniversalAlertConfirmModal";
    modalEl.className = "modal fade";
    modalEl.setAttribute("tabindex", "-1");
    modalEl.setAttribute("data-bs-backdrop", "static");
    modalEl.setAttribute("data-bs-keyboard", "false");
    modalEl.setAttribute("aria-hidden", "true");
    modalEl.innerHTML = `
      <div class="modal-dialog modal-dialog-centered" style="max-width: 440px;">
        <div class="modal-content border-0 shadow-lg" style="border-radius: 12px; overflow: hidden;">
          <div class="modal-header py-3 px-4 border-0" id="appModalHeader">
            <h5 class="modal-title fw-bold d-flex align-items-center gap-2 fs-6" id="appModalTitle">
              <i class="bi bi-info-circle-fill text-primary fs-5" id="appModalIcon"></i>
              <span id="appModalTitleText">Pemberitahuan</span>
            </h5>
            <button type="button" class="btn-close" id="appModalCloseBtn" data-bs-dismiss="modal" aria-label="Close" title="Tutup"></button>
          </div>
          <div class="modal-body px-4 py-2 text-secondary" id="appModalBody" style="font-size: 0.95rem; line-height: 1.5; white-space: pre-line;">
            <!-- Pesan Pop-up -->
          </div>
          <div class="modal-footer border-0 px-4 pb-4 pt-3 d-flex justify-content-end gap-2" id="appModalFooter">
            <button type="button" class="btn btn-outline-secondary px-3 py-2 fw-semibold" id="appModalCancelBtn" data-bs-dismiss="modal" style="display: none;">Batal</button>
            <button type="button" class="btn btn-primary px-4 py-2 fw-bold" id="appModalConfirmBtn">Mengerti</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modalEl);
  }
  return modalEl;
}

function showAppAlert(message, title = "Pemberitahuan", type = "info") {
  return new Promise((resolve) => {
    const modalEl = ensureAlertConfirmModalInDOM();
    const titleEl = document.getElementById("appModalTitleText");
    const iconEl = document.getElementById("appModalIcon");
    const bodyEl = document.getElementById("appModalBody");
    const cancelBtn = document.getElementById("appModalCancelBtn");
    const confirmBtn = document.getElementById("appModalConfirmBtn");

    titleEl.innerText = title;
    bodyEl.innerText = typeof message === "object" ? JSON.stringify(message, null, 2) : String(message);

    if (type === "success") {
      iconEl.className = "bi bi-check-circle-fill text-success fs-5";
      confirmBtn.className = "btn btn-success px-4 py-2 fw-bold";
    } else if (type === "error" || type === "danger") {
      iconEl.className = "bi bi-exclamation-triangle-fill text-danger fs-5";
      confirmBtn.className = "btn btn-danger px-4 py-2 fw-bold";
    } else if (type === "warning") {
      iconEl.className = "bi bi-exclamation-diamond-fill text-warning fs-5";
      confirmBtn.className = "btn btn-warning px-4 py-2 fw-bold text-dark";
    } else {
      iconEl.className = "bi bi-info-circle-fill text-primary fs-5";
      confirmBtn.className = "btn btn-primary px-4 py-2 fw-bold";
    }

    cancelBtn.style.display = "none";
    confirmBtn.innerText = "Mengerti";

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
      backdrop: 'static',
      keyboard: false
    });

    let handled = false;
    const cleanup = () => {
      if (!handled) {
        handled = true;
        modalEl.removeEventListener("hidden.bs.modal", onHidden);
        confirmBtn.onclick = null;
        resolve();
      }
    };

    const onHidden = () => {
      cleanup();
    };

    modalEl.addEventListener("hidden.bs.modal", onHidden, { once: true });
    confirmBtn.onclick = () => {
      modal.hide();
    };

    modal.show();
  });
}

function showAppConfirm(message, title = "Konfirmasi Tindakan", options = {}) {
  return new Promise((resolve) => {
    const modalEl = ensureAlertConfirmModalInDOM();
    const titleEl = document.getElementById("appModalTitleText");
    const iconEl = document.getElementById("appModalIcon");
    const bodyEl = document.getElementById("appModalBody");
    const cancelBtn = document.getElementById("appModalCancelBtn");
    const confirmBtn = document.getElementById("appModalConfirmBtn");

    titleEl.innerText = title;
    bodyEl.innerText = typeof message === "object" ? JSON.stringify(message, null, 2) : String(message);

    const type = options.type || "warning";
    if (type === "danger" || options.confirmBtnClass?.includes("danger")) {
      iconEl.className = "bi bi-exclamation-triangle-fill text-danger fs-5";
      confirmBtn.className = `btn ${options.confirmBtnClass || "btn-danger"} px-4 py-2 fw-bold`;
    } else {
      iconEl.className = "bi bi-question-circle-fill text-warning fs-5";
      confirmBtn.className = `btn ${options.confirmBtnClass || "btn-primary"} px-4 py-2 fw-bold`;
    }

    cancelBtn.style.display = "inline-block";
    cancelBtn.innerText = options.cancelText || "Batal";
    confirmBtn.innerText = options.confirmText || "Ya, Lanjutkan";

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
      backdrop: 'static',
      keyboard: false
    });

    let result = false;
    let handled = false;

    const cleanup = () => {
      if (!handled) {
        handled = true;
        modalEl.removeEventListener("hidden.bs.modal", onHidden);
        confirmBtn.onclick = null;
        cancelBtn.onclick = null;
        resolve(result);
      }
    };

    const onHidden = () => {
      cleanup();
    };

    modalEl.addEventListener("hidden.bs.modal", onHidden, { once: true });

    confirmBtn.onclick = () => {
      result = true;
      modal.hide();
    };

    cancelBtn.onclick = () => {
      result = false;
      modal.hide();
    };

    modal.show();
  });
}

// Global exposure
window.showAppAlert = showAppAlert;
window.showAlertModal = showAppAlert;
window.showAppConfirm = showAppConfirm;
window.showConfirmModal = showAppConfirm;

// Override window.alert agar seluruh pemanggilan alert() browser berubah jadi modal popup
window.alert = function(msg) {
  return showAppAlert(msg);
};

// Bootstrap 5 Global Defaults: Kunci semua modal agar tidak bisa ditutup klik sembarang tempat
if (typeof window !== "undefined") {
  if (window.bootstrap && window.bootstrap.Modal) {
    window.bootstrap.Modal.Default = window.bootstrap.Modal.Default || {};
    window.bootstrap.Modal.Default.backdrop = 'static';
    window.bootstrap.Modal.Default.keyboard = false;
  }

  // Kunci semua modal yang ada di DOM
  function lockAllModals() {
    document.querySelectorAll(".modal").forEach(modal => {
      modal.setAttribute("data-bs-backdrop", "static");
      modal.setAttribute("data-bs-keyboard", "false");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", lockAllModals);
  } else {
    lockAllModals();
  }
}

// Global Logout Action
async function handleLogout() {
  try {
    await api.post("/api/auth/logout");
  } catch (e) {
    console.warn("Logout error:", e);
  } finally {
    window.location.href = "/login";
  }
}
