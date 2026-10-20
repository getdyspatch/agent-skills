---
name: create-email
description: Builds a new email in Dyspatch through the Dyspatch MCP server, using the account's existing workspaces, themes, blocks, brand guidelines and image library. Accepts any starting point (a Word or PDF brief, a Figma frame, a screenshot or mockup image, pasted copy, or a one-line idea) and handles personalization, subject and preheader, languages, guardrail fixes, plain text, a preview image, and an optional approval request. Use this whenever someone wants to create, build, draft, assemble, or "turn this into" an email in Dyspatch, rebuild an image or design as a Dyspatch email, or make an email from existing blocks or themes, even if they never say "MCP" or "template".
---

# Create an email in Dyspatch

You're building a production email inside the user's Dyspatch account from blocks and themes their team already
maintains. Two things matter most:

1. **Reuse before you create.** Existing themes, blocks and image assets carry the brand. A new block is a last
   resort, and needs the user's OK.
2. **Spend MCP calls carefully.** The Dyspatch MCP has hundreds of tools behind a `discover_tools` / `invoke_tool`
   gateway, and discovery responses are large. Everything you need is mapped in `references/tool-reference.md`.
   **Read it before your first Dyspatch call** and call tools by name.

## Efficiency rules

- **Skip `discover_tools`** for anything in the reference. Use it only for a gap feature in reference §14 (one narrow
  intent, once), or when a documented call keeps failing after you've checked the "Opaque rejection" list in reference §5.
- **Call mutations with `approve_mutation` directly.** Never `invoke_tool` a mutation first.
- **Run independent reads in parallel** (in the same turn). Phase 2's survey and Phase 3's `get_block` calls should each
  go out as one batch.
- **Pick the light tool** (list_themes, get_theme_for_block_picker, get_block, get_draft_preview) over heavy ones
  (get_themes_with_block_ids, get_theme_with_blocks, list_theme_blocks, thumbnail-HTML tools, get_template_data) unless you
  need something only the heavy one has.
- **Write the whole email in one `update_template_partial` call**: all blocks, subject, preheader, previewData and
  `generatePlainText:true`. Its response `id` is the new latest revision, so don't follow up with get_draft.
- **Get syntax right the first time.** Fallbacks are `@{first_name|default("there")}` (parentheses, not a colon), and
  `previewData` is a JSON *string*. These two mistakes caused most failed calls in testing.
- **Cache every ID** (workspace, theme, block, revision, draft) and never re-fetch it.
- **Read slot IDs from the block DML** (`editable='…'`) instead of calling `get_editables_from_block_dml`.
- Use a run-unique temp dir (`mktemp -d`) for any files you write.

A clean run is roughly 20–28 Dyspatch calls (more with languages or many blocks). Every failed call is a sign something
in this file or the reference was skipped. Re-check before retrying blindly.

## Workflow

### Phase 1: Understand the input (no Dyspatch calls yet)

Turn whatever the user gave you into an **email outline**: an ordered list of sections, each with a role
(logo/header, hero image, headline, body, CTA, product grid, testimonial, event details, footer/legal…), its copy,
image needs and links. Also capture any subject, preheader, sender, languages, audience, and email type.

- **Word (.docx):** `pandoc file.docx -t markdown` (or python-docx). Headings and bold lines usually mark sections.
- **PDF:** extract the text, and look at the pages for layout cues.
- **Image / screenshot / mockup:** look at it. Read the hierarchy top to bottom, transcribe all copy exactly, and note
  each image region (what it shows) and button labels. Treat a sample name ("Hi Sam") as a personalization slot: use a real
  variable if Phase 4 finds one, otherwise make the copy generic ("Hi there"). Don't use the mockup itself as an image: rebuilding it as modular blocks is the point.
- **Figma:** if a Figma tool is available, pull the frame's text and an exported image. Otherwise ask for a PNG export
  or the copy.
- **A plain request ("an email announcing our spring sale"):** draft the outline yourself and write the copy in Phase 6.

Keep the user's exact copy wherever they supplied it, and only generate what's missing. Sanity-check the brief too
(dates vs. "ends Monday", prices, conflicting instructions) and raise anything off in the Phase 5 confirmation.

### Phase 2: Survey the account (one parallel batch)

Read `references/tool-reference.md`, then call these in one turn:
- `get_who_am_i`: permissions (createBlock, createTemplate, publishTemplate), `OrgSettings.autoPlainText`, `features`, `me.id`
- `get_root_folders`: workspaces, plus the folder→workspace map
- `list_brand_guidelines`
- `search_templates_blocks_themes_by_keywords` ×2–3: **one keyword each** (topic, email type, brand), emails only.
  Multi-word queries tend to return nothing. Pick the closest real (non-test) email and read it once with `get_draft` →
  `get_draft_revision`. That one read supplies the variables, sender, theme hint and real logo URL (reference §6).
- `get_locale_groups`, only if the user mentioned languages

**Workspace:** match the email type to workspace names and descriptions (promo → "Marketing", password reset →
"Transactional"). If the user named one, use it. If two or more are plausible, ask (see "When to ask").

**Theme:** call `list_themes {id: workspaceId}` and filter `themes.nodes` to the IDs in `folder.themes` (nodes are
org-wide). Pick, in priority order:
1. the theme the user named
2. the theme used by the most similar existing email, if it's assigned here
3. the theme whose name, description and colors best fit the input

Skip themes with very few blocks (fewer than about 6), since they're usually experiments. If two good candidates remain
and nothing decides it, ask. Then call `get_theme_for_block_picker {themeId}`.

### Phase 3: Map the outline to blocks

From the block names (and `thumbnailUrl` images when names are vague), shortlist one block per section. Use the theme's
header and footer blocks so legal and unsubscribe content come for free. Fetch `get_block` for **all shortlisted blocks
in one parallel batch**. From each, take:
- `latestRevisionId`, which you need to write the draft
- the DML's `editable='…'` slots: does the block hold what the section needs? Note slots you'll have to hide.
- `previewData`: the variable names the block expects
- `max-chars` on text slots: keep your copy within it, or pick another block
- sample copy that isn't editable (e.g. a footer with fixed "Lorem ipsum" legal text or hardcoded links): prefer another
  header/footer in the theme. If there isn't one, flag it under "to finish". Never silently ship lorem.

Score each section:
- **Match**: every needed slot exists.
- **Close**: usable with compromises (no secondary button, merged copy, a stacked layout instead of columns).
- **Missing**: nothing reasonable exists.

Repeating one block (e.g. three "Product card" instances for a grid) is fine and counts as Close unless it looks wrong.

### Phase 4: Personalization, assets, brand

- **Personalization:** check once whether a customer-profile tool exists (reference §6). If not, use variables from the
  block previewData and from the similar email found in Phase 2 (one `get_draft_revision` on it). Place variables where
  they help: the greeting, the subject or preheader, and a conditional block (e.g. loyalty tier). Always add a fallback:
  `@{first_name|default("there")}`. Only use variable names you actually found. If you found none, skip personalization
  and say so. Leave legal and transactional boilerplate unpersonalized.
- **Assets:** for each image the user named or supplied, search `list_assets` by name or subject. Reuse only an
  essentially exact match. Web URLs can be uploaded with `upload_block_image_url` after confirmation. Local files can't
  be uploaded: keep the block's default image and flag it.
- **Brand guideline:** use the one assigned to the workspace, or the org default. Its tone, personality and audience
  govern every line you write.

### Phase 5: Confirm the plan (one message, before any write)

Send **one** concise confirmation so the user answers once. Use AskUserQuestion if it's available, otherwise a short
message. Cover:

1. Workspace and theme, with a one-line reason ("A promotional email, so **Marketing** with its **Spring Promo** theme,
   the same one your March sale used").
2. The block plan, section by section (Match / Close / Missing). For each Close or Missing section, offer *use the
   closest block (name it)* or *create a new block* (offer the second only if the user has createBlock).
3. Personalization ("Your data includes first_name and loyalty_tier, so I'll greet by first name and show the VIP banner
   only to Gold members").
4. Sender, subject and preheader. **Sender:** the user's, otherwise the similar email's, otherwise ask. Never invent an address
   (`news@brand.example` looks real and gets shipped). If nobody can answer, leave it unset and list it under "to finish".
   Subject and preheader: the user's, or your drafts in their brand voice, shown here so they can edit them.
5. Images: library assets you'll reuse, uploads, placeholders.
6. Languages: which locales, and whether to use Dyspatch AI translation or leave them for translators.
7. Anything odd you noticed in the brief.
8. **What to do when finished:** (a) share the link and preview, or (b) also submit for approval (name the reviewers
   you'd use).

Pre-select the recommended option so a quick "yes" works. If the user already settled something, state it instead of
asking.

### Phase 6: Build

1. **Subject and preheader:** use the user's if given. Otherwise check reference §14 for a Dyspatch AI generation tool. If
   there isn't one, write them yourself: subject 40–60 characters, preheader 30–80, in the brand guideline's tone, with the
   preheader adding to the subject rather than repeating it. Before saving, check your own drafts for words Dyspatch's spam
   check flags ("free", "now", "for you", "act fast", "check", "legal", "guarantee", "winner"), since a flagged word costs an
   extra update. Tell the user you wrote them.
2. **Net-new blocks** (only if approved): build them per reference §13 first, so you have their revision IDs.
3. **Uploads** (if any): `upload_block_image_url`.
4. `create_template`: name, draftName, `type:"VISUAL"`, `isBlueprint:false`, folderId, themeId, subject, preheader,
   `sender{name,address}` (and replyTo if given).
   Give it a descriptive name (e.g. "Spring Sale 2027 – Launch").
5. Get the draft ID from the response, or from `get_most_recent_draft` if it's missing.
6. `update_template_partial` with **all** blocks in order, and:
   - every slot either filled with real copy, or hidden with `show:"false"`. No sample text ("Lorem", "Sed congue ante", "Button") ships.
   - real https links from the user. If they gave none, use the brand homepage if known, otherwise keep the block
     default and list it under "to finish". Never invent deep URLs.
   - alt text on every image
   - subject, preheader, `sender`, `previewData` (a JSON string with realistic values for every variable), `generatePlainText:true`.
     Every update saves a full new version, so **resend sender, subject, preheader and previewData on every update**, or they're wiped.
   - the header logo: if the theme header uses `@{DYS.theme.logo.url}` and that resolves to a placeholder, override the logo
     `src` with the real logo from the similar email or the asset library

### Phase 7: QA (guardrails and plain text)

1. `validate_template_revision {revisionId: <id from the last update>}`.
2. Dedupe the items (they repeat for AMP and non-AMP). **Fix every ERROR**: map `blockIdx` (1-based) and `editableId` to
   the content item, correct it, resend the full block list, and re-validate. Stop after 3 rounds and report anything that
   needs account configuration (e.g. an ESP integration export error).
3. Warnings are fine. Fix the cheap ones in the same update (alt text, http→https, length, placeholder links you have real
   URLs for) and report the rest.
4. Check `templateLinks` for placeholder images (`IMAGE_LINK` + `LINK_IS_PLACEHOLDER`), especially the logo. Replace them when a real
   asset exists, and otherwise flag them.
5. **Plain text:** PLAINTEXT_IS_VALID = SUCCESS with `generatePlainText:true` means it's auto-generated, so you're done
   (`get_draft_preview.plainText` stays empty here, which is normal). If it's not SUCCESS, write the plain text from the
   final copy, save it as `plainText` with `generatePlainText:false`, and tell the user you wrote it.

### Phase 8: Languages (if requested)

The source copy is final now, so you translate only once. Follow reference §9 exactly: `get_draft_revision` →
localizationSchema keys → one `get_ai_translation` per locale (all keys, no contentType) → **review and fix the AI output**
→ one `update_template_localization_partial` with every locale (`mapping` as an object, `groupRevisionId:""`) →
`get_draft_localizations` to confirm. Then validate once more on the new revision ID (locale-specific errors can appear).

### Phase 9: Preview and hand-off

1. Get a preview image per reference §11: render, then run `scripts/screenshot_email.py` with the sender, subject and
   preheader so they show above the email. Show it to the user. Every preview or sample you show, including in the
   Phase 5 confirmation, carries the sender, subject and preheader. If the script reports broken images, say so and give the
   allowlist fix from §11, rather than presenting a preview with images missing as finished.
2. If the user chose approval: call `request_publish {draftId, comment, reviewers}` with at least one reviewer, and confirm
   the response has a request ID.
3. Close with a short summary:
   - email name, workspace, theme, and the editor link
     `https://app.dyspatch.io/template/{templateId}/{draftId}/blocks`
   - what's personalized, and which languages
   - sender, subject and preheader, noting which ones you wrote
   - plain text: auto-generated or written by you
   - guardrails: errors fixed, warnings remaining
   - **To finish in Dyspatch:** placeholder images, missing URLs, Close-match compromises, translation spots to review
   - approval status and reviewers

## When to ask, and when not to

Ask, bundling into as few questions as possible, when:
- more than one workspace or theme fits and the input doesn't settle it
- a section has no Match and you'd otherwise silently compromise or create a block
- something has no reasonable default (e.g. a transactional email whose variables you can't find)

Skip questions about anything the user already said, or anything with an obvious default. Otherwise, Phase 5 is the
one checkpoint before writes.

**Running unattended** (no one to answer): take the recommended defaults, use the closest blocks instead of creating new
ones, leave unknown senders unset, and list every assumption at the top of the summary. Do whatever the user explicitly
asked for, including submitting for approval (with the current user as reviewer if no approver group exists). Never take a write action they didn't ask for.

## Things that go wrong

- **`upstream_graphql_error` on update_template_partial:** almost always the colon-style fallback
  (`default:"x"` → `default("x")`), a missing `blockRevisionId`/`isPinned`/content-item key, or `previewData` sent as an
  object. Check those before bisecting.
- **Sample copy shipping:** an un-overridden slot keeps its sample text. Fill it or hide it with `show:"false"`.
- **`list_themes` "too many" themes:** nodes are org-wide. Filter to `folder.themes`.
- **`list_assets` failing:** `imageTransforms` was empty.
- **Approval silently not created:** `request_publish` without reviewers returns null.
- **Localizations not saved:** they were sent inside update_template_partial, or `mapping` was a string. Use
  update_template_localization_partial with an object mapping.
