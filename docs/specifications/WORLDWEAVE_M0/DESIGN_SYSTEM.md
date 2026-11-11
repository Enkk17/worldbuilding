# Design System and UX Specification

## 1. Design direction

Visual concept: **premium fantasy editorial**. The product should feel like an elegant archive, atlas, and scholar's workspace—not a game HUD and not a skeuomorphic parchment novelty.

Principles:
- immersive but readable;
- restrained ornament;
- clear hierarchy;
- consistent interaction patterns;
- fast navigation;
- accessible contrast;
- responsive layouts;
- content-first pages.

## 2. Color tokens

Initial dark theme tokens (refine through contrast testing):
- `--ww-bg`: #10131B (Obsidian)
- `--ww-surface`: #191F2C (Midnight)
- `--ww-surface-raised`: #252D3C
- `--ww-border`: #303849
- `--ww-gold`: #C5A46D (Antique Gold)
- `--ww-blue`: #7892B5 (Arcane Blue)
- `--ww-forest`: #567C69
- `--ww-burgundy`: #9B6575
- `--ww-parchment`: #D8D0C0
- `--ww-text`: #E8EAF0
- `--ww-muted`: #AEB5C2

Provide semantic tokens for success, warning, danger, info, focus, disabled, and overlay. Never use color alone to communicate state.

Light theme is required for v1.0; it should use warm paper/stone surfaces without sacrificing contrast.

## 3. Typography

Use a highly readable UI sans-serif for controls and body text. A restrained serif display face may be used for universe titles and editorial headings. Do not use decorative fantasy fonts for paragraphs, forms, tables, or small labels. Bundle fonts locally where licensing permits; otherwise use robust system fallbacks.

## 4. Application shell

Desktop:
- left collapsible universe navigation;
- top bar with universe switcher, breadcrumbs, global search/command palette, notifications, profile;
- main content region;
- optional contextual right panel;
- resizable panels only where they materially help.

Mobile/tablet:
- compact navigation drawer or bottom navigation for primary destinations;
- reading-first layouts;
- editor controls adapted for touch;
- no hover-only interactions.

## 5. Navigation

Top-level modules:
- Overview
- Codex
- Chronicle
- Atlas
- Chronos
- Nexus
- Society
- Settings

`Ctrl/Cmd + K` opens a command palette for navigation, search, and common actions. Keyboard shortcuts must be discoverable and remappable or disableable if conflicts arise.

## 6. Core page patterns

### Overview
- universe identity banner;
- recent activity;
- quick-create actions;
- content statistics;
- member presence;
- customizable widgets later, not required as a full dashboard builder in v1.0.

### Codex list
- searchable, filterable, paginated table/card view;
- type filters;
- tags and status;
- sort and saved filters may be future enhancement;
- bulk actions only when permissions allow.

### Entity detail
- title and identity;
- summary;
- cover/media;
- structured properties;
- rich body;
- incoming/outgoing relations;
- linked documents;
- revision history;
- activity/comments.

### Editor
- distraction-reduced mode;
- outline/navigation;
- entity mention picker;
- autosave state that distinguishes local pending changes from server-confirmed persistence;
- collaboration presence;
- version history;
- accessible toolbar and keyboard commands.

### Atlas
- map canvas;
- zoom/pan;
- layer/marker panel;
- marker detail;
- keyboard-accessible marker list as an alternative to map-only interaction.

### Nexus
- bounded graph canvas;
- filter panel;
- node details;
- keyboard/search alternative;
- graph never becomes the only way to access relationships.

## 7. Components

Build a coherent component library:
- buttons, icon buttons, inputs, selects, comboboxes;
- dialogs, drawers, popovers, tooltips;
- tabs, breadcrumbs, command palette;
- cards, tables, pagination;
- badges, avatars, activity items;
- empty/loading/error states;
- entity cards and relation chips;
- editor toolbar;
- map marker controls;
- graph controls.

Use accessible primitives. Avoid one-off CSS for repeated patterns.

## 8. Motion and visual effects

- Short, purposeful transitions.
- Respect `prefers-reduced-motion`.
- No constant animated backgrounds.
- No excessive glassmorphism that harms contrast.
- Avoid parallax or heavy effects on content pages.
- Use ornamental motifs sparingly.

## 9. Accessibility

Target WCAG 2.2 AA:
- keyboard access;
- visible focus;
- semantic landmarks and headings;
- labels and error association;
- contrast;
- reduced motion;
- screen-reader names for icon-only buttons;
- non-color status indicators;
- map and graph alternatives;
- focus management in dialogs.

## 10. UX state requirements

Every data-driven screen must define:
- initial loading;
- empty state;
- populated state;
- validation error;
- permission denied;
- network failure;
- stale/conflict state;
- success confirmation;
- destructive-action confirmation.

Do not use fake data in production views. Demo fixtures must be clearly separated from real records.
