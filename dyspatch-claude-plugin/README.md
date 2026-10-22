# Dyspatch plugin for Claude

## Skills

### /dyspatch:create-email
Builds a new email in your Dyspatch account from whatever you have: a Word or PDF brief, a Figma frame, a screenshot or
mockup, pasted copy, or a one-line idea. It:

- picks the right workspace and theme (and asks when it's unclear)
- maps your content to existing blocks, and asks before compromising or creating a new block
- personalizes with customer data your emails already use
- reuses exact-match images from your asset library
- writes the subject and preheader in your brand guideline's voice when you don't supply them
- adds languages with Dyspatch AI translation
- fixes guardrail errors and makes sure plain text is set
- shows a preview with the sender, subject and preheader
- shares the editor link, or submits the email for approval

It confirms the plan once before making any changes.

### /dyspatch:email-qa-checklist
Runs a QA and proofing pass over an existing email (by name, ID or Dyspatch link) and reports findings by category
and severity (Blocker / Warning / FYI):

- **Guardrails:** every Dyspatch guardrail warning and error
- **Links & Images:** Links Review placeholders and invalid links, live HTTP status of every link and image,
  off-domain hosts (FYI)
- **Content:** spelling and grammar in your audience's locale, placeholder copy, date and price consistency, plain text
- **Accessibility:** alt text, link text, contrast
- **Brand:** theme, logo, colors, and copy against your Dyspatch brand guideline
- **Personalization:** variable syntax and fallbacks, ESP-specific code, conditional logic
- **Localization:** missing locales, untranslated or broken translations
- **Performance:** subject and preheader, above-the-fold hero and CTA, UTMs, mobile layout, size
- **Technical:** device previews, stretched images, dark mode
- **Compliance & Deliverability:** unsubscribe, legal footer, sender, spam words
- **Campaign:** checks against your campaign brief, when you give one

It can add your own QA checklist on top of these, skip sections you don't need, and remember your choices in
`~/.dyspatch/email-qa-preferences.json`. Choose a mode: report only, report and comment on the email in
Dyspatch (each comment pinned to the element it's about), or report, comment and apply fixes once you approve
them. The report comes as Markdown, an HTML page or a Word document.

If your Claude app can drive a browser (a built-in browser or a browser extension), sign in to Dyspatch there when
asked and the skill will also check the email visually on desktop and phone widths and work with device previews.

### /dyspatch:review-block-overrides
Reviews the blocks in your account (or one theme's blocks) for hardcoded visual styles that override your themes
and stop a block working across themes:

- **Colours and backgrounds**, **typography** and **borders** set to fixed values on DML elements, on links, in
  inline `style=""`, or in `<dys-style>` rules (with `!important` called out)
- Optionally, **spacing** (padding and margins)
- Theme variables (`@{...}`), button variants and comments aren't flagged
- Blocks **not assigned to any theme** and blocks **only in archived themes**
- The most common hardcoded colours, which are good candidates for theme colours or variables
- Template usage for the worst offenders, so you know which fixes affect live emails

It writes a Markdown report with every block linked to its code in Dyspatch, and summarizes the top findings in
chat. It's read-only and changes nothing in your account. Useful before merging or adding themes, rebranding, or
sharing blocks between brands.

### /dyspatch:block-optimizer
Analyzes your block library (all blocks, the themes you pick, or every theme in a workspace) and tells you what
to retire, fix or consolidate:

- **Inventory:**
  - unused blocks (no emails, drafts or blueprints)
  - stale blocks, where no email using them has been edited in a year (you can change the window)
  - blocks in no theme, and exact and near duplicates
- **Clarity:** unhelpful names, missing or placeholder descriptions, sample copy left as defaults, and, if your
  account has block tags, blocks that look like they're missing a tag
- **Quality:** style consistency (hardcoded colours and fonts, off-palette colours), accessibility (alt text,
  contrast, link text, small text), and editability (locked copy, duplicate or generic editable IDs)
- **Links & images:**
  - images hotlinked from outside Dyspatch or your own domains
  - ESP click-tracking links copied from sent emails
  - links without `https://`, `http://` links and hardcoded links
  - raw HTML without a good reason, test-rendered to confirm it actually shows up
- **Dyspatch features:**
  - theme logo (`DYS.theme.logo`)
  - variants, and variants and mirror layout switched on for common components
  - dark-mode styles, and the theme's **Lock Light Mode in Gmail** setting
  - `editable` and editable groups, `show`, partials and includes, `dys-repeat` and conditionals
  - block-level localization, when your account localizes

It asks only what you didn't say: which blocks to review, whether to just report or also fix, and the report
format (Markdown, HTML page or PDF). You get one report file in that format.

In fix mode it shows every change before saving, backs up each block and theme first, and never deletes blocks;
at most, it removes unused blocks from a theme. Two things you change in Dyspatch yourself, because the MCP can't:
the Lock Light Mode in Gmail toggle, and block tags.

## Requirements

- The **Dyspatch MCP server** connected in Claude (Dyspatch MCP).
- For previews with images: Claude's network access must allow `*.dyspatch.io` (an org admin sets this under claude.ai
  Admin settings → Capabilities). Previews are rendered with Playwright + Pillow if available.
- For QA link checks: outbound web access from Claude's environment (otherwise the skill gives you a command to
  run them locally). Device previews in Dyspatch use your organization's Litmus quota, so the skill asks before
  running new ones.
- For block reviews: code execution (Python 3.8+), and a Claude client that saves large tool results to a file.
  A whole account's blocks come back as one large response (about 10 KB per block), so in other clients review
  one theme at a time.
- For block optimization: code execution (Python 3.8+), and ideally a Claude client that saves large tool results to
  a file (block data is about 15 KB per block). PDF reports use a local Chrome or Edge (or Playwright); without one
  you get the HTML page to print to PDF.
