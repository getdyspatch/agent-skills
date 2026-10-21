---
name: review-block-overrides
description: Reviews every block in a Dyspatch account for hardcoded visual styles (colours, backgrounds, fonts, borders) that override theme styles and stop the block working across themes. Use when someone asks which blocks have inline or hardcoded styles, whether blocks are theme-agnostic, or is consolidating themes or sharing blocks between them.
---

# Review block overrides

Finds, block by block, every fixed visual value that beats the theme: a `background-color='#005640'` on a `dys-row`, an inline `style="color:#fff"`, or a `<dys-style>` rule. A block with none of these picks up whichever theme it's used in.

Read-only. It makes no changes to the account.

## When to use
- "Which blocks have hardcoded colours/fonts?", "are my blocks theme-agnostic?"
- Before merging themes, adding a new theme, or sharing blocks across themes/brands
- Cleaning up a block library (the report also flags unused and unassigned blocks)

## When NOT to use
- Reviewing one block's code → just read that block with `SingleBlockQuery`
- Comparing theme settings to each other → `getThemeComponentComparison`
- Fixing the overrides → this skill only reports. Offer to fix them as a separate step.

## Requirements
- Dyspatch MCP connected, and a user who can view blocks and themes
- Code execution (Python 3) for the bundled script. If there isn't any, use the manual method in `references/rules.md`.

## Steps

1. **Confirm scope in one question** (skip if the user already said). The default is all blocks and visual properties only. Offer `--include-spacing` if they also care about padding/margins.

2. **Fetch three responses and save each raw to a file.** All are read-only `invoke_tool` calls with `{}` args:
   | Tool | Gives | File |
   |---|---|---|
   | `GetAllBlocksQuery` | DML for every block | `blocks.json` |
   | `GetMinimalBlocksListQuery` | `templatesCount`, `themesCount` | `usage.json` |
   | `GetThemesWithBlockIDsQuery` | active theme → block IDs | `themes.json` |

   Responses are large (~1.5 KB per block). If the client already saved an oversized result to a file, use that file path as-is, because the script handles both formats. Don't re-read these into context.

3. **Run the script:**
   ```bash
   python3 scripts/audit_blocks.py --blocks blocks.json --usage usage.json --themes themes.json --out block-override-report.md
   ```
   It prints a JSON summary: counts, the top blocks and the top colours. `--usage` and `--themes` are optional. Without them the report skips the usage notes.

4. **Spot-check before reporting.** Open the DML of one flagged block and one clean block from `blocks.json`, and confirm the report matches. If the clean block contains a fixed visual value the script missed, tell the user and add it by hand.

5. **Report back briefly:**
   - Blocks scanned, how many were flagged, total overrides
   - The top 5 blocks by override count, each linked to its block in the app (`url` in the summary), noting which of them are unused
   - The most common hardcoded colours. These are good candidates for turning into theme colours or variables.
   - Counts for "not used in any template", "not assigned to any theme" and "only in archived themes"
   - A link to the report file. Don't paste the per-block detail into chat.

## Reading the results
- Every block name in the report links to its code view in the app: `https://app.dyspatch.io/block/base/<block_id>/code`.
- **Attribute** means a value set directly on a `dys-*` element. To fix it, remove the attribute so the theme default applies, or replace it with a theme variable (`@{...}`).
- **Inline style** means `style=""` on raw HTML inside the block. It's usually inside `dys-raw` or `dys-table`.
- **dys-style** means a CSS rule in the block. `!important` rules also beat theme CSS and are the hardest to spot in the editor.
- **Only in archived themes:** the MCP counts archived themes as assignments, so the block looks assigned but isn't usable in any live theme.
- Button `variant` is not an override. It selects a theme style.

## Limits
- Very large accounts give very large responses, and there's no pagination yet. Clients that spill big outputs to files handle this best.
- Archived blocks can't be excluded account-wide, so all blocks returned are scanned.
- Archived theme names aren't returned, only counts.

<!--
REVIEW NOTE (delete before sharing):
Testing log
- 2026-09-25 — Dyspatch.io org, Cowork — 161 blocks, 105 flagged, 993 overrides — pass; one parser miss (AMPscript `%>` in href) found by spot-check and fixed in script
Related findings: F-005 (no pagination), F-006 (archived theme counts), F-007 (no archived block filter)
-->
