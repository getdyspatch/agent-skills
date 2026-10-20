## Packaging and releases

`dyspatch.plugin` is a zip of this folder's contents (excluding this file). It is
built automatically by git hooks. Enable them once per clone:

```sh
git config core.hooksPath .githooks
```

- **pre-commit**: when files in this folder are staged, rebuilds `dyspatch.plugin`
  from the staged content and adds it to the commit.
- **post-commit**: when `version` in `.claude-plugin/plugin.json` has no release tag
  yet, creates an annotated tag `dyspatch-plugin-v<version>`.

To cut a release, bump `version` in `.claude-plugin/plugin.json`, commit, then
`git push --follow-tags`. Pushing the tag runs the `Release plugin` GitHub Action,
which publishes a GitHub Release with `dyspatch-<version>.plugin` attached.

To build the package manually: `scripts/build-plugin.sh [output-path]`.
