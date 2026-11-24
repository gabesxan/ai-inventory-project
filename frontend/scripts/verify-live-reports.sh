#!/usr/bin/env bash
# FE-02 live browser verification against local FastAPI + CPU DQN worker.
# Reads disposable credentials locally from DEMO_LOGIN_FILE without printing them.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="$APP_DIR/test-results/fe-02"
API_URL="${VITE_API_URL:-http://127.0.0.1:8104/api}"
UI_PORT="${UI_PORT:-4173}"
DEMO_LOGIN_FILE="${DEMO_LOGIN_FILE:-$APP_DIR/../codex/.local/demo-login.json}"

mkdir -p "$OUT_DIR"

if [ ! -f "$DEMO_LOGIN_FILE" ]; then
  echo "Missing DEMO_LOGIN_FILE at $DEMO_LOGIN_FILE" >&2
  exit 1
fi

# Verify live API is reachable
HEALTH_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${API_URL%/}/health")"
if [ "$HEALTH_CODE" != "200" ]; then
  echo "Live API health check failed (${API_URL%/}/health -> HTTP $HEALTH_CODE)" >&2
  exit 1
fi

# Start Vite dev server pointing directly at live API on allowed CORS port
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

# Authenticate via real HTTP without echoing secrets, then sign in through UI form
DEMO_EMAIL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["email"])' "$DEMO_LOGIN_FILE")"
DEMO_PASS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["password"])' "$DEMO_LOGIN_FILE")"

playwright-cli -s=fe02 open "http://127.0.0.1:${UI_PORT}/login"
playwright-cli -s=fe02 resize 1440 900
sleep 0.5
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-login-1440.png"

# Real admin login through form
playwright-cli -s=fe02 fill "#login-email" "$DEMO_EMAIL" >/dev/null
playwright-cli -s=fe02 fill "#login-password" "$DEMO_PASS" >/dev/null
unset DEMO_EMAIL DEMO_PASS
playwright-cli -s=fe02 click "button[type='submit']"
sleep 1.2

# 1. Verify live Dashboard (1440x900)
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

# 2. Verify legacy route /sugestoes-compra -> /relatorios?tab=replenishment with LIVE worker suggestion + comparison
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

# Expand live per-seed comparison details on first scenario group and capture screenshot
playwright-cli -s=fe02 click "css=[data-testid='comparison-group-synthetic']:first-of-type button[aria-expanded='false']"
sleep 0.4
playwright-cli -s=fe02 --raw eval "(() => {
  const detailRows = document.querySelectorAll('[data-testid=\"comparison-expanded-details\"] tbody tr').length;
  return JSON.stringify({ view: 'live-comparison-expanded', expandedSeedPolicyRows: detailRows });
})()"
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-comparison-expanded-1440.png"

# 3. Verify mobile viewport (390x844) + responsive drawer keyboard focus
playwright-cli -s=fe02 resize 390 844
sleep 0.4
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-replenishment-390.png"
playwright-cli -s=fe02 click ".mobile-menu-btn"
sleep 0.3
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-mobile-drawer-390.png"
playwright-cli -s=fe02 press Escape
sleep 0.3
playwright-cli -s=fe02 --raw eval "JSON.stringify({ mobileDrawerClosedOnEscape: !document.getElementById('primary-sidebar')?.classList.contains('open'), focusRestoredToTrigger: document.activeElement === document.querySelector('.mobile-menu-btn') })"

# Also check live Dashboard on mobile (390x844)
playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/"
sleep 0.8
playwright-cli -s=fe02 screenshot --filename="$OUT_DIR/live-dashboard-390.png"

# 4. Verify unauthenticated access to live /api/reports/replenishment returns 401
UNAUTH_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${API_URL%/}/reports/replenishment")"
echo "LIVE_UNAUTH_REPLENISHMENT_HTTP:$UNAUTH_CODE"

# 5. Verify operator permission guard in UI (OPERATOR cannot open /relatorios)
playwright-cli -s=fe02 route "**/api/auth/me" --body='{"id":99,"name":"Operador Teste","email":"operador@empresa.local","role":"OPERATOR","is_active":true,"created_at":"2026-10-01T10:00:00Z","updated_at":"2026-11-24T10:00:00Z"}'
playwright-cli -s=fe02 goto "http://127.0.0.1:${UI_PORT}/relatorios?tab=replenishment"
sleep 0.6
playwright-cli -s=fe02 --raw eval "JSON.stringify({ operatorRedirectedPath: location.pathname, operatorHasReportsNav: Boolean(document.querySelector('.sidebar-nav a[href=\"/relatorios\"]')) })"

playwright-cli -s=fe02 console error
echo "FE-02_LIVE_PLAYWRIGHT_OK"
