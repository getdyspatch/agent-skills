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

## Requirements

- The **Dyspatch MCP server** connected in Claude (Dyspatch MCP).
- For previews with images: Claude's network access must allow `*.dyspatch.io` (an org admin sets this under claude.ai
  Admin settings → Capabilities). Previews are rendered with Playwright + Pillow if available.
