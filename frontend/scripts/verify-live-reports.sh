#!/usr/bin/env bash
# FE-02 live browser verification against local FastAPI + CPU DQN worker (and integrated API when available).
# Reads disposable credentials locally from DEMO_LOGIN_FILE and DEMO_OPERATOR_LOGIN_FILE without printing them.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="$APP_DIR/test-results/fe-02"
API_URL="${VITE_API_URL:-http://127.0.0.1:8104/api}"
API_ROOT="${API_URL%/api}"
UI_PORT="${UI_PORT:-4173}"
DEMO_LOGIN_FILE="${DEMO_LOGIN_FILE:-$APP_DIR/../codex/.local/demo-login.json}"
DEMO_OPERATOR_LOGIN_FILE="${DEMO_OPERATOR_LOGIN_FILE:-$APP_DIR/../codex/.local/integrated-operator.json}"

mkdir -p "$OUT_DIR"

if [ ! -f "$DEMO_LOGIN_FILE" ]; then
  echo "Missing DEMO_LOGIN_FILE at $DEMO_LOGIN_FILE" >&2
  exit 1
fi

HEALTH_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${API_URL%/}/health")"
if [ "$HEALTH_CODE" != "200" ]; then
  echo "Live API health check failed (${API_URL%/}/health -> HTTP $HEALTH_CODE)" >&2
  exit 1
fi

OPENAPI_PATHS="$(curl -s "${API_ROOT}/openapi.json" | python3 -c 'import json,sys; p=json.load(sys.stdin).get("paths",{}); print(" ".join(sorted(p.keys())))' 2>/dev/null || true)"

(
  cd "$APP_DIR/frontend"
  VITE_API_URL="$API_URL" npx vite --host 127.0.0.1 --port "$UI_PORT" --strictPort
) > "$OUT_DIR/vite-live.log" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true; playwright-cli -s=fe02 close 2>/dev/null || true; rm -rf "$APP_DIR/.playwright-cli"' EXIT

for i in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${UI_PORT}/" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done

DEMO_EMAIL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["email"])' "$DEMO_LOGIN_FILE")"
DEMO_PASS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["password"])' "$DEMO_LOGIN_FILE")"

playwright-cli -s=fe02 open "http://127.0.0.1:${UI_PORT}/login"
playwright-cli -s=fe02 resize 1440 900
sleep 0.5
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-login-1440.png"

# Real admin login through UI form
playwright-cli -s=fe02 fill "#login-email" "$DEMO_EMAIL" >/dev/null
playwright-cli -s=fe02 fill "#login-password" "$DEMO_PASS" >/dev/null
unset DEMO_EMAIL DEMO_PASS
playwright-cli -s=fe02 click "button[type='submit']"
sleep 1.2

# 1. Live Dashboard (1440x900)
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-dashboard-1440.png"
playwright-cli -s=fe02 --raw eval "(() => {
  const kpis = [...document.querySelectorAll('.kpi-value')].map(el => el.textContent?.trim());
  const refMeta = document.querySelector('[data-testid=\"dashboard-reference-date\"]')?.textContent?.trim();
  const chartMeta = document.querySelector('[data-testid=\"chart-meta-strip\"]')?.textContent?.trim();
  const mainText = document.getElementById('main-content')?.textContent || '';
  return JSON.stringify({
    view: 'live-dashboard-1440',
    path: location.pathname,
    kpis,
    refMeta,
    chartMeta,
    hasAiPromo: /\bIA\b|intelig[eê]ncia artificial|dqn/i.test(mainText)
  });
})()"

# 2. Legacy route /sugestoes-compra -> /relatorios?tab=replenishment with LIVE worker suggestion + comparison
playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/sugestoes-compra"
sleep 1.2
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-replenishment-1440.png"
playwright-cli -s=fe02 --raw eval "(() => {
  const panel = document.querySelector('[data-testid=\"replenishment-panel\"]');
  const cmp = document.querySelector('[data-testid=\"policy-comparison-section\"]');
  const panelText = panel?.textContent || '';
  const cmpRows = [...(cmp?.querySelectorAll('[data-testid=\"comparison-group-synthetic\"] tbody tr') || [])].map(tr => tr.textContent?.trim());
  const buttons = [...(panel?.querySelectorAll('button') || [])].map(b => b.textContent?.trim());
  return JSON.stringify({
    view: 'live-replenishment-1440',
    url: location.pathname + location.search,
    hasDemoMouseSku: panelText.includes('DEMO-MOUSE-01'),
    hasQty3Un: panelText.includes('3 UN'),
    hasDisclosure: panelText.includes('Sugestão gerada por IA'),
    hasSyntheticOrigin: panelText.includes('Simulação acadêmica'),
    provenanceBar: document.querySelector('[data-testid=\"replenishment-provenance\"]')?.textContent?.trim(),
    hasAiLaunchOrBuyBtn: buttons.some(b => /gerar|rodar|comprar|pedido|treinar/i.test(b || '')),
    comparisonGroupTitle: cmp?.querySelector('.comparison-group-title')?.textContent?.trim(),
    comparisonSummaryRows: cmpRows
  });
})()"

# Expand live per-seed comparison details on first scenario group
playwright-cli -s=fe02 click "css=[data-testid='comparison-group-synthetic']:first-of-type button[aria-expanded='false']"
sleep 0.4
playwright-cli -s=fe02 --raw eval "(() => {
  const detailRows = document.querySelectorAll('[data-testid=\"comparison-expanded-details\"] tbody tr').length;
  return JSON.stringify({ view: 'live-comparison-expanded', expandedSeedPolicyRows: detailRows });
})()"
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-comparison-expanded-1440.png"

# 2b. Optional live integrated routes (FE-10, FE-13, FE-14) when exposed by target API
if echo "$OPENAPI_PATHS" | grep -q "/api/reports/imported-history"; then
  playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/relatorios?tab=imported-history"
  sleep 0.9
  playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-imported-history-1440.png"
  playwright-cli -s=fe02 --raw eval "JSON.stringify({ view: 'live-imported-history', rowCount: document.querySelectorAll('[data-testid=\"imported-history-panel\"] tbody tr').length, hasEmpty: Boolean(document.querySelector('[data-testid=\"imported-history-empty\"]')) })"
fi

if echo "$OPENAPI_PATHS" | grep -q "/api/reports/inventory-exceptions"; then
  playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/relatorios?tab=exceptions"
  sleep 0.9
  playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-exceptions-1440.png"
  playwright-cli -s=fe02 --raw eval "JSON.stringify({ view: 'live-exceptions', rowCount: document.querySelectorAll('[data-testid=\"inventory-exceptions-panel\"] tbody tr').length, hasEmpty: Boolean(document.querySelector('[data-testid=\"exceptions-empty-state\"]')) })"
fi

if echo "$OPENAPI_PATHS" | grep -q "/api/ai/imports/legacy/batches"; then
  playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/dados-ia"
  sleep 0.9
  playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-import-quality-1440.png"
  playwright-cli -s=fe02 --raw eval "JSON.stringify({ view: 'live-import-quality', rowCount: document.querySelectorAll('[data-testid=\"legacy-import-quality-panel\"] tbody tr').length, hasLatestSummary: Boolean(document.querySelector('[data-testid=\"legacy-latest-summary\"]')) })"
fi

# 3. Mobile viewport (390x844) + responsive drawer keyboard focus
playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/relatorios?tab=replenishment"
sleep 0.6
playwright-cli -s=fe02 resize 390 844
sleep 0.4
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-replenishment-390.png"
playwright-cli -s=fe02 click ".mobile-menu-btn"
sleep 0.3
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-mobile-drawer-390.png"
playwright-cli -s=fe02 press Escape
sleep 0.3
playwright-cli -s=fe02 --raw eval "JSON.stringify({ mobileDrawerClosedOnEscape: !document.getElementById('primary-sidebar')?.classList.contains('open'), focusRestoredToTrigger: document.activeElement === document.querySelector('.mobile-menu-btn') })"

playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/"
sleep 0.8
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-dashboard-390.png"

# 4. Unauthenticated live HTTP check -> 401
UNAUTH_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${API_URL%/}/reports/replenishment")"
echo "LIVE_UNAUTH_REPLENISHMENT_HTTP:$UNAUTH_CODE"

# 5. Real OPERATOR session check (zero /api/auth/me mocking when operator credentials work on live API)
playwright-cli -s=fe02 resize 1440 900
if [ -f "$DEMO_OPERATOR_LOGIN_FILE" ]; then
  OP_EMAIL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["email"])' "$DEMO_OPERATOR_LOGIN_FILE")"
  OP_PASS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["password"])' "$DEMO_OPERATOR_LOGIN_FILE")"
  OP_LOGIN_HTTP="$(python3 -c 'import json,urllib.request,urllib.error,sys
req=urllib.request.Request(sys.argv[1]+"/auth/login",data=json.dumps({"email":sys.argv[2],"password":sys.argv[3]}).encode(),headers={"Content-Type":"application/json"})
try:
  with urllib.request.urlopen(req) as r:
    body=json.loads(r.read().decode())
    tok=body.get("access_token","")
    r2=urllib.request.Request(sys.argv[1]+"/reports/replenishment",headers={"Authorization":"Bearer "+tok})
    try:
      urllib.request.urlopen(r2)
      print("200:200")
    except urllib.error.HTTPError as e2:
      print(f"200:{e2.code}")
except urllib.error.HTTPError as e:
  print(f"{e.code}:0")
' "${API_URL%/}" "$OP_EMAIL" "$OP_PASS")"
  echo "LIVE_OPERATOR_AUTH_AND_REPLENISHMENT_HTTP:$OP_LOGIN_HTTP"

  if [ "${OP_LOGIN_HTTP%%:*}" = "200" ]; then
    echo "OPERATOR_MODE:REAL_SESSION"
    playwright-cli -s=fe02 click ".sidebar-logout-btn"
    sleep 0.5
    playwright-cli -s=fe02 fill "#login-email" "$OP_EMAIL" >/dev/null
    playwright-cli -s=fe02 fill "#login-password" "$OP_PASS" >/dev/null
    unset OP_EMAIL OP_PASS
    playwright-cli -s=fe02 click "button[type='submit']"
    sleep 1.0
    playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/relatorios?tab=replenishment"
    sleep 0.6
    playwright-cli -s=fe02 --raw eval "JSON.stringify({ operatorMode: 'real', target: '/relatorios?tab=replenishment', redirectedPath: location.pathname, hasReportsNav: Boolean(document.querySelector('.sidebar-nav a[href=\"/relatorios\"]')) })"
    playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/dados-ia"
    sleep 0.5
    playwright-cli -s=fe02 --raw eval "JSON.stringify({ operatorMode: 'real', target: '/dados-ia', redirectedPath: location.pathname })"
    playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/usuarios"
    sleep 0.5
    playwright-cli -s=fe02 --raw eval "JSON.stringify({ operatorMode: 'real', target: '/usuarios', redirectedPath: location.pathname })"
  else
    unset OP_EMAIL OP_PASS
    echo "OPERATOR_MODE:NOT_PROVISIONED_ON_TARGET_API"
  fi
else
  echo "OPERATOR_MODE:NO_OPERATOR_LOGIN_FILE"
fi

playwright-cli -s=fe02 console error
echo "FE-02_LIVE_PLAYWRIGHT_OK"
