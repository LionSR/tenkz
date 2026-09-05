# tenkz compatibility and release policy

This file owns compatibility and versioning. `LANGUAGE.md` owns the public
mental model, `LANGUAGE-1.0.md` the grammar, and `ARCHITECTURE.md` the implementation
boundaries. `RELEASE-POLICY.md` is the release checklist.

The unactivated release-evidence campaign is retired. A release is a reviewed
commit with passing product checks, a reproducible manual, a tested archive,
and explicit maintainer approval to publish. There is no activation ceremony,
fixed soak duration, work-record quota, custom publisher, or signing-key lifecycle.
The former proposal remains in Git history at `fcbea38`; `SOAK-1.0.md` records
its retirement. This policy change neither bumps the version nor publishes it.

## Stabilization scope

The supported diagrams used by the TNLean blueprint define the completion
boundary. Fix demonstrated correctness, readability, installation, and documented
interface defects. Additional diagram families, universal automatic layout,
and architectural cleanup are not release prerequisites. Keep the known benchmark
gaps explicit; neither a passing compile nor a boundary check proves a cited
mathematical identity. Review real blueprint use at the candidate commit.

## Compatibility ownership

tenkz has two public surfaces. A release decision names both.

### TeX surface

The manual (`manual2.tex` and `chapters2/`) is the reader-facing contract and
must agree with the executable language registry. Documented environments,
commands, keys, defaults, diagnostics, topology, boundary meaning, labels,
and semantic ink form the public surface. Private controls and development
probes are excluded. Exact raster bytes are not promised across engines or fonts.
Before 1.0, an intentional migration updates the contract and callers together;
a freeze tag is not required to start stabilization.

### Event surface

`TNLOG.md` declares the event format and its current limits. The canonical
reader is `scripts/tenkzlib/tnlog.py`; the golden ledgers pin emitted bytes.
The current format has no in-band version negotiation. The first CTAN release
may document that limitation; adding a header is not a release prerequisite.
Unknown optional fields remain accepted. A new event kind requires an explicit
reader compatibility decision; no automatic negotiation is claimed.

A package patch keeps event bytes and meaning stable for unchanged input. An
additive compatible event change increments the documented event minor and
requires at least a package minor. A breaking event change increments both
majors. Test the actual readers against old and new streams when changing the
format; a documentation version alone does not establish compatibility.

## Package versions

tenkz uses semantic `MAJOR.MINOR.PATCH` versions.

### Patch

A patch fixes a defect without rejecting documented valid input, changing a
documented default, or changing mathematical meaning. Clearance, clipping,
typography, and other rendering corrections are patches when topology,
boundary meaning, labels, and semantic ink stay fixed. A patch emits the same
`.tnlog` bytes and semantics for unchanged input. Parser-only diagnostic fixes
may be patches when they neither accept an invalid event as valid nor reject a
valid event.

### Minor

A minor release adds a backward-compatible documented capability. Existing
valid sources keep their meaning and defaults. New language elements still
pass the extension and shrink gates; a minor number is not permission for an
unmanifested special case. Deprecation may begin in a minor release, but the
old spelling continues to compile for the rest of the major series.

An additive `.tnlog` kind or optional field is a minor change only after the
documented event minor is incremented, the canonical reader accepts old and new streams,
and consumers are tested against both.

### Major

A major release may remove deprecated input, change a documented default or
meaning, or make an incompatible event-format change. The migration guide,
tombstones, manual, registry, parser, emitters, and tests change together. A
major release never reuses a dead spelling for a new meaning.

## Deprecations, tombstones, and frozen twins

A deprecation starts in a minor release. It names one replacement, the earliest
major release allowed to remove it, and tests proving that the old spelling
still has its promised behavior. Removal at that major is permitted, not
mandatory. A warning cannot become a compilation error inside the same major
series.

When removal occurs, the dead spelling becomes a tombstone. The linter and
parser reject it with its migration. Tombstones are permanent and their names
are never recycled, including at a later major release. Pre-1.0 aliases and
their milestone sunsets remain governed by `LANGUAGE-1.0.md` and the shrink
ledger; any removal must migrate its consumers in the same reviewed change.

The frozen-twin escape hatch is a permanent library-entry-point split inside
one package. The owner-approved model is `quantikz` 0.9.8 frozen beside
`quantikz2` under a new library name in the same package. When a successor
cannot preserve the released surface, the old library entry point remains
installable with byte-tested TeX and `.tnlog` behavior, while the new language
ships beside it under a distinct library entry point in that package. The old
surface receives no new features and is never removed by the successor's next
major release. The release issue must cite the incompatibility, test both
surfaces, and publish separate manuals and release-tag histories. A separate
package, a per-command alias, a spelling-level twin removed at the next major,
a compatibility switch, or a silent semantic change is not the frozen-twin
escape hatch. This policy defines the ownership decision; it does not create
the successor entry point.

## Release tags

Package release tags use `tenkz-vMAJOR.MINOR.PATCH`. They are annotated and must
never be moved or reused. The maintainer creates a tag only after explicitly
approving the tested release commit. Signing may be used but no custom signing
service is required. Do not change unrelated tag namespaces.

Release notes record the exact commit, package and event versions, archive
SHA-256, validation results, and known limitations. No separate machine-readable
campaign ledger or release manifest is required. CTAN publication follows
`ctan/UPLOAD-CHECKLIST.md`; CTAN acceptance and distribution inclusion are
external steps, not consequences of a local passing check.

## Equation grouping

A boundary signature is checkable only against another boundary signature,
so the enforceable unit is not the picture but the group of pictures one
equation relates. tenkz has exactly one such group: the `tenkzeq`
environment, whose relation glyphs delimit the sides and whose juxtaposed
panels form a product term (`LANGUAGE-1.0.md` §7). The environment writes its
number into every panel's `picture` record and one `check` record for every
joiner it resolves, so a reader of the event stream alone knows which
pictures an author asserted equal and which comparisons were performed. That
is what makes the group enforceable: a mismatch inside one is a hard finding
of the stream, needing no source file and no reading of the mathematics
between the panels.

The group is also the metric context, and that forces the one piece of
machinery in the environment a reader would not expect: the equation typesets
its own body twice. An equation states that its panels are one object written
two ways, so the glyphs holding their inscribed names must come out the same
size, and the first panel therefore has to know what the last one measures.
Nothing else in the package needs a fact from later in the document; this
does. The panels are lifted out of the body and set once into a box that is
dropped, with the event stream silent, its recoverable diagnostics held back,
and every count the real run advances put back afterwards, which leaves
behind only the widest and deepest name of each size class. The real run then
sets every name of a class on that measure. It only ever grows a glyph, so a
name is never pushed outside the ink holding it, and an equation whose panels
already agreed is drawn exactly as it was.

Only the panels are measured, and that is not an optimisation. The measure is
a fact about the pictures, so the mathematics standing between them
contributes nothing to it, and running that mathematics twice is how a
counter, a cross-reference, or a write in an author's own tokens would be
performed twice. What remains double is a name inscribed in a panel, which is
what measuring a name costs and is the one place the language's own grammar
guarantees there is nothing but mathematics to typeset.

The panels are read from the body as written, which is the trade the previous
paragraph buys. A panel standing behind a conditional the body never takes
still lends its extent to the measure, and a panel arriving through a macro or
an included file lends none and is drawn exactly as it would be alone. Both
are wrong about the *sharing* and neither can misdraw a panel: the measure
only grows a glyph, and a glyph sharing nothing keeps its class floor while
an overflowing name moves to its station. Reading the panels along the
executed path instead would be right about the sharing and wrong about the
document, which is the trade this one refuses.

Two cheaper answers do not work. **Carrying the measure between LaTeX runs**
through the auxiliary file fails because the fixture and benchmark harnesses
compile once. **Fitting the name to the glyph** by shrinking type is refused
on sight: names are set at named sizes and are not scaled to fit. Fixing an
extent to its size class is not an equation substitute and no longer pretends
to be one: outside an equation there is no shared measure, so that is the
ordinary rule. A name that exceeds the fixed standalone glyph keeps its type
size and moves to the atom's label station; only an equation's explicit claim
that its panels are one object supplies the shared measure that may grow ink.

Two other spellings for the group were considered and are rejected.

A shared **`equation=<id>` picture key** would let any pictures anywhere in a
document declare themselves one group. It is rejected because it separates
the assertion from the thing asserted. The claim an equation makes is made by
the relation glyph standing between two panels; an identifier repeated on
scattered pictures restates that claim in a second place, where it can go
stale, contradict the typeset mathematics, or group panels no reader sees
side by side. It also gives the author two ways to spell one concept, which
the grammar's one-concept-one-spelling rule forbids, and it cannot express
the product joiner at all: an identifier says which pictures belong together
but not in which order they contract.

**Automatic grouping of consecutive pictures in one display**, inferred from
the order pictures appear in the event stream, needs no spelling at all. It is
rejected because the event stream records no displays. A picture's position in
the stream is the order TeX shipped it, which merges the panels of a display
with pictures from surrounding prose, from a float, from a footnote, and from
the same paragraph; nothing in the stream separates them. Recovering the
display would mean parsing the source beside the log and guessing which
separator is a relation — precisely the heuristic that made the old sibling
check advisory. Inference cannot be made hard, because the author never
declared anything for it to be hard about.

The audit keeps that heuristic, downgraded to what it is. Two consecutive
pictures joined by a source `=` outside every group raise the advisory
`eq-sibling-mismatch`: not a defect in the diagram but a picture pair still
to be moved into the scope. The hard rules apply inside the group only.

The heuristic also states its own limit. A display that asserts a relation
somewhere but joins other panels another way — a product, a sum, an arrow —
is read as `eq-sibling-unread` and nothing is claimed about it, because the
pairwise reading would compare one factor against a whole side. That is the
same argument one tier down: the composition is exactly what the scope
classifies and a reading of the source cannot.
