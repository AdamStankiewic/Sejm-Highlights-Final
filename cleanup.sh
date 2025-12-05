#!/bin/bash
# Automatyczny cleanup projektu Sejm Highlights Final
# Autor: Claude AI Assistant
# Data: 2025-12-05

set -e  # Exit on error

echo "🧹 SEJM HIGHLIGHTS CLEANUP SCRIPT"
echo "=================================="
echo ""

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# === KROK 1: Cleanup lokalnych plików ===
echo -e "${YELLOW}[1/5] Cleaning local cache files...${NC}"

# Python cache
if [ -d "__pycache__" ]; then
    echo "  ❌ Removing __pycache__/"
    rm -rf __pycache__
fi

find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Ruff cache
if [ -d ".ruff_cache" ]; then
    echo "  ❌ Removing .ruff_cache/"
    rm -rf .ruff_cache
fi

# Temp files
if [ -d "temp" ]; then
    echo "  🗑️ Cleaning temp/"
    rm -rf temp/*
    mkdir -p temp
fi

echo -e "${GREEN}  ✅ Cache cleaned${NC}"
echo ""

# === KROK 2: Backup venv requirements ===
echo -e "${YELLOW}[2/5] Backing up requirements...${NC}"

if [ -d "venv" ] || [ -d "venv311" ]; then
    # Try to generate fresh requirements from current venv
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        pip freeze > requirements_backup.txt
        deactivate
        echo -e "${GREEN}  ✅ Requirements saved to requirements_backup.txt${NC}"
    elif [ -f "venv311/bin/activate" ]; then
        source venv311/bin/activate
        pip freeze > requirements_backup.txt
        deactivate
        echo -e "${GREEN}  ✅ Requirements saved to requirements_backup.txt${NC}"
    else
        echo -e "${YELLOW}  ⚠️ Could not activate venv, skipping backup${NC}"
    fi
fi
echo ""

# === KROK 3: Remove venv (optional - ask user) ===
echo -e "${YELLOW}[3/5] Virtual environments...${NC}"
echo -e "${RED}⚠️ WARNING: This will remove venv/ and venv311/${NC}"
echo -e "You can recreate them with: ${GREEN}python -m venv venv && pip install -r requirements.txt${NC}"
echo ""
read -p "Remove virtual environments? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -d "venv" ]; then
        echo "  ❌ Removing venv/"
        rm -rf venv
    fi
    if [ -d "venv311" ]; then
        echo "  ❌ Removing venv311/"
        rm -rf venv311
    fi
    echo -e "${GREEN}  ✅ Virtual environments removed${NC}"
else
    echo -e "${YELLOW}  ⏭️ Skipping venv removal${NC}"
fi
echo ""

# === KROK 4: Git cleanup (move dev tools) ===
echo -e "${YELLOW}[4/5] Git cleanup - moving dev tools...${NC}"

# Create dev/ folder if not exists
mkdir -p dev

# Move dev tools
DEV_FILES=(
    "APP_URL_INTEGRATION_SNIPPET.py"
    "check_srt.py"
    "finish_processing.py"
    "list_youtube_channels.py"
    "quick_export.py"
    "regenerate_hardsub.py"
    "monitor_gpu.py"
    "test_correct_channel.py"
    "test_youtube_auth.py"
)

MOVED_COUNT=0
for file in "${DEV_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  📦 Moving $file to dev/"
        git mv "$file" "dev/" 2>/dev/null || mv "$file" "dev/"
        MOVED_COUNT=$((MOVED_COUNT + 1))
    fi
done

echo -e "${GREEN}  ✅ Moved $MOVED_COUNT dev tools to dev/${NC}"
echo ""

# === KROK 5: Update .gitignore ===
echo -e "${YELLOW}[5/5] Updating .gitignore...${NC}"

# Check if already has project-specific entries
if ! grep -q "# Project-specific" .gitignore; then
    cat >> .gitignore << 'EOF'

# Project-specific
output/
temp/
downloads/
models/*.pt
models/*.bin
venv311/

# Development (optional - uncomment to ignore dev/ folder)
# dev/

# System files
*.swp
*.swo
*~
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.code-workspace

EOF
    echo -e "${GREEN}  ✅ .gitignore updated${NC}"
else
    echo -e "${YELLOW}  ⏭️ .gitignore already updated${NC}"
fi
echo ""

# === FINAL: Git status ===
echo -e "${YELLOW}Git Status:${NC}"
git status --short

echo ""
echo -e "${GREEN}✅ CLEANUP COMPLETE!${NC}"
echo ""
echo "Next steps:"
echo "  1. Review changes: git status"
echo "  2. Commit: git add . && git commit -m 'chore: Project cleanup and reorganization'"
echo "  3. Recreate venv: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
echo ""
echo "See CLEANUP_AND_STABILIZATION_PLAN.md for full plan"
