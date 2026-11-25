// Fixture API for visual review only. Serves contract-shaped JSON on 127.0.0.1
// so screens can be captured without a database or real credentials.
// Report payloads come from docs/contracts/report-v1/fixtures.json.
// Usage: node frontend/scripts/ui-review/fixture-api.mjs [port]
// POST /__state {"replenishment":"ready|stale|calculating|insufficient_data|empty"}
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const contract = JSON.parse(
  readFileSync(resolve(here, "../../../docs/contracts/report-v1/fixtures.json"), "utf8")
);
const port = Number(process.argv[2] || 8199);
let replenishmentState = "ready";

const now = "2026-11-24T12:00:00Z";
const user = {
  id: 1, name: "Operador Demonstração", email: "demo@empresa.local", role: "ADMIN",
  is_active: true, created_at: now, updated_at: now,
};

// The integrated demo publishes 3 UN for DEMO-MOUSE-01 (LOCAL_DELIVERY.md).
const replenishmentRow = {
  ...contract.ready.body.items[0],
  sku: "DEMO-MOUSE-01",
  product_name: "Mouse óptico USB",
  recommended_quantity: "3.000",
};

function replenishment() {
  const body = structuredClone(contract[replenishmentState].body);
  if (body.items.length) body.items = [replenishmentRow];
  return body;
}

const days = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 9, 26 + i));
  const iso = d.toISOString().slice(0, 10);
  const e = (i * 7) % 5;
  const s = ((i * 11) % 7) + 1;
  return {
    date: iso,
    label: `${iso.slice(8, 10)}/${iso.slice(5, 7)}`,
    entries_count: e,
    exits_count: s,
    by_unit: { UN: { entries_qty: String(e * 4), exits_qty: String(s * 2) } },
  };
});

const alerts = [
  ["DEMO-MOUSE-01", "Mouse óptico USB", "Periféricos", "0", "5", "5", "Distribuidora Central", 4, "OUT_OF_STOCK"],
  ["DEMO-TEC-02", "Teclado ABNT2", "Periféricos", "0", "4", "4", "Distribuidora Central", 4, "OUT_OF_STOCK"],
  ["DEMO-CAB-03", "Cabo HDMI 2 m", "Cabos", "2", "10", "8", null, null, "BELOW_MIN"],
  ["DEMO-PAP-04", "Papel A4 75 g", "Escritório", "3", "12", "9", "Papelaria Norte", 2, "BELOW_MIN"],
].map(([sku, name, category_name, current_stock, min_stock, deficit, preferred_supplier_name, lead_time_days, stock_status], i) => ({
  product_id: i + 1, sku, name, category_name, unit: "UN", current_stock, min_stock, deficit,
  preferred_supplier_name, lead_time_days, stock_status,
}));

const dashboard = {
  active_products_count: 42,
  out_of_stock_count: 3,
  below_min_stock_count: 7,
  estimated_stock_value_brl: "48920.50",
  valuation_formula: "Saldo atual × custo de referência",
  valuation_disclaimer: "Valor de apoio à gestão, sem efeito contábil.",
  period_start: days[0].date,
  period_end: days[days.length - 1].date,
  entries_count: 18,
  exits_count: 64,
  adjustments_count: 2,
  reversals_count: 1,
  unit_summaries: [{ unit: "UN", unit_label: "Unidade", entries_qty: "72", exits_qty: "130", demand_exits_qty: "118" }],
  daily_chart: days,
  replenishment_list: alerts,
};

const page = (items) => ({ items, total: items.length, page: 1, page_size: 200, total_pages: 1 });
const products = alerts.map((a) => ({
  id: a.product_id, name: a.name, sku: a.sku, barcode: null, description: null, category_id: 1,
  category_name: a.category_name, unit: "UN", unit_label: "Unidade", is_discrete_unit: true,
  unit_cost: "25.00", min_stock: a.min_stock, safety_stock: "1", current_stock: a.current_stock,
  estimated_total_value: "0", location: null, preferred_supplier_id: null,
  preferred_supplier_name: a.preferred_supplier_name, lead_time_days: a.lead_time_days, is_active: true,
  has_movements: true, stock_status: a.stock_status, created_at: now, updated_at: now,
}));

function route(path) {
  if (path === "/api/auth/me") return user;
  if (path === "/api/dashboard") return dashboard;
  if (path === "/api/products" || path === "/api/reports/current-stock" || path === "/api/reports/below-minimum") return page(products);
  if (path === "/api/suppliers" || path === "/api/categories" || path === "/api/users") return page([]);
  if (path === "/api/movements/responsibles") return [{ id: 1, name: user.name }];
  if (path === "/api/products/units") return [{ code: "UN", label: "Unidade", allow_decimal: false }];
  if (path === "/api/reports/movements") return page([]);
  if (path === "/api/reports/replenishment") return replenishment();
  if (path === "/api/reports/comparison") return contract.comparison.body;
  if (path === "/api/reports/imported-history") return contract.imported_history.body;
  if (path === "/api/reports/inventory-exceptions") return contract.inventory_exceptions.body;
  if (path === "/api/ai/imports/legacy/batches") return contract.import_quality.body;
  return null;
}

createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  if (req.method === "OPTIONS") return res.writeHead(204).end();
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/__state" && req.method === "POST") {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      const next = JSON.parse(raw || "{}").replenishment;
      if (next in contract) replenishmentState = next;
      res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({ replenishmentState }));
    });
    return;
  }
  const body = route(url.pathname);
  if (body === null) return res.writeHead(404, { "Content-Type": "application/json" }).end('{"detail":"fixture ausente"}');
  res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(body));
}).listen(port, "127.0.0.1", () => console.log(`fixture api on http://127.0.0.1:${port}`));
