# Dyspatch MCP tool reference (for email-qa-checklist)

Every call a QA run needs, with shapes verified against the live MCP (2026-10-20). Call tools by name from here;
don't explore. Sizes are approximate response sizes, which is what costs tokens.

## Contents
1. Call budget and failure rules
2. Calling conventions
3. Find the email
4. Read the content
5. Render (one call for HTML, plain text, variables, locales)
6. Guardrails & Links Review
7. Theme & brand guideline
8. Personalization, conditionals & ESP code
9. Localization
10. UTM parameters
11. Device previews
12. Comments
13. Applying fixes
14. Known MCP faults
15. Known gaps

---

## 1. Call budget and failure rules

A report-only run needs about **10–14 Dyspatch calls**: find (1–2), the Step 3 batch (6–8), a theme read (1), one
render (1, more only for extra locales). Comment mode adds one `add_comment` per finding; fix mode adds one or
two writes and one re-validate. If you're well past that, stop and check you're not re-fetching something you have.

- **Never send the same failing call twice.** On an error, compare your args with this file (and §14) once and fix
  them. If it fails again, record the check as "not run (MCP error)" in the report and move on. A QA report with
  one gap is fine; ten minutes of retries isn't.
- **No `discover_tools`** for anything in this file. If you must (a call here is rejected with arguments that match
  it exactly), run one narrow intent with `topK: 2`. Any intent whose top match is `update_template_partial` returns
  ~75 KB, so phrase intents away from it.
- **Skip heavy calls you don't need:** `list_device_preview_available_clients` (~20 KB; use the default client list
  in §11), `get_template_data` (very large), `list_theme_blocks` (~220 KB), `get_themes_with_block_ids` (~60 KB).
- **Run independent reads in one parallel batch** and read each thing once. IDs, the revision and the render stay
  in memory for the whole run.

## 2. Calling conventions

- Real MCP tools: `discover_tools`, `invoke_tool`, `approve_mutation`, plus always-on `get_who_am_i`,
  `get_root_folders`, `search_templates_blocks_themes_by_keywords`.
- **Queries:** `invoke_tool({toolName, args})`. **Mutations:** `approve_mutation({toolName, args, approved:true, reason})`
  directly. Calling `invoke_tool` on a mutation only returns `approval_required`, a wasted round trip.
- Pure renders and checks are typed as mutations but change nothing: `render_template`, `render_template_version`,
  `render_unsaved_template`, `validate_rendered_template`, `validate_conditional`. They're fine in report-only mode;
  give `reason: "read-only render for QA"`.
- Most mutations wrap args in `{input:{...}}`. Exceptions: `update_template_partial` (`visualVersion`),
  `update_template_localization_partial` (`versionId`), `generate_device_test_saved_version` and
  `render_template_version` (top-level args).
- Errors are opaque: `invalid_arguments` = failed schema validation, `upstream_graphql_error` = rejected by the API.
- ID prefixes: fdr_ folder/workspace · thm_ theme · blk_ block · brv_ block rev · tem_ template · tdft_ draft ·
  tvr_ template version (revision) · loc_ localization · lg_/lgr_ locale group · bgl_ brand guideline · cmt_ comment.

## 3. Find the email

| input | calls |
|---|---|
| App URL `https://app.dyspatch.io/template/{tem_}/{tdft_}/blocks` | take the `tdft_` → `get_draft` |
| `tdft_…` | `get_draft {draftId}` |
| `tem_…` | `get_most_recent_draft {templateId}` → `template.mostRecentDraft.id` → `get_draft` |
| a name | `search_templates_blocks_themes_by_keywords`, then `get_draft` on the pick |

- `get_draft {draftId}` (~0.6 KB) → `templateDraft{id, name, templateId, template{name, type, folderId}, latestRevision{id},
  publishStatus, publishRequest{id, rejected}, isAwaitingTranslation, archived}`. `latestRevision.id` is the tvr_
  you QA; `template.folderId` is the workspace or a subfolder.
- Search: `search_templates_blocks_themes_by_keywords`
  `{input:{query:"<ONE word>", filters:{includeEmails:true, includeBlocks:false, includeThemes:false, includePush:false, includeSMS:false, includeVoice:false, includeLiveActivity:false, tagIds:[]}}}`
  (~10–15 KB, because each hit carries a plain-text dump of the email). **One distinctive word**: multi-word
  queries often return nothing. One row per draft. Use the search only to find the email; don't run extra
  searches for sibling emails unless a finding depends on the comparison (e.g. which theme the team usually uses).
- `get_template_version_data {templateId}` (~1.5 KB): every draft and published version with `status`, `tags[]`,
  `created`. Tells you whether a live version or a newer draft exists.

## 4. Read the content

`get_draft_revision {revisionId, draftId}` (~10 KB for a short email) is the main payload:
`templateDraftRevision{previewData (JSON string), subject, preheader, sender{name,address}, replyTo, utmParams{…},
themeId, ampState, customScript, blocks[]{blockId, blockRevisionId, html (the block's DML), content[]{id, value,
attributes[{name,value}], carouselImageOverrides[]}}, localizations[], localizationSchema.items[]{key, editableID, attributeName, tagName}}`.
It does **not** return `plainText`, `generatePlainText`, `isPinned` or block names (names: `get_theme_with_blocks`
`blocks.nodes[]`, or the BLOCKS_ARE_UP_TO_DATE guardrail item).

- **Effective copy of a slot** = the content item's `value`/attributes if present, otherwise the default in the
  block DML (`editable='<id>'`). A slot with no override ships its DML default, which is how sample copy slips through.
- A slot is hidden when its attributes contain `show` = `"false"`; don't proofread it.
- Each block may carry a `dys-conditional-block` item whose `cond` attribute is its condition (`"true"` = always).
- Copy and links outside `editable` slots come from the block. `localizable` (not `editable`) elements can still
  be translated per email but not edited. Fixing either means editing the block: report, don't patch.
- `blockIdx` in validation results is **1-based** into `blocks[]`.

## 5. Render (one call for HTML, plain text, variables, locales)

`render_template` m `{input:{revisionId:<tvr_>, showConditionalBlocks:true}}` (~15–30 KB) →
`{subject, preheader, plainText, variables[], blockHtml[], chromeStart, chromeEnd, blockAmpHtml[], …}`.

One call covers every render need. Use it instead of `render_template_version` (whole HTML only, no plain text)
and `render_unsaved_template` (needs the full block list sent back to it).
- `blockHtml[i]` is block i+1's HTML, **including blocks hidden by their condition** (with `showConditionalBlocks:true`),
  in the same order as the editor. That's what comment pins need (§12).
- `plainText` is the auto-generated plain text: the only way to read it.
- Links in the HTML are the **final tracked URLs**, with workspace link parameters appended (§10).
- Full email = `chromeStart + blockHtml.join("") + chromeEnd` (the `lang` attribute is in `chromeStart`). Size
  that string for the Gmail 102 KB clipping check; count characters rather than writing it to disk.
- **A locale:** add `lcid:"fr-FR"` to the same input. Don't pass `localizationId`: on some accounts both
  `render_template_version {id, localizationId}` and `render_template {…, localizationId}` fail with
  `upstream_graphql_error`, while `lcid` alone works.
- `previewData:"<JSON string>"` renders for one audience (e.g. to see which conditionals show for a Gold member).
  Combine it with `showConditionalBlocks:false`.

## 6. Guardrails & Links Review

`validate_template_revision {revisionId}` (query, ~20 KB) is both the guardrail run and Dyspatch's Links Review:

- `templateValidationItems[]{title, details, level: SUCCESS|WARNING|ERROR, type, lcids[], blocks[]{blockId,name,blockIdx}, blockRenderedMeta{amp, blockIdx, editableId}}`.
  Items repeat for amp:false and amp:true, so dedupe on (type, details, blockIdx, editableId). ERROR = Dyspatch
  blocks publishing.
- Types: SUBJECT_IS_VALID, PREHEADER_IS_VALID, PLAINTEXT_IS_VALID, ALT_TEXT_IS_VALID, URLS_ARE_SECURE_AND_VALID,
  SPAM_WORDS (**title = category**, **details = the word**), UNSUBSCRIBE_LINK_EXISTS, EMAIL_CONTENT_SIZE_IS_VALID,
  IMAGE_FILE_TYPE, INTEGRATION_EXPORT_IS_VALID, VARIABLE_SYNTAX_IS_VALID (flags `{{x}}` in content),
  BLOCKS_ARE_UP_TO_DATE (lists outdated blocks by name), LOCALES_ARE_TRANSLATED (one item per untranslated key per
  locale; also fires on non-text keys like "400px", image URLs and `""`: ignore those).
- **Known false passes, so verify these yourself:**
  - UNSUBSCRIBE_LINK_EXISTS passes on wording ("you are subscribed to…") even with no unsubscribe link.
  - URLS_ARE_SECURE_AND_VALID and Links Review don't flag fragment-only hrefs (`#download`).
  - SUBJECT_IS_VALID sometimes reports a short subject as within 40–60 characters, or a short personalized one as
    too long. Count it yourself.
- `templateLinks[]` is the Links Review list: `{url, type: NAV_LINK|IMAGE_LINK, linkContext (anchor text, or the image
  file name), lcids[], blockIdx, editableId, isEditable, warnings[{type: LINK_IS_PLACEHOLDER|LINK_IS_INVALID}]}`.
  `isEditable:false` = hard-coded in the block. URLs here are raw, **without** workspace link parameters.
  Placeholder detection flags `example.com` and `www.dyspatch.io` (a false positive when the org really is Dyspatch).
- `validate_rendered_template` m `{input:{revisionId, lcid?, previewData?, showConditionalBlocks?}}` validates one
  locale or audience. Rarely needed.

## 7. Theme & brand guideline

- `get_theme_with_blocks {themeId}` (~20 KB): the only source for `logoUrl, logoHref, logoActive`, fonts (in
  `headContent`), the palette (`basicFields.colors`, `usePaletteOnly`), `basicFields{bodyBackgroundColor, textFontColor, linkFontColor, buttonBackgroundColor}`,
  `archived`, and block names (`blocks.nodes[]{id, name}`). Call it once, only if Brand, Accessibility or comments need it.
- `list_themes {id:<workspace fdr_>}` (~10 KB): only the IDs in `folder.themes` are assigned to that workspace
  (`themes.nodes` is org-wide). Call it only to check whether the email's theme is assigned there.
- `list_brand_guidelines {}` (~1 KB) → `brandGuidelines.data[]{id, name, description, audience, tone[], personality[], default, workspaceIds[]}`.
  That's the whole record (no word lists, no get-by-id). Use the guideline whose `workspaceIds` include the
  workspace, otherwise the `default:true` one, unless it plainly belongs to another brand (SKILL.md Step 4).

## 8. Personalization, conditionals & ESP code

- Variables: `render_template.variables[]` lists every variable used. Compare them with the keys of `previewData`
  (a JSON string): a variable missing from previewData renders blank in previews and may be a typo.
- Dyspatch syntax: `@{first_name}`; fallback `@{first_name|default("there")}`. The colon form `default:"x"` works
  in the subject but is rejected in block content.
- ESP-specific code belongs inside `<dys-export targets='…'>` (or raw HTML). Anywhere else it renders literally,
  and it ships to every export target. Which ESP? There's no list-integrations tool: use `list_comments` events of
  type TEMPLATE_EXPORTED (`subtitle` = ESP name), `<dys-export targets>` in the DML, or say it's unknown.
- Conditions: `cond` on `dys-conditional-block` items and `<dys-if cond='…'>` in DML. Syntax-check non-trivial ones
  with `validate_conditional` m `{input:{condition:"<expr>"}}` → `{isValid, message}` (the field is `isValid`, not `valid`).

## 9. Localization

- `get_draft_localizations {draftId}` (~1 KB) → `latestRevision.localizations[]{id, name, lcid, mapping (JSON string)}`.
- Untranslated keys: compare each `mapping` with `localizationSchema.items[].key` plus the subject and preheader. A value
  identical to its key on a text item is probably untranslated. Skip `src`/`href`/size keys.
- Expected locales: no setting in the MCP. Use the user, the brief, or `get_locale_groups {}` if a group name matches.
- Proofread a translation in context with one `render_template {input:{revisionId, lcid}}` per locale (§5).

## 10. UTM parameters

- **Email level:** `get_draft_revision.utmParams{source, medium, campaign, term, content, customParams[]}`; empty = unset.
- **Workspace level:** no read tool. **The render (§5) is authoritative**: its links show exactly what's appended
  for this email. The search tool's `content` can show a different, org-level string; don't rely on it.
- **Per CTA:** UTMs typed into an `href` appear in `templateLinks[].url`.
- Unusual parameters in the appended string (`custom123=bob`, `test=1`) are worth a finding: they go out on every link.
- **Set at email level:** `update_template_partial` `visualVersion.utmParams` with **all five string keys**.

## 11. Device previews

- **Existing results (free):** `get_device_preview_latest_test_id {draftRevisionId:<tvr_>}` → testId or null →
  `get_device_preview_results {revisionId, testId}` → `results[]{clientId, url, thumbnailUrl}`. Null: none exist.
- **New test (uses the org's Litmus quota; needs the user's OK):** `get_dashboard_resources {}` →
  `organization.resources.litmus{limit, count}` (−1 = unlimited), then `generate_device_test_saved_version` m
  `{revisionId, clients:[…], lcid?, previewData?}`. Poll `get_device_preview_latest_test_id`, then
  `get_device_preview_results`, about every 30 s; give up after ~5 min and report "still running" with the link.
- **Default clients:** `CHROMEGMAILNEW`, `OL2019`, `OUTLOOKFORWINDOWS`, `APPLEMAIL26`, `APPLEMAIL26DARK`, `IPHONE16`,
  `IPHONE16DARK`, `ANDROID15GMAILAPP`, `IPHONE16OUTLOOKAPP` (+ `PLAINTEXT`, `COLORBLIND` if useful).
- Look at a few screenshots (download `url`, open the image). If you can't, share the links and say so.
- **Local fallback:** `scripts/screenshot_email.py` needs Playwright + Chromium + Pillow. Check once
  (`python -c "import playwright, PIL"`). If missing, don't install them unasked: report visual checks as not run
  and give the user the install command (`pip install playwright pillow && playwright install chromium`).

## 12. Comments

- `list_comments {draftId}` (~1–2 KB) → `comments[]{id, comment, subtitle, type, created, parentId, agent, resolved (0 = open), lcid, reviewers[]}`.
  Also the activity log (DRAFT_APPROVED, TEMPLATE_EXPORTED with the ESP in `subtitle`, DRAFT_SUBMITTED_FOR_DESIGN_REVIEW).
  Real feedback has a non-empty `comment`.
- `add_comment` m `{input:{draftId, revisionId:<tvr_>, comment:"<text>", coordinates:"<JSON string>", lcid?, parentId?}}` → `{id}`.
- **Pins:** `coordinates` is a JSON **string**: `{"xpath":"…","x":0,"y":0}`. The editor wraps every block (hidden
  ones included) in a container, so an XPath is `/html/body[1]/div[1]/div[1]/div[1]/div[<blockIdx>]/div[1]/<path in
  that block's HTML>`. **An XPath that doesn't resolve drops the pin at the bottom-left of the email**, so never
  hand-write one: use `scripts/comment_xpath.py` on the `blockHtml` from §5. Verified in the app for images,
  paragraphs, nested-table buttons and hidden conditional blocks.
  - Write only the blocks that need pins: `{"blocks": {"3": "<block 3 html>"}}`, dropping `<!--[if mso]>` comments.
    A finding about a whole block needs no HTML (`{"block": 2}` pins to its container).
  - Targets: `{"id":"L2","block":3,"href":"…"}`, `{"block":3,"text":"first words of the copy"}`, `{"img":"file-name"}`.
  - Findings with no element (subject, preheader, sender, workspace settings) go unpinned, with `coordinates:""`
    (untested; if it's rejected, pin to block 1: `{"block":1}`).
- `resolve_comment` m `{input:{commentId}}`: only for comments this skill posted that are now fixed.

## 13. Applying fixes

There's no fine-grained patch: `update_template_partial` m saves a **whole new version**.

1. Note the current `tvr_` (the rollback point).
2. From the `get_draft_revision` you already have, change only the approved items and send
   `{visualVersion:{draftId, blocks:[every block in order, each {blockId, blockRevisionId, isPinned:false, content}], subject, preheader,
   sender, replyTo, previewData (string), utmParams (all five keys), ampState, customScript, generatePlainText}}`.
   **Anything left out is cleared.** `isPinned` and `generatePlainText` aren't in the read payload: send
   `isPinned:false`, and `generatePlainText:true` when PLAINTEXT_IS_VALID passed or `render_template.plainText` was non-empty.
   Every content item needs `id, value, attributes, carouselImageOverrides`.
3. The response `{id}` is the new revision. Re-run `validate_template_revision` once.
4. Translations: `update_template_localization_partial` m `{versionId:<latest tvr_>, localizations:[{name, lcid, groupRevisionId:"", mapping:{…object…}}]}`
   with every existing locale (mappings read as strings, write as objects).
5. Outdated blocks: `get_block {blockId}` → `latestRevisionId`; re-check slot ids against the new DML.
6. Undo: `restore_draft_revision` m `{input:{draftId, revisionId:<pre-fix tvr_>, name:"Before QA fixes"}}`.

A PENDING_APPROVAL or approved draft may lose its approval when saved. Say so before applying fixes.

## 14. Known MCP faults

| symptom | cause | fix |
|---|---|---|
| `approval_required` from invoke_tool | it's a mutation (incl. renders) | `approve_mutation` |
| `upstream_graphql_error` rendering a locale | `localizationId` passed | `render_template {input:{revisionId, lcid}}` |
| `upstream_graphql_error` on update_template_partial | colon fallback in content, a missing content-item key, `previewData` as an object, `utmParams` missing a key | fix those; don't bisect first |
| `invalid_arguments` on get_draft_revision / get_draft_preview | missing `draftId` (both need it) | `{revisionId, draftId}` / `{templateId, draftId}` |
| search returns nothing | multi-word query | one word |
| huge discover_tools response | intent matched update_template_partial | don't explore; `topK: 2` if you must |
| comment pin at the email's bottom-left | XPath didn't resolve | regenerate with `comment_xpath.py` |
| Python won't start in Git Bash on Windows | working directory path too long | run scripts by absolute path from a short cwd |

## 15. Known gaps

| need | status | what to do |
|---|---|---|
| Spell / grammar check, Scribe review | not exposed | proofread yourself |
| HTTP status of links and images | not exposed | `scripts/check_links.py` |
| Workspace UTM settings | not readable | read the render's links (§10) |
| Brand voice beyond tone/personality/audience | not in schema | judge against what the guideline says |
| List ESP integrations | not exposed | signals in §8 |
| Customer data profiles | not exposed | `previewData` + reasoning |
| Required locales | not exposed | user, brief, sibling emails |
| Device previews without quota | not exposed | local screenshot if Playwright exists, else report as not run |
