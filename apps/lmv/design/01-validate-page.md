# LMV Validate Page

## Context
The primary page of the Lakeflow Migration Validator. A data engineer pastes ADF pipeline JSON, clicks Validate, and sees a detailed quality scorecard. This is the page they use most — it must be immediately understandable and visually impressive.

## Purpose
Upload an ADF pipeline definition (JSON), run validation, display a Conversion Confidence Score (0-100) with per-dimension breakdown across 7 quality dimensions.

## Layout

### Top section — two-column grid
**Left column: JSON Editor Card**
- Card with dark surface background, subtle border, 14px rounded corners
- Label above textarea: "ADF PIPELINE JSON" in monospace, uppercase, muted, letter-spaced
- Large textarea (300px tall, full width) with:
  - Dark base background (#060a13)
  - Monospace font (IBM Plex Mono, 12px)
  - 14px padding
  - Border brightens to accent blue on focus
  - Placeholder JSON showing a sample pipeline structure
- Below textarea: "Validate" button
  - Accent blue background (#2d7ff9), white text
  - Outfit font, 600 weight, 13px
  - 10px vertical / 28px horizontal padding
  - Rounded corners (8px)
  - Dims to 70% opacity while loading
  - Text changes to "Validating..." during request

**Right column: Scorecard Gauge Card**
- Same card style as left column
- Centered vertically and horizontally
- Before validation: muted monospace text "Paste ADF JSON and click Validate / to see the Conversion Confidence Score"
- During loading: spinner (36px circle, 3px border, accent blue top border, rotating 0.8s linear)
- After validation: large SVG radial gauge
  - 200px diameter circle
  - 14px stroke width
  - Background track: border color
  - Foreground arc: color-coded by score
    - Green (#00d68f) for score >= 90
    - Amber (#ffb547) for 70-89
    - Red (#ff5c5c) for < 70
  - Arc animates clockwise from 0 to score over 1.2s with ease-out curve
  - Subtle colored glow shadow behind the arc
  - Score number centered inside: Outfit font, 48px, 700 weight
  - Below gauge: label badge pill
    - "High Confidence" / "Review Recommended" / "Manual Intervention"
    - Monospace, 11px, uppercase, letter-spaced
    - Background tinted with the score color at 12% opacity
    - 1px border in score color at 13% opacity
    - Rounded pill (20px radius)

### Bottom section — Dimension Breakdown Card
- Full-width card below the two columns (20px gap)
- Appears with fade-in-up animation (0.5s delay after scorecard)
- Header: "DIMENSION BREAKDOWN" in Outfit, 14px, 600 weight, uppercase, muted, letter-spaced
- Seven dimension rows, sorted worst-to-best score, each with:
  - Left: small circle (18px) — green with checkmark if passed, red with X if failed
  - Name label: DM Sans, 13px, 500 weight, 180px fixed width
  - Score bar: flex-growing horizontal bar
    - Background: border color
    - Fill: color-coded (green/amber/red) with width = score percentage
    - 6px tall, 3px border-radius
    - Fill animates from 0 width (0.8s, staggered 60ms per row)
    - Subtle glow shadow on the fill
  - Score percentage: IBM Plex Mono, 13px, 600 weight, color-coded, 45px right-aligned
  - Expand arrow: small down-chevron, rotates 180deg when expanded
- Each row is clickable — expands to show a detail panel:
  - Indented 32px from left
  - Dark base background, subtle border, 8px radius, 12px padding
  - Key-value pairs in monospace:
    - Key: 11px, muted, 140px min-width
    - Value: 12px, secondary color
  - Shows dimension-specific details: placeholder task keys, notebook errors with file paths, missing parameter names, missing secret scope/key pairs, dependency counts

## Interaction states
- Error: red banner with warning icon, error message in monospace, dismiss X button
- Empty JSON / invalid JSON: error banner replaces gauge area
- All API calls use fetch with proper error handling

## Animations
- Page enters with fade-in-up (0.4s)
- Gauge arc reveals clockwise (1.2s cubic-bezier)
- Dimension bars grow from left (0.8s, staggered)
- Dimension rows slide in from left (0.4s, staggered 60ms)
- Detail panels fade in on expand

## Style
Same color/font system as app shell. Cards use #0c1221 background with #1a2744 border and 14px border-radius. 24px internal padding. Shadow: 0 2px 12px rgba(0,0,0,0.4).
