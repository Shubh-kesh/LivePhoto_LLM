# LivePhoto — Branding Integration (M5.5)

How a future bank can supply branding for the capture experience **without modifying capture or
security logic**.

## What a bank supplies

A small theme/identity object, e.g.:

```ts
{
  brand_name: 'Example Bank',
  logo_url: 'https://approved-cdn.example.com/livephoto/logo.svg', // approved asset only
  primary_color: '#0b3f8f',
  secondary_color: '#6b7280',
  support_text: 'Call 1-800-… for help',
}
```

No capture/security/PAD/VLM logic is touched.

## Where it plugs in

- **Branding slot** — `BrandHeader` (design system) accepts `brandName` and an optional `logo`
  node. The customer flow renders it from centralized copy
  (`captureCopy.brand.name`, default `LivePhoto`).
- **Theme** — all visual decisions are CSS custom properties in
  `src/design-system/tokens.css` (`--lp-color-primary`, `--lp-color-background`,
  `--lp-color-surface`, `--lp-color-text`, …). A bank primary/secondary color maps onto the
  semantic tokens; components only consume tokens, so no component or capture markup changes.
- **Copy/legal** — customer-facing strings live in `src/features/capture/copy.ts`
  (`captureCopy.*`). Approved help/legal text replaces entries there; the component tree is
  unchanged. The nested structure is the future localization seam.

## Example (conceptual — not implemented as remote theming)

```tsx
<BrandHeader brandName="Example Bank" logo={<img src={logoUrl} alt="Example Bank" />} />
```
and CSS custom properties sourced from the bank config:
```css
:root {
  --lp-color-primary: <bank-primary>;
  --lp-color-primary-hover: <derived>;
}
```

## Boundaries (kept intentionally)

- No remote/dynamic theming is implemented in M5.5 (a build-time/config seam only).
- `BrandHeader` and the tokens always have safe LivePhoto defaults.
- Logo assets must be approved and are not hotlinked by the app itself (see the no-remote-assets
  rule in `docs/CAPTURE_UX_DESIGN.md`).
- Branding never affects camera lifecycle, quality thresholds, security headers, or the
  success-state wording boundary ("Photo captured successfully", never verification).
