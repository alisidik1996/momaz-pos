/**
 * Momaz POS - TableManager
 * Fitur Universal: Sort, Live Search, Dropdown Max Show, dan Pagination Bootstrap 5
 */

class TableManager {
  constructor(tableElement, options = {}) {
    this.table = typeof tableElement === "string" ? document.querySelector(tableElement) : tableElement;
    if (!this.table) return;

    this.options = {
      pageSize: options.pageSize !== undefined ? options.pageSize : 10,
      pageSizeOptions: options.pageSizeOptions || [10, 25, 50, 100, -1],
      searchable: options.searchable !== false,
      sortable: options.sortable !== false,
      pagination: options.pagination !== false,
      showPageSize: options.showPageSize !== false,
      searchPlaceholder: options.searchPlaceholder || "Cari di tabel...",
      ...options
    };

    this.currentPage = 1;
    this.pageSize = this.options.pageSize;
    this.searchQuery = "";
    this.sortColumn = -1;
    this.sortDirection = "asc"; // 'asc' or 'desc'
    this.rawRows = [];
    this.filteredRows = [];

    this.initDOM();
    this.refresh();
  }

  initDOM() {
    // Wrapper around table container
    const tableResponsive = this.table.closest(".table-responsive") || this.table;
    const parentCard = tableResponsive.parentElement;

    // Check if toolbar already exists
    let toolbar = parentCard.querySelector(`.dt-toolbar[data-for="${this.getTableId()}"]`);
    if (!toolbar) {
      toolbar = document.createElement("div");
      toolbar.className = "dt-toolbar d-flex flex-wrap justify-content-between align-items-center gap-2 p-3 border-bottom bg-white";
      toolbar.setAttribute("data-for", this.getTableId());

      // Length dropdown
      let lengthHtml = "";
      if (this.options.showPageSize) {
        lengthHtml = `
          <div class="d-flex align-items-center gap-2">
            <span class="small text-muted fw-semibold">Tampilkan:</span>
            <select class="form-select form-select-sm dt-length-select" style="width: auto; min-width: 80px;">
              ${this.options.pageSizeOptions.map(opt => `
                <option value="${opt}" ${opt === this.pageSize ? 'selected' : ''}>
                  ${opt === -1 ? 'Semua' : opt}
                </option>
              `).join("")}
            </select>
            <span class="small text-muted">data</span>
          </div>
        `;
      }

      // Search box
      let searchHtml = "";
      if (this.options.searchable) {
        searchHtml = `
          <div class="dt-search-wrapper" style="max-width: 280px; width: 100%;">
            <div class="input-group input-group-sm">
              <span class="input-group-text bg-white"><i class="bi bi-search text-muted"></i></span>
              <input type="text" class="form-control form-control-sm dt-search-input" placeholder="${this.options.searchPlaceholder}">
              <button class="btn btn-outline-secondary dt-search-clear" type="button" style="display:none;" title="Bersihkan pencarian">
                <i class="bi bi-x"></i>
              </button>
            </div>
          </div>
        `;
      }

      toolbar.innerHTML = `
        <div class="dt-left">${lengthHtml}</div>
        <div class="dt-right">${searchHtml}</div>
      `;

      parentCard.insertBefore(toolbar, tableResponsive);

      // Event listener for length select
      const selectEl = toolbar.querySelector(".dt-length-select");
      if (selectEl) {
        selectEl.addEventListener("change", (e) => {
          this.pageSize = parseInt(e.target.value);
          this.currentPage = 1;
          this.render();
        });
      }

      // Event listener for search input
      const searchInput = toolbar.querySelector(".dt-search-input");
      const clearBtn = toolbar.querySelector(".dt-search-clear");
      if (searchInput) {
        let timer = null;
        searchInput.addEventListener("input", (e) => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            this.searchQuery = e.target.value.trim().toLowerCase();
            this.currentPage = 1;
            if (clearBtn) clearBtn.style.display = this.searchQuery ? "block" : "none";
            this.render();
          }, 150);
        });

        if (clearBtn) {
          clearBtn.addEventListener("click", () => {
            searchInput.value = "";
            this.searchQuery = "";
            clearBtn.style.display = "none";
            this.currentPage = 1;
            this.render();
          });
        }
      }
    }
    this.toolbar = toolbar;

    // Check if footer already exists
    let footer = parentCard.querySelector(`.dt-footer[data-for="${this.getTableId()}"]`);
    if (!footer) {
      footer = document.createElement("div");
      footer.className = "dt-footer d-flex flex-wrap justify-content-between align-items-center gap-2 p-3 border-top bg-white";
      footer.setAttribute("data-for", this.getTableId());
      footer.innerHTML = `
        <div class="small text-muted dt-info-text">Menampilkan 0 data</div>
        <nav class="dt-pagination-nav">
          <ul class="pagination pagination-sm mb-0"></ul>
        </nav>
      `;

      // Insert footer after table responsive
      if (tableResponsive.nextSibling) {
        parentCard.insertBefore(footer, tableResponsive.nextSibling);
      } else {
        parentCard.appendChild(footer);
      }
    }
    this.footer = footer;

    // Setup headers sortable
    this.setupHeaders();
  }

  getTableId() {
    if (!this.table.id) {
      this.table.id = "dt-table-" + Math.random().toString(36).substring(2, 9);
    }
    return this.table.id;
  }

  setupHeaders() {
    if (!this.options.sortable) return;
    const thead = this.table.querySelector("thead");
    if (!thead) return;

    const headers = thead.querySelectorAll("th");
    headers.forEach((th, idx) => {
      const title = th.innerText.trim().toLowerCase();
      // Skip non-sortable columns (e.g. actions, checkboxes, photos)
      if (
        th.classList.contains("no-sort") ||
        ["aksi", "action", "foto", "photo", ""].includes(title) ||
        th.querySelector("input[type='checkbox']")
      ) {
        return;
      }

      th.classList.add("dt-sortable");
      th.style.cursor = "pointer";
      th.style.userSelect = "none";
      th.setAttribute("title", "Klik untuk mengurutkan");

      // Add sort icon if not already added
      let icon = th.querySelector(".dt-sort-icon");
      if (!icon) {
        icon = document.createElement("i");
        icon.className = "bi bi-arrow-down-up text-muted ms-1 dt-sort-icon";
        icon.style.fontSize = "0.75rem";
        th.appendChild(icon);
      }

      // Remove old listener and add new
      th.onclick = () => {
        this.handleHeaderSort(idx, th);
      };
    });
  }

  handleHeaderSort(colIndex, thElement) {
    if (this.sortColumn === colIndex) {
      this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
    } else {
      this.sortColumn = colIndex;
      this.sortDirection = "asc";
    }

    // Update icons
    const thead = this.table.querySelector("thead");
    thead.querySelectorAll(".dt-sort-icon").forEach(icon => {
      icon.className = "bi bi-arrow-down-up text-muted ms-1 dt-sort-icon";
    });

    const activeIcon = thElement.querySelector(".dt-sort-icon");
    if (activeIcon) {
      activeIcon.className = `bi bi-sort-${this.sortDirection === "asc" ? "up" : "down"} text-primary ms-1 dt-sort-icon fw-bold`;
    }

    this.render();
  }

  refresh() {
    const tbody = this.table.querySelector("tbody");
    if (!tbody) return;

    // Read all rows
    const allTrs = Array.from(tbody.querySelectorAll("tr"));
    // Ignore empty/loading single row with colspan
    this.rawRows = allTrs.filter(tr => {
      const tdFirst = tr.querySelector("td");
      if (tdFirst && tr.children.length === 1 && tdFirst.hasAttribute("colspan")) {
        return false;
      }
      return true;
    });

    this.setupHeaders();
    this.render();
  }

  parseCellValue(cell) {
    if (!cell) return "";

    // If cell contains input or select, use its current value
    const input = cell.querySelector("input:not([type='checkbox']), select");
    let text = "";
    if (input) {
      if (input.tagName === "SELECT") {
        text = input.options[input.selectedIndex] ? input.options[input.selectedIndex].text.trim() : input.value;
      } else {
        text = String(input.value || "").trim();
      }
    } else {
      const checkbox = cell.querySelector("input[type='checkbox']");
      if (checkbox) {
        return checkbox.checked ? 1 : 0;
      }
      text = cell.innerText.trim();
    }

    if (!text) return "";

    // Check Rupiah: "Rp 150.000" or "-Rp 10.000"
    if (text.includes("Rp")) {
      const cleanNum = text.replace(/[^0-9,-]/g, "").replace(",", ".");
      const parsed = parseFloat(cleanNum);
      if (!isNaN(parsed)) return parsed;
    }

    // Check quantities / numbers like "15 pcs", "+10", "-5"
    if (/^[+-]?\d+(\.\d+)?\s*(pcs|item|x)?$/i.test(text)) {
      const parsed = parseFloat(text.replace(/[^0-9.-]/g, ""));
      if (!isNaN(parsed)) return parsed;
    }

    // Check pure numbers
    const num = parseFloat(text.replace(/,/g, ""));
    if (!isNaN(num) && /^-?\d+(\.\d+)?$/.test(text.replace(/,/g, ""))) {
      return num;
    }

    // Check Indonesian dates: e.g. "28 Okt 2026, 16.05"
    const idMonths = { jan: 0, feb: 1, mar: 2, apr: 3, mei: 4, may: 4, jun: 5, jul: 6, agu: 7, ags: 7, aug: 7, sep: 8, okt: 9, oct: 9, nop: 10, nov: 10, des: 11, dec: 11 };
    const indMatch = text.match(/^(\d{1,2})\s+([a-zA-Z]{3,})\s+(\d{4})(?:[,\s]+(\d{1,2})[\.:](\d{2}))?/i);
    if (indMatch) {
      const day = parseInt(indMatch[1]);
      const mStr = indMatch[2].toLowerCase().substring(0, 3);
      const m = idMonths[mStr];
      const year = parseInt(indMatch[3]);
      const hr = indMatch[4] ? parseInt(indMatch[4]) : 0;
      const min = indMatch[5] ? parseInt(indMatch[5]) : 0;
      if (m !== undefined) return new Date(year, m, day, hr, min).getTime();
    }

    // Check DD/MM/YYYY or DD-MM-YYYY dates
    const ddmmyyyy = text.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})(?:[,\s]+(\d{1,2})[\.:](\d{2}))?/);
    if (ddmmyyyy) {
      const day = parseInt(ddmmyyyy[1]);
      const m = parseInt(ddmmyyyy[2]) - 1;
      const year = parseInt(ddmmyyyy[3]);
      const hr = ddmmyyyy[4] ? parseInt(ddmmyyyy[4]) : 0;
      const min = ddmmyyyy[5] ? parseInt(ddmmyyyy[5]) : 0;
      return new Date(year, m, day, hr, min).getTime();
    }

    // Check standard ISO dates
    const d = new Date(text);
    if (!isNaN(d.getTime())) return d.getTime();

    return text.toLowerCase();
  }

  render() {
    const tbody = this.table.querySelector("tbody");
    if (!tbody) return;

    // 1. Filter
    if (!this.searchQuery) {
      this.filteredRows = [...this.rawRows];
    } else {
      this.filteredRows = this.rawRows.filter(tr => {
        const text = tr.innerText.toLowerCase();
        if (text.includes(this.searchQuery)) return true;
        // Also match inside input and select controls
        const inputs = tr.querySelectorAll("input, select");
        for (let i = 0; i < inputs.length; i++) {
          if (inputs[i].value && inputs[i].value.toLowerCase().includes(this.searchQuery)) {
            return true;
          }
        }
        return false;
      });
    }

    // 2. Sort
    if (this.sortColumn >= 0) {
      this.filteredRows.sort((a, b) => {
        const cellA = a.children[this.sortColumn];
        const cellB = b.children[this.sortColumn];
        const valA = this.parseCellValue(cellA);
        const valB = this.parseCellValue(cellB);

        let cmp = 0;
        if (typeof valA === "number" && typeof valB === "number") {
          cmp = valA - valB;
        } else {
          cmp = String(valA).localeCompare(String(valB), "id", { numeric: true });
        }
        return this.sortDirection === "asc" ? cmp : -cmp;
      });
    }

    // 3. Pagination math
    const totalItems = this.filteredRows.length;
    let totalPages = 1;
    let startIndex = 0;
    let endIndex = totalItems;

    if (this.pageSize > 0 && totalItems > 0) {
      totalPages = Math.ceil(totalItems / this.pageSize);
      if (this.currentPage > totalPages) this.currentPage = totalPages;
      if (this.currentPage < 1) this.currentPage = 1;

      startIndex = (this.currentPage - 1) * this.pageSize;
      endIndex = Math.min(startIndex + this.pageSize, totalItems);
    }

    // 4. Update row visibility & order in DOM
    // Reorder filtered rows in tbody
    const visibleSet = new Set(this.filteredRows.slice(startIndex, endIndex));

    this.rawRows.forEach(tr => {
      tr.style.display = visibleSet.has(tr) ? "" : "none";
    });

    // Re-append to preserve sort order
    this.filteredRows.forEach(tr => {
      tbody.appendChild(tr);
    });

    // 5. Update Info Text
    const infoEl = this.footer.querySelector(".dt-info-text");
    if (infoEl) {
      if (totalItems === 0) {
        if (this.rawRows.length === 0) {
          infoEl.innerText = "Belum ada data tersedia";
        } else {
          infoEl.innerHTML = `<span class="text-danger"><i class="bi bi-exclamation-circle me-1"></i>Tidak ada data yang cocok dengan pencarian "${this.searchQuery}"</span>`;
        }
      } else {
        let infoStr = `Menampilkan <strong>${startIndex + 1}</strong> sampai <strong>${endIndex}</strong> dari <strong>${totalItems}</strong> data`;
        if (this.searchQuery && totalItems !== this.rawRows.length) {
          infoStr += ` <small class="text-secondary">(difilter dari ${this.rawRows.length} total data)</small>`;
        }
        infoEl.innerHTML = infoStr;
      }
    }

    // 6. Render Pagination Buttons
    this.renderPaginationButtons(totalPages, totalItems);
  }

  renderPaginationButtons(totalPages, totalItems) {
    const ul = this.footer.querySelector(".pagination");
    if (!ul) return;

    if (totalPages <= 1 || this.pageSize === -1) {
      ul.innerHTML = "";
      return;
    }

    let html = "";

    // Prev Button
    const prevDisabled = this.currentPage === 1 ? "disabled" : "";
    html += `
      <li class="page-item ${prevDisabled}">
        <button class="page-link" type="button" onclick="TableManager.goToPage('${this.getTableId()}', ${this.currentPage - 1})">
          <i class="bi bi-chevron-left me-1"></i>Sebelumnya
        </button>
      </li>
    `;

    // Page Numbers with Ellipsis
    const maxVisiblePages = 5;
    let startPage = Math.max(1, this.currentPage - 2);
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage < maxVisiblePages - 1) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    if (startPage > 1) {
      html += `<li class="page-item"><button class="page-link" type="button" onclick="TableManager.goToPage('${this.getTableId()}', 1)">1</button></li>`;
      if (startPage > 2) {
        html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
      }
    }

    for (let p = startPage; p <= endPage; p++) {
      const active = p === this.currentPage ? "active" : "";
      html += `
        <li class="page-item ${active}">
          <button class="page-link" type="button" onclick="TableManager.goToPage('${this.getTableId()}', ${p})">${p}</button>
        </li>
      `;
    }

    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
      }
      html += `<li class="page-item"><button class="page-link" type="button" onclick="TableManager.goToPage('${this.getTableId()}', ${totalPages})">${totalPages}</button></li>`;
    }

    // Next Button
    const nextDisabled = this.currentPage === totalPages ? "disabled" : "";
    html += `
      <li class="page-item ${nextDisabled}">
        <button class="page-link" type="button" onclick="TableManager.goToPage('${this.getTableId()}', ${this.currentPage + 1})">
          Selanjutnya<i class="bi bi-chevron-right ms-1"></i>
        </button>
      </li>
    `;

    ul.innerHTML = html;
  }

  goTo(page) {
    this.currentPage = page;
    this.render();
  }

  // Static Registry & Helpers
  static instances = new Map();

  static bind(tableSelectorOrElement, options = {}) {
    const el = typeof tableSelectorOrElement === "string" ? document.querySelector(tableSelectorOrElement) : tableSelectorOrElement;
    if (!el) return null;

    let instance = TableManager.instances.get(el);
    if (!instance) {
      instance = new TableManager(el, options);
      TableManager.instances.set(el, instance);
      if (el.id) TableManager.instances.set(el.id, instance);
    } else {
      instance.refresh();
    }
    return instance;
  }

  static goToPage(tableId, page) {
    const instance = TableManager.instances.get(tableId);
    if (instance) {
      instance.goTo(page);
    }
  }

  static autoInitAll() {
    document.querySelectorAll(".card .table, .tab-pane .table").forEach(table => {
      // Don't bind inside modals or tables with opt-out or receipt table
      if (table.closest(".modal") || table.classList.contains("dt-ignore") || table.classList.contains("receipt-table")) return;
      TableManager.bind(table);
    });
  }
}

// Global exposure
window.TableManager = TableManager;

// Auto initialize tables on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    TableManager.autoInitAll();
  }, 100);
});
