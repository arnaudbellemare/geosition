## SEO / GEO PR checklist

- [ ] **Intent**: one clear user/search intent addressed (no thin duplicates).
- [ ] **Evidence**: issue ID in `seo/audit-issues.json` or changelog note in `seo/CHANGELOG.md`.
- [ ] **Rollback**: documented (revert SHA, flag, or redirect).
- [ ] **Locales**: if FR/EN, `seo/representative-urls.json` updated if URLs changed.
- [ ] **Risk**: `geo_scaled_content_risk` assessed for large content adds.
- [ ] **Verification**: `npm run seo:verify` passes locally.
- [ ] **Metrics**: no fabricated numbers in PR description — cite GSC/export paths only.
