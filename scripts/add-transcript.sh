#!/bin/bash
#
# Add a call transcript to Notion with auto-generated summary.
#
# Usage:
#   ./scripts/add-transcript.sh restaurants <file> [contact] [company]
#   ./scripts/add-transcript.sh partners   <file> [contact] [company]
#
# Examples:
#   ./scripts/add-transcript.sh restaurants transcript.txt "Jan Kowalski" "Pasta Palace"
#   ./scripts/add-transcript.sh partners call-notes.md "Anna Nowak" "VC Fund"
#   ./scripts/add-transcript.sh restaurants transcript.txt   # contact/company extracted from transcript
#
# Requires: claude CLI with Notion MCP configured

set -euo pipefail

# Notion page IDs for transcript sections
RESTAURANTS_PAGE="33052664-96b3-81bf-a37a-dcbdc7fd4a06"
PARTNERS_PAGE="33052664-96b3-810e-9e8e-fa568a7abf4b"

usage() {
  echo "Usage: $0 <restaurants|partners> <transcript-file> [contact] [company]"
  exit 1
}

[[ $# -lt 2 ]] && usage

CATEGORY="$1"
FILE="$2"
CONTACT="${3:-}"
COMPANY="${4:-}"

[[ ! -f "$FILE" ]] && echo "Error: File not found: $FILE" && exit 1

case "$CATEGORY" in
  restaurants|r) PAGE_ID="$RESTAURANTS_PAGE"; LABEL="Customer Discovery — Restaurants" ;;
  partners|p)    PAGE_ID="$PARTNERS_PAGE";    LABEL="Customer Discovery — Partners & Investors" ;;
  *) echo "Error: Category must be 'restaurants' (or 'r') or 'partners' (or 'p')" && exit 1 ;;
esac

DATE=$(date +%Y-%m-%d)
TRANSCRIPT=$(cat "$FILE")

# Build optional context
CONTEXT=""
[[ -n "$CONTACT" ]] && CONTEXT="Contact: $CONTACT. "
[[ -n "$COMPANY" ]] && CONTEXT="${CONTEXT}Company: $COMPANY. "

PROMPT="You have access to Notion MCP. Create a new page under the Notion page with ID $PAGE_ID (\"$LABEL\").

${CONTEXT}Date: $DATE.

Do this:
1. Read the transcript below
2. Generate a title in format: \"$DATE — [Company/Person] — [One-line topic]\"
3. Create the Notion page with this structure:
   - First paragraph bold: \"Summary\"
   - 3-5 bullet points summarising key takeaways, pain points, and action items
   - Empty paragraph
   - Bold paragraph: \"Key Quotes\"
   - 2-3 notable direct quotes as bullet points
   - Empty paragraph
   - Bold paragraph: \"Full Transcript\"
   - The complete transcript as paragraphs (split into chunks if needed, max 2000 chars per block)

TRANSCRIPT:
$TRANSCRIPT"

echo "Adding transcript to: $LABEL"
echo "$PROMPT" | claude --print
