# Dyspatch MCP tool reference (for create-email)

Everything here is callable without `discover_tools`. Names below are GraphQL tool names passed as `toolName`.

## Contents
1. Calling conventions
2. Identity & workspaces
3. Themes & blocks
4. Draft content structure (how block copy is stored)
5. Create & populate
6. Personalization
7. Brand guidelines
8. Images / assets
9. Localization
10. QA: guardrails & plain text
11. Preview image
12. Approval & handoff
13. Net-new blocks
14. Known gaps (as of this version)

---

## 1. Calling conventions

- Real MCP tools: `discover_tools`, `invoke_tool`, `approve_mutation`, plus always-on `get_who_am_i`,
  `get_root_folders`, `search_templates_blocks_themes_by_keywords`.
- **Queries:** `invoke_tool({toolName, args})`.
- **Mutations:** call `approve_mutation({toolName, args, approved:true, reason?})` directly. Calling `invoke_tool` on a
  mutation only returns `approval_required` and wastes a round trip. Some read-like tools are typed as mutations
  (render_unsaved_template, render_template, render_template_version, validate_rendered_template, render_unsaved_block);
  they also go through approve_mutation.
- Most mutations wrap args in `{input:{...}}`. Exceptions: `update_template_partial` (top-level `visualVersion`),
  `request_publish` (top-level `draftId`), `update_template_localization_partial` (top-level `versionId`).
- Errors are opaque (`invalid_arguments` = failed schema validation, `upstream_graphql_error` = rejected by the API).
  On an opaque error, check the arg shape against this file first. Only fall back to a narrow `discover_tools`
  intent (e.g. "create template") if the shape here seems wrong. `rankedCandidates` (the part with schemas) is capped
  at 5, so phrase the intent narrowly.
- Response envelope: `{status, executedToolName, operationType, data:{...}}`.
- ID prefixes: fdr_ folder/workspace · thm_ theme · trv_ theme rev · blk_ block · brv_ block rev · tem_ template ·
  tdft_ draft · tvr_ template version · loc_ localization · lg_/lgr_ locale group/rev · file_ asset · bgl_ brand guideline.

## 2. Identity & workspaces

| tool | type | args | use |
|---|---|---|---|
| get_who_am_i | q | — | ~8 KB. Call once. Read `permissions.createBlock`, `permissions.createTemplate`, `permissions.publishTemplate`, `permissions.listAssets`, `organization.OrgSettings.autoPlainText`, `organization.features{aiTranslation, scribeEmailAssistant, brief2Email, figmaImporter}`. |
| get_root_folders | q | — | `workspaces.nodes[]{id,name,description,items{emails}}` plus `folders.nodes[]{id,name,parentId,rootId}`. One call gives every workspace and the folder→workspace map. |
| get_workspaces | q | — | lightest `[{id,name}]` if that's all you need |
| get_folder | q | `{id}` | subfolders of a workspace, to choose a destination subfolder |
| get_workspace_permissions | q | `{id}` | per-workspace createTemplate / publishTemplate / editBlock |
| get_users_mentions | q | `{workspaceId}` | users in a workspace (reviewers for approval) |

No tool lists templates by folder. Use `search_templates_blocks_themes_by_keywords` or `list_campaigns` (returns folderId).

## 3. Themes & blocks

**Prefer these (light):**
- `list_themes` q `{id: <workspaceId>}` (the param is called `id` but takes the workspace folder ID) →
  `themes.nodes[]{id,name,description,basicFields{bodyBackgroundColor,textFontColor,linkFontColor,buttonBackgroundColor,...}}`
  and `folder.themes[]{id}`. **`themes.nodes` is every theme in the org. Only the IDs in `folder.themes` are assigned
  to this workspace.** Filter nodes to those IDs before you choose. ~10 KB.
- `get_theme_for_block_picker` q `{themeId}` → `theme{id,name,blocks.nodes[]{id,name,folderId,thumbnailUrl}}`.
  ~5 KB. `thumbnailUrl` is a viewable PNG of each block.
- `get_block` q `{blockId}` → `block{id,name,description,html (DML),latestRevisionId (brv_),previewData,isTemplateBound}`. ~1–3 KB.
  **It's the only light source of `latestRevisionId`, which you need to write the block into a draft.**

**Avoid unless necessary (heavy):** list_theme_blocks (~220 KB: it returns every block in the org, not just the theme's),
get_themes_with_block_ids (~60 KB), get_themes_thumbnail / get_theme_thumbnails_paginated
(HTML), get_theme_with_blocks (~25 KB, only for headContent/style variants), get_blocks_thumbnail (undocumented requestType).

**Editable slots:** read them straight from the DML. Every `editable='<id>'` attribute is a slot
(`title_1`, `text_1`, `img_1`, `button_1`, `pill_1`, `divider_1`…). Tags:
- `dys-title`, `dys-text`, `dys-button`, `dys-pill`: copy goes in `value` (HTML allowed).
- `dys-img`: `value` is empty. Override attributes `src`, `alt`, `href`, `title`, `width`, `height`.
- `dys-button`: also override `href` (and `variant`, `background-color`, `color`) via attributes.
- Text tags: optional attribute overrides `color`, `font-size`, `align`, `variant`.
- `dys-if` / repeatable groups: check `editableGroup` if the DML has repeating structures.

Only call `get_editables_from_block_dml` q `{dml}` if the DML is ambiguous (nested groups, carousels).

## 4. Draft content structure

A template version holds an ordered `blocks[]`. Each entry is one block **instance**, and the same block can repeat:

```json
{ "blockId": "blk_…", "blockRevisionId": "brv_…", "isPinned": false,
  "content": [
    {"id":"title_1","value":"Spring is here, @{first_name}","attributes":[],"carouselImageOverrides":[]},
    {"id":"text_1","value":"<p style=\"margin-top:0;margin-bottom:0\">Body copy…</p>","attributes":[],"carouselImageOverrides":[]},
    {"id":"img_1","value":"","attributes":[{"name":"src","value":"https://…png"},{"name":"alt","value":"Hero"}],"carouselImageOverrides":[]},
    {"id":"button_1","value":"Shop now","attributes":[{"name":"href","value":"https://brand.com/spring"}],"carouselImageOverrides":[]}
  ]}
```
Rules:
- Every content item needs all four keys: `id, value, attributes, carouselImageOverrides`.
- `attributes` hold overrides only. Omitted editables and attributes fall back to the block's DML defaults, so
  **override every slot that holds sample or placeholder copy**, or it ships as-is.
- Text values are HTML. Wrap paragraphs as `<p style="margin-top:0;margin-bottom:0">…</p>`. `<br/>`, `<a href>`, `<strong>`, `<span>` are fine.
- Personalization: `@{variable}` in values, subject and preheader. **Fallback syntax is a function call:
  `@{first_name|default("there")}`.** The colon form `@{first_name|default:"there"}` is rejected in block content with an
  opaque `upstream_graphql_error` (oddly, the subject field accepts it), so use parentheses everywhere.
- Slot IDs are arbitrary strings: `title_1`, but also `Title`, `Hero Button`, `Text 3`, even `true`. Copy them exactly from the DML.
- **Hiding a slot you don't need:** override attribute `show` = `"false"` (works on title/text/img/button/pill even when not
  listed in editable-styles). Use it on unused sample slots (a "Subtitle" under a title, a third button) rather than leaving
  sample copy like "Sed congue ante" or "Button".
- Overriding `href`, `src`, `alt`, `align` and `show` via `attributes` works on any editable element.
- To hide a block instance conditionally: content item `{"id":"dys-conditional-block","value":"","attributes":[{"name":"cond","value":"loyalty_tier == \"gold\""}],"carouselImageOverrides":[]}`.

## 5. Create & populate

1. **create_template** m
   `{input:{name, draftName, type:"VISUAL", isBlueprint:false, folderId, themeId, subject?, preheader?, previewData?, description?, sender?{name,address}, replyTo?{name,address}}}`.
   Read the template ID (and the draft ID, if it's returned) from the response.
2. If there's no draft ID in the response: `get_most_recent_draft` q `{templateId}` → `template.mostRecentDraft.id`.
3. **update_template_partial** m (no `input` wrapper). Send **all blocks in one call**:
   ```
   {visualVersion:{draftId, blocks:[…full ordered list…], subject, preheader, sender:{name,address}, replyTo?,
     generatePlainText:true, previewData:"<JSON string>", utmParams?}}
   ```
   → `{id: <new tvr_>, draftId}`. **That `id` is the new latest revision, so you don't need get_draft afterwards.**
   **Each update saves a whole new version.** Anything you leave out (sender, replyTo, subject, preheader) is cleared, even if
   create_template set it. Resend sender, subject, preheader and previewData on every update.
   `blocks` replaces the whole list. To change one block later, resend all of them.
   Opaque rejection? Check, in order: the colon-style fallback syntax, a missing `blockRevisionId` / `isPinned` / one of the
   four content-item keys, and `previewData` sent as an object instead of a string. Bisect (send half the blocks) only after those.
4. `get_draft` q `{draftId}` → `templateDraft{id,templateId,latestRevision{id},publishStatus}` (~0.6 KB). Use it only if you've lost
   track of the latest revision ID.
5. Read back only when needed: `get_draft_preview` q `{templateId, draftId}` (copy and plainText, ~6 KB) or `get_draft_revision`
   q `{revisionId, draftId}` (full content, localizationSchema and previewData, ~25 KB).

Optional dry run without saving: `render_unsaved_template` m
`{input:{blocks:[{blockId,blockRevisionId,content}], options:{title:<subject>, preheader}, themeId, folderId, previewData, generatePlainText:true}}`
→ subject, preheader, plainText, `variables[]`, renderWarnings, blockHtml[], chromeStart/chromeEnd. ~20 KB. Use it only when testing net-new DML
or debugging a rejected update.

Clone shortcut (when the user says "like our X email"): `duplicate_template` m `{input:{id, name, folderId}}` →
get_most_recent_draft → get_draft → get_draft_revision → edit blocks → update_template_partial.

## 6. Personalization

- `previewData` is a **JSON string** on drafts and renders (`"{\"first_name\":\"Ada\",\"loyalty_tier\":\"Gold\"}"`).
- Customer data profiles: check once with `discover_tools("list customer data profiles")`. If a list/get tool appears in the top 5, use it to read
  the profile fields available to the workspace. If not (the current state), infer variables from:
  1. `previewData` on the blocks you already fetched with get_block (free, already in hand; often empty), then
  2. a similar existing email: `search_templates_blocks_themes_by_keywords`
     `{input:{query:"<ONE keyword>", filters:{includeEmails:true, includeBlocks:false, includeThemes:false, includePush:false, includeSMS:false, includeVoice:false, includeLiveActivity:false, tagIds:[]}}}`
     **Multi-word queries often return nothing** ("loyalty welcome" → 0, while "loyalty" and "welcome" each return hits). Send 2–3
     single-keyword searches in the same parallel batch (topic, email type, brand). Ignore results that are obviously tests ("test", "[skill-test]", "copy of").
     The result includes the draft ID, so go straight to `get_draft` → `get_draft_revision` → `previewData`, the `@{…}` tokens in the content, its
     `sender`, its theme, and its header logo URL. (list_campaigns can't filter by folder and often misses new emails, so don't use it here.)
     This one read feeds personalization, the sender default, the theme choice (reuse it if that theme is assigned to the target workspace)
     and a real logo URL.
- Only personalize with variables you found. Never invent a variable name. If none are found anywhere, skip personalization and say so.

## 7. Brand guidelines

- `list_brand_guidelines` q — → `brandGuidelines.data[]{id,name,description,audience,tone[],personality[],default,workspaceIds[]}` (~1 KB).
  Pick the one whose `workspaceIds` include the chosen workspace. Otherwise use the `default:true` one when its workspaceIds are empty.
- Visual brand comes from the theme: don't override colors or fonts unless the user asks.

## 8. Images / assets

- `list_assets` q:
  `{isChildFolder:false, openFolderId:"", imageTransforms:[{"key":"thumb","compress":true,"width":200}], limit:10, filter:{searchTerm:"<name>", type_eq:"FILE"}}`
  **`imageTransforms` must be non-empty or the call fails.** → `assets{totalCount, data[]{id,name,url,imageMeta{altText,imageWidthPx,imageHeightPx}}}`.
  Use `url` as the `src`.
- Match bar: reuse only an asset that's essentially the same image (same filename stem or an identical subject/variant, matching dimensions).
  "Similar" is not a match.
- Upload a web image the user gave as a URL: `upload_block_image_url` m
  `{input:{url, optimize:true, altText, name, folderId?}, imageTransforms:[{"key":"thumb","compress":true,"width":200}]}` → hosted Dyspatch URL.
- A local image file (no public URL) can't be uploaded through these tools. Leave the block's default image or another theme image,
  and list it in the hand-off as "replace in Dyspatch".

## 9. Localization

Do this **after** the source-language copy is final (post-QA), so you translate once.

1. Read the source keys: `get_draft_revision` q `{revisionId, draftId}` → `localizationSchema.items[]{key, attributeName, editableID, tagName}`.
   The subject and preheader aren't in items. Use the exact subject and preheader strings as their keys.
   (`get_template_data` also exposes the schema, but that response can be very large.) Translate: subject, preheader, items with `attributeName:""`
   (text, titles, button labels), and `alt` items. Skip `src`/`href` items and brand names. Untranslated keys fall back to the source text (and show up as a LOCALES_TRANSLATED warning, which is fine).
   Keys are the exact saved strings, including the `<p style="margin-top:0;margin-bottom:0">` wrapper.
2. If AI translation is wanted and `features.aiTranslation` is true: `get_ai_translation` q `{input:{keys:[…all keys…], locale:"fr-FR"}}`
   (**no `contentType`**, because adding it causes an error) → `data.aiTranslation.results{<key>:<translation>}`. It's a query, so no approval
   is needed. Send one call per locale with all keys.
3. **Review the AI output before saving.** Known defects: apostrophes HTML-escaped (`&#39;`) in plain fields like the subject, brand
   names translated or mangled ("Brand Co" → "Brand &amp; Co"), the space before `@{var}` dropped ("Bonjour@{first_name}"), occasional
   truncation, `<br />` tags or link boundaries moved inside rich text (a link wrapping the wrong words), and fallback strings inside
   `default("…")` left in the source language. Check that each translation keeps the same tags and `@{…}` tokens as its source, and fix
   anything off by hand.
4. Write all locales in **one** call: `update_template_localization_partial` m (no input wrapper)
   ```
   {versionId:<latest tvr_>, localizations:[
     {name:"French (France)", lcid:"fr-FR", groupRevisionId:"", mapping:{"<source key>":"<translation>", …}},
     {name:"Spanish (Spain)", lcid:"es-ES", groupRevisionId:"", mapping:{…}}]}
   ```
   **`mapping` is a JSON object** (read-backs return it as a string). **`groupRevisionId:""` works for standalone languages.** Only use a locale
   group's `lgr_` (from `get_locale_groups`) if the user asks for a locale group. The call returns a new latest revision ID.
   Without AI translation, pass `mapping:{}` to create the language for translators to fill.
   Putting `localizations` inside `update_template_partial` does **not** save them (it runs saveVersionWithoutLocalizations).
5. Verify: `get_draft_localizations` q `{draftId}` → `latestRevision.localizations[]{lcid, name}`.

## 10. QA: guardrails & plain text

- **validate_template_revision** q `{revisionId}` (a query, no approval, the most complete check) →
  `templateValidationItems[]{title, details, level: ERROR|WARNING|SUCCESS, type, blockRenderedMeta{blockIdx (1-based), editableId}}`
  plus `templateLinks[]{url, blockIdx, editableId, warnings[{type: LINK_IS_INVALID|LINK_IS_PLACEHOLDER}]}`.
  Items repeat for amp true/false, so dedupe them. Common types: SUBJECT_IS_VALID (40–60 chars), PREHEADER_IS_VALID (30–80),
  PLAINTEXT_IS_VALID, ALT_TEXT_IS_VALID, URLS_ARE_SECURE_AND_VALID (`#` and http count as invalid), SPAM_WORDS, UNSUBSCRIBE_LINK_EXISTS,
  EMAIL_CONTENT_SIZE_IS_VALID, INTEGRATION_EXPORT_IS_VALID.
  `list_guardrails_rules` q shows which rules an org set to ERROR vs WARNING (you rarely need it, since the levels come back on each item).
- Prefer validate_template_revision over validate_rendered_template (a mutation that returns a subset).
- **Scan `templateLinks` for `IMAGE_LINK` entries with `LINK_IS_PLACEHOLDER`.** A common one is the theme Header block's
  `@{DYS.theme.logo.url}` resolving to a grey placeholder logo. Replace it (override the header img `src`) with the real logo URL from
  the similar email or the asset library. A placeholder logo is the most visible defect a reviewer will spot.
- SUBJECT_IS_VALID sometimes flags personalized subjects as "too long" even when they're short. Treat it as a warning and don't chase it.
- **Plain text:** set `generatePlainText:true` in update_template_partial. That's the per-draft auto flag. **`PLAINTEXT_IS_VALID` = SUCCESS
  in validate_template_revision confirms it worked.** `get_draft_preview.plainText` stays empty with auto plain text, because it only shows
  manually written text, so don't use it as a check. Only if PLAINTEXT_IS_VALID isn't SUCCESS should you write the plain text yourself
  (from the final copy: headings, paragraphs, `Label: URL` for links) and save it as `visualVersion.plainText` with `generatePlainText:false`.

## 11. Preview image

No MCP tool returns a PNG/JPG of a draft. The editor's "Download As" PNG/JPG isn't exposed. Every preview you show must
include the **sender (name + address), subject and preheader** next to the email, because reviewers judge those as part of the
email. The script draws an inbox-style header with them.
(Skip list_campaigns thumbnails: new emails usually aren't listed yet, they lag behind saves, and they carry no header info.)

1. `render_template_version` m `{id:<latest tvr_>}` → `data.renderTemplateVersion.html` (~20 KB). MCP results can't be piped to disk,
   so write the `html` value to a file in a run-unique temp dir (`mktemp -d`) with your file-writing tool. Copy the visible markup
   exactly. You may drop the invisible preheader spacer characters and `<!--[if mso]>` blocks to save tokens.
   Then run
   `python scripts/screenshot_email.py <dir>/email.html <dir>/preview.png --subject "…" --preheader "…" --from-name "…" --from-email "…"`
   (headless Chromium via Playwright + Pillow). Use the subject and preheader with variables resolved to the preview data
   (e.g. "Welcome, Jordan"). The script prints `images_broken` and `broken_hosts`.
   If the html field has errors, use `render_unsaved_template` (chromeStart + blockHtml.join("") + chromeEnd).
2. **If `images_broken` > 0**, this environment's network allowlist is blocking Dyspatch's image CDN (usually `cdn-web-assets.dyspatch.io`).
   Don't present the preview as complete. Show it labeled "images blocked in this environment", and tell the user:
   *"An admin can allow `*.dyspatch.io` in Claude's network/egress settings (claude.ai Admin settings → Capabilities)
   so previews include images. Meanwhile, the Dyspatch link shows the full preview."* If a browser tool that runs on the user's
   machine is available, opening the Dyspatch preview link there is an alternative.

## 12. Approval & handoff

- `request_publish` m `{draftId, comment, reviewers:[userId,…]}` (no input wrapper) submits the draft for approval.
  **Pass at least one reviewer.** Without reviewers it returns `requestTemplatePublish:null` and silently creates nothing. Check that the
  response has a request `id` (tdpr_…) and treat null as failure.
  Reviewer IDs, in order of preference: the users the person named → the workspace's approvers (`list_workflow_approver_groups` q, matching
  `folderId`) → (if someone can answer) `get_users_mentions` `{workspaceId}` and ask which ones → otherwise the current user
  (`get_who_am_i.me.id`, flagged in the summary).
- `create_template_external_share_link` m `{templateId, draftId, includeGlobalData:false, includePreviewData:true, dataProfileIds:[]}` creates
  a share link for external reviewers. It returns an ID, so use it only if asked.
- `send_test_email_many` m sends real email. Only do it if the user explicitly asks.
- App link (opens the draft in the block editor): `https://app.dyspatch.io/template/{templateId}/{draftId}/blocks`
  e.g. `https://app.dyspatch.io/template/tem_01m512fc5pnfdr7vrt4ymgw3zx/tdft_01m512fc5s7fd7zkj8bsvh8ssy/blocks`.
  Note it's singular `template` and has no `drafts/` segment. Use the tem_ and tdft_ IDs from create_template / get_most_recent_draft.

## 13. Net-new blocks (only with createBlock permission and the user's OK)

- Cheapest: `duplicate_block` m `{input:{id, name}}` on the closest block → `update_block` m `{input:{id, html:<edited DML>, isTemplateBound:false, isVisualBlock:false}}`
  → `add_block_to_theme` m `{id:<blockId>, themeId}`.
- From scratch: `create_block` m `{input:{name, html:<DML>, themeId, description?, previewData?}}`. For a one-off scoped to this email:
  `isTemplateBound:true, originDraftId:<draftId>`.
- Test DML first with `render_unsaved_block` m `{input:{dml, themeId}}`.
- DML skeleton (copy the conventions from a sibling block in the same theme):
  `<dys-block><dys-row><dys-column><dys-title editable='title_1'>…</dys-title><dys-text editable='text_1'>…</dys-text><dys-button editable='button_1' href='#'>…</dys-button></dys-column></dys-row></dys-block>`
- After creating it, `get_block` the new block for its `latestRevisionId`.

## 14. Known gaps (check with one narrow discover_tools call if the feature matters; the MCP is evolving)

| feature | current state | fallback |
|---|---|---|
| list customer data profiles | no list/get tool | infer from block previewData or a recent email's previewData |
| AI subject/preheader/copy (Scribe) | not exposed | write them yourself using the brand guideline. Say so in the hand-off |
| Figma / image-to-email / brief importers | not exposed | parse the input yourself (see SKILL.md, Phase 1) |
| PNG/JPG of a draft ("Download As") | not exposed | render + `scripts/screenshot_email.py` |
| App deep links | not exposed | build from the pattern in §12 |
| AI image generation | not exposed | use library assets or block defaults |
