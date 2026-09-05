# Hacking on tenkz

`LANGUAGE.md` is the short public semantic contract and `LANGUAGE-1.0.md`
the binding inventory.  `ARCHITECTURE.md` owns the internal pipeline.  This file is the operational checklist for changing and
debugging the package.

## Fast build loop

Compile a standalone example from its own directory.  Keep the timeout: an
expl3 loop over an expanded `\q_no_value` otherwise looks like a slow run.

```sh
timeout 120 env TEXINPUTS="<repo>/tex/tenkz//:" \
  xelatex -interaction=nonstopmode -halt-on-error <file>.tex
```

Build the compact manual until contents, references, and tables settle:

```sh
python3 scripts/tenkz_manual_doctest.py
python3 scripts/tenkz_manual_build.py build --require-engine
```

The release build is
`python3 scripts/tenkz_manual_build.py check --require-engine`: two
isolated copies of the manual's sources, each compiled until the engine stops
requesting a rerun (at least two and at most six passes) under a
`SOURCE_DATE_EPOCH` read from `tenkz.sty`'s `\ProvidesPackage` date, the event
stream audited, and the two PDFs required to agree byte for byte
before one is installed at `output/pdf/tenkz-manual.pdf`.  The title-page
date must name the package's month and year or the build refuses.  CI runs
it on every change and uploads the PDF as the `tenkz-manual` artifact.

The generated language reference is
`chapters2/generated-language-reference.tex`.  Regenerate it from the
executable registry at `tex/tenkz/tenkz-language-registry.tex`; parser-facing
language code lives in `tex/tenkz/tenkz-language.code.tex`.  Do not edit the
generated file as an independent vocabulary list.  The manual has a short
fallback so a clean pre-generation checkout still compiles.

The RMP book has a separate driver and interface:

```sh
python3 scripts/tenkz_rmp.py check --id <target>
python3 scripts/tenkz_rmp.py check --section <section>
python3 scripts/tenkz_rmp.py check --all
python3 scripts/tenkz_rmp.py book --all
python3 scripts/tenkz_rmp.py render --all
python3 scripts/tenkz_rmp.py compare --all \
  --source-root References/RMP_TIKZ_SOURCE_CODE
```

Every command works inside a scratch tree that is removed on exit.  Set
`TENKZ_RMP_WORK_ROOT` to a new or empty directory to keep the tree instead,
with each target's compile transcript, event log, and PDF; continuous
integration does this so a failing run's evidence survives for upload.

Every command first runs the corpus-wide physical-dimension ownership check,
even when `check --id` selects one target.  Case dimensions are classified as
metric, projection/frame, route/string, or composition/layout and ratcheted in
`scripts/tenkzlib/dimensions.py`; comment dimensions fail separately.  The two
fixed benchmark-book page-layout files have exact path-specific counts and do
not count as figure geometry.  These core ceilings are aggregate ratchets:
net reductions pass and uncompensated count increases fail.  Exact balanced
replacements and ownership-site moves are rejected by the exact per-occurrence
inventory described below.

The comparison command requires a separate author-source tree supplied through
`--source-root`.  The canonical local home is the gitignored
`References/RMP_TIKZ_SOURCE_CODE/` directory.  It contains the authors'
standalone `ImagesReview Section II` through `ImagesReview Section V` source
drop used to establish the `author_source` and `author_lines` pairings in
`tests/tenkz/rmp/manifest.toml`; the source drop is not redistributed by this
repository.

The four cited section files are identified by
`tests/tenkz/rmp/author-source.sha256`.  `compare` verifies and snapshots those
files before compiling any corpus target, so a missing, edited, or different
source drop fails quickly and later filesystem changes cannot alter the
comparison.  Pairing verdicts are also bound to the author-source identities,
extraction ranges, and canonical paper placement triples (order, line, asset)
by `pairing_sha256` in `tests/tenkz/rmp/verdicts.toml`.
Generated PDFs, auxiliary files, logs, and filesystem metadata are not
provenance: only the section sources cited by the pairing manifest define the
external authority.  A source tree in another local directory is acceptable
only when it matches the committed hashes.

Per-target verdicts are stored in `tests/tenkz/rmp/verdicts.toml`, one
stanza per target.  Any status may be recorded, including failure; the check
rejects lies, never gaps: a stale `case_sha256`, a `faithful` claim without a
second viewer and a verified pairing, or a `blocked` entry that names no
missing capability all fail, while recorded gaps merely appear in the book's
histogram.  A judged verdict pins the SHA-256 of its case; editing the case
stales exactly that verdict.

The ordinary corpus — 6 standalone fixtures in `PROVENANCE.tsv`, 9 files once
the driver adds its three local fixtures — keeps its existing default interface:

```sh
scripts/tenkz_corpus.sh
scripts/tenkz_corpus.sh --render
```

Both suites may share lower-level helpers; neither frontend changes the
other's defaults.

## Golden event streams

The event ledger is `tests/tenkz/golden-events.sha256`.

```sh
scripts/tenkz_golden.sh --check
```

The check recompiles every top-level `tests/tenkz/*.tex` standalone fixture and
requires each `.tnlog` event stream to be byte-identical to the stored SHA-256
baseline.  Nested suites such as `tests/tenkz/kernel/` have their own gates.
Run the command without an argument to take a new snapshot:

```sh
scripts/tenkz_golden.sh
```

Re-pin only when fixture source changes or a reviewed package contract change
intentionally changes the emitted events, and the new streams have been
reviewed as the intended contract.  Behavior-preserving package changes must
pass `--check`; they do not authorize a new baseline.

## Pixel regression

The same-session pixel-pair command (`tenkz_pixelpair.sh`) existed for the
redraw campaign and expired at its close: the S4 surface swap deleted the
last fixtures in its source manifest, and the script with them.  The
exact-toolchain pins in `tests/tenkz/kernel/golden-pixels.sha256` are the
remaining pixel regression gate: after an approved XeTeX, Poppler, font, or
intentional render change, inspect the full-resolution fixtures.  Before
re-pinning, run `scripts/tenkz_kernel_probes.sh --check`: an expected pixel
mismatch is acceptable, but every non-pixel probe must pass, including
structural assertions, sugar-expansion parity, and the event-stream
comparison.  If a separate reviewed contract change intentionally affects a
non-pixel pin, review and update that contract first, then rerun until every
non-pixel probe passes.  Do not snapshot after any non-pixel failure.  Then
re-pin with `scripts/tenkz_kernel_probes.sh --snapshot`, which updates both
the pixel and event ledgers.

## Shrink sessions

The shrink checker reports six meters:

1. public vocabulary census;
2. parser-leaf paths;
3. escape-spelling use in the demand corpus;
4. mean non-comment lines across the 130 RMP cases;
5. aliases and their sunsets;
6. overloaded names, union types, and shared enum words.

```sh
python3 scripts/tenkz_shrink.py meters
python3 scripts/tenkz_shrink.py flags
python3 scripts/tenkz_shrink.py gate --base-ref origin/main
```

When any intentional change alters a computed meter—including a registry,
demand-corpus, or parser-source identity change—compute and review the new
baseline before the gate:

```sh
python3 scripts/tenkz_shrink.py meters > /tmp/tenkz-census-baseline.json
diff -u tests/tenkz/census-baseline.json /tmp/tenkz-census-baseline.json
cp /tmp/tenkz-census-baseline.json tests/tenkz/census-baseline.json
python3 scripts/tenkz_shrink.py gate --base-ref origin/main
```

At the start of a new 0.9 or 1.0 shrink session, advance
`CURRENT_MILESTONE` in `scripts/tenkz_shrink.py` in the same change.  The
`flags` and `gate` actions use that constant to decide which alias sunsets are
due.

The registry's implementation ledgers are `kernel` and `sugar(...)`: kernel
rows are one-in-one-out vocabulary, while sugar rows must expand into kernel
spellings and earn continued use.  The other status words record lifecycle
debt: `alias(...; sunset=...)` reads old sources until its stated rewrite, and
`escape` names raw geometry whose uses count in meter M3.

A retired spelling leaves a tombstone row in the same registry, giving its
scope, the dead spelling, and the migration.  Retiring a word is therefore
one edit: the source lint builds its rejection from those rows and reports
the migration with the finding, and `tenkz_language.py check` requires every
spelling the parser refuses by name to carry a row stating the same
migration, and every row for a word struck from a live alphabet to name a
spelling the parser refuses and the alphabet no longer holds.

Four shapes of row, by what is left of the spelling.  `key=value` is a word
struck from a live key's alphabet, and the parser refuses it through a branch
of that key.  The other three no longer exist at all, so the parser has
nothing to branch on and the unknown-key error or an undefined spelling
answers them; the check is that the registry really has dropped the spelling,
and the lint is what reads the row.  A bare `key` is a retired key.  A
spelling beginning with a backslash is a retired command, takes the scope
`command`, and is matched from its own backslash.  A row under the scope
`environment` is a retired environment, such as the dialects LANGUAGE-1.0
section 10 lists, and is matched where a document names one, in the argument
of `\begin` or `\end`.

Write a multi-word key with `~` as the rest of the registry does and wrap a
long migration; both are read out before any row is compared or matched, so
the spelling a document writes is the spelling that is caught.  A row that
states no spelling is a finding, and one spelling is buried once across the
whole ledger, since the lint reads flat source where no scope is visible.

The gate first compares the pinned meters with the base revision.  M1 total or
kernel growth requires an `Extension-gate: #NNNN` citation, or a
`Census-correction: #NNNN` citation while parser identities are unchanged;
command or environment growth permits only the extension citation.  M2
path-count growth and every parser-leaf identity change, including replacement
or removal, require the extension citation.  M3 or M4 growth requires the
census-correction citation.  M6 component growth also requires a census
correction while parser identities are unchanged.  M5 alias-count growth is
rejected unconditionally, and every alias must have a valid sunset.

After that ratchet passes, a public-census decrease is accepted.  Otherwise,
every raised low-consumer, co-occurrence, lonely-type, sugar-shaped, and due
alias-sunset flag needs a verdict in the latest `docs/tenkz/SHRINK.md` session.
The ledger is append-only: retain the entire pre-change file byte-for-byte as a
prefix and add corrections and verdicts in a new final session section.

A verdict is a table row whose first cell is the exact `flag:*` ID printed by
`flags` (escape an internal table pipe as `\|`).  Its second cell must begin
with one of `keep-because`, `keep`, `dies`, `demoted`, `folds`, `respelled`,
`becomes`, `moves`, `confirmed`, `confirmed merge`, `tombstoned`,
or `sugar preset` and include an unexpired `expiry <milestone>` or `permanent`
lifetime.  The alternative execution form must begin exactly
`executes at the <milestone> freeze`.  Prose outside such a row is not a
machine-readable verdict.

## Stabilization and release

Preserve the documented surface while fixing demonstrated defects. Before 1.0,
an intentional migration updates the contract and consumers together. Use
`RELEASE-POLICY.md` for the release checklist and `DESIGN.md` for compatibility.
The former release campaign and its harness are retired. Ordinary product checks
remain required; `python3 scripts/check_tenkz_policy.py` checks package metadata,
reference coverage, and the declared event reader contract without GitHub access.
A simplification review may conclude that no change is justified.

## Shared parsers

`scripts/tenkzlib/tnlog.py` is the canonical schema-validating parser for
`.tnlog` event streams.  Use it whenever a checker needs structured event
fields.  One narrow regression test still inspects raw lines directly,
`scripts/test_tenkz_peps_torus.py`.
Before changing event syntax, field order, or validation, search every `.tnlog`
consumer and update or migrate these exceptions; do not assume the canonical
parser is their only dependency.
`scripts/tenkzlib/texcase.py` provides shared TeX comment stripping,
balanced-group matching, and picture-construct scanning.  Import these modules
when adding or modifying a checker that needs those answers.
Known local balanced-group parsers remain in
`scripts/tenkz_shrink.py::_group_payload` and
`scripts/tenkz_language.py::_group`; keep both aligned until they migrate to
`texcase.py`.  RMP case-header extraction remains local to
`scripts/tenkz_rmp.py`; do not claim it as shared until it moves into the
library.  Never add another parser for syntax already parsed by
`scripts/tenkzlib/`.

## Stage ownership

Each stage file begins with its declared input, output, owned-state, invariant,
and next-stage contract.

These are normative ownership rules for new code and migration destinations,
not a claim that every historical path has moved.  The live `tenkz-core`,
`tenkz-kernel`, and `tenkz-tree` files still combine
some parsing, geometry, rendering, and event work; direct `\draw`
or `\node` emission in those files remains migration debt.

- `tenkz-model.code.tex` owns normalized semantic records and freezes topology
  after validation.
- `tenkz-metric.code.tex` owns the motivated metric registry and its sole
  dimension accessor.
- `tenkz-geometry.code.tex` owns frames, placement resolution, directions, and
  silhouette support distances; it emits no ink.
- `tenkz-render.code.tex` owns final mark and string emission from frozen
  records and resolved geometry; it parses nothing and stores no topology.
- `tenkz-string.code.tex` owns saved string paths and the crossing, join, and
  gap ledgers consumed by rendering.

The string stage has one further explicit exception: until string/render
integration is complete, string fixtures use the temporary
`\__tenkz_string_dev_draw:nn` primitive in `tenkz-string.code.tex`, which issues
the development `\draw` directly.

Read the header before changing a stage, and keep new state in the stage that
owns its answer.

## Pull-request evidence

Every change under `tex/tenkz/` records both semantic and visual evidence in
the pull-request body:

```sh
scripts/tenkz_golden.sh --check
scripts/tenkz_kernel_probes.sh --check
```

The golden gate proves event-stream parity for the top-level corpus fixtures.
Run the applicable suite-specific semantic gates for affected nested fixtures.
The kernel probes' pixel ledger proves render parity for the kernel suite; a
change that can affect a drawing outside it attaches reviewed replacement
render evidence.  If a reviewed contract or drawing intentionally changes,
state the affected fixtures and attach the reviewed replacement evidence
instead of claiming parity.

The disposition guard validates the migration ledger and reconciles its
inventories against the external Blueprint sources when available and the
top-level `tests/tenkz/*.tex` fixtures.  It runs both
`test_check_tenkz_dispositions.py` and `check_tenkz_dispositions.py` in the
`tenkz-dispositions.yml` workflow.

## Audit and visual review

After compiling, audit the exact event stream used by the rendering and lint
the source:

```sh
python3 scripts/tenkz_audit.py <job>.tnlog
python3 scripts/tenkz_lint.py <source>.tex
```

The external TNLean blueprint is a separate validation scope. Run its current
build and diagram checks from that checkout when a change affects those consumers;
this repository does not contain a blueprint sweep command. Report that scope
separately from the local fixture and RMP results.

Render every affected PDF and inspect it.  Exit status is not visual review.

```sh
mkdir -p tmp/pdfs/tenkz
pdftocairo -png -r 200 -singlefile <file>.pdf \
  tmp/pdfs/tenkz/<name>
```

Inspect labels, clipped ink, crossings, region contours, paired pages, and
section transitions.  A meaningful geometry change requires a fresh render.
Generated PDFs and PNGs are build artifacts, not committed source.

## Source and event checks

- Each figure states `Formula`, `Ink`, `Boundary`, `Source`, and
  `Capabilities` in its source header where the corpus format requires them.
- Structural capability tags name the public construct that owns the picture
  model. Since the S4 surface swap every picture is the kernel surface, so
  a case carries `kernel` whether it spells the retained switch or only the
  `tenkz` environment; the retired `grid` tag is rejected.
- A diagrammatic equation has the intended boundary signature on both sides.
  The equation group is `tenkzeq` and nothing else (`DESIGN.md`, "Equation
  grouping"): inside it a mismatch is a hard finding of both the compiler and
  the audit, while two pictures joined by a bare source `=` raise only the
  advisory that names the pair still to be moved into the scope.
- A matrix keeps two open virtual indices, a doubled-space map keeps four,
  and a scalar keeps none.
- The applied channel is `[sandwich, east={cup=$X$}]`; a west cup feeds the
  adjoint.
- Canonical sources do not use aliases, private control sequences, raw
  `tikzpicture`, whole-figure macros, or undocumented coordinate escapes.
- `\tndeclareatom` declarations have complete typed ports.  There is no
  public `\tndefine` mechanism.

## Architecture checks

Before editing a stage, read its five-line contract.  Maintain the direction

```text
language -> model -> style/atoms -> geometry -> kernel layout -> rendering -> events
```

Validation ends before measurement.  Rendering neither parses user syntax nor
changes topology.  Public names come from the executable registry; private
names follow `\__tenkz_<owner>_...:`.  Unsupported requested ink is a coded
error, never a warning followed by omission.

Since the S4 surface swap the package binds the kernel surface at load;
`r_load_surface.tex` pins that contract, and `KERNEL-LOAD-SWEEP.md` records
the historical pre-swap audit of the once-inert boundary.

## expl3 and PGF traps

These mistakes have shipped bugs here.

1. Never expand `\q_no_value`.  Use the house accessor or a TF form of
   `\prop_get`.
2. Integer factors sit to the right of `*` in `\dimexpr`; prefer
   `\dim_eval:n`.  Do not put a leading decimal factor before a dimension
   macro in a pgfkeys value.
3. Double parameter tokens inside nested inline mappings: `##1` in the body
   of an `\int_step_inline:nnn` defined by another macro.
4. Normalize integer registers with `\int_eval:n` before using them as
   property keys.
5. User-input colons have catcode 12.  String-normalize before parsing
   `rows=`, `ports=`, and similar delimited forms.
6. `\use:e` passes `#` literally; do not double it there.
7. PGF keys split at literal commas and an unbraced value can be truncated at
   a second equals sign.  Brace values containing either character.
8. Expand integer registers explicitly in `\iow` event writes.
9. Picture IDs nest: the global UID and group-local current ID have different
   ownership.  A nested picture must not clobber its parent.
10. `\prop_new:N` builds a flat store: `\prop_get`, `\prop_if_in` and
    `\prop_item` all compare the wanted key against every other key, so a
    store the picture fills costs the square of its size to read.  Declare
    such a store with `\__tenkz_prop_new_indexed:N`, which answers a key in
    one step.  A pair-keyed store — one entry per pair of routes — is the
    worst case and must never be flat.
11. Call sites may alias an argument to the result variable:
    `\__tenkz_kernel_atom_skin_base:nN { \tl_use:N \l__tenkz_kernel_r_c_tl }
    \l__tenkz_kernel_r_c_tl` reads and writes one token list.  Inside such a
    function, read every input before the first write to the target: once
    the target holds `\q_no_value`, re-expanding the argument is trap 1 and
    loops forever.

## Geometry discipline

One base pitch controls the metric.  Repeated dimensions are named ratios.
Clearance uses the measured silhouette plus the single daylight separation;
do not add a constant that predicts what another pass will draw.

Useful focused regressions include:

```sh
python3 scripts/test_tenkz_label_overlap.py
```

Run the focused test while iterating, then the affected corpus or benchmark
section, then the repository gates appropriate to the change.

### RMP dimension inventory

The RMP driver applies two dimension checks before compiling any target.  The
aggregate ownership ratchets reject increases, unowned or commented case
dimensions, and benchmark-book allowlist drift.  The version-5 inventory in
`tests/tenkz/rmp/dimension-ownership.json` additionally freezes every active
literal at its semantic owner site.  Each case first lists its executed PICTURE
scopes.  Public tenkz environments, `tenkzeq`, and `tngroup` receive
hierarchical, per-parent source-order anchors even when their bodies contain no
dimensions.  The construct list records the drawing constructs: picture
environments and `tntree`.  A nested drawing's anchor includes its
PICTURE ancestry.  Command and drawing-container invocations are anchored
beneath their owning drawing; dimension-free commands and semantic starred
variants still receive source-order anchors.  `tenkzeq` is recorded only as a
scope.  It may precede the first drawing, and therefore has no honest drawing
owner.  An invocation's identity includes the exact PICTURE scope in which it
executes.  Dimension-bearing rows reference the exact owning invocation and
carry a comment-independent, TeX-token-normalized command or option skeleton.
Every option skeleton also
includes the registry-validated environment or command that owns it, so moving
a value between compatible option containers, same-name sibling invocations,
or PICTURE scopes changes the site identity.  Scopes, constructs, and
invocations stored in inert macro bodies are excluded by the same execution
mask as dimension ownership.
Owned values use `<dimension>` markers one-for-one with their literal vector;
dimensions belonging to a narrower nested site use `<nested-dimension>` and
are counted only by that nested owner.
Structural option separators and comment splices do not change a skeleton, but
significant whitespace inside argument token lists and option values does,
including nested bracket values.  Authored marker punctuation is escaped before
generated dimension placeholders are inserted.  Only repeated identical
skeletons receive a local occurrence number.  This catches a balanced
replacement or cross-site move that leaves all aggregate counts unchanged.

After an intentional, reviewed migration, update that exact inventory with:

```sh
python3 scripts/update_tenkz_dimension_inventory.py
python3 scripts/test_tenkz_dimension_inventory.py
```

The updater runs the aggregate ceilings before writing, rejects a malformed
old inventory, prints the site-level diff and the
case/scope/construct/invocation/site/dimension totals, and is byte-idempotent.
Do not edit the inventory to make an unexplained movement pass.  Comment
literals and the benchmark-book layout allowlist stay under their existing
orthogonal ratchets and never appear in these case rows.

## Historical design records

Superseded design proposals, migration inventories, reviews, and 0.6
worklists live under `docs/tenkz/history/`.  They explain earlier decisions but
do not define current syntax.  Do not revive a spelling from history without
passing the extension gates in `LANGUAGE.md`.
