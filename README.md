# Dyspatch Agent Skills

Agent skills for [Dyspatch](https://www.dyspatch.io), packaged as a Claude plugin. The skills are built to make
the best use of the Dyspatch MCP server: they call its tools by name, keep calls few and parallel, and confirm before
they change anything in your account.

**Download:** [the latest `dyspatch.plugin`](https://github.com/getdyspatch/agent-skills/releases/latest/download/dyspatch.plugin).
Earlier versions and release notes are on the [GitHub releases page](https://github.com/getdyspatch/agent-skills/releases).

## The Dyspatch plugin

The plugin lives in [`dyspatch-claude-plugin/`](dyspatch-claude-plugin/). It contains three skills:

| Skill | What it does |
|---|---|
| `/dyspatch:create-email` | Builds a new email in Dyspatch from a Word or PDF brief, a Figma frame, a screenshot, pasted copy or a one-line idea, using your existing workspaces, themes, blocks, brand guidelines and image library. It handles personalization, subject and preheader, translations, guardrail fixes and plain text, and can submit the email for approval. |
| `/dyspatch:email-qa-checklist` | Runs a QA and proofing pass over an existing email: guardrails, links and images, spelling, accessibility, brand, personalization, localization, performance, compliance and your campaign brief. It reports findings by severity and can post them as comments in Dyspatch or apply fixes once you approve them. |
| `/dyspatch:review-block-overrides` | Audits your blocks for hardcoded colours, fonts and borders that override your themes and stop blocks working across themes. It also flags blocks that aren't in any theme or are only in archived themes. Read-only. |

You don't have to type the skill name. Asking Claude to "build an email from this brief", "QA my spring sale email"
or "which blocks have hardcoded styles?" picks the right skill. See the
[plugin README](dyspatch-claude-plugin/README.md) for full details of each skill.

### Requirements

- A Claude plan with plugins.
- The **Dyspatch MCP server** connected in Claude. The skills don't work without it.
- A Dyspatch account. The skills can only do what your Dyspatch user is allowed to do.
- Code execution turned on in Claude, for the bundled scripts (previews, link checks, block audits).

## Install in Claude Desktop or Claude on the web

Plugins are shared between Claude on the web, the Claude Desktop app and Cowork, so you only install once.

### 1. Add the plugin

1. Download [the latest `dyspatch.plugin`](https://github.com/getdyspatch/agent-skills/releases/latest/download/dyspatch.plugin).
2. In Claude (web or Desktop), go to **Customize → Plugins**
   ([claude.ai/customize/plugins](https://claude.ai/customize/plugins)).
3. Click **Add → Upload plugin** and choose the `.plugin` file.

To update, upload the newer `.plugin` file the same way.

### 2. Use it

With the Dyspatch MCP server connected, start a new chat (or a Cowork task) and ask for what you need, or type `/` and pick a `dyspatch:` skill.

### Installing for a whole organization (Team and Enterprise)

An Owner can make the plugin available to everyone:

1. Go to **Organization settings → Plugins & skills**
   ([claude.ai/admin-settings/skills](https://claude.ai/admin-settings/skills)).
2. Click **Add → Upload plugin** and choose the `.plugin` file.
3. Set its access: **Available to install**, **Installed by default** or **Required**. On Enterprise, you can also
   limit it to certain groups.

If members can't upload or use plugins, check that Skills are turned on in your organization's settings.

## Development

See [`dyspatch-claude-plugin/README-DEV.md`](dyspatch-claude-plugin/README-DEV.md) for how the package is built and
how releases are cut.
