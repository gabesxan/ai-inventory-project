# EstoqueFácil — UI Design Direction & Token Specification (FE-03)

## Reference review status

- **Reference:** Fyntra Branding & UI/UX Design System (Reda ait maha & Oserex Studio, Behance `244559105`).
- **Frame availability:** As recorded in the project design direction, the public Behance gallery returned an HTTP error and is not indexed in accessible search results. Visual frames could not be inspected directly; exact reference hues, font pairings, and pixel proportions remain unverified until screenshots or frames are supplied.
- **Adopted interpretation:** Original EstoqueFácil ERP visual system built from the documented Fyntra structural principles — quiet light working canvas, tonal panel surfaces, structured sans-serif typography with tabular numerals, controlled primary accent, understated 1 px separation, and high-density scannable data presentation.

## Original EstoqueFácil visual tokens

### Color roles

| Token | Value | Role / Contrast |
| --- | --- | --- |
| `--surface-canvas` | `#F4F6F8` | Quiet light application canvas |
| `--surface-primary` | `#FFFFFF` | Primary cards, tables, modals, controls |
| `--surface-tonal` | `#F8FAFB` | Secondary tonal panels, table headers, modal footers |
| `--surface-subtle` | `#EEF2F5` | Hover tints, recessed controls, neutral pills |
| `--ink-primary` | `#111827` | Headings, primary data values (17.4:1 on white) |
| `--ink-secondary` | `#475467` | Subtitles, column headers, helper text (7.5:1 on white) |
| `--ink-muted` | `#667085` | Captions, metadata, timestamps (4.9:1 on white) |
| `--border-default` | `#E4E7EC` | Quiet panel and container separation |
| `--border-strong` | `#CFD6DF` | Interactive control borders (inputs, selects, secondary buttons) |
| `--accent-primary` | `#0F625B` | Controlled EstoqueFácil brand accent (6.8:1 with `#FFFFFF`) |
| `--accent-primary-hover` | `#0B4D47` | Primary button and active control hover |
| `--accent-subtle` | `#ECF7F5` | Active navigation tint, subtle brand emphasis |
| `--state-success` / `--state-success-bg` | `#166534` / `#ECFDF3` | Normal stock, confirmed import, entries |
| `--state-warning` / `--state-warning-bg` | `#92400E` / `#FFFBEB` | Below minimum, stale or simulated notice |
| `--state-danger` / `--state-danger-bg` | `#991B1B` / `#FEF2F2` | Out of stock, errors, destructive actions |
| `--state-info` / `--state-info-bg` | `#1D4ED8` / `#EFF6FF` | Neutral system disclosures and informational alerts |

### Typography & numeric discipline

- **Sans stack:** `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- **Mono stack:** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace` (SKUs, barcodes, hashes, batch IDs)
- **Type scale:** `--text-xs` (0.75rem), `--text-sm` (0.8125rem), `--text-base` (0.875rem / 14px dense ERP default), `--text-md` (0.9375rem), `--text-lg` (1.0625rem), `--text-xl` (1.375rem), `--text-2xl` (1.625rem)
- **Tabular figures:** `font-variant-numeric: tabular-nums` enforced on KPI values, tables, quantities, currency, and pagination.

### Spacing, elevation & focus

- **Spacing scale:** 4 px base grid (`--space-1` through `--space-8`).
- **Radii:** `--radius-sm` (6 px), `--radius-md` (10 px), `--radius-lg` (14 px), `--radius-pill` (999px).
- **Elevation:** Restrained hairline borders (`1px solid var(--border-default)`) with minimal ambient shadow (`--shadow-xs`, `--shadow-sm`, `--shadow-modal`).
- **Focus visibility:** Explicit `:focus-visible` double ring (`0 0 0 2px var(--surface-primary), 0 0 0 4px var(--accent-primary)`) for keyboard navigation across buttons, fields, tabs, links, and modal actions.

## Shared controls covered in FE-03

- Buttons (`.btn`, primary, secondary, success, danger, outline-danger, ghost, subtle, small)
- Form inputs, selects, textareas, field hints, validation errors, filter groups
- Badges (semantic pills with hairline borders and tabular counts)
- Cards, tonal panels, KPI metric blocks, alerts, empty/loading state boxes
- Data tables (predictable row height, sticky-ready uppercase headers, tabular numbers, horizontal scroll container)
- Dialogs (`Modal.tsx` with focus restoration & Escape handling, `ConfirmModal.tsx`)
- Pagination (`Pagination.tsx`) and original geometric `BrandMark.tsx`
