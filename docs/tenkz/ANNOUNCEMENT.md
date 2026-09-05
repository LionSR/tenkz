# tenkz 0.8.0 — prepared announcement

Prepared for the first CTAN submission, dated 2026-09-05. Publication is
pending final maintainer approval and CTAN acceptance.

## Announcement text

tenkz is a LaTeX package for drawing tensor-network diagrams from a description
of tensors, indices and connections. It supports matrix product states, PEPS
sheets, string diagrams and channel diagrams through a common TikZ-based
language. Common networks use declared frames and addresses; irregular figures
may require relative placement and authored routes.

Version 0.8.0 brings the unified kernel language to the first CTAN candidate.
It replaces the older front ends with one vocabulary for atoms, wires and
marks. This is a breaking pre-1.0 release; migration instructions are included.
The equation audit checks compatible boundary signatures, while mathematical
identities remain the author's responsibility.

The upload includes a PDF manual and its rebuildable LaTeX sources. Runtime
dependencies are a current LaTeX installation, pgf/TikZ, hobby and spath3.
The package and documentation are distributed under Apache License 2.0.

Project and manual sources: https://github.com/LionSR/tenkz
Bug reports: https://github.com/LionSR/tenkz/issues

## Release notes

The 1.0 compatibility freeze is not claimed. The semantic event format remains
1.3 and does not provide in-band version negotiation. The benchmark ledger
records 114 faithful cases, 12 cosmetic gaps and four deferred structural gaps;
the prior full-review fingerprint is stale. Authored routes and label stations
can need adjustment. The manual has repeated-topology audit advisories.

The final release record must attach the tested commit, archive SHA-256,
validation results and visual-review evidence before publication. CTAN and
GitHub release URLs are recorded after the corresponding publication succeeds.

The projected `wind` renderer does not reliably depict torus basis cycles;
see [#301](https://github.com/LionSR/tenkz/issues/301). The manual teaches the
quotient construction with an explicitly labeled TikZ schematic.
