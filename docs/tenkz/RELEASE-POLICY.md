# Releasing tenkz

`DESIGN.md` owns compatibility. This checklist owns release preparation and
publication; `ctan/UPLOAD-CHECKLIST.md` contains CTAN-specific instructions.
A first CTAN release may use a pre-1.0 version. CTAN availability and the 1.0
compatibility promise are separate decisions.

## 1. Choose the release scope

Review the diagrams used in real blueprint work. Resolve demonstrated defects
in the supported scope and record remaining limitations. Benchmark verdicts
remain honest: cosmetic or explicitly deferred structural gaps do not require
new kernel capabilities just to reach zero. The full corpus must still compile
and pass its automated audits. A no-change simplification review is valid.

## 2. Validate the candidate

Use a clean checkout of the exact candidate commit. The following standing
checks must pass. Run relevant tests locally and use the applicable CI results
at that commit; a later change requires revalidation of affected evidence.

| Gate | Command | Where it runs |
|---|---|---|
| registry and language check | `python3 scripts/tenkz_language.py check` | `pr-ci.yml`, `tenkz-shrink` |
| shrink ratchet | `python3 scripts/tenkz_shrink.py gate` (+ `test_tenkz_shrink.py`) | `pr-ci.yml`, `tenkz-shrink` |
| corpus compile and event parity | `scripts/tenkz_corpus.sh`; `scripts/tenkz_golden.sh --check` | `pr-ci.yml`, `tenkz-corpus` |
| kernel and string probes | `scripts/tenkz_kernel_probes.sh`; `scripts/tenkz_string_probes.sh` | `pr-ci.yml`, `tenkz-corpus` |
| corpus provenance, dimensions, render | `test_tenkz_corpus_provenance.py`, `test_tenkz_dimension_inventory.py`, `test_tenkz_corpus_render.py` | `pr-ci.yml`, `tenkz-corpus` |
| manual doc-test | `python3 scripts/tenkz_manual_doctest.py` | `pr-ci.yml`, `tenkz-corpus` |
| manual compile and event audit | `python3 scripts/tenkz_manual_build.py check --require-engine` (two isolated builds, each compiled until rerun warnings stop) | `pr-ci.yml` (`tenkz-corpus`), `tenkz-release-policy.yml` |
| picture-source lint and shared parsers | `python3 scripts/tenkz_lint.py --census`; `test_tnlog.py`, `test_texcase.py`, `test_tenkz_kernel_audit.py` | `pr-ci.yml` (`tenkz-corpus`) |
| CTAN staging tree and archive | `python3 scripts/tenkz_ctan.py check` (+ `test_tenkz_ctan.py`) | `tenkz-release-policy.yml`; `pr-ci.yml`, `tenkz-corpus` runs it with `--require-smoke` |
| migration guard | `python3 scripts/test_check_tenkz_dispositions.py`; `python3 scripts/check_tenkz_dispositions.py` | `tenkz-dispositions.yml` (`scan`) |
| version, reference, and event compatibility assertions | `python3 scripts/test_check_tenkz_policy.py`; `python3 scripts/check_tenkz_policy.py` | `tenkz-policy.yml` |

Review changed figures against their mathematical sources. Visual claims name
the rendered file, DPI, and what was checked; ink-moving changes retain an
independent second view. Automated audits establish their documented structural
checks, not the truth of an asserted identity. A stale full-review fingerprint
must be disclosed; per-case verdicts are not a new full visual review.

## 3. Prepare the release

The version declaration in `tex/tenkz/tenkz.sty` owns the package version and
date. A release-preparation change updates the manual, change record, README
and citation metadata consistently. `TNLOG.md` states its own event version;
only change that version when the event contract changes.

Build the manual reproducibly, then run `python3 scripts/tenkz_ctan.py check --require-smoke` and `python3 scripts/tenkz_ctan.py sync`. The archive must
include the manual PDF and the sources needed to rebuild it. Record the tested
commit, archive SHA-256, checks and visual evidence, and known limitations in
the release notes. A separate campaign manifest is unnecessary.

## 4. Publish after maintainer approval

The maintainer explicitly approves the final commit and archive, creates its
annotated `tenkz-vMAJOR.MINOR.PATCH` tag, and submits the archive through CTAN's
upload form. Never move or reuse a release tag. Follow up on CTAN's response
and check distribution inclusion separately. Local checks do not imply CTAN
acceptance or immediate availability in TeX Live or MiKTeX.

No fixed soak, work-record quota, activation PR, dedicated publisher, secret
inventory, or cryptographic tag-object protocol is required. The former inactive
campaign is retired; its history remains available through `SOAK-1.0.md`.
