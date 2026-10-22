# Dyspatch MCP tool reference (for block-optimizer)

Every call this skill needs, with shapes checked against the live MCP (2026-10-21). Call tools by name from here;
don't explore. Sizes are approximate, and they are what costs tokens.

## Contents
1. Call budget and failure rules
2. Calling conventions
3. Resolving the scope
4. Gathering (blocks, themes, usage)
5. Last-used dates
6. Localization signals
6b. Gmail light-mode lock
7. Fixes: blocks
8. Fixes: themes
9. Fixes: inventory
10. Known MCP faults
11. Known gaps

---

## 1. Call budget and failure rules

A report-only run costs:

- **One theme:** 2 gather calls, plus 1 for locale groups, 1 head render (§6b), and one `get_block_templates` per
  stale candidate.
- **A workspace:** 1 call, then 3 per theme (gather pair plus head render), plus the same extras.
- **The whole account:** 3 calls, then 2 per active theme (theme payload plus head render), plus the same extras.

If you're well past that, stop and check you aren't re-fetching something you already have.

- **Never send the same failing call twice.** On an error, compare your args with this file (and §10) once and
  fix them. If the call fails again, record that check as "not run (MCP error)" and move on.
- **No `discover_tools`.** Everything is here. `topK` doesn't cap the schemas it returns (you always get about 5
  full input schemas, 10–40 KB), so even a "small" discovery call is expensive.
- **Run independent reads in one parallel batch**, and read each thing once.
- **Large results go to disk, not context.** `get_blocks` is about **15 KB per block** (it carries
  `editableFields` for every element). A 28-block theme is about 400 KB. Clients like Claude Code save oversized
  results to a file and give you the path: pass that path straight to the script, and never Read it. Results that
  come back inline (a theme of about 30 KB, for example) must be written to a file before the script can use them.
  Write the JSON exactly as returned, using your file-writing tool.

## 2. Calling conventions

- Real MCP tools are `discover_tools`, `invoke_tool` and `approve_mutation`, plus the always-on `get_who_am_i`,
  `get_root_folders` and `search_templates_blocks_themes_by_keywords`.
- **Queries:** `invoke_tool({toolName, args})`. **Mutations:** `approve_mutation({toolName, args, approved:true, reason})`.
  Sending a mutation through `invoke_tool` only returns `approval_required`, which wastes a round trip.
- `render_unsaved_block` is typed as a mutation but changes nothing. Use `reason: "read-only render to validate DML"`.
- Errors are opaque. `invalid_arguments` means the call failed schema validation; `upstream_graphql_error` means the
  API rejected it.
- ID prefixes: fdr_ workspace/folder · thm_ theme · trv_ theme revision · blk_ block · brv_ block revision ·
  tem_ template · tdft_ draft · bloc_ block localization · lg_ locale group.
- Block link in the app: `https://app.dyspatch.io/block/base/<blk_id>/code`. Theme pages have no verified deep
  link, so name the theme and its ID instead.

## 3. Resolving the scope

Only call these when the user's request doesn't already give you IDs.

| Need | Call | Size | Notes |
|---|---|---|---|
| Workspace names → IDs | `get_workspaces {}` | ~1 KB | `[{id, name}]`. `get_root_folders` (~10 KB) also works but is heavier. |
| Every theme's name → ID | `list_themes {id:<any workspace fdr_>}` | ~10 KB | `themes.nodes[]` is **every theme in the org**. `folder.themes[]` is only the ones assigned to that workspace. |
| Themes in one workspace, with their block IDs | `get_themes_with_block_ids {filter:{folderId:<fdr_>}}` | 5–15 KB | Each theme has `{id, name, templateCount, blockCount, basicFields, blocks.nodes[]{id}}`. Active themes only. |
| Every active theme, with its block IDs | `get_themes_with_block_ids {}` | ~55 KB | Use only for whole-account scope. |

Match theme and workspace names case-insensitively, and ignore emoji and other leading symbols ("📰 Marketing").
If a name matches more than one, ask the user.

## 4. Gathering (blocks, themes, usage)

Run all of these in **one parallel batch** once the theme IDs are known.

| Call | Args | Gives | Size |
|---|---|---|---|
| `get_theme_with_blocks` | `{themeId}` | See the theme fields below | 25–55 KB |
| `get_blocks` | `{themeId}`, or `{}` for the whole account | See the block fields below | ~15 KB per block |
| `get_unassigned_blocks` | `{}` | Blocks in no theme, with the same usage counts and dates | 1–10 KB |
| `get_locale_groups` | `{}` | `localeGroups[]{id, name, lcids[]}`. A non-empty list means the account localizes. | ~1 KB |
| `get_tags` | `{type:"block"}` | `tags.data[]{id, name, type[], isActive, enableAllWorkspaces, workspaces[]}`, the block tags defined in the account. Each block's own tags are in `tags[]` on `get_blocks` and the theme payload's `blocks.nodes[]`. | ~1 KB |

`get_theme_with_blocks` returns the following, and is the source for every theme check:

| Field | What it tells you |
|---|---|
| `headContent` | `<dys-font>`, `<dys-style>` (dark-mode CSS lives here) and `<dys-attributes>` (defaults and `variant=` definitions) |
| `logoUrl`, `logoHref`, `logoActive` | Whether the theme logo is set, which `@{DYS.theme.logo.url}` needs |
| `editableStyleControls` | A **JSON string**, keyed by component, e.g. `{"dys-button":{"variant":true,…},"dys-row":{"direction":true,…}}`. `variant:true` means Variants are enabled for that component. `direction:true` on dys-row/dys-group means **Mirror Layout** is enabled. |
| `useLayouts`, `autoEditableStyles`, `usePaletteOnly`, `basicFields.colors`, `archived`, `latestRevision.id` | Other theme settings |
| `blocks.nodes[]` | Per block: `{id, name, description, created, modified, templatesCount, blueprintsCount, themesCount, themes[]{id}}`. **This is the only bulk source of usage counts**: 0 templates and 0 blueprints means no email or draft uses the block. |

`get_blocks` gives, per block:

- `{id, name, description, html, created, modified, isTemplateBound, isVisualBlock, latestRevisionId, themes[]{id}, localizationSchema[], thumbnailUrl}`.
- `editableFields[]{id, tagName, editableGroup, editableStyles[], attributes[]}`.
- `pageToken` and `hasMoreResults` for paging.
- **There's no usage count here.** Usage comes from the theme payloads, or from `get_unassigned_blocks`.

For whole-account scope:

- `get_blocks {}` returns every block, archived themes' blocks included. It has no pagination input; if
  `hasMoreResults` is true, say the review covers only the blocks returned.
- Blocks whose only themes are archived get no usage count, because archived themes aren't in
  `get_themes_with_block_ids`. The script reports those blocks' usage as "?".

## 5. Last-used dates

There's no bulk "last used" field. The closest is the newest `modified` date among the emails that use the block:

- `get_block_templates {blockId}` (~0.3 KB **per email using the block**, so ~30 KB for a block in 90 emails) returns `block.templates[]{id, name, modified, lastUpdatedBy}`.
  The **max(`modified`)** is the block's last-used date. That is the last time an email using the block was edited,
  not the last send; say so in the report.
- `get_drafts_for_block {blockId, includePublished:true, includeSubmitted:true, includeAwaitingTranslation:true}`
  lists drafts with status but **no dates**. Use it only if the user asks which drafts or workspaces use a block.
- Call `get_block_templates` only for the script's `usage_candidates`. Those are blocks in use, used by 15 emails
  or fewer, and created before the stale cut-off, so a newer block can't be stale. They're listed least used
  first. Blocks in more than 15 emails are counted as "not dated, assumed active" in the report. Run them in parallel batches of up to 20.
  With more than 40 candidates, ask the user before fetching: "N blocks need one call each to date their last
  use. Fetch all, the 40 oldest, or skip?"
- Write `usage.json` as `{"blk_…": <max modified unix seconds>, …}`. Leave out blocks whose list came back empty.

## 6. Localization signals

The account localizes if any of these is true:

- `get_locale_groups` returns groups.
- Any block has a non-empty `localizationSchema` (it uses `localizable`).
- The user says so.

`get_who_am_i.organization.resources.localization.count` is **not** reliable for this; it was 0 on an account that
localizes. Pass `--localization yes|no` to the script when you know, or `--locale-groups <file>` to let it decide.

Block-level translations: `get_block {blockId}` (~2–5 KB) returns `localizations[]{id, name, lcidList, mapping (JSON string)}`
and `localizationSchema[]{key, editableID, tagName}`. Use it only when proposing a localization fix for one block.

## 6b. Gmail light-mode lock

Themes have a **Lock Light Mode in Gmail** toggle (Theme → Settings). It's new and not yet in the docs. It stops
the Gmail iOS/Android apps force-inverting colours. When it's on, the rendered `chromeStart` ends its `<head>` with
`<meta name="color-scheme" content="light only" />`, right after the font links. When it's off, the tag isn't
there at all. (Verified live 2026-10-21. The tag isn't in `chromeStartAmpHtml`, so read the HTML head, and the
toggle adds no `:root` rule.)

- **It isn't in the theme API.** `get_theme_with_blocks` doesn't return it, and `create_or_update_theme` can't
  set it. The only way to read it is the rendered head. The user changes it in the app.
- **Read it with one dry-run render per theme.** The script's phase-1 summary gives `head_renders`, which is
  `{thm_id: {blockId, blockRevisionId}}` (the smallest block in each theme). For each theme, call
  `render_unsaved_template` m
  `{input:{blocks:[{blockId, blockRevisionId, content:[]}], options:{title:"", preheader:""}, themeId}}`
  with `reason: "read-only dry-run render to read the theme head"`. Nothing is saved. It costs ~10–15 KB inline per
  theme; run all the themes in one parallel batch.
- In each response's `chromeStart`, look for `<meta name="color-scheme" content="…">` and a `color-scheme:`
  declaration on `:root`. Don't copy the response. Write only the two values to `heads.json`, and use `""` when
  one is absent:
  `{"thm_…": {"color_scheme_meta": "light only", "root_color_scheme": ""}, …}`.
  Then pass `--heads heads.json` to the script. A theme left out of `heads.json` is reported as "?" (not checked).
- `u + #body a {…}` in every rendered head is Dyspatch's standard link-colour fix for Gmail. It isn't a dark-mode
  setting.
- If a theme the user says has the lock on shows no meta, report the check as "couldn't be read" rather than "off",
  and quote what the head did contain. The output format may have changed.

## 7. Fixes: blocks

1. **Back up first.** Before any change, write the block's current `html` (from `get_blocks`, already on disk) to
   `<run dir>/backup/<blk_id>.dml`. That file is the rollback.
2. **Validate the new DML:** `render_unsaved_block` m `{input:{dml:<new DML>, themeId:<a theme the block is in>}}`.
   It returns `{html, ampHtml, variables[], localizationSchema[]}`. If it errors, the DML is invalid: fix it or
   skip the block. Compare `localizationSchema` with the block's current one, because a changed key orphans
   existing translations.
3. **Save:** `update_block` m
   `{input:{id, html:<new DML>, isTemplateBound:<current value>, isVisualBlock:<current value>}}`.
   - `isTemplateBound` and `isVisualBlock` are required, so copy them from `get_blocks`.
   - Leave `name`, `description`, `localizations` and `folderId` out, so they stay as they are.
   - The response is the updated block, with a new `latestRevisionId`.
   - **First save of a run:** re-read that block with `get_block {blockId}` and confirm the name, description and
     localizations survived before you update more. (Omitted fields were preserved in testing of the schema, but
     not proven on every account.)
4. **Rename a block or edit its description** with the same call: `name` and `description` only, plus the two
   required booleans.
5. **Hosted images:** `upload_block_image_url` m
   `{input:{url:<external image URL>, optimize:true, altText, name, folderId?}, imageTransforms:[{"key":"thumb","compress":true,"width":200}]}`
   returns a Dyspatch-hosted URL. Swap it into the block's `src`. `imageTransforms` must be non-empty.
6. **Copy instead of editing in place** when a fix is structural (merging duplicates, adding `dys-repeat`,
   introducing partials): `duplicate_block` m `{input:{id, name}}`, edit the copy, and let the user switch emails
   over in their own time.
7. **Rollback:** `update_block` with the backed-up DML. `get_block_revisions {blockId, pageSize:5}` lists earlier
   revisions (id, created, user), but no restore tool has been verified, so rely on the backup file.

What a block update does to emails:

- Email versions pin a block revision (`blockRevisionId`). Existing emails keep rendering the **old** revision
  until someone updates the block in that email; Dyspatch flags it with the BLOCKS_ARE_UP_TO_DATE guardrail.
- Renaming or removing an `editable` id drops the content that emails have stored under that id once they update.
  Never rename editable ids on a block that's in use unless the user explicitly accepts that.
- A block shared by several themes changes in all of them.

## 8. Fixes: themes

`create_or_update_theme` m takes `{input:{id, name, description, headContent, editableStyleControls, logoUrl?, logoHref?, logoActive?, useLayouts?, usePaletteOnly?, autoEditableStyles?, figmaUrl?}}`.

- **`id`, `name`, `description`, `headContent` and `editableStyleControls` are required.** Send them exactly as
  `get_theme_with_blocks` returned them, changing only the approved parts. `editableStyleControls` stays a JSON
  **string**.
- Enable Variants for a component by setting `"variant": true` under it in `editableStyleControls`.
- Enable Mirror Layout by setting `"direction": true` under `dys-row` and `dys-group`.
- Turn on the theme logo with `logoUrl` (a Dyspatch-hosted image), `logoHref` (where it links) and `logoActive:true`.
  You need a real logo from the user or the asset library. Never invent one.
- To add dark mode, append the approved `<dys-style>@media (prefers-color-scheme: dark){…}</dys-style>` to
  `headContent`, outside `<dys-attributes>`. Show the exact CSS to the user before saving.
- **Lock Light Mode in Gmail can't be set here** (§6b). Tell the user where the toggle is (Theme → Settings). When
  the theme also has dark-mode styles, add `:root { color-scheme: light dark; }` in a `<dys-style>` in
  `headContent`, so Apple Mail and other clients still use them.
- Theme changes affect **every email that uses the theme** the next time it renders or is edited. Treat them as
  high-impact and get explicit approval for each theme. Back up the original `headContent` and
  `editableStyleControls` to `<run dir>/backup/<thm_id>.json` first.
- To check a theme change, render a block that uses it: `render_unsaved_block {input:{dml, themeId}}` reflects the
  saved theme. For a dry run of unsaved head content, use `render_unsaved_blocks_theme` (query)
  `{blocks:[{id, dml}], themeHead:<new headContent>}`.

## 9. Fixes: inventory

- **Never delete blocks** in this skill. Deleting is permanent, and a block used by old emails can still matter for
  re-sends. Offer to remove unused blocks from a theme instead. That's reversible, and the block stays in the
  library.
- **Remove a block from a theme:** `update_blocks_in_theme` m `{themeId, blockIds:[…every block that should
  remain…]}`. It **replaces** the theme's whole block list, so build `blockIds` from that theme's
  `blocks.nodes[].id` minus only the approved removals, and double-check the count before you send it.
- **Assign a block to a theme:** `add_block_to_theme` m `{id:<blk_id>, themeId}`.
- **Duplicates:** the MCP can't move emails from one block to another in bulk. Report the duplicate group, name
  the block to keep (the one used most), and leave the switch to the user.

## 10. Known MCP faults

| Symptom | Cause | What to do |
|---|---|---|
| `approval_required` from `invoke_tool` | It's a mutation (including `render_unsaved_block`) | Use `approve_mutation` |
| A huge `discover_tools` response | `topK` doesn't cap the schemas returned | Don't call it |
| An oversized result saved to a file | `get_blocks` is about 15 KB per block | Pass the path to the script; don't Read it |
| Theme results come back inline (30–55 KB) | Under the client's file threshold | Write them to a file once, then work from the file |
| `update_blocks_in_theme` removed too much | `blockIds` replaces the whole list | Re-send the full list from the backup |
| `invalid_arguments` on `create_or_update_theme` | A required field is missing, or `editableStyleControls` was sent as an object | Send all five required fields; send the controls as a string |
| Python won't start in Git Bash on Windows | The working-directory path is too long | Run scripts by absolute path from a short cwd |

## 11. Known gaps

| Need | Status | What to do |
|---|---|---|
| Last send date per block | Not exposed | Use the newest email `modified` date (§5) and say it's a proxy |
| Usage counts for blocks only in archived themes | Not exposed in bulk | One `get_block_templates` call each, if the user cares |
| Archiving a block | No verified tool | Remove it from its themes instead (§9) |
| Applying tags to a block | No verified tool | List the suggested tags in the report; the user applies them in the app |
| Moving emails between blocks (duplicate merges) | Not exposed | Report it; the user switches emails in the app |
| Theme deep link | Not verified | Name the theme and its ID |
| Gmail light-mode lock | Not readable or writable through the theme tools | Read it from a dry-run render (§6b); the user flips the toggle in the app |
