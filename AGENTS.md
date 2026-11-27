# AGENTS.md

## Project

Chinese-language popular-science book, not an application. `content/*.md` is the manuscript; `build/make_book.py` renders the print PDF with ReportLab. The tracked deliverable is `output/人工智能简史.pdf` (currently 117 pages, ~51k Chinese characters, 9 vector figures). Print design is intentionally light: page backgrounds are pure white, and cover/back/part dividers use light line art; avoid reintroducing large dark fills.

## Build and verify

```bash
pip install reportlab pypdfium2 pillow
python build/make_book.py
python -c "import pypdfium2 as p; print(len(p.PdfDocument('output/人工智能简史.pdf')))"
```

- `pypdfium2`/`Pillow` are for inspection and page rendering only; ReportLab is the build dependency.
- The build reads five OFL fonts from `fonts/` (`NotoSerifSC-*`, `NotoSansSC-Regular/Bold`, `LXGWWenKai-Regular.ttf`) and no longer uses Windows system fonts. `fonts/` is gitignored (~73 MB); a fresh clone must download the files, and the build fails fast with a list if any are missing.
- The build overwrites the tracked PDF. Preview PNGs under `output/` are gitignored.
- There is no `package.json`, test suite, linter, or CI. The PDF build plus a page/layout check is the verification.
- A page-count change after content edits is expected; inspect page breaks before committing. After font/leading changes, flag near-empty pages (under ~250 extracted characters; the appendix part-divider is intentionally short).
- To inspect a page without changing the PDF (requires Pillow): `python -c "import pypdfium2 as p; p.PdfDocument('output/人工智能简史.pdf')[8].render(scale=2).to_pil().save('output/p9.png')"`.

## Structure and wiring

- `CHAPTERS` in `build/make_book.py` controls chapter order, source file, part, title, subtitle, and lead. The first `#` heading in each chapter file is skipped, so editing only a chapter H1 does not change the PDF.
- `PARTS` supplies the four part dividers; each chapter's `part` index must match. Content files are referenced explicitly, not discovered by glob—renaming one requires updating `CHAPTERS`.
- `content/15-附录.md` is hardcoded as the appendix. Its H1s start appendix sections, its H2s populate the TOC; chapter H2s never appear in the TOC.
- README's TOC and page/character/figure counts are manual, as are the stats in `docs/03-结构终审.md`. Update the README TOC and counts when chapters change; treat the PDF and `make_book.py` as the source of truth.

## Manuscript format

`parse_blocks()` implements a Markdown subset:

- Blocks: `##`, `###`, `> ` quotes, `- ` bullets, `1. ` numbered lists (flat only), `---` scene breaks, pipe tables (first row is the header; separator row is ignored), `::: note <title>` … `:::` for “技术小注”, and `![fig:<id>](caption)`.
- Inline: `**bold**`, `*italic*`, `` `code` ``, `[text](url)`.
- Figures are ReportLab vector drawings (`fig_*`, registered in `FIGURES` with a height); unknown IDs render a placeholder. `assets/cover.png` is only the README cover—the PDF cover is drawn by `draw_cover()`.
- Figure numbers/captions and in-text references (“图 8-1”) are manual; grep when renumbering.
- `make_table()` special-cases `人物`/`模型` headers, compacts tables with ≥20 body rows, and hardcodes the `模型` table caption; review it before changing those tables.

## Writing rules

- Follow `docs/02-写作规范与事实核查.md`: story first; no fabricated quotes; separate fact from judgment; use “据公开报道”/“截至本书写作时” for post-2024 claims.
- China belongs in “中国坐标” sections inside chapters, not a separate chapter.
- Use “技术小注” blocks for technical asides; keep terminology consistent with `docs/04-审校与修订记录.md`.
- `docs/01` and `docs/03` are design/review history, not build config.
- Text is CC BY-NC-SA 4.0; code is MIT (`LICENSE`, `LICENSE-CODE`).
