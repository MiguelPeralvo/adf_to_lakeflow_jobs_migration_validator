# LMV App Shell — Navigation & Layout

## Context
Lakeflow Migration Validator (LMV) — a Databricks App that helps migration teams validate ADF-to-Databricks Lakeflow Jobs conversions. Used by data engineers and solutions architects during enterprise migration projects.

## Purpose
The app shell provides navigation between four core pages: Validate, Harness, Parallel Test, and History. It should communicate "precision engineering tooling" — not a consumer app, but a professional instrument.

## Layout
- Fixed dark sidebar on the left (220px wide)
- Top of sidebar: product name "Lakeflow Migration Validator" in two lines, with "Migration Validator" in accent blue. Below that, version badge "LMV v0.1.0" in monospace, muted
- Four navigation items stacked vertically, each with:
  - A small square icon container (28px, rounded 6px corners)
  - Label text to the right
  - Active state: icon container fills accent blue, text turns accent blue, row has subtle blue tint background
  - Inactive state: icon container is dark surface, text is muted gray
- Navigation items: Validate (checkmark icon), Harness (refresh/cycle icon), Parallel (left-right arrows icon), History (hourglass icon)
- Bottom of sidebar: small footer text "ADF → Databricks / Lakeflow Jobs" in monospace, muted, separated by a thin horizontal line
- Main content area fills remaining width, padded 32px top, 40px sides, max-width 1100px
- Content area has no visible border — just the dark base background

## Style
- Background base: #060a13 (deep navy-black)
- Sidebar surface: #0c1221 (slightly lighter)
- Borders: #1a2744 (subtle, 1px)
- Accent blue: #2d7ff9
- Text primary: #dfe6f0
- Text secondary: #7a8ba8
- Text muted: #4a5a75
- Font display (product name, headings): Outfit, 600-700 weight
- Font body (nav labels): DM Sans, 400-500 weight
- Font mono (version, footer): IBM Plex Mono, 400 weight
- Transitions: 180ms ease on hover/active states
- No shadows on sidebar — just the right border separates it from content
