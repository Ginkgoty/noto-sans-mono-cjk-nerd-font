"""Render vector glyph charts from the built fonts."""

import string
from math import ceil
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/glyphs"
PAPER = "#ffffff"
INK = "#1f1f1f"
ACCENT = "#0b57d0"


def svg(width, height, elements):
    """Wrap the drawing in an SVG of the requested size."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="{PAPER}"/>'
        + "\n".join(elements)
        + "</svg>\n"
    )


def label(x, y, text, size=16, color=INK):
    """Return an SVG text label positioned on the given baseline."""
    return (
        f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="{size}" '
        f'fill="{color}">{text}</text>'
    )


class Face:
    """Render text and icons from one built regional font."""

    def __init__(self, region, style="Regular"):
        """Load a region and weight from the build directory."""
        self.font = TTFont(
            ROOT / f"dist/NotoSansMonoCJK{region}NF-{style}.otf"
        )
        self.cmap = self.font.getBestCmap()
        self.glyphs = self.font.getGlyphSet()

    def outline(self, cp):
        """Return SVG path commands for a Unicode code point."""
        glyph = self.glyphs[self.cmap[cp]]
        pen = SVGPathPen(self.glyphs)
        glyph.draw(pen)
        return pen.getCommands()

    def line(self, text, x, y, size, color=INK, *, tracking=0):
        """Draw glyph outlines along a baseline.

        Size and extra tracking use SVG user units. Character
        positions follow the advances stored in the selected face.
        """
        paths = []
        units = self.font["head"].unitsPerEm
        scale = size / units
        for char in text:
            cp = ord(char)
            path = self.outline(cp)
            if path:
                paths.append(
                    f'<path transform="translate({x:g} {y}) '
                    f'scale({scale:g} {-scale:g})" d="{path}" fill="{color}"/>'
                )
            x += self.glyphs[self.cmap[cp]].width * size / units + tracking
        return "".join(paths)

    def icon(self, cp, x, y, box):
        """Fit a glyph in a square centred at (x, y)."""
        bounds = BoundsPen(self.glyphs)
        self.glyphs[self.cmap[cp]].draw(bounds)
        if bounds.bounds is None:
            return ""
        left, bottom, right, top = bounds.bounds
        scale = box / max(right - left, top - bottom, 1)
        return (
            f'<path transform="translate({x} {y}) '
            f"scale({scale:.8g} {-scale:.8g}) "
            f'translate({-(left + right) / 2:g} {-(bottom + top) / 2:g})" '
            f'd="{self.outline(cp)}" fill="{ACCENT}"/>'
        )


def specimen(sc):
    """Show the weights, regional forms, and terminal icons."""
    bold = Face("SC", "Bold")
    marks = [
        label(28, 37, "Noto Sans Mono CJK Nerd Font", 24),
        sc.line("中文筆記  日本語  한글", 28, 108, 50),
        bold.line("Bold  粗体字样", 30, 156, 30, ACCENT),
    ]
    for i, region in enumerate(("SC", "TC", "HK", "JP", "KR")):
        x = 30 + 145 * i
        marks.extend(
            [label(x, 211, region, 15), Face(region).line("茶道", x, 257, 40)]
        )
    for i, cp in enumerate(
        (0xE0B0, 0xF120, 0xEA60, 0xF013, 0xF07C, 0xF09B, 0xF15B, 0xF0004)
    ):
        x = 30 + i * 91
        marks.extend(
            [sc.icon(cp, x + 27, 316, 26), label(x, 355, f"U+{cp:04X}", 12)]
        )
    (OUT / "specimen.svg").write_text(svg(760, 380, marks))


def thousand_character_specimen(sc):
    """Draw the opening verses in each of the five regional faces."""
    simplified = (
        "天地玄黄，宇宙洪荒。",
        "日月盈昃，辰宿列张。",
        "寒来暑往，秋收冬藏。",
        "闰余成岁，律吕调阳。",
    )
    traditional = (
        "天地玄黃，宇宙洪荒。",
        "日月盈昃，辰宿列張。",
        "寒來暑往，秋收冬藏。",
        "閏餘成歲，律呂調陽。",
    )
    regions = (
        ("SC", "Simplified Chinese"),
        ("TC", "Taiwan"),
        ("HK", "Hong Kong"),
        ("JP", "Japan"),
        ("KR", "Korea"),
    )
    marks = [
        sc.line("千字文", 28, 102, 48),
        label(30, 141, "Thousand Character Classic", 18),
    ]
    for slot, (region, name) in enumerate(regions, start=1):
        x = 28 + (slot % 2) * 380
        y = 38 + (slot // 2) * 208
        face = sc if region == "SC" else Face(region)
        marks.append(label(x, y, f"{region}  /  {name}", 16, ACCENT))
        verses = simplified if region == "SC" else traditional
        for i, verse in enumerate(verses):
            marks.append(face.line(verse, x, y + 36 + i * 36, 25))
    (OUT / "thousand-character-classic.svg").write_text(svg(760, 622, marks))


def quick_brown_fox_specimen(sc):
    """Render the fox sentence in English and five regional editions."""
    rows = (
        ("SC", "English", "The quick brown fox jumps over the lazy dog."),
        ("SC", "SC  /  Simplified Chinese", "敏捷的棕色狐狸跃过了那只懒狗。"),
        ("TC", "TC  /  Traditional Chinese", "敏捷的棕色狐狸躍過了那隻懶狗。"),
        ("HK", "HK  /  Cantonese", "隻敏捷嘅啡色狐狸跳過咗嗰隻懶狗。"),
        (
            "JP",
            "JP  /  Japanese",
            "素早い茶色のキツネが怠け者の犬を飛び越える。",
        ),
        ("KR", "KR  /  Korean", "날쌘 갈색 여우가 게으른 개를 뛰어넘는다."),
    )
    marks = [
        "<title>The quick brown fox in six regional "
        "and language samples</title>"
    ]
    for i, (region, name, sentence) in enumerate(rows):
        y = 30 + i * 76
        face = sc if region == "SC" else Face(region)
        marks.extend(
            [
                f"<g><title>{sentence}</title>",
                label(28, y, name, 15, ACCENT),
                face.line(sentence, 28, y + 34, 25),
                "</g>",
            ]
        )
    (OUT / "quick-brown-fox.svg").write_text(svg(760, 466, marks))


def coding_specimen(sc):
    """Show ASCII and a Python example with Chinese text."""
    bold = Face("SC", "Bold")
    marks = [
        bold.line("Basic Latin", 28, 38, 24),
        sc.line(string.ascii_uppercase, 28, 91, 36, tracking=2),
        sc.line(string.ascii_lowercase, 28, 139, 36, tracking=2),
        sc.line(string.digits, 28, 193, 32, tracking=2),
        sc.line("0Oo   1Il   5S   2Z", 275, 193, 32, ACCENT, tracking=2),
        sc.line(string.punctuation, 28, 242, 31, tracking=2),
        '<rect x="16" y="273" width="728" height="165" '
        'rx="8" fill="#f5f7fa"/>',
        bold.line("Python", 32, 304, 18, ACCENT),
        sc.line("def codepoints(text: str) -> list[str]:", 32, 347, 24),
        sc.line('    return [f"U+{ord(ch):04X}" for ch in text]', 32, 380, 24),
        sc.line('print(codepoints("你好，世界"))', 32, 417, 24),
    ]
    (OUT / "coding.svg").write_text(svg(760, 454, marks))


def main():
    """Write the samples, glyph charts, and Markdown index."""
    OUT.mkdir(parents=True, exist_ok=True)
    sc = Face("SC")
    specimen(sc)
    thousand_character_specimen(sc)
    quick_brown_fox_specimen(sc)
    coding_specimen(sc)
    with TTFont(ROOT / ".cache/NotoSansMonoCJKsc-Regular.otf") as original:
        additions = sorted(sc.cmap.keys() - original.getBestCmap().keys())
    index = [
        "# Glyph chart",
        "",
        f"All {len(additions):,} added Unicode mappings in SC Regular, "
        "ordered by code point. Choose a range to open its chart. "
        "Outlines are scaled to fit each cell; the printed label gives "
        "the hexadecimal code point.",
        "",
        "| First | Last | Chart |",
        "| --- | --- | --- |",
    ]
    for start in range(0, len(additions), 160):
        group = additions[start : start + 160]
        first, last = group[0], group[-1]
        title = f"U+{first:04X} – U+{last:04X}"
        name = f"{first:05X}-{last:05X}.svg"
        marks = [label(16, 32, title, 23)]
        for i, cp in enumerate(group):
            x, y = 16 + 90 * (i % 10), 59 + 69 * (i // 10)
            marks.extend(
                [
                    sc.icon(cp, x + 27, y + 13, 29),
                    label(x, y + 45, f"U+{cp:04X}", 13),
                ]
            )
        page = svg(920, 65 + 69 * ceil(len(group) / 10), marks)
        (OUT / name).write_text(page)
        index.append(
            f"| U+{first:04X} | U+{last:04X} | [View chart]({name}) |"
        )
    (OUT / "README.md").write_text("\n".join(index) + "\n")


if __name__ == "__main__":
    main()
