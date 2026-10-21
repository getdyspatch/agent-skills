# Built-in email QA checklist

The default checks, by section. Each item has a default severity:

- **Blocker**: the email shouldn't go out until it's fixed (broken or placeholder links, lorem ipsum, a missing
  unsubscribe, a variable that will render blank or raw, a guardrail ERROR).
- **Warning**: worth fixing before send, but a human may reasonably accept it (a weak subject line, a missing UTM,
  alt text that just repeats the filename).
- **FYI**: no action required, but the reviewer should know (an off-domain link, a redirect, a style preference).

Use judgment: raise or lower a severity when the context clearly calls for it, and say why. A custom checklist
item from the user is a Warning unless the user marked it otherwise or its wording makes it a must ("must", "never",
"required", "legal").

Section keys (used in the preferences file): `guardrails`, `links_images`, `content`, `accessibility`, `brand`,
`personalization`, `localization`, `performance`, `technical`, `compliance`, `campaign`, `custom`.

## Contents
1. Guardrails
2. Links & Images
3. Content
4. Accessibility
5. Brand
6. Personalization
7. Localization
8. Performance
9. Technical
10. Compliance & Deliverability
11. Campaign (only with a brief)
12. Custom (the user's own list)

---

## 1. Guardrails (`guardrails`)

Dyspatch's own checks, run first. Every non-SUCCESS item is reported in the section it belongs to (an ALT_TEXT item
goes under Accessibility, URLS_ARE_SECURE_AND_VALID under Links), tagged "guardrail".

| check | default |
|---|---|
| Any guardrail at level ERROR | Blocker |
| Any guardrail at level WARNING | Warning (except the known false positive below) |
| SUBJECT_IS_VALID flagging a short personalized subject as too long | FYI (known false positive) |
| INTEGRATION_EXPORT_IS_VALID failing | Blocker, but needs account config, not an email edit. Say so. |
| A guardrail that passed but is wrong (unsubscribe check passing with no link; link check passing `#…` hrefs) | Report the underlying issue at its own severity, and note that Dyspatch's check passed it |
| Items for a section the user switched off | Still listed briefly under Guardrails |

## 2. Links & Images (`links_images`)

| check | default |
|---|---|
| Placeholder link or image (Links Review / `LINK_IS_PLACEHOLDER`, `#`, `example.com`, `href` left at a block default) | Blocker |
| Fragment-only link (`#download`, `?utm…#explore`) on a CTA or nav link: goes nowhere in an inbox, and Links Review doesn't flag it | Blocker |
| Test or junk parameters appended to every link (`custom123=bob`, `test=1`), usually from workspace link settings | Warning (fix in workspace settings) |
| Invalid link (`LINK_IS_INVALID`, malformed URL, `http://` where https exists) | Blocker for malformed, Warning for http |
| Link or image doesn't return 2xx (HTTP check) | Blocker for 4xx/5xx, Warning for timeouts, FYI for redirects |
| An image URL that serves something other than an image | Blocker |
| Link or image host outside the owned domains (Dyspatch's CDN always counts as owned) | FYI. List the hosts once rather than per link. |
| The theme logo resolving to Dyspatch's grey placeholder logo | Blocker |
| `mailto:` / `tel:` links: well-formed address or number | Warning if malformed |
| The same CTA label pointing to different URLs (or two different CTAs sharing one URL by mistake) | Warning |
| Image dimensions wildly off the slot (a 2000px-wide image squeezed into a 600px email is fine; a stretched aspect ratio isn't) | Warning |
| Very heavy images (over ~1 MB each) | Warning (also a Performance item) |

## 3. Content (`content`)

| check | default |
|---|---|
| Spelling errors in the user's locale (subject, preheader, body, alt text, button labels, plain text) | Blocker for the subject, preheader, headline and CTAs; Warning elsewhere |
| Grammar and punctuation errors | Warning |
| Locale consistency (US vs UK spelling mixed, e.g. "color" and "colour") | Warning |
| Lorem ipsum, "Sed congue ante", "Button", "Headline here", "[INSERT …]", "TBD", "XX%", "TK" | Blocker |
| Dates, days of the week and prices that disagree with each other ("ends Monday, March 3" when March 3 is a Tuesday) | Blocker |
| Stale content relative to today: a past year in a headline ("best of 2023"), a past event, an expired offer, the wrong season or holiday | Blocker |
| Plain-text version missing, auto-generated from stale copy, or missing CTAs/URLs present in the HTML | Warning |
| Repeated words, double spaces, inconsistent capitalization of the same CTA or product name | FYI |
| Inconsistent product, feature or brand naming | Warning |

Proper nouns, brand and product names, URLs and variable names aren't spelling errors. Check the brand guideline
and the theme for the official spellings before flagging them.

## 4. Accessibility (`accessibility`)

| check | default |
|---|---|
| Image without alt text that carries meaning (hero, product, text-in-image) | Blocker |
| Alt text that's just a filename, "image", "logo.png" or "hero" | Warning |
| Decorative image (spacer, divider) with descriptive alt text instead of `alt=""` | FYI |
| Key message only in an image (images off = no message) | Warning |
| Vague link text ("click here", "learn more" repeated with different destinations) | Warning |
| Body text smaller than 14px, or low contrast between text and background (WCAG AA 4.5:1) | Warning |
| Heading structure skips around or uses headings for styling only | FYI |
| `lang` attribute missing or wrong for the locale in the rendered HTML | FYI |

## 5. Brand (`brand`)

| check | default |
|---|---|
| The theme isn't the expected one for the workspace / brand / email type (compare with similar emails) | Warning |
| Logo isn't the brand's real logo, or is outdated, stretched or on the wrong background | Blocker for a placeholder logo, Warning otherwise |
| Colors or fonts overridden in blocks so they no longer match the theme | Warning |
| Theme archived, or not assigned to the email's workspace | Warning |
| Copy off the brand guideline's tone, personality or audience (or off the house style in the user's custom checklist) | Warning, quoting the line and the guideline trait |
| Brand or product name misspelled or styled wrong | Blocker |

Brand guidelines in Dyspatch hold a description, audience, tone and personality (no word lists). Judge copy against those, and quote the specific
line and trait when flagging ("'Grab it before it's gone!!!' feels pushy against the guideline's 'calm, expert'
tone"). Don't flag copy for not matching your own taste.

## 6. Personalization (`personalization`)

| check | default |
|---|---|
| Dyspatch variable syntax broken (`@{first_name` unclosed, `@{ first name }`, `{first_name}`, `@first_name`) | Blocker |
| Fallback missing on a variable that can be empty (`@{first_name}` in a greeting without `default("…")`) | Warning |
| Colon-style fallback `default:"x"` instead of `default("x")` | Warning (works in the subject, fails in blocks) |
| Variable used in the email but missing from the preview data, or with a name not seen in other emails | Warning: possibly a typo or a field that doesn't exist |
| ESP-specific code (Liquid `{{ }}`, `{% %}`, AMPscript `%%[ ]%%`, merge tags `*|FNAME|*`) outside a raw/ESP-tagged element, or for a different ESP than the workspace exports to | Blocker |
| Conditional logic that's always true or always false, contradicts itself, compares to the wrong type (`tier == Gold` unquoted), or leaves a gap (no content for any branch some recipients fall into) | Blocker for a broken expression, Warning for a coverage gap |
| Overlapping conditionals that would show two versions of the same block to one recipient | Warning |
| Personalized copy that reads badly with the fallback ("Hi there, your there account") | Warning |

For each conditional, write out its expression in plain words and list which audience segments see it, so the
reviewer can confirm the intent.

## 7. Localization (`localization`)

Skip this section when the email has one language and nothing (brief, workspace, campaign, user) says it needs more.

| check | default |
|---|---|
| A required locale is missing (from the brief, the user, the workspace's other emails, or a locale group) | Blocker |
| A locale exists but has untranslated keys (LOCALES_TRANSLATED warning, or source text in the mapping) | Warning |
| Translation defects: `&#39;` in plain fields, mangled brand names, the space dropped before `@{var}`, truncation, moved link boundaries, fallback text left in the source language | Warning |
| Spelling or grammar errors in a translation | Warning |
| Dates, currencies, number formats not localized (`$` in a fr-FR email, MM/DD in en-GB) | Warning |
| Translated copy overflowing its slot (much longer than the source in a fixed-width button) | FYI |

## 8. Performance (`performance`)

Subjective by nature. Explain the reasoning and offer an alternative; don't just score.

| check | default |
|---|---|
| Subject line: length (≈40–60 chars), clarity, specificity, curiosity or benefit, fit with the audience | Warning if weak. Suggest 2–3 alternatives. |
| Preheader: adds to the subject rather than repeating it; isn't "View in browser" or leftover body copy | Warning |
| Hero and primary CTA above the fold (roughly the first 500px on mobile, 600px on desktop) | Warning |
| One clear primary CTA; secondary CTAs visually subordinate | Warning |
| UTM parameters set at the workspace or email level | Warning if none |
| Primary CTAs carry campaign-specific UTMs (`utm_campaign`, `utm_content` per CTA) rather than generic ones | Warning |
| Mobile: responsive layout, stacking columns, tap targets ≥ 44px, no tiny text | Warning |
| Total email size under ~100 KB of HTML (Gmail clips at 102 KB) | Warning, Blocker if clipped above the unsubscribe |
| Image-to-text balance (an email that's one big image) | Warning |

## 9. Technical (`technical`)

| check | default |
|---|---|
| Device / client previews render without broken layout, overlapping text or missing images | Blocker for broken layout, Warning for minor issues |
| Images stretched or squashed (aspect ratio of the source differs from the rendered size) | Warning |
| Images not sharp on high-res screens (natural width under ~2× the displayed width) | FYI |
| Draft state a reviewer should know: not approved, a newer draft or live version exists, a test-looking name | FYI, in the report header |
| Placeholder or sample content anywhere (also see Content) | Blocker |
| Dark-mode issues visible in previews (black logo on dark background, invisible text) | Warning |
| Empty blocks or hidden slots leaving visible gaps | Warning |
| Raw/custom HTML blocks with unclosed tags or scripts | Blocker |

## 10. Compliance & Deliverability (`compliance`)

| check | default |
|---|---|
| Unsubscribe link present (marketing email), going somewhere real (not `#…` or a placeholder), checked on the link itself rather than via the guardrail | Blocker |
| Physical mailing address / legal footer present (marketing email) | Blocker |
| Sender name and address set, on a real domain, consistent with the brand | Blocker if missing |
| Reply-to set when the email invites replies | Warning |
| Spam-trigger words or patterns (SPAM_WORDS guardrail, ALL CAPS, `!!!`, "100% free") | Warning |
| Required disclaimers for offers (terms, expiry, eligibility) present when the email makes an offer | Warning |
| Transactional emails: no promotional content that would make them marketing under CAN-SPAM/CASL | Warning |

Transactional emails (password reset, receipt) don't need an unsubscribe. Don't flag that as a Blocker for them.

## 11. Campaign (`campaign`, only with a brief)

| check | default |
|---|---|
| Every must-have from the brief is present: key message, offer, CTA wording, dates, legal lines, products | Blocker if missing |
| CTA wording and destination URLs match the brief | Blocker if a URL differs, Warning if wording differs |
| UTMs reflect the brief: `utm_campaign` matches the campaign name/code, `utm_source`/`utm_medium` follow the convention used in the brief or the workspace defaults | Warning |
| Personalization or conditionals the brief calls for are present and target the audience it names | Blocker if missing |
| Subject and preheader follow the brief (if it gives them or gives direction) | Warning |
| Audience, tone and goal: the email's copy matches the brief's audience and objective | Warning |
| Send date, sender or locale in the brief that conflicts with the email | Warning |
| Anything in the email that contradicts the brief (a different discount, an extra product, a different date) | Blocker |

Quote the brief line next to each finding so the reviewer can see both.

## 12. Custom (`custom`)

Each item from the user's own checklist becomes one finding (pass or fail), reported under the most fitting
section above and tagged "custom". If a custom item duplicates a built-in check, report it once and tag it with
both. If a custom item can't be checked with the available tools (for example "tested in Litmus"), report it as
"Needs manual check" rather than guessing.
