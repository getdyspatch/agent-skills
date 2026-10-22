---
name: block-optimizer
description: Analyzes and optimizes a Dyspatch block library (all blocks, chosen themes, or a workspace's themes) through the Dyspatch MCP server. Finds unused, stale and duplicate blocks; checks clarity (names, descriptions, tag usage), style consistency, accessibility, editability, hotlinked images, hardcoded links and raw HTML; and checks how well blocks and themes use Dyspatch features (theme logo, variants, mirror layout, editable groups, show, partials, dys-repeat, conditionals, block localization, dark mode and the Gmail light-mode lock). Reports in Markdown, HTML or PDF, and can apply approved fixes. Use this when someone wants a block or theme audit, cleanup or optimization, asks which blocks are unused, duplicated or out of date, wants to reduce or consolidate blocks, asks whether their themes use variants or dark mode, or wants blocks made more editable, reusable or accessible, even if they never say "optimize".
---

# Block optimizer (Dyspatch)

You're reviewing a block library the way a senior email developer would before a redesign or cleanup:

- What can go? (unused, stale and duplicate blocks)
- What's fragile? (hotlinked images, ESP tracking links copied from sent emails, raw HTML, hardcoded styles)
- What's hard for editors? (locked copy, vague names, near-identical blocks to choose between)
- Where would a Dyspatch feature remove whole blocks? (`show`, variants, mirror layout, `dys-repeat`, partials,
  conditionals, theme logo, block localization)

The output is a prioritized report and, if asked, approved fixes.

Two principles:

1. **Fewer, better findings.** A deterministic script does the counting. Your job is the judgement it can't make
   (is this raw HTML justified? what do these near-duplicates actually differ by?) and a short list of the changes
   worth making. Dedupe, and don't pad the report with Lows.
2. **Cheap on the MCP.** Every tool name and argument shape is in `references/tool-reference.md`. Read it before
   your first Dyspatch call, and don't use `discover_tools`. Batch independent calls in parallel. Never re-send a
   failing call unchanged; after one corrected retry, record the check as not run and move on. Large results stay
   on disk: pass the file paths to the scripts and never read those files into context.

Read `references/checks.md` before judging findings (Step 5). It has the severity rubric, the judgement calls, and
the DML syntax for every fix.

## Requirements
- **The Dyspatch MCP server, connected.** If `invoke_tool` and `get_who_am_i` aren't available, stop and ask the
  user to connect the Dyspatch MCP. Don't work around it.
- A Dyspatch user who can view blocks and themes (fix mode also needs edit rights).
- Code execution (Python 3.8+) for the scripts. Without it, use the manual method in `references/checks.md` §5, for
  one theme only.

## Step 0: Preferences

Look for `./.dyspatch/block-optimizer-preferences.json`, then `~/.dyspatch/block-optimizer-preferences.json`:

```json
{"report_format": "markdown", "owned_domains": ["acme.com", "acmecdn.net"], "stale_days": 365, "report_dir": "."}
```

Saved values count as "specified". Show them in one line ("Using your saved setup: PDF report, acme.com as your
domain, stale after 365 days") so the user can change them. After the run, save new answers to the user-level file
(create `~/.dyspatch/`), say where, and save only what the user actually chose. If the file can't be written, say so
and carry on.

## Step 1: Set up the run (one question, only for what's unspecified)

Work out these three settings from the request and preferences. Ask about **only the missing ones, in one bundled
question** (use AskUserQuestion if it's available):

1. **Scope:**
   - **All blocks** in the account.
   - **Specific themes:** which ones?
   - **A workspace:** every active theme available in that workspace, and their blocks.

   If they pick themes or a workspace without naming them, include the names to choose from in the same question.
   Get them with `get_workspaces` and/or `list_themes` (reference §3) before asking. Don't fetch them if the
   user already named the scope.
2. **Mode:** **report only** (default), or **report and fix**. Fix mode still shows every change for approval
   before anything is saved (Step 7).
3. **Format:** **Markdown** (default), **HTML** (a styled page to open or share), or **PDF**.

Don't ask these; state them so the user can correct them:

- **Stale window:** 365 days, unless the user said otherwise.
- **Owned domains:** infer them from the theme `logoUrl`/`logoHref` hosts and the most common link host in the
  blocks. Show your guess: "I'll treat acme.com as yours; images hosted elsewhere get flagged."
- **Localization in use:** decided from locale groups and block localizations (reference §6).

For a big scope, give the user a heads-up rather than asking. Whole-account and many-theme scopes mean large
responses (about 15 KB per block, though they go to disk). Mention it in one line, with the number of themes.

## Step 2: Gather (one parallel batch)

Make a short run directory (`mktemp -d`, or `~/.dyspatch/runs/<date>` on Windows, because long paths stop Python
from starting). Resolve the theme IDs (reference §3), then send **one parallel batch**:

| Scope | Calls |
|---|---|
| Specific themes | per theme: `get_theme_with_blocks {themeId}` + `get_blocks {themeId}` |
| Workspace | `get_themes_with_block_ids {filter:{folderId}}` → then the same per-theme pair for each theme |
| All blocks | `get_blocks {}` + `get_unassigned_blocks {}` + `get_themes_with_block_ids {}` → then `get_theme_with_blocks` per active theme |

Every scope also needs `get_locale_groups {}` and `get_tags {type:"block"}`, about 1 KB each.

Save every response to a file in the run directory, as returned:

- **Oversized results** the client saved to disk: use those paths directly.
- **Inline results:** write them to a file once. Theme payloads (25–55 KB) usually come back inline.

You need a theme payload for every theme in scope. It's the only source of usage counts, logo, variants, mirror
layout and dark-mode data.

## Step 3: Analyze (phase 1)

```bash
python <skill>/scripts/analyze_blocks.py \
  --blocks <dir>/blocks-*.json --themes <dir>/theme-*.json [--unassigned <dir>/unassigned.json] \
  --locale-groups <dir>/locales.json --tags <dir>/tags.json --domains acme.com,acmecdn.net --stale-days 365 \
  --scope "Workspace: Marketing (4 themes)" --json <dir>/findings.json --out <dir>/block-optimizer-report.md
```

The script writes the findings JSON and a Markdown report, then prints a short JSON summary:

- counts by severity and axis, unused blocks, duplicate groups
- the top blocks
- `usage_candidates`: in-use blocks old enough to be stale, whose last-used date it still needs

Work from that summary. Don't read the findings JSON whole; Grep it, or the report, for what you need.

## Step 4: Last-used dates and Gmail lock (phase 2)

Send these in one parallel batch:

- **Last-used dates:** `get_block_templates {blockId}` for each ID in `usage_candidates`, in batches of 20. With
  more than 40 candidates, ask the user first (reference §5). Write `usage.json` as `{blockId: newest template modified}`.
  - Each response lists every email that uses the block, about 0.3 KB per email. So the script only offers
    blocks used by at most 15 emails (`--usage-max-templates`); busier blocks are assumed active. `usage_candidate_templates`
    tells you the total cost up front.
  - Only raise the cap if the user specifically wants their most-used blocks dated.
- **Gmail light-mode lock:** one dry-run `render_unsaved_template` per theme in `head_renders` (reference §6b).
  It's the only way to read the theme's Lock Light Mode in Gmail toggle. From each `chromeStart`, write just the
  `color-scheme` meta and `:root color-scheme` values to `heads.json`.

Then re-run the Step 3 command with `--usage <dir>/usage.json --heads <dir>/heads.json`.

"Last used" here means the last edit to any email that uses the block. It isn't the last send, so say that once
in the report.

Skip the usage calls if the user only wants unused blocks or `usage_candidates` is empty. Skip the renders only if
the user doesn't care about dark mode.

## Step 5: Review what the script can't

Read `references/checks.md` §2 and §4. Then look at the evidence for your judgement calls:

```bash
python <skill>/scripts/block_dml.py <dir>/blocks-*.json --ids blk_a,blk_b --max-chars 4000
```

It prints the named blocks' DML, without reading the big file into context. Look at:

- The top blocks.
- Each near-duplicate pair: what actually differs, and which feature would merge them.
- Every raw-HTML block: justified or not. For up to 3 of the most-used raw-HTML or interactive blocks, also
  dry-run `render_unsaved_block {input:{dml, themeId}}` and compare the output with the DML.
  - Raw sections that vanish, an interactive toggle whose controls don't render, or instruction or sample text
    that shows in the body are High findings the static scan can't see.
  - Keep it to 3 renders; each is a few KB.
- A couple of clean, heavily used blocks, to confirm the script isn't missing something. If it missed a real
  issue, add it to the report by hand.

From that, decide:

- severity adjustments (a locked legal footer isn't a problem; a seasonal block isn't "stale")
- consolidation proposals ("these 5 blocks → 2"), naming suggestions, and style-consistency outliers within a theme

## Step 6: Report

Edit `<dir>/block-optimizer-report.md` in place:

- Replace the `<!-- SUMMARY … -->` line with 3–6 bullets: the biggest wins, each with a number ("Retire 14 unused
  blocks", "Merge 3 duplicate groups", "Enable variants on button and text in 2 themes").
- Add a **Consolidation plan** section after the summary if you found merges.
- Replace the `<!-- NOT CHECKED … -->` line with anything skipped and why (usage dates not fetched, MCP errors,
  blocks only in archived themes, Gmail lock not read for a theme), or "Nothing skipped".
- Change any severities you adjusted, and add the reason to the detail.

Every finding has a reference (TH1, L2, E3…) so the user can say "fix L2 and E1". Keep them.

The Markdown in `<dir>` is your working file. **Deliver one file, in the chosen format**, named
`block-optimizer-<scope-slug>-<YYYY-MM-DD>.<md|html|pdf>`, in `report_dir`:

- **Markdown:** copy the working file.
- **HTML or PDF:** convert it, then give the user only that file. Don't hand over the Markdown or HTML alongside a
  PDF.

```bash
python <skill>/scripts/render_report.py <dir>/block-optimizer-report.md --format pdf --out <report_dir>/<name>.pdf   # or html
```

PDF uses a local Chrome or Edge (or Playwright), and writes only the PDF. If it prints `PDF_UNAVAILABLE`, the HTML
it wrote instead is the deliverable: tell the user Print → Save as PDF produces the same thing.

**In chat**, keep it short:

- the scope, and the blocks and themes analysed
- counts by severity
- the summary bullets
- the top 5 findings, each with its block linked (`https://app.dyspatch.io/block/base/<id>/code`)
- what wasn't checked
- the path to the report

Don't paste the per-block tables.

## Step 7: Fixes (fix mode only)

1. **Propose.** Group fixable findings (`auto: true` in the findings JSON, plus your own) into:
   - **Safe block edits:** alt text, http→https, `dys-comment` for HTML comments, `editable-group` pairs,
     theme-logo variables in headers, `editable` on clearly per-email content, `localizable` on locked footer copy,
     hosted copies of hotlinked images, `editable` on a `dys-repeat`, descriptions you've written (from the block's
     contents). Missing tags can't be applied through the MCP, so list them for the user to apply in the app.
   - **Theme settings:** enable variants and mirror layout on common components, set the logo (only with a real
     logo URL), add dark-mode CSS (show the exact CSS), add `:root { color-scheme: light dark; }` when the Gmail
     lock is on and the theme has dark styles. **Lock Light Mode in Gmail** itself can't be set through the MCP:
     tell the user to turn it on in Theme → Settings, and to verify with a real send to the Gmail app.
   - **Inventory:** remove unused blocks from a theme (never delete).
   - **Report-only:** duplicate merges, `dys-repeat` or partial restructures, renamed editable ids on in-use blocks,
     ESP tracking URLs (the real destination is unknown; ask the user for it).

   Show these **once**, as before → after per block or theme, with the impact:
   - Emails keep the old block revision until they're updated.
   - Theme changes affect every email using the theme.
   - A block shared across themes changes in all of them.

   Get approval for all, some, or none.
2. **Apply** in this order, following reference §7–§9:
   1. Back up each original to `<dir>/backup/`.
   2. Validate each new DML with `render_unsaved_block`.
   3. Save with `update_block`. After the **first** save, verify it with `get_block` before continuing.
   4. Theme changes go through `create_or_update_theme`, with every required field carried over.
   5. Inventory changes go through `update_blocks_in_theme`, with the full remaining list.
3. **Re-run** the Step 3 analysis on fresh `get_blocks`/`get_theme_with_blocks` for the changed themes only.
4. **Update the report.** Mark each finding Fixed, Skipped or Open, and list the backup files for rollback.

Never invent content to make a fix: a logo URL, a link destination, alt text for an image you can't see. Those
stay open until the user supplies them. Alt text is the exception: you may propose it when the file name, nearby
copy or the block thumbnail makes the image clear, and mark it as a suggestion.

## Running unattended

With nobody to answer:

- Use saved preferences. With none: scope is all blocks, or the one theme or workspace named in the request; the
  report is Markdown; the mode is report only.
- Skip Step 4 if there are more than 40 candidates, and say so.
- Never apply fixes unless the request explicitly asked for them, and even then only the safe block edits.
- Save no preferences, and list your assumptions at the top of the report.

## Things that go wrong

- **Context blow-up:** reading `get_blocks` output into context (about 15 KB per block). Pass file paths to the
  scripts, and use `block_dml.py` for the few blocks you need to see.
- **Missing usage counts:** running without theme payloads, so every block shows "?" emails. Fetch
  `get_theme_with_blocks` for each theme in scope.
- **"Unused" that isn't:** blocks only in archived themes have no count. The script shows them as "?", so don't
  call them unused.
- **Wiping a theme's block list:** `update_blocks_in_theme` replaces the list. Always send the full remaining set.
- **Breaking emails with a rename:** changing editable ids on in-use blocks drops stored content once emails
  update. Don't, unless the user accepts that.
- **Thrashing the MCP:** retrying failed calls unchanged, or calling `discover_tools`. Reference §1 and §10 cover
  the known faults.
