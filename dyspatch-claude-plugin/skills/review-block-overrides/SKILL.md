---
name: review-block-overrides
description: Reviews the blocks in a Dyspatch account, through the Dyspatch MCP server, for hardcoded visual styles (colours, backgrounds, fonts, borders) that override theme styles and stop a block working across themes. Also flags blocks that aren't assigned to any theme or are only in archived themes. Use this when someone asks which blocks have inline or hardcoded styles, whether their blocks are theme-agnostic or portable, wants a block library audit or cleanup, or is consolidating themes, adding a theme, rebranding, or sharing blocks between themes or brands.
---

# Review block overrides

Finds, block by block, every fixed visual value that beats the theme: a `background-color='#005640'` on a `dys-row`,
a `color` on a link, an inline `style="color:#fff"`, or a `<dys-style>` rule. A block with none of these picks up
whichever theme it's used in.

Read-only. It makes no changes to the account.

## When to use
- "Which blocks have hardcoded colours/fonts?", "are my blocks theme-agnostic?"
- Before merging themes, adding a new theme, rebranding, or sharing blocks across themes/brands
- Cleaning up a block library (the report also flags unassigned blocks and blocks only in archived themes)

## When NOT to use
- Reviewing one block's code → read that block with `get_block {blockId}`
- Comparing a theme's component variants → `get_theme_component_comparison {themeId}`
- Fixing the overrides → this skill only reports. Offer to fix them as a separate step.

## Requirements
- **The Dyspatch MCP server, connected.** If its tools (`invoke_tool`, `get_who_am_i`) aren't available, stop
  and ask the user to connect the Dyspatch MCP in Claude. Don't try to work without it.
- A Dyspatch user who can view blocks and themes.
- Code execution (Python 3.8+) for the bundled script. If there isn't any, use the manual method in
  `references/rules.md`, and limit the review to one theme.

## Calling the MCP
- Every call here is a read-only query: `invoke_tool({toolName, args})`. Call tools by the names below. Don't use
  `discover_tools`.
- Never send a failing call twice unchanged. If a call fails, check its args against this file once, and if it
  fails again, tell the user which call failed and stop.

## Steps

1. **Confirm scope in one question** (skip if the user already said):
   - **All blocks** (default) or **one theme**. A whole account is one large response (about 10 KB per block;
     2.5 MB for 256 blocks). One theme is much smaller, and is the only practical option in a client that can't
     save large tool results to a file.
   - Visual properties only (default), or spacing too (`--include-spacing` flags padding and margins).

   For one theme, call `get_themes_with_block_ids` first and match the theme by name to get its `id`.

2. **Fetch two responses and save each raw to a file.** Run them in parallel:
   | Tool | Args | Gives | File |
   |---|---|---|---|
   | `get_blocks` | `{}`, or `{themeId}` for one theme | every block's DML (`html`) and theme IDs (`themes[]`, archived themes included) | `blocks.json` |
   | `get_themes_with_block_ids` | `{}` | active themes, their names and block IDs (~55 KB) | `themes.json` |

   If the client saved an oversized result to a file, pass that file path to the script as-is. The script reads
   both the bare JSON and the `[{"type":"text","text":…}]` wrapper. **Don't read these files into context.**

3. **Run the script:**
   ```bash
   python3 scripts/audit_blocks.py --blocks blocks.json --themes themes.json --out block-override-report.md
   ```
   It writes the report and prints a JSON summary: counts, notes, the top 5 blocks (with `id` and `url`) and the
   top colours. `--themes` is optional. Without it, the report can't name themes or tell active themes from
   archived ones.

4. **Check template usage for the top blocks.** Call `get_block_templates {blockId}` for each of the top 5 blocks
   (run them in parallel). An empty `templates` list means no email uses the block, so fixing it is low-risk.
   Don't call it for every block.

5. **Spot-check before reporting.** In `blocks.json`, find one flagged block and one clean block (search by ID,
   don't load the file), read their `html`, and confirm the report matches. If the clean block has a fixed visual
   value that the script missed, tell the user and add it to the report by hand.

6. **Report back briefly:**
   - Blocks scanned, how many were flagged, total overrides
   - The top 5 blocks by override count, each linked to its block in the app (`url` in the summary), with how many
     templates use each one
   - The most common hardcoded colours. These are good candidates for theme colours or variables.
   - Counts for "Not assigned to any theme" and "Only in archived themes"
   - A link to the report file. Don't paste the per-block detail into chat.

## Reading the results
- Every block name in the report links to its code view in the app: `https://app.dyspatch.io/block/base/<block_id>/code`.
- **Attribute** means a value set directly on an element: a `dys-*` element, a link's `color`, or a legacy
  `bgcolor`. To fix it, remove the attribute so the theme default applies, or replace it with a theme variable (`@{...}`).
- **Inline style** means `style=""` on raw HTML inside the block. It's usually inside `dys-raw` or `dys-table`.
- **dys-style** means a CSS rule in the block. `!important` rules also beat theme CSS and are the hardest to spot
  in the editor.
- **Only in archived themes:** the block is assigned to themes, but all of them are archived, so it isn't usable
  in any live theme.
- Button `variant` is not an override. It selects a theme style.
- The same colour can appear as a hex value and as a name (`#FFFFFF` and `white`). Treat them as one when you
  suggest theme colours.

## Limits
- `get_blocks` has no pagination input. It returned all 256 blocks of a test account in one page; if a response
  has `hasMoreResults: true`, say the review covers only the blocks returned.
- Archived blocks can't be excluded, so every block returned is scanned.
- Archived themes' names aren't returned, only that a block is in them.
- Template usage is checked for the top blocks only, because it takes one call per block.
