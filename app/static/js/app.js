const KINDS = {
  annual: "Annual",
  hundred_hour: "100-hour",
  repair: "Repair",
  ad: "AD / SB",
  oil: "Oil service",
  ferry: "Ferry",
  other: "Other",
};

const RECORD_STATUSES = {
  open: "Open",
  in_work: "In work",
  awaiting_parts: "Awaiting parts",
  complete: "Complete",
};

const INVOICE_STATUSES = {
  draft: "Draft",
  issued: "Issued",
  partial: "Partial",
  paid: "Paid",
  void: "Void",
};

const METHODS = { check: "Check", card: "Card", ach: "ACH", cash: "Cash", other: "Other" };

const RATINGS = { A: "Airframe", P: "Powerplant", AP: "A&P" };

const CERT = {
  annual:
    "I certify that this aircraft has been inspected in accordance with an annual inspection and was determined to be in airworthy condition.",
  hundred_hour:
    "I certify that this aircraft has been inspected in accordance with a 100-hour inspection and was determined to be in airworthy condition.",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const SCHEDULE_KINDS = {
  visit: "Visit",
  inspection: "Inspection",
  parts: "Parts",
  ferry: "Ferry",
  other: "Note",
};

const SOURCE_LABEL = {
  entry: "On the schedule",
  record: "Work opened",
  annual: "Annual due",
  invoice: "Invoice due",
};

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const WEEKDAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const state = {
  shop: null,
  dashboard: null,
  customers: [],
  aircraft: [],
  records: [],
  invoices: [],
  user: null,
  filters: { records: "", billing: "", fleet: "" },
};

let signedIn = false;
let modalHandler = null;
let renderToken = 0;
let busy = false;
let pendingFlash = "";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function money(cents) {
  const amount = Number(cents || 0);
  const sign = amount < 0 ? "-" : "";
  return `${sign}$${(Math.abs(amount) / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function lineQty(line) {
  const number = Number(line.quantity);
  if (line.kind === "labor" || line.kind === "travel") return number.toFixed(1);
  if (Number.isInteger(number)) return String(number);
  return number.toFixed(2);
}

function hours(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toFixed(1);
}

function todayISO() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function prettyDate(iso) {
  if (!iso) return "—";
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return esc(iso);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

function dueClass(days) {
  if (days === null || days === undefined) return "";
  if (days < 0) return "due-overdue";
  if (days <= 30) return "due-soon";
  return "";
}

function dueLabel(days) {
  if (days === null || days === undefined) return "No annual date";
  if (days < 0) return `${Math.abs(days)} days overdue`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

function pill(status, labels) {
  const known = Object.prototype.hasOwnProperty.call(labels, status);
  const key = known ? status : "other";
  return `<span class="pill pill-${key}">${esc(labels[status] || status)}</span>`;
}

function ratingLabel(code) {
  return RATINGS[code] || code || "A&P";
}

function errorMessage(data, fallback) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || "Check the form.").join(" ");
  }
  return fallback || "Request failed.";
}

async function api(path, options = {}) {
  const opts = { method: options.method || "GET", headers: { "X-Kinney-Request": "1" } };
  if (options.body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, opts);
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !path.endsWith("/api/login")) {
    showLogin();
    throw new Error(errorMessage(data, "Sign in required."));
  }
  if (!response.ok) throw new Error(errorMessage(data, response.statusText));
  return data;
}

function showFlash(message, kind = "error") {
  const el = document.getElementById("flash");
  el.hidden = false;
  el.className = `flash flash-${kind}`;
  el.textContent = message;
}

function dollarsToCents(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) throw new Error("Use a dollar amount like 125.00.");
  const [dollars, cents = ""] = text.split(".");
  return Number(dollars) * 100 + Number((cents + "00").slice(0, 2));
}

function dollarsToCentsOrZero(value) {
  const text = String(value ?? "").trim();
  if (!text) return 0;
  return dollarsToCents(text);
}

function parseHours(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+(\.\d)?$/.test(text)) throw new Error("Enter hours in tenths, such as 1.5.");
  return Number(text);
}

function parseQty(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) throw new Error("Enter a quantity like 1 or 2.50.");
  const number = Number(text);
  if (!(number > 0)) throw new Error("Quantity has to be greater than zero.");
  return number;
}

function optionalNumber(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const number = Number(text);
  if (Number.isNaN(number)) throw new Error("Enter a number.");
  return number;
}

function optionalText(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function parseRoute() {
  const parts = (location.hash.replace(/^#/, "") || "briefing").split("/").filter(Boolean);
  const known = ["briefing", "calendar", "records", "billing", "fleet", "present", "admin"];
  if (!known.includes(parts[0])) return { name: "briefing", parts: [] };
  return { name: parts[0], parts: parts.slice(1) };
}

function setHeader(title, eyebrow, actions = "") {
  document.getElementById("view-title").textContent = title;
  document.getElementById("eyebrow").textContent = eyebrow;
  document.getElementById("top-actions").innerHTML = actions;
  document.title = `${title} · Kinney Aviation`;
}

function setNav(name) {
  document.querySelectorAll(".rail-nav a").forEach((link) => {
    const current = link.dataset.nav === name;
    link.classList.toggle("is-current", current);
    if (current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function renderBanner() {
  const el = document.getElementById("banner");
  if (!state.shop || !state.shop.demo_seeded || sessionStorage.getItem("kinney-hide-demo")) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  el.hidden = false;
  el.innerHTML = `<p>Sample fleet for Kinney Aviation. These owners and airplanes are demonstrations. Replace them with the live fleet.</p><button type="button" class="btn btn-ghost-dark" data-action="hide-demo">Dismiss</button>`;
}

async function loadCore() {
  const [dashboard, customers, aircraft, records, invoices] = await Promise.all([
    api("/api/dashboard"),
    api("/api/customers"),
    api("/api/aircraft"),
    api("/api/records"),
    api("/api/invoices"),
  ]);
  state.dashboard = dashboard;
  state.shop = dashboard.shop;
  state.customers = customers;
  state.aircraft = aircraft;
  state.records = records;
  state.invoices = invoices;
}

function go(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

function field(label, name, value, opts = {}) {
  const required = opts.required ? "required" : "";
  const span = opts.wide ? " span-2" : "";
  if (opts.type === "textarea") {
    return `<label class="${span.trim()}">${esc(label)}<textarea name="${name}" rows="${opts.rows || 4}" ${required}>${esc(value || "")}</textarea></label>`;
  }
  if (opts.type === "select") {
    const options = opts.options
      .map((option) => `<option value="${esc(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${esc(option.label)}</option>`)
      .join("");
    return `<label class="${span.trim()}">${esc(label)}<select name="${name}" ${required}>${options}</select></label>`;
  }
  const type = opts.type || "text";
  const extra = [
    required,
    opts.step ? `step="${opts.step}"` : "",
    opts.min != null ? `min="${opts.min}"` : "",
    opts.placeholder ? `placeholder="${esc(opts.placeholder)}"` : "",
    opts.readOnly ? "readonly" : "",
  ].filter(Boolean).join(" ");
  return `<label class="${span.trim()}">${esc(label)}<input name="${name}" type="${type}" value="${esc(value ?? "")}" ${extra}></label>`;
}

function optionsFrom(map) {
  return Object.entries(map).map(([value, label]) => ({ value, label }));
}

function customerOptions(selected) {
  return state.customers.map((customer) => ({
    value: String(customer.id),
    label: customer.name,
    selected: customer.id === selected,
  }));
}

function aircraftOptions(selected) {
  return state.aircraft.map((item) => ({
    value: String(item.id),
    label: `${item.registration} · ${item.make} ${item.model}`,
    selected: item.id === selected,
  }));
}

function selectOptions(options, selected) {
  return options
    .map((option) => {
      const isSelected = option.selected || String(option.value) === String(selected);
      return `<option value="${esc(option.value)}" ${isSelected ? "selected" : ""}>${esc(option.label)}</option>`;
    })
    .join("");
}

function openModal(title, body, onSubmit) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-form").innerHTML = `${body}<div class="modal-actions"><button type="button" class="btn btn-ghost-dark" data-action="close-modal">Cancel</button><button type="submit" class="btn btn-primary">Save</button></div>`;
  modalHandler = onSubmit;
  const modal = document.getElementById("modal");
  modal.hidden = false;
  const first = modal.querySelector("input, select, textarea");
  if (first) first.focus();
}

function closeModal() {
  document.getElementById("modal").hidden = true;
  modalHandler = null;
}

function modalError(message) {
  const form = document.getElementById("modal-form");
  let el = document.getElementById("modal-error");
  if (!el) {
    el = document.createElement("p");
    el.id = "modal-error";
    el.className = "form-error";
    form.prepend(el);
  }
  el.textContent = message;
}

async function run(action) {
  if (busy) return;
  busy = true;
  try {
    await action();
  } catch (error) {
    showFlash(error.message || "Something went wrong.");
  } finally {
    busy = false;
  }
}

function filteredRecords() {
  const query = state.filters.records.trim().toLowerCase();
  return state.records.filter((record) => {
    if (!query) return true;
    return [record.number, record.registration, record.title, record.customer_name, KINDS[record.kind]]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function filteredInvoices() {
  const query = state.filters.billing.trim().toLowerCase();
  return state.invoices.filter((invoice) => {
    if (!query) return true;
    return [invoice.number, invoice.registration, invoice.customer_name, invoice.record_number, invoice.status]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function recordsTable(rows) {
  if (!rows.length) return `<p class="empty">No work orders match.</p>`;
  const body = rows
    .map((record) => `
      <tr data-href="#records/${record.id}" tabindex="0">
        <td>${esc(record.number)}</td>
        <td class="reg">${esc(record.registration)}</td>
        <td>${esc(record.title)}${record.customer_name ? `<br><span class="muted">${esc(record.customer_name)}</span>` : ""}</td>
        <td>${esc(KINDS[record.kind] || record.kind)}</td>
        <td>${pill(record.status, RECORD_STATUSES)}</td>
        <td>${prettyDate(record.opened_on)}</td>
        <td class="money">${money(record.total_cents)}</td>
      </tr>`)
    .join("");
  return `<div class="table-wrap"><table>
    <thead><tr><th>Work order</th><th>Aircraft</th><th>Title</th><th>Kind</th><th>Status</th><th>Opened</th><th class="money">To bill</th></tr></thead>
    <tbody>${body}</tbody>
  </table></div>`;
}

function invoicesTable(rows) {
  if (!rows.length) return `<p class="empty">No invoices match.</p>`;
  const body = rows
    .map((invoice) => `
      <tr data-href="#billing/${invoice.id}" tabindex="0">
        <td>${esc(invoice.number)}</td>
        <td class="reg">${esc(invoice.registration)}</td>
        <td>${esc(invoice.customer_name)}${invoice.record_number ? `<br><span class="muted">${esc(invoice.record_number)}</span>` : ""}</td>
        <td>${pill(invoice.status, INVOICE_STATUSES)}</td>
        <td class="money">${money(invoice.total_cents)}</td>
        <td class="money">${invoice.status === "draft" || invoice.status === "void" ? "—" : money(invoice.amount_due_cents)}</td>
        <td>${prettyDate(invoice.due_on)}</td>
      </tr>`)
    .join("");
  return `<div class="table-wrap"><table>
    <thead><tr><th>Invoice</th><th>Aircraft</th><th>Owner</th><th>Status</th><th class="money">Total</th><th class="money">Due</th><th>Due date</th></tr></thead>
    <tbody>${body}</tbody>
  </table></div>`;
}

function renderBriefing() {
  const dash = state.dashboard;
  setHeader("Briefing", "Kinney Aviation", `<button type="button" class="btn btn-ghost-dark" data-action="edit-shop">Shop profile</button>`);
  const annuals = dash.annuals.length
    ? `<div class="table-wrap"><table><tbody>${dash.annuals.map((item) => `
        <tr data-href="#present/aircraft/${item.aircraft_id}" tabindex="0">
          <td class="reg">${esc(item.registration)}</td>
          <td>${esc(item.make)} ${esc(item.model)}<br><span class="muted">${esc(item.customer_name)} · ${esc(item.home_airport || "Arizona")}</span></td>
          <td class="${dueClass(item.days_remaining)}">${esc(dueLabel(item.days_remaining))}<br><span class="muted">${prettyDate(item.annual_due)}</span></td>
        </tr>`).join("")}</tbody></table></div>`
    : `<p class="empty">No annuals inside the next ${60} days.</p>`;
  const openInvoices = dash.open_invoices.length
    ? invoicesTable(dash.open_invoices.map((item) => ({
        ...item,
        record_number: "",
        due_on: item.due_on,
      })))
    : `<p class="empty">Nothing is waiting on payment.</p>`;
  document.getElementById("view").innerHTML = `
    <p class="lede" style="margin-bottom:1rem">Airframe, powerplant, and Arizona fly-to-you work, kept in one log. Billing reads the work order. The presentation is the same record, set for the owner.</p>
    <section class="stats">
      <article class="stat"><span class="stat-label">Open work</span><strong class="stat-value">${esc(dash.open_work)}</strong><span class="stat-meta">${esc(dash.awaiting_parts)} awaiting parts</span></article>
      <article class="stat"><span class="stat-label">Receivables</span><strong class="stat-value">${money(dash.receivables_cents)}</strong><span class="stat-meta">Issued and partial</span></article>
      <article class="stat"><span class="stat-label">Draft billing</span><strong class="stat-value">${money(dash.draft_cents)}</strong><span class="stat-meta">Not issued yet</span></article>
      <article class="stat"><span class="stat-label">Not yet billed</span><strong class="stat-value">${esc(dash.unbilled_count)}</strong><span class="stat-meta">Work orders with no invoice</span></article>
    </section>
    <div class="split">
      <section class="panel">
        <header class="panel-head"><h2>Recent work</h2><a href="#records">All records</a></header>
        ${recordsTable(dash.recent_records.map((item) => ({ ...item, customer_name: "" })))}
      </section>
      <section class="panel">
        <header class="panel-head"><h2>Annuals due</h2><a href="#fleet">Fleet</a></header>
        ${annuals}
      </section>
    </div>
    <div class="split">
      <section class="panel">
        <header class="panel-head"><h2>Money on the books</h2><a href="#billing">Billing</a></header>
        ${openInvoices}
      </section>
      <section class="panel">
        <header class="panel-head"><h2>What this shop signs</h2></header>
        <ul class="practice-list">
          <li><strong>Airframe.</strong> Structure, gear, flight controls, and the aircraft itself.</li>
          <li><strong>Powerplant.</strong> Engines, propellers, and the systems that run them.</li>
          <li><strong>Pilot-mechanic ferry.</strong> Fly to an Arizona field, do the work, and bring the airplane home.</li>
        </ul>
      </section>
    </div>`;
}

function renderRecords() {
  setHeader("Records", "Maintenance records", `<button type="button" class="btn btn-primary" data-action="new-record">New work order</button>`);
  document.getElementById("view").innerHTML = `
    <p class="lede" style="margin-bottom:0.8rem">Each work order holds the discrepancy, the corrective action, and the time and parts billing will use.</p>
    <div class="filters"><input data-filter="records" type="search" placeholder="Search work orders, N-numbers, owners" value="${esc(state.filters.records)}" aria-label="Search work orders"></div>
    <div id="filtered-list">${recordsTable(filteredRecords())}</div>`;
}

function lineTable(lines, kind, locked) {
  if (!lines.length) return `<p class="empty">None yet.</p>`;
  const rows = lines
    .map((line) => `
      <tr>
        <td>${kind === "part" && line.part_number ? `${esc(line.part_number)} — ` : ""}${esc(line.description)}</td>
        <td class="num">${kind === "part" ? esc(line.quantity) : hours(line.hours)}</td>
        <td class="money">${money(kind === "part" ? line.unit_price_cents : line.rate_cents)}</td>
        <td class="money">${money(line.amount_cents)}</td>
        <td>${locked ? "" : `<button type="button" class="btn btn-danger" data-action="delete-${kind}" data-id="${line.id}">Remove</button>`}</td>
      </tr>`)
    .join("");
  const qty = kind === "part" ? "Qty" : "Hours";
  const rate = kind === "part" ? "Price" : "Rate";
  return `<div class="table-wrap"><table><thead><tr><th>Description</th><th class="num">${qty}</th><th class="money">${rate}</th><th class="money">Amount</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

async function renderRecordDetail(id) {
  const record = await api(`/api/records/${id}`);
  const locked = Boolean(record.invoice && record.invoice.status !== "draft");
  setHeader(record.number, `${record.registration} · ${record.aircraft_label}`, `<a class="btn btn-ghost-dark" href="#present/record/${record.id}">Work sheet</a>`);
  const invoiceNote = !record.invoice
    ? `<button type="button" class="btn btn-primary" data-action="bill-record" data-id="${record.id}">Bill this work</button>`
    : `<a class="btn btn-brass" href="#billing/${record.invoice.id}">Open ${esc(record.invoice.number)}</a> ${record.invoice.stale ? `<button type="button" class="btn btn-primary" data-action="refresh-invoice" data-id="${record.invoice.id}">Refresh draft</button>` : ""}`;
  const stale = record.invoice && record.invoice.stale
    ? `<div class="callout"><p>The draft invoice is behind this work order. Refresh it before you issue.</p></div>`
    : "";
  const lockNote = locked
    ? `<div class="callout"><p>${esc(record.invoice.number)} is ${esc(record.invoice.status)}. Labor, parts, and travel stay as billed. You can still update the write-up.</p></div>`
    : "";
  const certButton = CERT[record.kind]
    ? `<button type="button" class="btn btn-ghost-dark" data-action="insert-rts" data-kind="${esc(record.kind)}">Insert certification wording</button>`
    : "";
  document.getElementById("view").innerHTML = `
    <p class="back"><a href="#records">All records</a></p>
    ${stale}${lockNote}
    <div class="split">
      <form class="panel stack" data-form="record" data-id="${record.id}">
        <header class="panel-head"><h2>${esc(record.title)}</h2>${pill(record.status, RECORD_STATUSES)}</header>
        <div class="form-grid">
          ${field("Title", "title", record.title, { required: true, wide: true })}
          ${field("Kind", "kind", record.kind, { type: "select", options: optionsFrom(KINDS) })}
          ${field("Status", "status", record.status, { type: "select", options: optionsFrom(RECORD_STATUSES) })}
          ${field("Discrepancy", "discrepancy", record.discrepancy, { type: "textarea", wide: true })}
          ${field("Corrective action", "corrective_action", record.corrective_action, { type: "textarea", wide: true })}
          ${field("Location", "location", record.location || "", { placeholder: "KFLG" })}
          ${field("Opened", "opened_on", record.opened_on || "", { type: "date", required: true })}
          ${field("Closed", "closed_on", record.closed_on || "", { type: "date" })}
          ${field("Tach", "tach_hours", record.tach_hours ?? "", { type: "number", step: "0.1", min: "0" })}
          ${field("Hobbs", "hobbs_hours", record.hobbs_hours ?? "", { type: "number", step: "0.1", min: "0" })}
          ${field("Rating", "rating", record.rating, { type: "select", options: optionsFrom(RATINGS) })}
          ${field("Travel hours", "travel_hours", hours(record.travel_hours) === "—" ? "0.0" : hours(record.travel_hours), { type: "number", step: "0.1", min: "0", readOnly: locked })}
          ${field("Sign-off", "signoff_name", record.signoff_name)}
          ${field("Certificate", "certificate_ref", record.certificate_ref)}
          ${field("Return to service", "rts_statement", record.rts_statement, { type: "textarea", wide: true, rows: 3 })}
          ${field("Notes", "notes", record.notes || "", { type: "textarea", wide: true, rows: 2 })}
        </div>
        <div class="row-actions">${certButton}<button type="submit" class="btn btn-brass">Save work order</button>${record.has_billing ? "" : `<button type="button" class="btn btn-danger" data-action="delete-record" data-id="${record.id}">Delete</button>`}</div>
      </form>
      <div class="stack">
        <section class="panel">
          <header class="panel-head"><h2>Labor</h2></header>
          ${lineTable(record.labor_lines, "labor", locked)}
          ${locked ? "" : `<form data-form="labor" data-id="${record.id}" class="form-grid" style="margin-top:0.8rem">
            ${field("Description", "description", "", { required: true, wide: true })}
            ${field("Hours", "hours", "1.0", { type: "number", step: "0.1", min: "0.1", required: true })}
            ${field("Rate", "rate", (record.labor_lines[0] ? record.labor_lines[0].rate_cents / 100 : state.shop.default_labor_rate_cents / 100).toFixed(2), { required: true })}
            <div class="span-2"><button type="submit" class="btn btn-ghost-dark">Add labor</button></div>
          </form>`}
        </section>
        <section class="panel">
          <header class="panel-head"><h2>Parts</h2></header>
          ${lineTable(record.part_lines, "part", locked)}
          ${locked ? "" : `<form data-form="part" data-id="${record.id}" class="form-grid" style="margin-top:0.8rem">
            ${field("Part number", "part_number", "")}
            ${field("Description", "description", "", { required: true })}
            ${field("Quantity", "quantity", "1", { required: true })}
            ${field("Unit price", "price", "", { required: true, placeholder: "42.50" })}
            <div class="span-2"><button type="submit" class="btn btn-ghost-dark">Add part</button></div>
          </form>`}
        </section>
        <section class="panel">
          <header class="panel-head"><h2>Billable total</h2></header>
          <dl class="totals">
            <dt>Labor</dt><dd>${money(record.labor_cents)}</dd>
            <dt>Parts</dt><dd>${money(record.parts_cents)}</dd>
            <dt>Travel · ${money(record.travel_rate_cents)}/hr</dt><dd>${money(record.travel_cents)}</dd>
            <dt class="grand">Work order</dt><dd class="grand">${money(record.total_cents)}</dd>
          </dl>
          <div class="row-actions" style="margin-top:0.8rem">${invoiceNote}</div>
        </section>
      </div>
    </div>`;
}

function renderBilling() {
  setHeader("Billing", "Integrated billing", "");
  document.getElementById("view").innerHTML = `
    <p class="lede" style="margin-bottom:0.8rem">Invoices are built from the labor, parts, and travel already on a work order.</p>
    <div class="filters"><input data-filter="billing" type="search" placeholder="Search invoices" value="${esc(state.filters.billing)}" aria-label="Search invoices"></div>
    <div id="filtered-list">${invoicesTable(filteredInvoices())}</div>`;
}

async function renderInvoiceDetail(id) {
  const invoice = await api(`/api/invoices/${id}`);
  const draft = invoice.status === "draft";
  const open = invoice.status === "issued" || invoice.status === "partial";
  setHeader(invoice.number, `${invoice.registration} · ${invoice.customer_name}`, `<a class="btn btn-primary" href="#present/invoice/${invoice.id}">Present invoice</a>`);
  const rows = invoice.lines.map((line) => `
    <tr>
      <td>${esc({ labor: "Labor", part: "Part", travel: "Travel" }[line.kind] || line.kind)} · ${esc(line.description)}</td>
      <td class="num">${lineQty(line)}</td>
      <td class="money">${money(line.unit_cents)}</td>
      <td class="money">${money(line.amount_cents)}</td>
    </tr>`).join("");
  const payments = invoice.payments.length
    ? `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Method</th><th>Reference</th><th class="money">Amount</th><th></th></tr></thead><tbody>
        ${invoice.payments.map((payment) => `<tr>
          <td>${prettyDate(payment.paid_on)}</td>
          <td>${esc(METHODS[payment.method] || payment.method)}</td>
          <td>${esc(payment.reference || "—")}</td>
          <td class="money">${money(payment.amount_cents)}</td>
          <td>${invoice.status === "void" ? "" : `<button type="button" class="btn btn-danger" data-action="delete-payment" data-id="${payment.id}">Remove</button>`}</td>
        </tr>`).join("")}
      </tbody></table></div>`
    : `<p class="empty">No payments yet.</p>`;
  document.getElementById("view").innerHTML = `
    <p class="back"><a href="#billing">All invoices</a> · <a href="#records/${invoice.record_id}">${esc(invoice.record_number)}</a></p>
    ${invoice.stale ? `<div class="callout"><p>This draft does not match the work order anymore.</p></div>` : ""}
    <div class="split">
      <section class="panel">
        <header class="panel-head"><h2>${esc(invoice.record_title)}</h2>${pill(invoice.status, INVOICE_STATUSES)}</header>
        <div class="table-wrap"><table>
          <thead><tr><th>Line</th><th class="num">Qty</th><th class="money">Rate</th><th class="money">Amount</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="4">No lines.</td></tr>`}</tbody>
        </table></div>
        <dl class="totals" style="margin-top:0.8rem">
          <dt>Subtotal</dt><dd>${money(invoice.subtotal_cents)}</dd>
          <dt>Tax</dt><dd>${money(invoice.tax_cents)}</dd>
          <dt>Paid</dt><dd>${money(invoice.paid_cents)}</dd>
          <dt class="grand">Balance</dt><dd class="grand">${money(invoice.balance_cents)}</dd>
        </dl>
      </section>
      <div class="stack">
        <form class="panel stack" data-form="invoice-meta" data-id="${invoice.id}">
          <h2>Invoice details</h2>
          ${field("Notes", "notes", invoice.notes, { type: "textarea", rows: 3 })}
          ${field("Tax", "tax", (invoice.tax_cents / 100).toFixed(2), { readOnly: !draft })}
          ${field("Due date", "due_on", invoice.due_on || "", { type: "date" })}
          <button type="submit" class="btn btn-ghost-dark">Save details</button>
        </form>
        <section class="panel">
          <header class="panel-head"><h2>Payments</h2></header>
          ${payments}
          ${open ? `<form data-form="payment" data-id="${invoice.id}" class="form-grid" style="margin-top:0.8rem">
            ${field("Amount", "amount", (invoice.amount_due_cents / 100).toFixed(2), { required: true })}
            ${field("Date", "paid_on", todayISO(), { type: "date", required: true })}
            ${field("Method", "method", "check", { type: "select", options: optionsFrom(METHODS) })}
            ${field("Reference", "reference", "")}
            <div class="span-2"><button type="submit" class="btn btn-primary">Record payment</button></div>
          </form>` : ""}
        </section>
        <div class="row-actions">
          ${draft ? `<button type="button" class="btn btn-primary" data-action="issue-invoice" data-id="${invoice.id}">Issue invoice</button>` : ""}
          ${draft && invoice.stale ? `<button type="button" class="btn btn-brass" data-action="refresh-invoice" data-id="${invoice.id}">Refresh from work order</button>` : ""}
          ${invoice.status !== "void" && invoice.payments.length === 0 ? `<button type="button" class="btn btn-danger" data-action="void-invoice" data-id="${invoice.id}">Void</button>` : ""}
        </div>
      </div>
    </div>`;
}

function fleetCards(list) {
  if (!list.length) return `<p class="empty">No aircraft match.</p>`;
  return `<div class="cards">${list.map((item) => `
    <a class="aircraft-card" href="#fleet/${item.id}">
      <div class="reg">${esc(item.registration)}</div>
      <p>${esc(item.make)} ${esc(item.model)}${item.home_airport ? ` · ${esc(item.home_airport)}` : ""}</p>
      <p>${esc(item.customer_name)}</p>
      <p class="${dueClass(item.days_to_annual)}">${esc(dueLabel(item.days_to_annual))}</p>
      <p>${item.open_record_count ? `${esc(item.open_record_count)} open` : "No open squawks"} · ${item.balance_cents ? money(item.balance_cents) + " due" : "No balance"}</p>
    </a>`).join("")}</div>`;
}

function fleetBody() {
  const query = state.filters.fleet.trim().toLowerCase();
  const aircraft = state.aircraft.filter((item) => {
    if (!query) return true;
    return [item.registration, item.make, item.model, item.customer_name, item.home_airport].join(" ").toLowerCase().includes(query);
  });
  const owners = state.customers.filter((customer) => {
    if (!query) return true;
    return [customer.name, customer.city, customer.email].join(" ").toLowerCase().includes(query);
  });
  return `
    <div class="split">
      <section class="panel"><header class="panel-head"><h2>Aircraft</h2></header>${fleetCards(aircraft)}</section>
      <section class="panel">
        <header class="panel-head"><h2>Owners</h2></header>
        ${owners.length ? `<div class="table-wrap"><table><tbody>${owners.map((customer) => `
          <tr>
            <td><strong>${esc(customer.name)}</strong><br><span class="muted">${esc(customer.city || "Arizona")} · ${esc(customer.aircraft_count)} aircraft</span></td>
            <td><button type="button" class="btn btn-ghost-dark" data-action="edit-customer" data-id="${customer.id}">Edit</button></td>
          </tr>`).join("")}</tbody></table></div>` : `<p class="empty">No owners match.</p>`}
      </section>
    </div>`;
}

function renderFleet() {
  setHeader("Fleet", "Owners and aircraft", `<button type="button" class="btn btn-ghost-dark" data-action="new-customer">New owner</button><button type="button" class="btn btn-primary" data-action="new-aircraft">New aircraft</button>`);
  document.getElementById("view").innerHTML = `
    <div class="filters"><input data-filter="fleet" type="search" placeholder="Search the fleet" value="${esc(state.filters.fleet)}" aria-label="Search the fleet"></div>
    <div id="filtered-list">${fleetBody()}</div>`;
}

async function renderAircraftDetail(id) {
  const aircraft = state.aircraft.find((item) => item.id === Number(id)) || await api(`/api/aircraft/${id}`);
  const records = state.records.filter((record) => record.aircraft_id === aircraft.id);
  setHeader(aircraft.registration, `${aircraft.make} ${aircraft.model}`, `<a class="btn btn-primary" href="#present/aircraft/${aircraft.id}">Open briefing</a>`);
  document.getElementById("view").innerHTML = `
    <p class="back"><a href="#fleet">Fleet</a></p>
    <div class="split">
      <section class="panel">
        <header class="panel-head"><h2>${esc(aircraft.customer_name)}</h2><button type="button" class="btn btn-ghost-dark" data-action="edit-aircraft" data-id="${aircraft.id}">Edit aircraft</button></header>
        <div class="fact-grid">
          <div class="fact"><span>Home</span><strong>${esc(aircraft.home_airport || "—")}</strong></div>
          <div class="fact"><span>Tach</span><strong>${hours(aircraft.tach_hours)}</strong></div>
          <div class="fact"><span>Annual</span><strong class="${dueClass(aircraft.days_to_annual)}">${esc(dueLabel(aircraft.days_to_annual))}</strong></div>
          <div class="fact"><span>Serial</span><strong>${esc(aircraft.serial_number || "—")}</strong></div>
          <div class="fact"><span>Engine</span><strong>${esc(aircraft.engine_model || "—")}</strong></div>
          <div class="fact"><span>Balance</span><strong>${money(aircraft.balance_cents)}</strong></div>
        </div>
        <p class="muted">${esc(aircraft.notes || "")}</p>
        <div class="row-actions">
          <button type="button" class="btn btn-primary" data-action="new-record" data-aircraft="${aircraft.id}">New work order</button>
          ${records.length ? "" : `<button type="button" class="btn btn-danger" data-action="delete-aircraft" data-id="${aircraft.id}">Delete aircraft</button>`}
        </div>
      </section>
      <section class="panel">
        <header class="panel-head"><h2>Work on this aircraft</h2></header>
        ${recordsTable(records)}
      </section>
    </div>`;
}

function renderPresentIndex() {
  setHeader("Present", "Presentation layer", "");
  const aircraft = state.aircraft.map((item) => `
    <a class="aircraft-card" href="#present/aircraft/${item.id}">
      <div class="reg">${esc(item.registration)}</div>
      <p>${esc(item.make)} ${esc(item.model)} · ${esc(item.customer_name)}</p>
      <p>Owner briefing</p>
    </a>`).join("");
  document.getElementById("view").innerHTML = `
    <p class="lede" style="margin-bottom:1rem">Briefings, work sheets, and invoices read the same records. Nothing is retyped for the owner.</p>
    <div class="stats">
      <article class="stat"><span class="stat-label">Briefing</span><strong class="stat-value">Aircraft</strong><span class="stat-meta">Times, annual, open squawks, balance</span></article>
      <article class="stat"><span class="stat-label">Work sheet</span><strong class="stat-value">Record</strong><span class="stat-meta">Discrepancy, action, sign-off</span></article>
      <article class="stat"><span class="stat-label">Invoice</span><strong class="stat-value">Bill</strong><span class="stat-meta">The work order, priced</span></article>
    </div>
    <section class="panel" style="margin-bottom:0.75rem"><header class="panel-head"><h2>Aircraft briefings</h2></header><div class="cards">${aircraft}</div></section>
    <section class="panel"><header class="panel-head"><h2>Invoices</h2></header>${invoicesTable(state.invoices)}</section>`;
}

function sheetHead(kicker) {
  const shop = state.shop;
  const today = new Date();
  const stamp = `${today.getDate()} ${MONTHS[today.getMonth()]} ${today.getFullYear()}`;
  return `
    <header class="sheet-head">
      <div>
        <p class="sheet-brand">${esc(shop.business_name)}</p>
        <p class="sheet-kicker">${esc(shop.certificate_label)} · ${esc(shop.base_city)}</p>
      </div>
      <p class="sheet-meta"><strong>${esc(kicker)}</strong>${esc(stamp)}<br>${esc(shop.phone || "")}<br>${esc(shop.email || "")}</p>
    </header>
    <hr class="brass-rule">`;
}

function renderAircraftSheet(data) {
  const aircraft = data.aircraft;
  document.title = `${aircraft.registration} briefing · Kinney Aviation`;
  const open = data.open_items.length
    ? data.open_items.map((item) => `
        <article class="discrepancy">
          <h3>${esc(item.number)} · ${esc(KINDS[item.kind] || item.kind)} · ${esc(RECORD_STATUSES[item.status] || item.status)}</h3>
          <p>${esc(item.discrepancy || item.title)}</p>
        </article>`).join("")
    : `<p class="empty">No open discrepancies.</p>`;
  const log = data.logbook.map((item) => `
    <tr>
      <td>${prettyDate(item.closed_on || item.opened_on)}</td>
      <td>${esc(item.number)}</td>
      <td>${esc(KINDS[item.kind] || item.kind)}</td>
      <td>${esc(item.corrective_action || item.discrepancy || item.title)}</td>
      <td>${esc(item.signoff_name || "—")}</td>
    </tr>`).join("");
  const moneyRows = data.invoices.filter((invoice) => invoice.status !== "void");
  const openBalance = moneyRows.reduce((sum, invoice) => sum + invoice.balance_cents, 0);
  document.getElementById("view").innerHTML = `
    <div class="present-toolbar no-print">
      <a class="btn btn-ghost-dark" href="#present">All presentations</a>
      <a class="btn btn-ghost-dark" href="#fleet/${aircraft.id}">Back to fleet</a>
      <button type="button" class="btn btn-primary" data-action="print">Print</button>
    </div>
    <article class="sheet">
      ${sheetHead("Aircraft briefing")}
      <h2 class="sheet-reg">${esc(aircraft.registration)}</h2>
      <p class="sheet-sub">${esc(aircraft.year_manufactured || "")} ${esc(aircraft.make)} ${esc(aircraft.model)}${aircraft.serial_number ? ` · S/N ${esc(aircraft.serial_number)}` : ""}${aircraft.home_airport ? ` · ${esc(aircraft.home_airport)}` : ""}</p>
      <div class="fact-grid">
        <div class="fact"><span>Owner</span><strong>${esc(aircraft.customer_name)}</strong></div>
        <div class="fact"><span>Tach / Hobbs</span><strong>${hours(aircraft.tach_hours)} / ${hours(aircraft.hobbs_hours)}</strong></div>
        <div class="fact"><span>Annual</span><strong class="${dueClass(aircraft.days_to_annual)}">${esc(dueLabel(aircraft.days_to_annual))}</strong></div>
        <div class="fact"><span>Engine</span><strong>${esc(aircraft.engine_model || "—")}</strong></div>
        <div class="fact"><span>Total time</span><strong>${hours(aircraft.total_time_hours)}</strong></div>
        <div class="fact"><span>Open balance</span><strong>${money(openBalance)}</strong></div>
      </div>
      <h3>Open items</h3>
      ${open}
      <h3 style="margin-top:1rem">Log</h3>
      <div class="table-wrap"><table class="logbook"><thead><tr><th>Date</th><th>Work order</th><th>Kind</th><th>Entry</th><th>Signed</th></tr></thead><tbody>${log}</tbody></table></div>
      <h3 style="margin-top:1rem">Account</h3>
      ${moneyRows.length ? `<div class="table-wrap"><table><thead><tr><th>Invoice</th><th>Status</th><th class="money">Total</th><th class="money">Due</th></tr></thead><tbody>
        ${moneyRows.map((invoice) => `<tr><td>${esc(invoice.number)}</td><td>${esc(INVOICE_STATUSES[invoice.status] || invoice.status)}</td><td class="money">${money(invoice.total_cents)}</td><td class="money">${money(invoice.balance_cents)}</td></tr>`).join("")}
      </tbody></table></div>` : `<p class="empty">No invoices on file.</p>`}
      <p class="muted" style="margin-top:1rem">Working record for ${esc(data.shop.mechanic_name)}. The aircraft logbook remains the official record.</p>
    </article>`;
}

function renderRecordSheet(data) {
  const record = data.record;
  document.title = `${record.number} work sheet · Kinney Aviation`;
  document.getElementById("view").innerHTML = `
    <div class="present-toolbar no-print">
      <a class="btn btn-ghost-dark" href="#records/${record.id}">Back to work order</a>
      <button type="button" class="btn btn-primary" data-action="print">Print</button>
    </div>
    <article class="sheet">
      ${sheetHead("Work sheet")}
      <p class="muted">${esc(record.number)} · ${prettyDate(record.opened_on)}${record.closed_on ? ` – ${prettyDate(record.closed_on)}` : ""}</p>
      <h2 class="sheet-reg">${esc(record.registration)}</h2>
      <p class="sheet-sub">${esc(record.aircraft_label)} · ${esc(record.customer_name)} · ${esc(KINDS[record.kind] || record.kind)}</p>
      <div class="fact-grid">
        <div class="fact"><span>Location</span><strong>${esc(record.location || "—")}</strong></div>
        <div class="fact"><span>Tach</span><strong>${hours(record.tach_hours)}</strong></div>
        <div class="fact"><span>Rating</span><strong>${esc(ratingLabel(record.rating))}</strong></div>
      </div>
      <article class="discrepancy"><h3>Discrepancy</h3><p>${esc(record.discrepancy || record.title)}</p></article>
      <article class="discrepancy"><h3>Corrective action</h3><p>${esc(record.corrective_action || "—")}</p></article>
      <h3>Labor and parts</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Item</th><th class="num">Qty</th><th class="money">Amount</th></tr></thead>
        <tbody>
          ${record.labor_lines.map((line) => `<tr><td>Labor · ${esc(line.description)}</td><td class="num">${hours(line.hours)}</td><td class="money">${money(line.amount_cents)}</td></tr>`).join("")}
          ${record.part_lines.map((line) => `<tr><td>${line.part_number ? esc(line.part_number) + " · " : ""}${esc(line.description)}</td><td class="num">${esc(line.quantity)}</td><td class="money">${money(line.amount_cents)}</td></tr>`).join("")}
          ${record.travel_cents ? `<tr><td>Pilot-mechanic travel</td><td class="num">${hours(record.travel_hours)}</td><td class="money">${money(record.travel_cents)}</td></tr>` : ""}
        </tbody>
      </table></div>
      <p style="text-align:right;font-family:var(--display);font-size:1.3rem">${money(record.total_cents)}</p>
      <div class="signoff">
        <div>
          <p>${esc(record.rts_statement || "Return to service statement not entered.")}</p>
          <div class="sign-line"></div>
          <p class="muted">${esc(record.signoff_name || data.shop.mechanic_name)} · ${esc(record.certificate_ref || data.shop.certificate_label)}</p>
        </div>
        <p class="muted">Status: ${esc(RECORD_STATUSES[record.status] || record.status)}. This sheet is the shop copy. The aircraft logbook remains the official record.</p>
      </div>
    </article>`;
}

function renderInvoiceSheet(data) {
  const invoice = data.invoice;
  document.title = `${invoice.number} · Kinney Aviation`;
  const stamp = invoice.status === "paid"
    ? `<div class="stamp">PAID</div>`
    : invoice.status === "void"
      ? `<div class="stamp stamp-void">VOID</div>`
      : "";
  document.getElementById("view").innerHTML = `
    <div class="present-toolbar no-print">
      <a class="btn btn-ghost-dark" href="#billing/${invoice.id}">Back to invoice</a>
      <button type="button" class="btn btn-primary" data-action="print">Print</button>
    </div>
    <article class="sheet">
      ${stamp}
      ${sheetHead("Invoice")}
      <div class="sheet-head">
        <div>
          <h2 class="sheet-reg" style="font-size:clamp(2rem,5vw,3rem)">${esc(invoice.number)}</h2>
          <p class="sheet-sub">${esc(invoice.customer_name)}<br>${esc(invoice.registration)} · ${esc(invoice.aircraft_label)}<br>${esc(invoice.record_number)} · ${esc(invoice.record_title)}</p>
        </div>
        <p class="sheet-meta"><strong>${esc(INVOICE_STATUSES[invoice.status] || invoice.status)}</strong>Issued ${prettyDate(invoice.issued_on)}<br>Due ${prettyDate(invoice.due_on)}</p>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>Description</th><th class="num">Qty</th><th class="money">Rate</th><th class="money">Amount</th></tr></thead>
        <tbody>${invoice.lines.map((line) => `<tr><td>${esc(line.description)}</td><td class="num">${lineQty(line)}</td><td class="money">${money(line.unit_cents)}</td><td class="money">${money(line.amount_cents)}</td></tr>`).join("")}</tbody>
      </table></div>
      <dl class="totals">
        <dt>Subtotal</dt><dd>${money(invoice.subtotal_cents)}</dd>
        <dt>Tax</dt><dd>${money(invoice.tax_cents)}</dd>
        <dt>Paid</dt><dd>${money(invoice.paid_cents)}</dd>
      </dl>
      <div class="amount-due"><span>${invoice.status === "draft" ? "Draft total" : "Amount due"}</span><strong>${money(invoice.status === "draft" ? invoice.total_cents : invoice.amount_due_cents)}</strong></div>
      ${invoice.notes ? `<p style="margin-top:0.8rem">${esc(invoice.notes)}</p>` : ""}
      <p class="muted" style="margin-top:1rem">Payable to ${esc(data.shop.business_name)}. ${esc(data.shop.mechanic_name)} · ${esc(data.shop.certificate_label)}.</p>
    </article>`;
}

function isoFromParts(year, monthIndex, day) {
  return `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function parseISODate(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
}

function shiftMonth(iso, delta) {
  const date = parseISODate(iso) || new Date();
  const target = new Date(date.getFullYear(), date.getMonth() + delta, 1);
  const last = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  return isoFromParts(target.getFullYear(), target.getMonth(), Math.min(date.getDate(), last));
}

function monthCells(anchor) {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const start = new Date(first);
  start.setDate(1 - first.getDay());
  const cells = [];
  for (let index = 0; index < 42; index += 1) {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    cells.push(day);
  }
  return cells;
}

function applySession() {
  const session = document.getElementById("rail-session");
  const adminLink = document.querySelector("[data-nav=admin]");
  const brand = document.getElementById("brand");
  const admin = Boolean(state.user && state.user.role === "admin");
  adminLink.hidden = !admin;
  document.querySelectorAll("[data-shop]").forEach((link) => {
    link.hidden = admin;
  });
  if (brand) brand.setAttribute("href", admin ? "#admin" : "#briefing");
  if (!state.user) {
    session.hidden = true;
    return;
  }
  document.getElementById("rail-user").textContent = state.user.display_name;
  document.getElementById("rail-role").textContent = admin ? "Administrator" : "Shop";
  session.hidden = false;
  document.getElementById("app").hidden = false;
  document.getElementById("login").hidden = true;
  document.body.classList.remove("is-login");
}

function showLogin(note) {
  signedIn = false;
  state.user = null;
  document.body.classList.add("is-login");
  document.body.classList.remove("is-presenting");
  document.getElementById("app").hidden = true;
  const login = document.getElementById("login");
  login.hidden = false;
  const error = document.getElementById("login-error");
  error.hidden = true;
  error.textContent = "";
  const noteEl = document.getElementById("login-note");
  noteEl.hidden = !note;
  noteEl.textContent = note || "";
  const flash = document.getElementById("flash");
  flash.hidden = true;
  flash.textContent = "";
  pendingFlash = "";
  const username = login.querySelector("[name=username]");
  if (username) username.focus();
}

function showApp() {
  signedIn = true;
  applySession();
}

function dayItem(item) {
  const when = item.starts_at ? `${item.starts_at} · ` : "";
  const title = item.href ? `<a href="${esc(item.href)}">${esc(item.title)}</a>` : esc(item.title);
  const remove = item.editable
    ? `<button type="button" class="btn btn-danger" data-action="delete-entry" data-id="${item.entry_id}">Remove</button>`
    : "";
  return `<article class="day-item">
    <p class="day-meta">${esc(when)}${esc(SOURCE_LABEL[item.source] || item.source)}</p>
    <h3>${title}</h3>
    ${item.detail ? `<p>${esc(item.detail)}</p>` : ""}
    ${remove}
  </article>`;
}

async function renderCalendar(iso) {
  const selectedDate = parseISODate(iso) || parseISODate(todayISO());
  const selected = isoFromParts(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate());
  const cells = monthCells(selectedDate);
  const start = isoFromParts(cells[0].getFullYear(), cells[0].getMonth(), cells[0].getDate());
  const endDate = cells[cells.length - 1];
  const end = isoFromParts(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
  const calendar = await api(`/api/calendar?start=${start}&end=${end}`);
  const byDay = {};
  for (const item of calendar.items) {
    if (!byDay[item.date]) byDay[item.date] = [];
    byDay[item.date].push(item);
  }
  setHeader("Calendar", "Shop schedule", `<button type="button" class="btn btn-ghost-dark" data-action="cal-open" data-date="${todayISO()}">Today</button>`);
  const dow = WEEKDAYS_SHORT.map((name) => `<div class="cal-dow">${name}</div>`).join("");
  const grid = cells.map((day) => {
    const key = isoFromParts(day.getFullYear(), day.getMonth(), day.getDate());
    const items = byDay[key] || [];
    const chips = items.slice(0, 3).map((item) => `<span class="cal-chip cal-${esc(item.kind)}">${esc(item.label)}</span>`).join("");
    const more = items.length > 3 ? `<span class="cal-more">+${items.length - 3} more</span>` : "";
    const outside = day.getMonth() === selectedDate.getMonth() ? "" : " is-outside";
    const today = key === todayISO() ? " is-today" : "";
    const current = key === selected ? " is-selected" : "";
    const count = items.length === 1 ? "1 item" : `${items.length} items`;
    return `<button type="button" class="cal-day${outside}${today}${current}" data-action="cal-open" data-date="${key}" aria-pressed="${current ? "true" : "false"}" aria-label="${day.getDate()} ${MONTH_LONG[day.getMonth()]}, ${count}"><span class="cal-num">${day.getDate()}</span>${chips}${more}</button>`;
  }).join("");
  const dayItems = byDay[selected] || [];
  const list = dayItems.length
    ? `<div class="day-list">${dayItems.map(dayItem).join("")}</div>`
    : `<p class="empty">Nothing on this day yet. Add the visit, inspection, or parts run.</p>`;
  const heading = `${WEEKDAYS[selectedDate.getDay()]}, ${selectedDate.getDate()} ${MONTH_LONG[selectedDate.getMonth()]} ${selectedDate.getFullYear()}`;
  const aircraftChoices = [{ value: "", label: "No aircraft" }].concat(aircraftOptions());
  document.getElementById("view").innerHTML = `
    <div class="calendar-layout">
      <section class="panel">
        <div class="cal-toolbar">
          <h2>${esc(`${MONTH_LONG[selectedDate.getMonth()]} ${selectedDate.getFullYear()}`)}</h2>
          <div class="cal-nav">
            <button type="button" class="btn btn-ghost-dark" data-action="cal-open" data-date="${shiftMonth(selected, -1)}">Previous</button>
            <button type="button" class="btn btn-ghost-dark" data-action="cal-open" data-date="${shiftMonth(selected, 1)}">Next</button>
          </div>
        </div>
        <p class="cal-legend">
          <span><i class="swatch swatch-visit"></i> Scheduled</span>
          <span><i class="swatch swatch-work"></i> Work opened</span>
          <span><i class="swatch swatch-annual"></i> Annual due</span>
          <span><i class="swatch swatch-due"></i> Invoice due</span>
        </p>
        <div class="cal-grid">${dow}${grid}</div>
      </section>
      <section class="panel">
        <header class="panel-head"><h2>${esc(heading)}</h2></header>
        ${list}
        <form data-form="schedule" data-date="${selected}">
          <div class="form-grid">
            ${field("Title", "title", "", { required: true, wide: true, placeholder: "Fly to Flagstaff" })}
            <label>Kind<select name="kind">${selectOptions(optionsFrom(SCHEDULE_KINDS), "visit")}</select></label>
            <label>Aircraft<select name="aircraft_id">${selectOptions(aircraftChoices, "")}</select></label>
            ${field("Time", "starts_at", "", { type: "time" })}
            ${field("Notes", "notes", "", { type: "textarea", wide: true, rows: 2 })}
          </div>
          <div class="row-actions"><button type="submit" class="btn btn-primary">Add to this day</button></div>
        </form>
      </section>
    </div>`;
}

async function exportShop() {
  const response = await fetch("/api/admin/export", { headers: { "X-Kinney-Request": "1" } });
  if (response.status === 401) {
    showLogin();
    throw new Error("Sign in required.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(errorMessage(data, "Export failed."));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "kinney-aviation-backup.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  showFlash("Shop file downloaded. Keep it private. It includes password hashes.", "ok");
}

async function renderAdmin() {
  setHeader("Admin", "Shop administration");
  if (!state.user || state.user.role !== "admin") {
    document.getElementById("view").innerHTML = `<section class="panel"><p>The administrator page is for managing who can sign in.</p></section>`;
    return;
  }
  const users = await api("/api/admin/users");
  const activeAdmins = users.filter((user) => user.role === "admin" && user.active);
  const lastAdminId = activeAdmins.length === 1 ? activeAdmins[0].id : null;
  const rows = users.map((user) => {
    const locked = user.id === lastAdminId;
    const roleButton = locked
      ? ""
      : `<button type="button" class="btn btn-ghost-dark" data-action="set-role" data-id="${user.id}" data-role="${user.role === "admin" ? "shop" : "admin"}">${user.role === "admin" ? "Make shop" : "Make administrator"}</button>`;
    const activeButton = locked
      ? ""
      : `<button type="button" class="btn btn-ghost-dark" data-action="set-active" data-id="${user.id}" data-active="${user.active ? "false" : "true"}">${user.active ? "Deactivate" : "Activate"}</button>`;
    return `<tr>
      <td><strong>${esc(user.display_name)}</strong><br><span class="muted">${esc(user.username)}</span></td>
      <td>${user.role === "admin" ? "Administrator" : "Shop"}</td>
      <td>${user.active ? "Active" : "Inactive"}</td>
      <td>
        <button type="button" class="btn btn-ghost-dark" data-action="reset-password" data-id="${user.id}" data-name="${esc(user.display_name)}">Reset password</button>
        ${roleButton}
        ${activeButton}
      </td>
    </tr>`;
  }).join("");
  document.getElementById("view").innerHTML = `
    <section class="panel">
      <header class="panel-head"><h2>Shop file</h2></header>
      <p class="backup-note">Export every owner, aircraft, work order, invoice, calendar entry, shop profile, and sign-in account. The file includes password hashes, so keep it private. Import replaces the shop with that file.</p>
      <div class="row-actions">
        <button type="button" class="btn btn-primary" data-action="export-data">Export all data</button>
      </div>
      <form data-form="import-shop">
        <div class="form-grid">
          <label class="span-2">Import file
            <input type="file" name="file" accept="application/json,.json" required />
          </label>
        </div>
        <div class="row-actions"><button class="btn btn-brass" type="submit">Import all data</button></div>
      </form>
    </section>
    <section class="panel">
      <header class="panel-head"><h2>New account</h2></header>
      <form data-form="new-user">
        <div class="form-grid">
          ${field("Name", "display_name", "", { required: true })}
          ${field("Username", "username", "", { required: true, placeholder: "dispatch" })}
          ${field("Password", "password", "", { type: "password", required: true, wide: true })}
          <label>Role<select name="role">${selectOptions([{ value: "shop", label: "Shop" }, { value: "admin", label: "Administrator" }], "shop")}</select></label>
        </div>
        <div class="row-actions"><button class="btn btn-primary" type="submit">Add account</button></div>
      </form>
    </section>
    <section class="panel">
      <header class="panel-head"><h2>Accounts</h2></header>
      <div class="table-wrap"><table class="account-table"><thead><tr><th>Person</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    </section>`;
}

function openPasswordModal() {
  openModal("Change password", `
    <div class="form-grid">
      ${field("Current password", "current_password", "", { type: "password", required: true, wide: true })}
      ${field("New password", "new_password", "", { type: "password", required: true, wide: true })}
      ${field("Confirm new password", "confirm_password", "", { type: "password", required: true, wide: true })}
    </div>`, async (data) => {
    if (data.get("new_password") !== data.get("confirm_password")) throw new Error("Those new passwords do not match.");
    const result = await api("/api/account/password", {
      method: "POST",
      body: { current_password: data.get("current_password"), new_password: data.get("new_password") },
    });
    showLogin(result.message || "Password updated. Sign in again.");
  });
}

function openResetModal(id, name) {
  openModal(`Reset password for ${name}`, `
    <div class="form-grid">
      ${field("New password", "password", "", { type: "password", required: true, wide: true })}
    </div>`, async (data) => {
    const saved = await api(`/api/admin/users/${id}`, { method: "PATCH", body: { password: data.get("password") } });
    if (saved && saved.signed_out) showLogin("Password updated. Sign in again.");
    else {
      showFlash("Password updated.", "ok");
      render();
    }
  });
}

async function renderPresent(parts) {
  if (!parts.length) {
    document.body.classList.remove("is-presenting");
    renderPresentIndex();
    return;
  }
  document.body.classList.add("is-presenting");
  const [kind, id] = parts;
  if (kind === "aircraft") renderAircraftSheet(await api(`/api/present/aircraft/${id}`));
  else if (kind === "record") renderRecordSheet(await api(`/api/present/records/${id}`));
  else if (kind === "invoice") renderInvoiceSheet(await api(`/api/present/invoices/${id}`));
  else {
    document.body.classList.remove("is-presenting");
    renderPresentIndex();
  }
}

async function render() {
  if (state.user && state.user.role === "admin" && parseRoute().name !== "admin") {
    document.body.classList.remove("is-presenting");
    if (location.hash !== "#admin") location.hash = "#admin";
    return;
  }
  const token = ++renderToken;
  const route = parseRoute();
  const presenting = route.name === "present" && route.parts.length > 0;
  document.body.classList.toggle("is-presenting", presenting);
  applySession();
  setNav(route.name);
  const view = document.getElementById("view");
  if (!view.dataset.loaded) view.innerHTML = `<p class="muted">Loading the shop…</p>`;
  try {
    if (route.name === "admin") {
      const banner = document.getElementById("banner");
      banner.hidden = true;
      banner.innerHTML = "";
      await renderAdmin();
    } else {
      await loadCore();
      if (token !== renderToken) return;
      renderBanner();
      if (route.name === "briefing") renderBriefing();
      else if (route.name === "records" && route.parts[0]) await renderRecordDetail(route.parts[0]);
      else if (route.name === "records") renderRecords();
      else if (route.name === "billing" && route.parts[0]) await renderInvoiceDetail(route.parts[0]);
      else if (route.name === "billing") renderBilling();
      else if (route.name === "fleet" && route.parts[0]) await renderAircraftDetail(route.parts[0]);
      else if (route.name === "fleet") renderFleet();
      else if (route.name === "calendar") await renderCalendar(route.parts[0]);
      else if (route.name === "present") await renderPresent(route.parts);
    }
    if (token !== renderToken) return;
    view.dataset.loaded = "1";
    if (pendingFlash) {
      showFlash(pendingFlash, "ok");
      pendingFlash = "";
    }
  } catch (error) {
    if (token !== renderToken || !signedIn) return;
    view.innerHTML = `<p class="form-error">${esc(error.message || "The shop could not be loaded.")}</p>`;
  }
}

function openCustomerModal(customer) {
  openModal(customer ? "Edit owner" : "New owner", `
    <div class="form-grid">
      ${field("Name", "name", customer ? customer.name : "", { required: true, wide: true })}
      ${field("Email", "email", customer ? customer.email || "" : "", { type: "email" })}
      ${field("Phone", "phone", customer ? customer.phone || "" : "")}
      ${field("City", "city", customer ? customer.city || "" : "", { wide: true })}
      ${field("Notes", "notes", customer ? customer.notes || "" : "", { type: "textarea", wide: true, rows: 3 })}
    </div>`, async (data) => {
    const body = {
      name: data.get("name"),
      email: optionalText(data.get("email")),
      phone: optionalText(data.get("phone")),
      city: optionalText(data.get("city")),
      notes: optionalText(data.get("notes")),
    };
    if (customer) await api(`/api/customers/${customer.id}`, { method: "PATCH", body });
    else await api("/api/customers", { method: "POST", body });
    showFlash(customer ? "Owner updated." : "Owner added.", "ok");
    render();
  });
}

function openAircraftModal(aircraft) {
  if (!state.customers.length) {
    showFlash("Add an owner before adding an aircraft.");
    return;
  }
  openModal(aircraft ? "Edit aircraft" : "New aircraft", `
    <div class="form-grid">
      <label class="span-2">Owner<select name="customer_id" required>${selectOptions(customerOptions(aircraft ? aircraft.customer_id : state.customers[0].id))}</select></label>
      ${field("N-number", "registration", aircraft ? aircraft.registration : "", { required: true, placeholder: "N5183K" })}
      ${field("Home airport", "home_airport", aircraft ? aircraft.home_airport || "" : "", { placeholder: "KFLG" })}
      ${field("Make", "make", aircraft ? aircraft.make : "", { required: true })}
      ${field("Model", "model", aircraft ? aircraft.model : "", { required: true })}
      ${field("Serial", "serial_number", aircraft ? aircraft.serial_number || "" : "")}
      ${field("Year", "year_manufactured", aircraft ? aircraft.year_manufactured || "" : "", { type: "number" })}
      ${field("Engine", "engine_model", aircraft ? aircraft.engine_model || "" : "", { wide: true })}
      ${field("Tach", "tach_hours", aircraft && aircraft.tach_hours != null ? aircraft.tach_hours : "", { type: "number", step: "0.1", min: "0" })}
      ${field("Hobbs", "hobbs_hours", aircraft && aircraft.hobbs_hours != null ? aircraft.hobbs_hours : "", { type: "number", step: "0.1", min: "0" })}
      ${field("Total time", "total_time_hours", aircraft && aircraft.total_time_hours != null ? aircraft.total_time_hours : "", { type: "number", step: "0.1", min: "0" })}
      ${field("Annual due", "annual_due", aircraft ? aircraft.annual_due || "" : "", { type: "date" })}
      ${field("Notes", "notes", aircraft ? aircraft.notes || "" : "", { type: "textarea", wide: true, rows: 2 })}
    </div>`, async (data) => {
    const body = {
      customer_id: Number(data.get("customer_id")),
      registration: data.get("registration"),
      make: data.get("make"),
      model: data.get("model"),
      serial_number: optionalText(data.get("serial_number")),
      year_manufactured: optionalNumber(data.get("year_manufactured")),
      engine_model: optionalText(data.get("engine_model")),
      tach_hours: optionalNumber(data.get("tach_hours")),
      hobbs_hours: optionalNumber(data.get("hobbs_hours")),
      total_time_hours: optionalNumber(data.get("total_time_hours")),
      home_airport: optionalText(data.get("home_airport")),
      annual_due: optionalText(data.get("annual_due")),
      notes: optionalText(data.get("notes")),
    };
    if (aircraft) await api(`/api/aircraft/${aircraft.id}`, { method: "PATCH", body });
    else await api("/api/aircraft", { method: "POST", body });
    showFlash(aircraft ? "Aircraft updated." : "Aircraft added.", "ok");
    render();
  });
}

function openRecordModal(aircraftId) {
  if (!state.aircraft.length) {
    showFlash("Add an aircraft before opening a work order.");
    return;
  }
  const selected = aircraftId || state.aircraft[0].id;
  openModal("New work order", `
    <div class="form-grid">
      <label class="span-2">Aircraft<select name="aircraft_id" required>${selectOptions(aircraftOptions(Number(selected)))}</select></label>
      ${field("Title", "title", "", { required: true, wide: true })}
      ${field("Kind", "kind", "repair", { type: "select", options: optionsFrom(KINDS) })}
      ${field("Opened", "opened_on", todayISO(), { type: "date", required: true })}
      ${field("Discrepancy", "discrepancy", "", { type: "textarea", wide: true })}
      ${field("Location", "location", "", { placeholder: "Airport, if not the home field" })}
      ${field("Travel hours", "travel_hours", "0.0", { type: "number", step: "0.1", min: "0" })}
    </div>`, async (data) => {
    const created = await api("/api/records", {
      method: "POST",
      body: {
        aircraft_id: Number(data.get("aircraft_id")),
        title: data.get("title"),
        kind: data.get("kind"),
        opened_on: data.get("opened_on"),
        discrepancy: data.get("discrepancy") || "",
        location: optionalText(data.get("location")),
        travel_hours: parseHours(data.get("travel_hours") || "0.0"),
      },
    });
    closeModal();
    go(`#records/${created.id}`);
  });
}

function openShopModal() {
  const shop = state.shop;
  openModal("Shop profile", `
    <div class="form-grid">
      ${field("Business", "business_name", shop.business_name, { required: true })}
      ${field("Mechanic", "mechanic_name", shop.mechanic_name, { required: true })}
      ${field("Certificate", "certificate_label", shop.certificate_label, { required: true, wide: true })}
      ${field("Phone", "phone", shop.phone || "")}
      ${field("Email", "email", shop.email || "")}
      ${field("Base", "base_city", shop.base_city || "", { wide: true })}
      ${field("Labor rate", "labor", (shop.default_labor_rate_cents / 100).toFixed(2), { required: true })}
      ${field("Travel rate", "travel", (shop.default_travel_rate_cents / 100).toFixed(2), { required: true })}
      ${field("Payment terms (days)", "payment_terms_days", shop.payment_terms_days, { type: "number", min: "0", required: true })}
    </div>`, async (data) => {
    await api("/api/shop", {
      method: "PATCH",
      body: {
        business_name: data.get("business_name"),
        mechanic_name: data.get("mechanic_name"),
        certificate_label: data.get("certificate_label"),
        phone: data.get("phone") || "",
        email: data.get("email") || "",
        base_city: data.get("base_city") || "",
        default_labor_rate_cents: dollarsToCents(data.get("labor")),
        default_travel_rate_cents: dollarsToCents(data.get("travel")),
        payment_terms_days: Number(data.get("payment_terms_days")),
      },
    });
    showFlash("Shop profile saved.", "ok");
    render();
  });
}

function formData(form) {
  return new FormData(form);
}

async function onSubmit(event) {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (form.id === "modal-form") {
    event.preventDefault();
    if (!modalHandler) return;
    try {
      await modalHandler(new FormData(form));
      closeModal();
    } catch (error) {
      modalError(error.message || "Could not save.");
    }
    return;
  }
  const kind = form.dataset.form;
  if (!kind) return;
  event.preventDefault();
  await run(async () => {
    const data = formData(form);
    const id = form.dataset.id;
    if (kind === "record") {
      await api(`/api/records/${id}`, {
        method: "PATCH",
        body: {
          title: data.get("title"),
          kind: data.get("kind"),
          status: data.get("status"),
          discrepancy: data.get("discrepancy") || "",
          corrective_action: data.get("corrective_action") || "",
          location: optionalText(data.get("location")),
          opened_on: data.get("opened_on"),
          closed_on: data.get("status") === "complete" && !optionalText(data.get("closed_on"))
            ? todayISO()
            : optionalText(data.get("closed_on")),
          tach_hours: optionalNumber(data.get("tach_hours")),
          hobbs_hours: optionalNumber(data.get("hobbs_hours")),
          rating: data.get("rating"),
          travel_hours: parseHours(data.get("travel_hours") || "0"),
          signoff_name: data.get("signoff_name") || "",
          certificate_ref: data.get("certificate_ref") || "",
          rts_statement: data.get("rts_statement") || "",
          notes: optionalText(data.get("notes")),
        },
      });
      showFlash("Work order saved.", "ok");
      render();
    } else if (kind === "labor") {
      await api(`/api/records/${id}/labor`, {
        method: "POST",
        body: {
          description: data.get("description"),
          hours: parseHours(data.get("hours")),
          rate_cents: dollarsToCents(data.get("rate")),
        },
      });
      showFlash("Labor added.", "ok");
      render();
    } else if (kind === "part") {
      await api(`/api/records/${id}/parts`, {
        method: "POST",
        body: {
          part_number: data.get("part_number") || "",
          description: data.get("description"),
          quantity: parseQty(data.get("quantity")),
          unit_price_cents: dollarsToCents(data.get("price")),
        },
      });
      showFlash("Part added.", "ok");
      render();
    } else if (kind === "payment") {
      await api(`/api/invoices/${id}/payments`, {
        method: "POST",
        body: {
          amount_cents: dollarsToCents(data.get("amount")),
          paid_on: data.get("paid_on"),
          method: data.get("method"),
          reference: data.get("reference") || "",
        },
      });
      showFlash("Payment recorded.", "ok");
      render();
    } else if (kind === "invoice-meta") {
      const body = { notes: data.get("notes") || "" };
      const due = optionalText(data.get("due_on"));
      if (due) body.due_on = due;
      const taxField = form.querySelector("[name=tax]");
      if (taxField && !taxField.readOnly) body.tax_cents = dollarsToCentsOrZero(data.get("tax"));
      await api(`/api/invoices/${id}`, { method: "PATCH", body });
      showFlash("Invoice details saved.", "ok");
      render();
    } else if (kind === "schedule") {
      const aircraft = optionalText(data.get("aircraft_id"));
      await api("/api/schedule", {
        method: "POST",
        body: {
          scheduled_on: form.dataset.date,
          title: data.get("title"),
          kind: data.get("kind"),
          notes: data.get("notes") || "",
          starts_at: optionalText(data.get("starts_at")),
          aircraft_id: aircraft ? Number(aircraft) : null,
        },
      });
      showFlash("Added to the day.", "ok");
      render();
    } else if (kind === "new-user") {
      await api("/api/admin/users", {
        method: "POST",
        body: {
          display_name: data.get("display_name"),
          username: data.get("username"),
          password: data.get("password"),
          role: data.get("role"),
        },
      });
      showFlash("Account added.", "ok");
      render();
    } else if (kind === "import-shop") {
      const file = form.querySelector("[name=file]").files[0];
      if (!file) throw new Error("Choose a shop file.");
      if (!window.confirm("Replace the shop with this file? Records, invoices, the calendar, and accounts in this file overwrite what is here now.")) return;
      let payload;
      try {
        payload = JSON.parse(await file.text());
      } catch {
        throw new Error("That file is not JSON.");
      }
      const result = await api("/api/admin/import", { method: "POST", body: payload });
      state.user = await api("/api/me");
      applySession();
      document.getElementById("view").dataset.loaded = "";
      state.shop = null;
      state.dashboard = null;
      state.customers = [];
      state.aircraft = [];
      state.records = [];
      state.invoices = [];
      pendingFlash = result.message || "Shop data replaced.";
      if (state.user.role !== "admin") {
        if ((location.hash || "#briefing") !== "#briefing") location.hash = "#briefing";
        else render();
      } else render();
    }
  });
}

document.addEventListener("submit", onSubmit);

document.addEventListener("click", (event) => {
  const actionEl = event.target.closest("[data-action]");
  const hrefEl = event.target.closest("[data-href]");
  if (actionEl) {
    const action = actionEl.dataset.action;
    const id = actionEl.dataset.id;
    if (action === "close-modal") closeModal();
    else if (action === "hide-demo") {
      sessionStorage.setItem("kinney-hide-demo", "1");
      renderBanner();
    } else if (action === "print") window.print();
    else if (action === "edit-shop") openShopModal();
    else if (action === "new-customer") openCustomerModal(null);
    else if (action === "edit-customer") openCustomerModal(state.customers.find((item) => item.id === Number(id)));
    else if (action === "new-aircraft") openAircraftModal(null);
    else if (action === "edit-aircraft") openAircraftModal(state.aircraft.find((item) => item.id === Number(id)));
    else if (action === "new-record") openRecordModal(actionEl.dataset.aircraft);
    else if (action === "insert-rts") {
      const box = document.querySelector("[name=rts_statement]");
      if (box && CERT[actionEl.dataset.kind]) {
        box.value = CERT[actionEl.dataset.kind];
        box.focus();
      }
    } else if (action === "delete-record" && window.confirm("Delete this work order?")) {
      run(async () => {
        await api(`/api/records/${id}`, { method: "DELETE" });
        go("#records");
      });
    } else if (action === "delete-aircraft" && window.confirm("Delete this aircraft?")) {
      run(async () => {
        await api(`/api/aircraft/${id}`, { method: "DELETE" });
        go("#fleet");
      });
    } else if (action === "delete-labor") {
      run(async () => {
        await api(`/api/labor/${id}`, { method: "DELETE" });
        render();
      });
    } else if (action === "delete-part") {
      run(async () => {
        await api(`/api/parts/${id}`, { method: "DELETE" });
        render();
      });
    } else if (action === "delete-payment") {
      run(async () => {
        await api(`/api/payments/${id}`, { method: "DELETE" });
        showFlash("Payment removed.", "ok");
        render();
      });
    } else if (action === "bill-record") {
      run(async () => {
        const invoice = await api(`/api/records/${id}/invoice`, { method: "POST" });
        go(`#billing/${invoice.id}`);
      });
    } else if (action === "refresh-invoice") {
      run(async () => {
        await api(`/api/invoices/${id}/refresh`, { method: "POST" });
        showFlash("Draft refreshed from the work order.", "ok");
        render();
      });
    } else if (action === "issue-invoice") {
      run(async () => {
        await api(`/api/invoices/${id}/issue`, { method: "POST" });
        showFlash("Invoice issued.", "ok");
        render();
      });
    } else if (action === "cal-open") {
      go(`#calendar/${actionEl.dataset.date}`);
    } else if (action === "delete-entry" && window.confirm("Remove this from the day?")) {
      run(async () => {
        await api(`/api/schedule/${id}`, { method: "DELETE" });
        showFlash("Removed from the day.", "ok");
        render();
      });
    } else if (action === "export-data") {
      run(() => exportShop());
    } else if (action === "sign-out") {
      run(async () => {
        await api("/api/logout", { method: "POST" });
        showLogin();
      });
    } else if (action === "change-password") openPasswordModal();
    else if (action === "reset-password") openResetModal(id, actionEl.dataset.name);
    else if (action === "set-role") {
      run(async () => {
        await api(`/api/admin/users/${id}`, { method: "PATCH", body: { role: actionEl.dataset.role } });
        showFlash("Account updated.", "ok");
        render();
      });
    } else if (action === "set-active") {
      run(async () => {
        await api(`/api/admin/users/${id}`, { method: "PATCH", body: { active: actionEl.dataset.active === "true" } });
        showFlash("Account updated.", "ok");
        render();
      });
    } else if (action === "void-invoice" && window.confirm("Void this invoice?")) {
      run(async () => {
        await api(`/api/invoices/${id}/void`, { method: "POST" });
        showFlash("Invoice voided.", "ok");
        render();
      });
    }
    return;
  }
  if (hrefEl && !event.target.closest("a, button, input, select, textarea, label")) {
    location.hash = hrefEl.dataset.href;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
  if (event.key === "Enter" && event.target.dataset && event.target.dataset.href) {
    location.hash = event.target.dataset.href;
  }
});

document.addEventListener("input", (event) => {
  const name = event.target.dataset.filter;
  if (!name) return;
  state.filters[name] = event.target.value;
  const list = document.getElementById("filtered-list");
  if (!list) return;
  if (name === "records") list.innerHTML = recordsTable(filteredRecords());
  if (name === "billing") list.innerHTML = invoicesTable(filteredInvoices());
  if (name === "fleet") list.innerHTML = fleetBody();
});

window.addEventListener("hashchange", () => {
  if (!signedIn) return;
  document.getElementById("flash").hidden = true;
  render();
});

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const data = new FormData(form);
  button.disabled = true;
  try {
    state.user = await api("/api/login", {
      method: "POST",
      body: { username: data.get("username"), password: data.get("password") },
    });
    form.querySelector("[name=password]").value = "";
    showApp();
    document.getElementById("view").dataset.loaded = "";
    render();
  } catch (error) {
    const err = document.getElementById("login-error");
    err.hidden = false;
    err.textContent = error.message || "Sign in failed.";
    document.getElementById("login-note").hidden = true;
  } finally {
    button.disabled = false;
  }
});

async function boot() {
  try {
    state.user = await api("/api/me");
    showApp();
    render();
  } catch {
    showLogin();
  }
}

boot();
