# Building and adapting the fonts

Start with one region and weight while working on a change. The same build
script produces the ten fonts in a full release.

## Build one font

Run these commands from the project root. You need Python 3.10 or newer, Bash,
curl, unzip, sha256sum, and FontForge with Python scripting. CI uses FontForge
20251009. If your executable is outside your PATH, set `FONTFORGE` to its
absolute path.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
scripts/prepare.sh
.venv/bin/python scripts/build_font.py SC Regular
```

Open `dist/NotoSansMonoCJKSCNF-Regular.otf` to inspect the result. Substitute
`TC`, `HK`, `JP`, or `KR` for `SC` to build another edition, or use `Bold` for
the second weight. Each build reopens the font files and runs the checks
described below.

## Check Python changes

From the project root, use the same virtual environment as the build. Install
the development requirements once, then run both checks before submitting a
Python change.

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check scripts
.venv/bin/ruff format --check scripts
```

Use `.venv/bin/ruff format scripts` to apply formatting. The
[Ruff configuration](../ruff.toml) targets Python 3.10 and sets a 79-character
line limit and a 72-character limit for comments and docstrings. The linter
checks imports, naming, common Python mistakes, and PEP 257 docstrings.
Describe the glyph or metric assumptions that callers need to know. CI runs
these checks before building the fonts.

## Where the glyphs come from

Noto publishes its own Mono editions of Noto Sans CJK. They already have
half-width ASCII and regional forms for Han characters and punctuation. We
start with the ten static Regular and Bold OTFs from the
[Noto Sans CJK 2.004 Mono directory](https://github.com/notofonts/noto-cjk/tree/523d033d6cb47f4a80c58a35753646f5c3608a78/Sans/Mono).
The Western lettering comes from the matching weight of
[NotoSansM Nerd Font Mono](https://github.com/ryanoasis/nerd-fonts/tree/v3.5.1/patched-fonts/Noto/Sans-Mono).

[The preparation script](../scripts/prepare.sh) downloads these fonts and the
Nerd Fonts 3.5.1 patcher into `.cache/` and verifies them against
[inputs.sha256](../inputs.sha256). When updating a source, update its pinned
download location and checksum together.

## Changing icons or regional forms

Each regional source already fills all 65,535 OpenType glyph slots. To free
space for icons, [build_font.py](../scripts/build_font.py) drops the `locl`
substitutions that switch regional forms within a font, then removes unused
glyphs. Each family keeps its own default forms and Unicode variation
sequences. Other OpenType layout features are retained where applicable.

The script runs the official Nerd Fonts patcher on a temporary font containing
the source's ASCII glyphs. It copies newly mapped icons into the regional font
and checks that the original Unicode mappings, metrics, and variation sequences
survive this step. To change the icon sets, edit the patcher options in
`patch_icons` and review the [icon licenses](../licenses/Icon-sets.md).
The selection includes Powerline, Codicons, Font Awesome, Material Design,
Octicons, and Weather. Font Logos is omitted because the upstream license audit
lists its license as unspecified.

## Changing lettering or spacing

[hybrid.py](../scripts/hybrid.py) brings in the Western outlines and fits the
regional glyphs and icons to the terminal grid. Printable ASCII and terminal
icons advance 600 font units. Full-width characters advance 1200. Han outlines
are enlarged by 3% around the cell centre and CJK midline, while modern Hangul
syllables keep their original outline size. Halfwidth Hangul uses the 600-unit
cell. Full-width punctuation retains its regional shapes.

The final OpenType fonts use CFF outlines rebuilt without per-glyph hints.
The build checks family and style names, cell widths, the bounds of printable
ASCII against the donor font, and representative Han outlines. After changing
the design, also inspect mixed text and icon alignment at the size you use in
your editor or terminal.

## Generate samples and release archives

Build both weights for all five regions before generating the samples or
packaging a release.

```sh
for region in SC TC HK JP KR; do
  for style in Regular Bold; do
    .venv/bin/python scripts/build_font.py "$region" "$style"
  done
done
.venv/bin/python scripts/glyph_chart.py
.venv/bin/python scripts/package.py
(cd dist && sha256sum -c SHA256SUMS)
```

[The sample generator](../scripts/glyph_chart.py) renders the README samples
and glyph charts under [docs/glyphs](glyphs/) from the built fonts.
[The packaging script](../scripts/package.py) writes one ZIP per region and a
shared `SHA256SUMS` file to `dist/`.

The [GitHub Actions workflow](../.github/workflows/fonts.yml) builds and checks
all five regions on pull requests and pushes to `main`. Pushing a version tag
such as `v0.1.0` also publishes the archives and checksums as a GitHub Release
after verification.
