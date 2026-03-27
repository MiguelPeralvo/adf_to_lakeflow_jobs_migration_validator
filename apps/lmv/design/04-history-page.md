# LMV History Page

## Context
Implementation teams run validations repeatedly as they iterate on pipeline conversions. The history page lets them search for a pipeline by name and see how its quality score has changed over time — tracking progress from "Manual Intervention" to "High Confidence."

## Purpose
Search by pipeline name, see a timeline of past scorecards, expand any entry to view the full dimension breakdown.

## Layout

### Search Card
- Full-width card with horizontal flex:
  - Text input (flex: 1): pipeline name search
    - Placeholder: "Pipeline name to search..."
    - Supports Enter key to submit
  - "Search" button (accent blue)

### Loading state
- Card with spinner and "Loading history..."

### Empty state (after search, no results)
- Card with centered muted text: `No history found for "{name}"`

### Results — timeline list
- Vertical stack of expandable entries, 8px gap between them
- Each entry is a card-like row:
  - Default (collapsed): single row with:
    - Left: score number in Outfit, 22px, 700 weight, color-coded, right-aligned in 50px space
    - Label badge pill (same style as Validate page gauge badge)
    - Spacer (flex: 1)
    - Timestamp: monospace, 11px, muted, formatted as "Mar 27, 2026, 3:45 PM"
    - Expand arrow: small chevron, rotates 180deg when expanded
  - Entire row is clickable (cursor pointer, no user-select)
  - Background changes to elevated color (#111d33) when expanded
  - Border: 1px solid border color, 8px radius

  - Expanded: below the collapsed row, the full Dimension Breakdown component appears
    - 18px horizontal padding, 18px bottom padding
    - Fade-in-up animation (0.3s)
    - Same dimension bars and expandable details as the Validate page

### Behavior
- Only one entry expanded at a time (clicking another collapses the previous)
- Entries ordered by timestamp (most recent first)
- Score numbers provide instant visual scanning — you can see the progression from red to amber to green at a glance

## Animations
- Page fade-in-up
- Timeline entries slide-in staggered (not needed if list is long — only animate first 10)
- Expand/collapse: chevron rotation (180ms), detail panel fade-in-up (0.3s)

## Style
Same system. The timeline entries should feel like log entries — dense, scannable, monospace timestamps. The score numbers are the visual anchor — large, bold, color-coded.
