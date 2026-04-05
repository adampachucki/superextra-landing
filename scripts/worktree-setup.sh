#!/bin/bash
# Sets up a new worktree with symlinked env files and fresh node_modules
set -e
MAIN_REPO="$HOME/src/superextra-landing"
WT_DIR="$1"

# Symlink env files
ln -sf "$MAIN_REPO/.env" "$WT_DIR/.env"
ln -sf "$MAIN_REPO/agent/.env" "$WT_DIR/agent/.env"

# Install node dependencies
cd "$WT_DIR"
npm install --no-audit --no-fund 2>&1 | tail -1
echo "Worktree ready: $WT_DIR"
