# CTAN candidate 0.8.0 — 2026-09-05

The candidate uses package version 0.8.0 and date 2026-09-05 throughout the
manual, READMEs, citation metadata and change record. It is a pre-1.0 release
with a breaking migration from the retired front ends, not a compatibility
freeze. The semantic event contract stays at 1.3; no event behavior changes
in this preparation.

The upload includes `tenkz.pdf` and the current manual sources under `doc/`.
The CTAN check rebuilds the manual from the unpacked archive, verifies the
runtime in a clean installation and compiles eight offline examples across
six picture classes. The inactive release campaign has been removed.

## Final validation

Build from the clean candidate commit using `RELEASE-POLICY.md` section 2.
Record the commit and archive SHA-256 with the results outside the archive
(the archive cannot contain its own digest). The ordinary CI checks, isolated
reproducible manual build and `tenkz_ctan.py check --require-smoke` must pass.
Review the rendered manual before approving publication.

The inherited benchmark ledger has 114 faithful cases, 12 cosmetic gaps and
four deferred structural gaps. The old full-review fingerprint is stale;
these are per-case verdicts, not a fresh visual review of the entire corpus.
The manual retains repeated-topology audit advisories. The cover labels
and two tutorial annotations have been adjusted for legibility. No diagram capability is added
solely to eliminate these acknowledged limitations.

The `wind` projection does not reliably draw transverse torus basis cycles.
The manual uses an explicitly labeled fundamental-square schematic; the
renderer limitation is tracked in [#301](https://github.com/LionSR/tenkz/issues/301).

## Publication

The complete announcement is in `../ANNOUNCEMENT.md`; the upload form values
are in `UPLOAD-CHECKLIST.md`. After final maintainer approval, create the
annotated `tenkz-v0.8.0` tag and submit the checked archive. Record the actual
CTAN response and verify TeX Live/MiKTeX inclusion separately. A valid local
archive does not establish CTAN acceptance or distribution availability.

CTAN requires PDF documentation with sources, README/license information and
a meaningful version. A TDS zip is optional. Name availability was checked on
2026-09-05; a missing catalogue entry is not a reservation.

- [Upload preparation](https://ctan.org/help/upload-pkg)
- [Upload addendum](https://ctan.org/file/help/ctan/CTAN-upload-addendum)
- [Upload form](https://ctan.org/upload/)
