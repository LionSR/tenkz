# tenkz extraction from TNLean

Extracted from `LionSR/TNLean` without rewriting that repository's history.

```text
TN_SOURCE_SHA=85a12e6b524310795bb7aaa7d3e3fc33a59566c0
FILTERED_TIP=24e66c54087f50c9ddde202b5a194000cbd1f1d0
filter-paths.txt sha256=68fa0487929f9eabe0f677aa082f23ab8fe4217e41293cac5046983887526dc4
commit-map sha256=e55e0f26616c9d70fafb21fd954950abaacf373c8fc70ebee226417a258ee2b6
file_count=656
rewritten_commits=986
```

`TN_SOURCE_SHA` is TNLean `origin/main` at freeze (Wielandt pass-through
retirement, #7160). That commit did not touch tenkz paths, so `git filter-repo`
maps it to the zero SHA and the filtered tip is the rewritten image of
#7157, whose tenkz blobs are byte-identical to the freeze tree.

The soak-era policy block in `DESIGN.md` is unchanged: work class
`formalization-or-blueprint`, excluded path `TNLean/Archive/**`, and TNLean
issue numbers in the blocker chain remain the campaign contract until that
campaign is re-homed. Those issue numbers still resolve on TNLean.

TNLean consumers that did not move: the plasTeX SVG pipeline, blueprint
picture sources, slide decks, the blueprint event sweep, and the retired
`tex/tn/` demolition guard.
