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

## Requirements

- The **Dyspatch MCP server** connected in Claude (Dyspatch MCP).
- For previews with images: Claude's network access must allow `*.dyspatch.io` (an org admin sets this under claude.ai
  Admin settings → Capabilities). Previews are rendered with Playwright + Pillow if available.
- For QA link checks: outbound web access from Claude's environment (otherwise the skill gives you a command to
  run them locally). Device previews in Dyspatch use your organization's Litmus quota, so the skill asks before
  running new ones.
