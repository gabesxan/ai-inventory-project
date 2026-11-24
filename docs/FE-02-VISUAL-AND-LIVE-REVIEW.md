# FE-02 · Live End-to-End Suggestion & Visual Alignment Review

## Live environment verified

- **Frontend branch:** `feat/ui-reports` served on `http://127.0.0.1:4173` (`VITE_API_URL=http://127.0.0.1:8104/api`)
- **Live backend:** FastAPI + CPU DQN worker running on `http://127.0.0.1:8104/api` (`API-02` `65148f3`, `API-05` `71e32c5`)
- **Verification command:** `bash frontend/scripts/verify-live-reports.sh` (reads disposable login locally from `../codex/.local/demo-login.json` without logging credentials)
- **Console diagnostics:** 0 errors, 0 warnings

## Functional & security verification results

1. **Live Admin sign-in & Dashboard (`/`):**
   - Authenticated over live `/api/auth/login` and `/api/dashboard`.
   - Displayed backend-matched metrics (`4` active products, `1` out of stock, `3` below minimum, `5 ent. / 11 saí.`, `R$ 1.215,40`), reference date `24/11/2026`, labeled chart unit (`lançamentos/dia`), and zero AI promotion.
2. **Stored CPU DQN suggestion on tab load (`/sugestoes-compra` → `/relatorios?tab=replenishment`):**
   - Legacy route redirected automatically to `/relatorios?tab=replenishment`.
   - Loaded `GET /api/reports/replenishment` automatically on open without any user trigger or AI launch button.
   - Displayed `DEMO-MOUSE-01` (`Mouse Óptico USB Corporativo`), `3 UN`, plain text disclosure `Sugestão gerada por IA`, origin `Simulação acadêmica`, reference date `24/11/2026`, `dqn-v1 · synthetic_inventory_v1`.
   - Confirmed absence of AI launch buttons, AI nav items, promotional AI badges, and automatic purchasing controls.
3. **Live paired policy comparison (`GET /api/reports/comparison`):**
   - Rendered all 3 held-out synthetic scenario groups (54 rows across 18 paired instances), labeled `Simulação acadêmica`.
   - Displayed exact measured results across `Base-Stock`, `(s, S)`, and `DQN` with accompanying units (`R$`, `%`, `d`, `un.`), including transparent visibility of higher DQN cost (e.g., `baseline`: Base-Stock `R$ 569,67` / `92,5%`, `(s, S)` `R$ 566,83` / `92,4%`, DQN `R$ 798,83` / `59,7%`).
   - Expanding `baseline` revealed all 18 paired seed rows and execution metadata (`model_run_id`, `trained_at`, `generated_at`).
4. **Role & auth guards:**
   - Unauthenticated `GET http://127.0.0.1:8104/api/reports/replenishment` returned `HTTP 401`.
   - `OPERATOR` session navigating directly to `/relatorios?tab=replenishment` redirected to `/` with `/relatorios` omitted from navigation.
5. **Responsive navigation & keyboard focus (`1440x900` & `390x844`):**
   - Desktop keeps mobile controls hidden and displays the two-zone ERP shell cleanly.
   - Mobile (`390x844`) opens the slide-in drawer, moves focus inside the drawer, closes on `Escape`, and restores focus to `.mobile-menu-btn`.

## Visual review against design direction

- **Reference basis:** Original EstoqueFácil visual direction (`docs/UI_DESIGN_DIRECTION.md`, derived from `01-Design-Direction.md`).
- **Missing reference frames:** The public Behance case study (`Fyntra Branding & UI/UX Design System`, Behance `244559105`) remained inaccessible; exact reference hues and pixel proportions could not be compared frame-by-frame and remain recorded as pending accessible reference frames.
- **Desktop (`1440x900`) and Mobile (`390x844`) visual check:**
  - Quiet light canvas (`#F4F6F8`), tonal panels (`#F8FAFB`), crisp 1 px hairline borders (`#E4E7EC`), controlled deep slate-teal accent (`#0F625B`), and tabular numeric alignment hold across shell, dashboard, and Reposição.
  - Horizontal table scrolling contains wide report tables cleanly on `390 px` without breaking page layout or hiding filters/provenance.
- **Captured evidence (local, gitignored):** `test-results/fe-02/live-login-1440.png`, `live-dashboard-1440.png`, `live-dashboard-390.png`, `live-replenishment-1440.png`, `live-replenishment-390.png`, `live-comparison-expanded-1440.png`, `live-mobile-drawer-390.png`.
