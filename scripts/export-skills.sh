#!/bin/bash
# Export Claude Code skills, knowledge, and memory for deployment to another machine.
# Run from the lmv repo root.
set -e

EXPORT_DIR="${1:-/tmp/claude-skills-export}"
mkdir -p "$EXPORT_DIR/skills/lmv-autodev"
mkdir -p "$EXPORT_DIR/skills/wkmigrate-autodev"
mkdir -p "$EXPORT_DIR/knowledge"
mkdir -p "$EXPORT_DIR/memory"

echo "Exporting skills..."
cp ~/.claude/skills/lmv-autodev/SKILL.md "$EXPORT_DIR/skills/lmv-autodev/"
cp ~/.claude/skills/wkmigrate-autodev/SKILL.md "$EXPORT_DIR/skills/wkmigrate-autodev/"

echo "Exporting knowledge base..."
cp knowledge/*.md "$EXPORT_DIR/knowledge/"

echo "Exporting memory..."
MEMORY_DIR=$(find ~/.claude/projects -type d -name "memory" -path "*adf*lakeflow*" 2>/dev/null | head -1)
if [ -n "$MEMORY_DIR" ]; then
    cp "$MEMORY_DIR"/*.md "$EXPORT_DIR/memory/"
else
    echo "WARNING: memory directory not found"
fi

echo "Exporting golden sets (calibration + corpus)..."
mkdir -p "$EXPORT_DIR/golden_sets"
cp golden_sets/calibration_pairs.json "$EXPORT_DIR/golden_sets/"
cp golden_sets/expression_loop_post_w16.json "$EXPORT_DIR/golden_sets/"

echo ""
echo "=== Export complete ==="
echo "Files at: $EXPORT_DIR"
echo ""
echo "To import on another machine:"
echo "  1. Clone the lmv repo"
echo "  2. Copy skills:    cp -r $EXPORT_DIR/skills/* ~/.claude/skills/"
echo "  3. Copy knowledge: cp $EXPORT_DIR/knowledge/*.md <repo>/knowledge/"
echo "  4. Copy golden sets: cp $EXPORT_DIR/golden_sets/* <repo>/golden_sets/"
echo "  5. Create memory dir: mkdir -p ~/.claude/projects/<project-hash>/memory/"
echo "     (Run 'claude' once in the repo to auto-create the project dir)"
echo "  6. Copy memory:    cp $EXPORT_DIR/memory/*.md ~/.claude/projects/<project-hash>/memory/"
echo ""
echo "The <project-hash> is auto-generated from the repo path."
echo "Find it with: ls ~/.claude/projects/ | grep adf"
