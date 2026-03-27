# LMV Harness Page

## Context
The harness orchestrates end-to-end migration validation: connect to ADF, fetch a pipeline, translate with wkmigrate, validate, and optionally suggest fixes. It's the "one-click" experience for implementation teams who want to validate a pipeline by name without manually exporting JSON.

## Purpose
Enter a pipeline name, run the full harness, see the scorecard plus fix suggestions. This page may take 30-60 seconds to complete (it calls ADF + wkmigrate + validation), so loading state is critical.

## Layout

### Top section — description
- Page title: "Harness Run" in Outfit, 20px, 600 weight
- Subtitle paragraph: "End-to-end: fetch ADF pipeline, translate with wkmigrate, validate, and optionally suggest fixes." in DM Sans, 13px, secondary color, max-width 600px

### Input Card
- Single card with a horizontal flex layout:
  - Left (flex: 1): Pipeline Name input
    - Label: "PIPELINE NAME" in monospace, uppercase, muted
    - Text input: full width, dark base background, border, monospace font, 13px
    - Placeholder: "e.g., etl_daily_ingestion"
    - Focus brightens border to accent blue
    - Supports Enter key to submit
  - Right: "Run Harness" button (same style as Validate button)
    - Disabled (50% opacity) when input is empty or loading
    - Text changes to "Running..." during request

### Loading state
- Full-width card below input
- Centered spinner with message: "Running harness — this may take a minute..."
- Spinner: same style as Validate page

### Results (after success) — two-column layout
**Left column (280px fixed): Scorecard Card**
- Centered gauge (same component as Validate page)
- Below gauge: two metadata lines in monospace, 11px, muted:
  - "Pipeline: {name}" with name in primary color
  - "Iterations: {count}" with count in primary color

**Right column (flex: 1): Details**
- Top card: Dimension Breakdown (same component as Validate page)
- Below (if fix suggestions exist): Fix Suggestions Card
  - Header: "FIX SUGGESTIONS" in Outfit, 14px, 600 weight, amber color, uppercase
  - Each suggestion as a pre-formatted block:
    - Dark base background, border, 8px radius, 10px padding
    - Monospace font, 12px, secondary color
    - JSON-formatted content
    - 8px bottom margin between suggestions

### Error state
- Red error banner (same component as Validate page)
- Dismissible with X button

## Animations
- Page fade-in-up (0.4s)
- Results appear with fade-in-up (0.4s) after loading completes
- Gauge and dimension bars animate as on Validate page

## Style
Same system. Input fields: dark base background, border, monospace, 10px vertical + 14px horizontal padding, 8px radius.
