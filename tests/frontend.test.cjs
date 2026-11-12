const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "..");

function environment(template = "pos/index.html") {
  const html = fs.readFileSync(path.join(root, "app/templates", template), "utf8");
  const dom = new JSDOM(html, { url: "https://testserver/pos", runScripts: "outside-only" });
  const window = dom.window;
  const addListener = window.document.addEventListener.bind(window.document);
  window.document.addEventListener = (name, listener, ...options) => {
    if (name !== "DOMContentLoaded") addListener(name, listener, ...options);
  };
  window.bootstrap = { Modal: class {
    static Default = {};
    static getOrCreateInstance() { return new this(); }
    show() {}
    hide() {}
  }};
  window.posSound = { beep() {}, success() {}, error() {} };
  window.Headers = globalThis.Headers;
  const context = dom.getInternalVMContext();
  new vm.Script(fs.readFileSync(path.join(root, "app/static/js/api.js"), "utf8")).runInContext(context);
  new vm.Script(fs.readFileSync(path.join(root, "app/static/js/pos.js"), "utf8")).runInContext(context);
  return dom;
}

test("toast treats user-controlled text as text, not HTML", () => {
  const dom = environment();
  try {
    dom.window.showToast('<img src=x onerror="window.compromised=true">');
    const toast = dom.window.document.querySelector(".toast");
    assert.equal(toast.querySelector("img"), null);
    assert.ok(toast.textContent.includes("<img"));
  } finally { dom.window.close(); }
});

test("product names and image URLs cannot inject HTML attributes", () => {
  const dom = environment();
  try {
    dom.window.renderProducts([{
      id: 1, name: '<img id="injected" src=x>', image_url: 'x" onerror="alert(1)',
      sku: "SKU", base_price: 10, stock: 1,
    }]);
    assert.equal(dom.window.document.getElementById("injected"), null);
    assert.equal(dom.window.document.querySelector("[onerror]"), null);
    assert.ok(dom.window.document.getElementById("pos-product-grid").textContent.includes("<img"));
  } finally { dom.window.close(); }
});

test("quantity controls identify variants separately from their parent", () => {
  const dom = environment();
  try {
    dom.window.eval(`cart = [
      {product_id: 1, variant_id: 10, product_name: "M", sku: "M", quantity: 1, unit_price: 10, subtotal: 10, discount_amount: 0, stock: 5},
      {product_id: 1, variant_id: 11, product_name: "L", sku: "L", quantity: 1, unit_price: 10, subtotal: 10, discount_amount: 0, stock: 5}
    ]; renderCart();`);
    const second = dom.window.document.querySelectorAll(".cart-item")[1];
    dom.window.eval(second.querySelectorAll(".qty-btn")[1].getAttribute("onclick"));
    assert.equal(dom.window.eval("cart[0].quantity"), 1);
    assert.equal(dom.window.eval("cart[1].quantity"), 2);
    dom.window.eval(second.querySelector("a").getAttribute("onclick"));
    assert.equal(dom.window.eval("cart.length"), 1);
    assert.equal(dom.window.eval("cart[0].variant_id"), 10);
  } finally { dom.window.close(); }
});

test("a delayed product search cannot replace newer search results", async () => {
  const dom = environment();
  try {
    let oldResolve;
    dom.window.eval("api.get = url => window.lookup(url)");
    dom.window.lookup = url => url.includes("q=old") ? new Promise(resolve => { oldResolve = resolve; }) : Promise.resolve([{ id: 2, name: "New", stock: 1, base_price: 10 }]);
    const oldSearch = dom.window.loadProducts("old");
    await dom.window.loadProducts("new");
    oldResolve([{ id: 1, name: "Old", stock: 1, base_price: 10 }]);
    await oldSearch;
    assert.equal(dom.window.eval("currentProducts[0].id"), 2);
  } finally { dom.window.close(); }
});

test("double-clicking payment submits only one checkout", async () => {
  const dom = environment();
  try {
    dom.window.eval("currentShift = {id: 1, status: 'open'}; cart = [{product_id: 1, quantity: 1, unit_price: 10, discount_amount: 0, subtotal: 10}]");
    dom.window.document.getElementById("pay-modal-grandtotal-raw").value = 10;
    dom.window.document.getElementById("pay-amount-paid").value = 10;
    dom.window.document.getElementById("selected-payment-method").value = "cash";
    let calls = 0;
    let finish;
    dom.window.checkout = () => { calls++; return new Promise(resolve => { finish = resolve; }); };
    dom.window.eval("api.post = () => window.checkout(); openReceiptModal = async () => {}; loadProducts = async () => {}; initShiftCheck = async () => {};");
    const first = dom.window.executePayment();
    const second = dom.window.executePayment();
    assert.equal(calls, 1);
    finish({ id: 1, invoice_number: "INV-TEST" });
    await Promise.all([first, second]);
    assert.equal(dom.window.eval("cart.length"), 0);
  } finally { dom.window.close(); }
});

test("the API client preserves caller headers and uses cookie credentials", async () => {
  const dom = environment();
  try {
    const headers = { "X-Custom": "value" };
    let sent;
    dom.window.fetch = async (_, options) => {
      sent = options;
      return { status: 200, ok: true, headers: { get: () => "application/json" }, json: async () => ({}) };
    };
    dom.window.options = { method: "POST", body: "{}", headers };
    await dom.window.eval("api.request('/api/test', options)");
    assert.deepEqual(headers, { "X-Custom": "value" });
    assert.equal(sent.credentials, "same-origin");
  } finally { dom.window.close(); }
});

function loadInlineScripts(dom, template) {
  const html = fs.readFileSync(path.join(root, "app/templates", template), "utf8");
  for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
    new vm.Script(match[1], { filename: template }).runInContext(dom.getInternalVMContext());
  }
}

test("user table escapes names and keeps quoted delete arguments intact", () => {
  const template = "backoffice/users.html";
  const dom = environment(template);
  try {
    loadInlineScripts(dom, template);
    const username = `O'Connor\"><img id="injected-user" src=x>`;
    dom.window.renderUsersTable([{ id: 1, username, full_name: username, role: "cashier", is_active: true, created_at: "2026-11-03T00:00:00Z" }]);
    assert.equal(dom.window.document.getElementById("injected-user"), null);
    let received;
    dom.window.deleteUser = (_, name) => { received = name; };
    const button = dom.window.document.querySelector("button[onclick^='deleteUser']");
    dom.window.eval(button.getAttribute("onclick"));
    assert.equal(received, username);
  } finally { dom.window.close(); }
});

test("member table escapes names and preserves quoted member names in actions", () => {
  const template = "backoffice/members.html";
  const dom = environment(template);
  try {
    loadInlineScripts(dom, template);
    const name = `O'Connor\"><img id="injected-member" src=x>`;
    dom.window.renderMembersTable([{ id: 1, name, member_id: null, total_spend: 0, total_commission: 0 }]);
    assert.equal(dom.window.document.getElementById("injected-member"), null);
    let received;
    dom.window.deleteMember = (_, value) => { received = value; };
    dom.window.eval(dom.window.document.querySelector("button[onclick^='deleteMember']").getAttribute("onclick"));
    assert.equal(received, name);
  } finally { dom.window.close(); }
});

test("member discounts scale when cart quantity changes", () => {
  const dom = environment();
  try {
    dom.window.eval(`cart = [{ product_id: 1, product_name: "Discount", sku: "D", unit_price: 100,
      quantity: 1, stock: 5, discount_amount: 0, subtotal: 100,
      member_discount_type: "percent", member_discount_value: 10 }];
      applyMemberDiscountToCart({id: 1}); updateCartQty("product:1", 1);`);
    assert.equal(dom.window.eval("cart[0].discount_amount"), 20);
    assert.equal(dom.window.eval("cart[0].subtotal"), 180);
  } finally { dom.window.close(); }
});

test("F9 preserves noncash payment selection through member confirmation", async () => {
  const dom = environment();
  try {
    dom.window.eval("currentShift = {id: 1, status: 'open'}; cart = [{product_id: 1, quantity: 1, unit_price: 10, discount_amount: 0, subtotal: 10}]; setupKeyboardShortcuts();");
    dom.window.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "F9" }));
    await dom.window.continueWithoutMember();
    assert.equal(dom.window.document.getElementById("selected-payment-method").value, "qris");
  } finally { dom.window.close(); }
});

test("every inline template script is syntactically valid JavaScript", () => {
  const templates = ["login.html", "setup.html", "pos/index.html", ...[
    "dashboard", "inventory", "members", "products", "reports", "returns", "sales", "settings", "shifts", "users"
  ].map(name => `backoffice/${name}.html`)];
  for (const template of templates) {
    const html = fs.readFileSync(path.join(root, "app/templates", template), "utf8");
    for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
      assert.doesNotThrow(() => new vm.Script(match[1], { filename: template }));
    }
  }
});
