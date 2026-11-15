# Unjobless Design System

Implementation: `apps/web/src/styles/tokens.css` (tokens), `apps/web/src/styles/global.css` (components), `apps/web/src/components/ui/` (React components), `apps/web/src/components/shell/` (app shell).

## Direction

Taken from `docs/design-references/unjobless-ui-reference.webp` as *style only*: light grey canvas, white and soft-grey cards with large radii, broad low-opacity shadows, purple/lilac accent, gradient pill CTAs, circular icon bubbles, floating pill bottom navigation. Not taken: the reference brand, mascot, medical copy or screen composition. Unjobless adds desktop/tablet layouts and denser data views.

## Tokens

Playbook §6 tokens are used as-is, with two documented accessibility changes:

| Token | Playbook | Used | Reason |
|---|---|---|---|
| `--foreground-muted` | `#858591` (3.4:1 on white) | `#6e6e7a` (≈4.9:1 on white, ≈4.5:1 on `#F3F3F5`) | WCAG AA for small metadata text |
| `--warning` | `#B7791F` (≈3:1 on `--warning-soft`) | `#8A5A12` | AA text contrast inside warning badges/alerts |

Added: radius scale (card 24 / large 28 / control 14 / pill), shadow scale (`--shadow-card`, `--shadow-float`), 8px spacing scale, type scale, motion durations (150/200 ms, zeroed under `prefers-reduced-motion`), layout and safe-area variables.

Typography: **Inter Variable** (SIL OFL 1.1), self-hosted via `@fontsource-variable/inter` — no third-party font CDN, works offline in the PWA, full Latin coverage for Indonesian and English. Tabular numerals via `.num` for scores, counts, salaries and timestamps.

## Components

| Component | Notes |
|---|---|
| `Button` | Variants `primary` (gradient pill, one per view), `secondary`, `ghost`, `ai` (lilac, quieter than primary), `danger`; sizes md (44px) / sm (36px); `loading` shows spinner + `aria-busy`; icon-only requires `aria-label`. |
| `Card`, `CardTitle` | Tones `default` (white), `soft` (grey), `hero` (soft gradient, used sparingly for AI/hero surfaces). |
| `Badge` | Neutral, brand, success, warning, danger, info, outline. Always text, never colour-only. |
| `TextInput`, `TextArea`, `Select`, `Checkbox`, `Field` | Visible labels, hint + error wired with `aria-describedby`, `aria-invalid`. |
| `Dialog` | Native `<dialog>` (focus trap, Esc); bottom sheet on mobile. |
| `Tabs` | WAI-ARIA tabs with roving tabindex and arrow keys. |
| `Menu` | Menu button pattern: arrow keys, Esc returns focus. |
| `Tooltip` | Hover + keyboard focus, `role="tooltip"`. |
| `Skeleton`, `LoadingCards` | `role="status"` + screen-reader label; shimmer disabled under reduced motion. |
| `EmptyState`, `Alert`, `ErrorState`, `Toast` | Live regions for async feedback. |
| `Meter` | Numeric score + bar; `null` renders the word "Unknown", never 0. |
| `PageHeader` | Title, description, breadcrumb, actions. |

## Responsive shell

| Width | Navigation |
|---|---|
| < 768px | Compact top bar + floating safe-area-aware bottom nav (Overview, Discover, Import, Profile, More → sheet with every section). Content padded for the nav and `env(safe-area-inset-*)`. |
| 768–1099px | Icon rail sidebar (labels via `title`/accessible name). |
| ≥ 1100px | Full sidebar with grouped sections (Workspace, You, Data, System). Content max width 1280px; long text limited to 72ch (`.reading`). |

Touch targets ≥ 44px. A skip link jumps to `#main`. An offline banner appears when `navigator.onLine` is false.
