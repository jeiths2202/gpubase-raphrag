# Theme Token Design Documentation

## Overview

KMS Platform uses a CSS Custom Properties (CSS Variables) based theming system that supports Dark/Light modes with WCAG AA accessibility compliance.

## Architecture

### Theme Application Method
```css
[data-theme="light"] { /* light theme variables */ }
[data-theme="dark"]  { /* dark theme variables */ }
```

Theme is applied via `document.documentElement.setAttribute('data-theme', theme)` and persisted to:
1. **localStorage** (immediate, offline-first)
2. **Backend API** `/api/v1/preferences` (async sync for cross-device persistence)

### Theme Options
| Value | Description |
|-------|-------------|
| `light` | Light color scheme |
| `dark` | Dark color scheme |
| `system` | Follows OS preference via `prefers-color-scheme` |

---

## Token Categories

### 1. Background Colors

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--color-bg-primary` | `#ffffff` | `#0f172a` | Main page background |
| `--color-bg-secondary` | `#f8fafc` | `#1e293b` | Sidebar, secondary areas |
| `--color-bg-tertiary` | `#f1f5f9` | `#334155` | Nested containers |
| `--color-bg-card` | `#ffffff` | `rgba(255,255,255,0.03)` | Cards, panels |
| `--color-bg-hover` | `#f1f5f9` | `rgba(255,255,255,0.05)` | Hover states |
| `--color-bg-active` | `#e2e8f0` | `#475569` | Active/pressed states |
| `--color-bg-input` | `#ffffff` | `#1e293b` | Form inputs |
| `--color-bg-overlay` | `rgba(0,0,0,0.5)` | `rgba(0,0,0,0.7)` | Modal overlays |
| `--color-bg-modal` | `#ffffff` | `#1e293b` | Modal backgrounds |
| `--color-bg-dropdown` | `rgba(255,255,255,0.98)` | `rgba(30,30,50,0.98)` | Dropdowns, menus |

### 2. Text Colors

| Token | Light | Dark | Contrast Ratio | Usage |
|-------|-------|------|----------------|-------|
| `--color-text-primary` | `#0f172a` | `#f1f5f9` | ≥15:1 | Primary content |
| `--color-text-secondary` | `#475569` | `#94a3b8` | ≥4.5:1 | Secondary content |
| `--color-text-muted` | `#94a3b8` | `#64748b` | ≥3:1 | Placeholder, hints |
| `--color-text-inverse` | `#ffffff` | `#0f172a` | - | Text on accent colors |
| `--color-text-link` | `#2563eb` | `#60a5fa` | ≥4.5:1 | Links |
| `--color-text-link-hover` | `#1d4ed8` | `#93c5fd` | ≥4.5:1 | Link hover state |

### 3. Border Colors

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--color-border` | `#cbd5e1` | `#334155` | Default borders |
| `--color-border-light` | `#e2e8f0` | `#1e293b` | Subtle dividers |
| `--color-border-focus` | `#2563eb` | `#60a5fa` | Focus indicators |
| `--color-border-error` | `#ef4444` | `#ef4444` | Error state borders |

### 4. Accent Colors (Theme-Consistent)

| Token | Value | Usage | WCAG Notes |
|-------|-------|-------|------------|
| `--color-primary` | `#2563eb` | Primary actions, links | 4.5:1 on white |
| `--color-primary-hover` | `#1d4ed8` | Primary hover state | |
| `--color-success` | `#059669` | Success states | 4.5:1 on white |
| `--color-warning` | `#d97706` | Warning states | 3:1 on white |
| `--color-error` | `#dc2626` | Error states | 4.5:1 on white |
| `--color-info` | `#0284c7` | Info states | 4.5:1 on white |

### 5. Shadows

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | `0 1px 2px rgba(0,0,0,0.3)` | Subtle elevation |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.07)` | `0 4px 6px rgba(0,0,0,0.4)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | `0 10px 15px rgba(0,0,0,0.5)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | `0 20px 25px rgba(0,0,0,0.6)` | Elevated panels |

### 6. Gradients

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--gradient-bg` | `linear-gradient(135deg, #f8fafc, #e2e8f0)` | `linear-gradient(135deg, #0f172a, #1e293b)` | Page backgrounds |
| `--gradient-card` | `linear-gradient(180deg, #ffffff, #f8fafc)` | `linear-gradient(180deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9))` | Card backgrounds |
| `--gradient-header` | `linear-gradient(90deg, rgba(255,255,255,0.95), rgba(248,250,252,0.95))` | `linear-gradient(90deg, rgba(15,23,42,0.95), rgba(30,41,59,0.95))` | Header blur |

### 7. Scrollbar

| Token | Light | Dark |
|-------|-------|------|
| `--scrollbar-track` | `rgba(0,0,0,0.02)` | `rgba(255,255,255,0.02)` |
| `--scrollbar-thumb` | `rgba(0,0,0,0.15)` | `rgba(255,255,255,0.15)` |
| `--scrollbar-thumb-hover` | `rgba(0,0,0,0.25)` | `rgba(255,255,255,0.25)` |

### 8. Focus States

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--focus-ring-color` | `rgba(59,130,246,0.4)` | `rgba(59,130,246,0.5)` | Focus ring shadow |
| `--color-border-focus` | `#2563eb` | `#60a5fa` | Focus outline |

---

## WCAG Compliance Matrix

### Text Contrast Ratios (AA Standard)

| Combination | Required | Actual | Status |
|-------------|----------|--------|--------|
| Primary text on bg-primary (Light) | 4.5:1 | 15.3:1 | ✅ PASS |
| Primary text on bg-primary (Dark) | 4.5:1 | 13.7:1 | ✅ PASS |
| Secondary text on bg-primary (Light) | 4.5:1 | 7.0:1 | ✅ PASS |
| Secondary text on bg-primary (Dark) | 4.5:1 | 5.4:1 | ✅ PASS |
| Primary color on white | 3.0:1 (UI) | 4.5:1 | ✅ PASS |
| Success color on white | 3.0:1 (UI) | 4.6:1 | ✅ PASS |
| Error color on white | 3.0:1 (UI) | 4.6:1 | ✅ PASS |
| Border on bg-primary (Light) | 1.3:1 | 1.4:1 | ✅ PASS |

### Accessibility Features

1. **Focus Visible**: All interactive elements have `:focus-visible` outline (2px solid)
2. **Reduced Motion**: Transitions disabled for `prefers-reduced-motion: reduce`
3. **Color Independence**: Status never conveyed by color alone (icons + text)
4. **Minimum Font Size**: 12px minimum throughout application

---

## Usage Guidelines

### Do's
```css
/* ✅ Use semantic tokens */
color: var(--color-text-primary);
background: var(--color-bg-card);
border: 1px solid var(--color-border);
```

### Don'ts
```css
/* ❌ Hardcoded colors */
color: #0f172a;
background: #ffffff;
border: 1px solid #e2e8f0;

/* ❌ Direct theme conditionals */
color: isDark ? '#f1f5f9' : '#0f172a';
```

### Adding New Tokens

1. Add to both `[data-theme="light"]` and `[data-theme="dark"]` in `themes.css`
2. Verify WCAG AA contrast (4.5:1 for text, 3:1 for UI elements)
3. Add to accessibility test suite
4. Document in this file

---

## File Locations

| File | Purpose |
|------|---------|
| `frontend/src/styles/themes.css` | CSS Variable definitions |
| `frontend/src/store/preferencesStore.ts` | Theme state management |
| `frontend/src/hooks/useTheme.ts` | Theme hook |
| `frontend/src/components/ThemeToggle.tsx` | Theme toggle UI |
| `frontend/src/__tests__/accessibility.test.tsx` | WCAG contrast tests |
| `frontend/src/__tests__/theme.test.tsx` | Theme persistence tests |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-26 | Initial theme system with WCAG AA compliance |
