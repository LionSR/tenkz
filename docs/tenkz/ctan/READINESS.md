# CTAN readiness assessment — 2026-09-05

The runtime archive builds and installs successfully. It is not yet ready to
submit: the archive omits the documentation sources, and release metadata still
needs a deliberate preparation change. No new diagram capability is required
by the CTAN upload requirements checked here.

## Verified locally

- The full 130-target RMP compile, lint, and audit passed at `fcbea38`; this
  stabilization change does not modify runtime TeX or benchmark cases.
- The manual built twice to identical bytes (276,525 bytes), with no hard
  audit errors and six advisories. Two advisories concern author-selected
  label stations on the cover channel; four concern repeated topology.
  The cover was inspected, but this is not a complete fresh visual review.
- All 60 CTAN staging regression tests passed.
- `python3 scripts/tenkz_ctan.py check --require-smoke` passed: 17 runtime
  files resolved from the unpacked archive; the clean-install example and
  eight offline cases over six picture classes compiled and audited.
- The inspection archive is `build/ctan-assessment/tenkz-0.7.zip`, SHA-256
  `363ae779d253f68fc3facead255a4f4daeba2803c7dfd0c41300a062c097ed02`.
  It contains 23 files plus its directory entry; `tenkz.pdf` is present,
  but the manual TeX sources are absent. This is an assessment artifact,
  not an approved release.
- The CTAN package JSON lookup for `tenkz` returned HTTP 404 on this date.
  That is not a name reservation or acceptance decision.

## Remaining work

1. **Include rebuildable documentation sources.** Add the manual entry point,
   style, chapters, and all source dependencies to the upload layout; verify
   that the manual rebuilds from the unpacked upload without the repository.
   Keep the runtime usable as a flat arXiv submission. The existing staging
   check does not test documentation-source completeness.
2. **Prepare one coherent release.** Choose the package version and date and
   synchronize the manual, READMEs, citations, changelog, and announcement.
   Currently the package/manual say 0.7 while the changelog describes 1.0.
   Review the manual advisories and disclose benchmark limitations. A pre-1.0
   CTAN release is an option; there is no need to promise 1.0 to upload.
3. **Review and submit the final artifact.** Rebuild and validate the chosen
   commit, obtain maintainer approval, tag it, and submit the complete archive
   through CTAN's form. Respond to CTAN review and verify distribution inclusion
   separately; neither timing nor acceptance is established by our checks.

## External requirements checked

CTAN asks for an archive, README and license information, a meaningful version,
and PDF documentation with its source. Its preferred layout is browsable and
usually flat; a TDS zip is optional. Our unactivated signing and evidence campaign
was a repository policy, not a CTAN prerequisite.

- [Upload preparation](https://ctan.org/help/upload-pkg)
- [Upload addendum](https://ctan.org/file/help/ctan/CTAN-upload-addendum)
- [Upload form and metadata](https://ctan.org/upload/)
- [CTAN Apache-2.0 entry](https://ctan.org/license/apache2)
