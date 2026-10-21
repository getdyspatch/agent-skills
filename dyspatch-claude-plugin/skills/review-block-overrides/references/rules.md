# Override rules

The same rules `scripts/audit_blocks.py` applies. Use them to review by hand when code execution isn't available.
Manual review is slower and less reliable, so review one theme at a time (`get_blocks {themeId}`), batch blocks,
and say in the report that it was done by hand.

## Flag a value when all three are true

1. **It's a visual property a theme controls:**
   - Colour: `color`, `background`, `background-color`, `background-url`, `background-image`, `container-background-color`, `inner-background-color`, `border-color` and its per-side variants
   - Typography: `font-family`, `font-size`, `font-weight`, `font-style`, `line-height`, `letter-spacing`, `text-decoration`, `text-transform`
   - Border: `border`, `border-top`/`-right`/`-bottom`/`-left`, `border-width`, `border-style`, `border-radius`
   - Optional (only if the user asks): `padding*`, `margin*`, `inner-padding`
2. **It's set in the block**, in one of these places:
   - as an attribute on a `dys-*` element, e.g. `<dys-text color='#FFF'>`
   - as `color` on a link, e.g. `<a color='#777777'>`, or as a legacy `bgcolor` on any element
   - in inline `style=""` on any element
   - in a CSS rule inside `<dys-style>`, including inside `@media`. Note any `!important`.
3. **It's a fixed value.** These are not flagged:
   - variables such as `@{brand.primary}` or `{{...}}`
   - `transparent`, `inherit`, `initial`, `unset`

## Never flag
- Anything inside `<!-- -->` or `<dys-comment>`
- Width, height, alignment, `show`, `editable*`, `css-class`
- Button/pill `variant`, which selects a theme style rather than overriding one
- `border='0'` on a raw `<table>`, which is a reset

## Theme notes per block
From each block's `themes[]` in `get_blocks`, and the active themes in `get_themes_with_block_ids`:
- `themes[]` is empty → "Not assigned to any theme"
- `themes[]` isn't empty, but none of its IDs is an active theme → "Only in archived themes"

## Links
Link every block name to `https://app.dyspatch.io/block/base/<block_id>/code`.
