#!/bin/sh
# Builds dyspatch-claude-plugin/dyspatch.plugin (a zip of the plugin folder's
# contents) from the git index, so the package matches exactly what is staged.
#
# Usage: scripts/build-plugin.sh [output-path]

set -e

PLUGIN_DIR=dyspatch-claude-plugin
PACKAGE=dyspatch.plugin

cd "$(git rev-parse --show-toplevel)"
out=${1:-$PLUGIN_DIR/$PACKAGE}

tree=$(git write-tree)
git archive --format=zip --mtime=@0 "$tree:$PLUGIN_DIR" -- . \
	':!README-DEV.md' ":!$PACKAGE" > "$out"

echo "Built $out"
