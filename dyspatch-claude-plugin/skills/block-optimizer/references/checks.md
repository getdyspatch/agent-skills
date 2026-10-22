# Checks, severities and DML syntax

The checks `scripts/analyze_blocks.py` runs, the judgement calls that are yours, and the DML each fix needs.
Syntax is from docs.dyspatch.io (DML reference, Using editable, Variants, Targeting dark mode).

## Contents
1. Severity rubric
2. Axes: what the script flags, and what you add
3. DML syntax for fixes
4. What the script can't judge
5. Manual method (no code execution)

---

## 1. Severity rubric

| Severity | Meaning | Examples |
|---|---|---|
| **High** | Broken, risky or clearly wasteful. Fix soon. | ESP click-tracking links copied into a block · no theme logo · exact duplicate blocks · element both `editable` and `localizable` · `dys-repeat` without `editable` · unused block older than the stale window |
| **Medium** | Costs editors time, breaks portability, or misses a feature that would remove blocks | hotlinked images · no editable content in a content block · hardcoded styles (10+) · near-duplicates · no variants / dark mode · desktop+mobile copies without `editable-group` · raw HTML without a reason · list content without `dys-repeat` |
| **Low** | Polish and hygiene | generic editable ids · hardcoded links · `#` links · HTML comments · off-palette colours · Gmail light lock off on a theme that has dark styles · no description |
| **Info** | Context, not a problem | template-bound blocks · uses conditionals |

Adjust a severity when the context plainly changes it, and say why. For example, a locked legal footer is fine; a
hotlinked image on the company's own CDN is fine once the user confirms the domain. Don't inflate: a report with
80 Lows buries the 5 Highs.

## 2. Axes

### Inventory: unused and stale
- **Unused:** `templatesCount == 0` and `blueprintsCount == 0` in the theme payload. That covers every email,
  draft and blueprint. It's High if the block is older than the stale window, otherwise Medium (it may be new and
  about to be used).
- **Stale:** in use, but no email using it has been edited in `--stale-days` (default 365). This needs the
  last-used dates (tool-reference §5).
- **Not in any theme** / **only in archived themes:** editors can't reach the block.
- **Your call:** a seasonal block (Black Friday, holiday) that's stale is expected. Say "seasonal, keep" rather
  than "retire".

### Duplicates
- **Exact:** the same DML once comments, whitespace and editable ids are normalized. Keep the most-used one.
- **Near (≥ 85% similar, same element structure):** the usual cause is copy-and-tweak. Suggest a single block
  whose differences become `show` toggles, editable styles, a variant, or a `dys-if`.
- **Same name in the same theme:** confusing in the block picker.
- **Your call:** open both DMLs for the top near-duplicate pairs and describe what actually differs ("only the
  button colour" → variant; "an extra subtitle" → `show`).

### Editability
- No `editable` on any content element, some content locked, editable+localizable conflicts, duplicate editable
  ids, generic ids (`Element 1`, `true`), no `editable-styles` when the theme doesn't auto-enable them.
- **Your call:** locked content is correct for legal copy, brand lockups and compliance text. Flag only what an
  editor would plausibly change per email (headlines, body, CTAs, images, links).

### Clarity
- Sample or lorem copy as defaults, unhelpful names ("Copy of…", "Group 6", "Test"), duplicate names.
- **Descriptions:** editors see them in the block picker, and they're how editors tell similar blocks apart.
  - Flagged when missing or weak: a placeholder ("test", "TODO"), an auto note ("Auto Import – 2025-07-15…"),
    one that repeats the name, or one under 15 characters.
  - Low, or Medium when 10+ emails use the block.
  - **Your call:** for the most-used blocks, propose a one-sentence description from what the block contains and
    is used for.

### Tags
`get_tags {type:"block"}` lists the block tags defined in the account; each block's tags come with the block.
- **No tags defined:** one line in the report. Suggest tags only if the library is large and the names don't help
  editors find blocks.
- **Tags defined but no block uses them:** say so plainly. Tags that exist but aren't applied don't help anyone.
- **Possibly missing tag:** an untagged block that is a near-duplicate of a tagged block, is named like the
  tagged ones, or matches what the tag's name implies. For example, "Has Logic" → contains `dys-if`/`dys-for`;
  "Promo" → promotional copy.
- **Your call:**
  - Tags with workflow meanings ("Staging", "Feature-") can't be inferred from content. The report marks them
    "needs your judgement", so describe how they're used rather than guessing.
  - Prune obvious false suggestions before reporting.
- **Your call:** read the default copy, editable ids and description of the most-used blocks the way a new
  editor would. Do they say what the block is for and what goes where? Suggest better names in a table
  (current → proposed).

### Style consistency
- Hardcoded colour and type attributes, inline `style`, fonts set in the block, colours outside the theme palette.
- For a per-property list, point to `/dyspatch:review-block-overrides`; don't duplicate its detail.
- **Your call:** compare blocks *within a theme*. Do titles use the same levels and sizes? Do buttons use theme
  variants or each set their own colour? Is padding consistent (e.g. 20px vs 24px vs 32px rows)? Name the outliers.

### Accessibility
- Images without `alt`, weak alt ("image", file names), vague link text ("click here"), text under 12px, contrast
  under 4.5:1 when both colours are in the block.
- **Your call:** heading order (`dys-title level`: one `h1` per email, so most blocks should be `h2`+), text
  baked into images (judge from `thumbnailUrl` if you look at one), and colour-only meaning.

### Links & images
- **Hotlinked images:** `src`, `background-url` or `icon-src` on a host that is neither `*.dyspatch.io` nor an
  owned domain.
- **ESP click-tracking URLs** (`/ls/click?upn=`, `ct.sendgrid.net`, `list-manage.com/track`…): these get copied in
  when someone builds a block from a sent email. They're High: clicks go to someone else's ESP account, and the
  links expire.
- Links with no scheme (`www.acme.com`). Clients treat them as relative, so they're dead (**High**).
- `http://` URLs, hardcoded links (not editable, and not inside an editable text element), `#` placeholders.
- Social profile links and brand links (home, privacy) are fine hardcoded. Only flag them if they're wrong.

### Hardcoded HTML
- `dys-raw` / `dys-html` sections (and whether they're outside `dys-export`, which means they ship to every
  ESP), `dys-table`, raw `<table>`/`<div>` tags, and `<!-- -->` comments (they ship; `dys-comment` doesn't).
- **Justified:** ESP code (AMPscript, Liquid) inside `dys-export`, interactive CSS (checkbox/radio toggles), schema
  markup (Google annotations), tracking pixels, genuinely tabular data in `dys-table`.
- **Not justified:** layout rebuilt in tables or divs, styled text in spans, buttons as `<a>` with inline styles.
  For each raw block, say which case it is.
- **Does it render?** For the top raw or interactive blocks, a dry-run render (SKILL.md Step 5) shows what
  recipients actually get. Raw HTML can be stripped or mangled, and instruction text inside schema or annotation
  blocks can end up visible. If it's broken, that's High however justified the raw HTML is.

### Theme features
- **Logo:** is `logoActive` on with a `logoUrl`? Do header and logo blocks use `@{DYS.theme.logo.url}` and
  `@{DYS.theme.logo.href}`? A header that hardcodes its logo needs one copy per brand.
- **Variants:** defined in `<dys-attributes>` (`variant=`)? Enabled in `editableStyleControls` for the common
  components (row, column, group, text, title, button, img)? Are block `variant=` values defined in the theme?
  Are some theme variants used by no block (for example, ones named after sample copy, which come from Figma
  imports)?
- **Mirror Layout:** `direction` enabled for `dys-row` and `dys-group`, so one "Image | Content" block also serves
  as "Content | Image". If both directions exist as separate blocks, call that out as a merge.
- **Dark mode:** `@media (prefers-color-scheme: dark)` rules in the theme head.
- **Gmail light-mode lock** (Theme → Settings → Lock Light Mode in Gmail; new, not yet in the docs): the Gmail
  iOS/Android apps force-invert colours in dark mode unless the email says `color-scheme: light only`, and the
  toggle adds that. Read it from a dry-run render (tool-reference §6b).

  | Lock | Theme has dark styles? | Finding |
  |---|---|---|
  | Off | No | **Medium.** Dark mode is uncontrolled everywhere. Suggest the lock if the brand should stay light, or dark styles. |
  | Off | Yes | **Low.** Gmail ignores the dark styles and inverts anyway. The lock keeps Gmail light while other clients use the dark styles. |
  | On | Yes, but no `:root { color-scheme: light dark; }` | **Medium.** `light only` also switches off the dark styles in Apple Mail and other clients. Add the `:root` rule. |
  | On | — | Old blend-mode or Gmail hack CSS is now redundant (**Low**). |

  - **Your call:** the lock overrides the recipient's dark-mode preference. Recommend it for brands whose colours
    or logos break when inverted, not as a blanket rule.
  - Litmus and device previews of the Gmail app may still show forced dark mode, so verification needs a real send
    to the Gmail app. The lock doesn't affect desktop Gmail.

### Advanced features (opportunities)
- **`editable-group`:** `dys-desktop` + `dys-mobile` copies with editable content should share an
  `editable-group`, so one control edits both.
- **`show`:** near-duplicates that differ by one element should become one block with `show` on that element.
- **Partials and includes:** identical columns side by side (use a partial with `id-suffix`), or the same row in
  3+ blocks (a shared partial, or an imported block).
- **`dys-repeat`:** 3+ identical rows or items (product lists, feature bullets, NPS scales). Wrap one item in
  `dys-repeat` instead of shipping 2-, 3- and 4-item versions.
- **Block-level conditionals:** set per email under Display Options, not in DML, so the script can't see them in
  blocks. In-block `dys-if`/`dys-elif`/`dys-else` is visible.
  - **Your call:** near-duplicate blocks that differ by audience (member/guest, tier, region) → one block with
    `dys-if` branches, or one block shown conditionally per email.
  - Check that personalized branches have a `dys-else` fallback.
- **Your call on reduction:** estimate how many blocks the library could lose if the opportunities were adopted
  ("6 'N-column' and 'N-item' blocks → 2 with `dys-repeat`").

### Localization (only when the account localizes)
- Locked copy in footers, headers, legal and nav blocks that isn't `localizable`. Translating it once at block level
  means every email using the block gets it.
- **Your call:** per-email copy should stay `editable` (translated per email). Block-level localization is for copy
  that rarely changes.
- Hardcoded `align='left'` in localized blocks blocks RTL flipping; `start` and `end` flip automatically.

## 3. DML syntax for fixes

```html
<!-- editable, with field and style limits -->
<dys-button editable='Primary CTA' editable-fields='content,href' editable-styles='align'>Shop now</dys-button>

<!-- theme logo -->
<dys-img src='@{DYS.theme.logo.url}' href='@{DYS.theme.logo.href}' alt='Acme' editable='Logo' editable-fields='alt' />

<!-- optional element -->
<dys-title editable='Subtitle' show='true'>…</dys-title>

<!-- variant (defined in the theme's <dys-attributes>) -->
<dys-button variant='secondary' editable='CTA'>…</dys-button>
<!-- theme: <dys-attributes><dys-button background-color='#1F77D4' color='#fff' variant='secondary' /></dys-attributes> -->

<!-- desktop / mobile copies edited together -->
<dys-desktop><dys-text editable='Desktop text' editable-group='intro'>Hi</dys-text></dys-desktop>
<dys-mobile><dys-text editable='Mobile text' editable-group='intro'>Hi</dys-text></dys-mobile>

<!-- repeatable list -->
<dys-repeat editable='Features'><dys-text editable='Feature'>Fast setup</dys-text></dys-repeat>

<!-- partial, defined once per block (one dys-includes, last child of dys-block) -->
<dys-row>
  <dys-column><dys-include name='card' id-suffix='-1'/></dys-column>
  <dys-column><dys-include name='card' id-suffix='-2'/></dys-column>
</dys-row>
<dys-includes><dys-partial name='card'><dys-img editable='img' src='…' alt='…'/><dys-text editable='txt'>…</dys-text></dys-partial></dys-includes>

<!-- block-level translation for fixed copy (never also editable) -->
<dys-text localizable='Legal notice'>© 2026 Acme Inc.</dys-text>

<!-- conditional with fallback -->
<dys-if-else><dys-if cond="tier == 'gold'">…</dys-if><dys-else>…</dys-else></dys-if-else>

<!-- ESP-only code, so it doesn't ship to other ESPs -->
<dys-export targets='ampscript'><dys-raw>%%[ … ]%%</dys-raw></dys-export>

<!-- stripped on export (unlike <!-- -->) -->
<dys-comment>Why this raw HTML is here</dys-comment>
```

Theme dark mode goes in the theme head, outside `<dys-attributes>`. Target `dys-text` through a theme
`css-class` and its inner `div`:

```html
<dys-style>
  :root { color-scheme: light dark; }  /* keeps these styles working when Lock Light Mode in Gmail is on */
  @media (prefers-color-scheme: dark) {
    #body { background-color: #121212 !important; }
    .body-text > div { color: #FFFFFF !important; }
  }
</dys-style>
```

Rules the docs state:
- An element can't be both `editable` and `localizable`.
- Editable and localizable ids must be unique within a block.
- `dys-repeat` needs `editable` and at least one child.
- A block has only one `dys-includes`.

## 4. What the script can't judge

These are yours. Spend your reading on the top blocks and pairs, not the whole library.

1. Whether locked content is deliberately locked (legal or brand).
2. Whether raw HTML is justified (§2, Hardcoded HTML).
3. What near-duplicates actually differ by, and which DML feature would merge them.
4. Clarity of names, ids and default copy for a new editor, and better names to use.
5. Style consistency across a theme's blocks (spacing, title sizes, button treatment).
6. Conditional and localization opportunities that come from what blocks are for.
7. Whether "stale" blocks are seasonal.

## 5. Manual method (no code execution)

This is slower and less reliable, so limit it to one theme and say in the report that it was done by hand.
Fetch `get_theme_with_blocks` and `get_blocks {themeId}`. For each block, apply §2 by reading its `html`.
Use `templatesCount` from the theme payload for usage, and compare blocks with similar names for duplicates.
Write the same report structure.
