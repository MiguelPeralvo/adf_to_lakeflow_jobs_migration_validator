# LMV Parallel Test Page

## Context
The parallel test runs the same pipeline on both ADF and Databricks, compares outputs per activity, and scores equivalence. This is the ultimate migration validation — not "does the code look right" but "does it produce the same result."

## Purpose
Enter a pipeline name and parameters, run both sides, see a comparison table showing which activities match and which diverge, plus an equivalence score.

## Layout

### Top section
- Page title: "Parallel Test" in Outfit, 20px, 600 weight
- Subtitle: "Run the ADF pipeline and converted Lakeflow Job side-by-side, compare outputs per activity." in DM Sans, 13px, secondary color, max-width 600px

### Input Card
- Two-column grid inside the card:
  - Left: Pipeline Name input (same style as Harness page)
  - Right: Parameters (JSON) input
    - Label: "PARAMETERS (JSON)"
    - Text input with placeholder: `{"env": "dev"}`
    - Monospace font
- Below inputs: "Run Parallel Test" button

### Loading state
- "Executing on ADF + Databricks..." with spinner

### Results — two-column layout
**Left column (280px): Scores**
- Equivalence Gauge (compact):
  - 56px diameter circle with 3px colored border
  - Percentage number inside, Outfit 18px, 700 weight, color-coded
  - Label "Equivalence" in Outfit 14px, 600 weight
  - Sublabel "ADF vs Databricks" in monospace 11px, muted
  - Glow shadow matching the color
- Below: full CCS Scorecard Gauge

**Right column (flex: 1): Comparison Table Card**
- Full-width data table with:
  - Header row: "Activity", "Match", "ADF Output", "Databricks Output", "Diff"
    - Monospace, 11px, muted, uppercase, letter-spaced
    - 2px bottom border (bright border color)
  - Data rows (one per activity):
    - Activity name: monospace, 12px, primary color, 500 weight
    - Match column: circular indicator (24px)
      - Green background tint + green checkmark if match
      - Red background tint + red X if mismatch
    - ADF Output: monospace, 12px, secondary color, max-width 200px, ellipsis overflow, title tooltip with full value
    - Databricks Output: same style
    - Diff: monospace, 12px, red color if present, italic "—" if no diff
  - Rows animate in with slide-in (0.3s, staggered 40ms)
  - Rows have 1px bottom border, 10px vertical + 14px horizontal padding

## Animations
- Page fade-in-up
- Results fade-in-up after loading
- Table rows staggered slide-in
- Equivalence gauge number animates up from 0

## Style
Same system. Table uses full width of the card. No zebra striping — use the row borders for separation. Match indicators are the visual anchor of each row.
