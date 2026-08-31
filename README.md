# tenkz

Tensor-network diagrams from a description of the network.

tenkz is a LaTeX package that draws matrix product states, tensor trains,
PEPS sheets, string diagrams, and channel sandwiches from a statement of
what the network is. An author writes down the tensors, their indices, and
how the indices meet; the drawing measures where the ink goes. No
coordinates and no lengths appear in a picture source.

This repository is the package, its manual, regression corpus, and release
tools. It was extracted from [TNLean](https://github.com/LionSR/TNLean),
which still consumes the package to render blueprint pictures.

```latex
\begin{tenkz}[cols=2]
  \tn[ports={180:virtual:$\alpha$, 90:physical:$i_1$}]{A} &
  \tn[ports={0:virtual:$\beta$, 90:physical:$i_2$}]{B}
\end{tenkz}
```

The two tensors are chained by `&`, the bond between them is drawn because
their adjacent index slots meet, and the open indices are the ones the
source names.

While drawing, tenkz writes an event stream recording the structure it
resolved. Checking tools read that stream to confirm that a printed picture
and the contraction it claims to show agree.

## Requirements

- LaTeX2e with expl3 (TeX Live 2023 or later)
- pgf/TikZ
- `hobby` and `spath3` (separate CTAN packages; missing either fails at load)

The corpus, manual, and reference figures are built with XeTeX.

## Build

```sh
# Language registry and shrink ratchet
python3 scripts/tenkz_language.py check
python3 scripts/tenkz_shrink.py gate --base-ref origin/main

# Regression corpus and golden event streams
scripts/tenkz_corpus.sh
scripts/tenkz_golden.sh --check

# Compact manual: examples doctested, then a reproducible build
python3 scripts/tenkz_manual_doctest.py
python3 scripts/tenkz_manual_build.py check --require-engine
```

Operational detail lives in [`docs/tenkz/HACKING.md`](docs/tenkz/HACKING.md).
The public language is [`docs/tenkz/LANGUAGE.md`](docs/tenkz/LANGUAGE.md).

## Installation

Put the files under `tex/tenkz/` on `TEXINPUTS`, or in a local texmf tree
under `tex/latex/tenkz/`. Then `\usepackage{tenkz}` binds the `tenkz` and
`tenkzeq` environments.

A CTAN staging archive is built by `python3 scripts/tenkz_ctan.py archive`.

## Issues

Open package work here. Open issues were transferred from TNLean at the
split; the old TNLean URLs redirect. One TNLean issue remains because it
edits blueprint sources, not this package:
[LionSR/TNLean#5693](https://github.com/LionSR/TNLean/issues/5693).

The library tracker is [#10](https://github.com/LionSR/tenkz/issues/10).
Issue numbers cited in `DESIGN.md` / `SOAK-1.0.md` are the original TNLean
numbers and still resolve through those redirects.

## License

Apache License, Version 2.0. See [`LICENSE`](LICENSE).

## Version

Version 0.7, released 2026-07-22. The change record is
[`docs/tenkz/CHANGES.md`](docs/tenkz/CHANGES.md).
