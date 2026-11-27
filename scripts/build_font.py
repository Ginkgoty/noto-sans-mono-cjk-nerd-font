"""Patch a regional CID-keyed CFF font with Nerd Fonts icons."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from fontTools import subset
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from hybrid import build as build_hybrid

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
ICON_FLAGS = (
    "--fontawesome --fontawesomeext --codicons --material --octicons "
    "--pomicons --powerline --powerlineextra --powersymbols --weather"
).split()


def patch_icons(source, patcher, work):
    """Return a patched ASCII seed with icons sized for the source face.

    FontForge works on a temporary TrueType copy so it can fit icons to
    the original cell without rewriting the regional CFF outlines.
    The caller must close the returned font before removing the work
    directory.
    """
    em = source["head"].unitsPerEm
    cmap = {
        cp: name
        for cp, name in source.getBestCmap().items()
        if 32 <= cp <= 126
    }
    names = [".notdef", *dict.fromkeys(cmap.values())]
    builder = FontBuilder(em, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(cmap)
    glyphs = source.getGlyphSet()
    outlines = {}
    for name in names:
        pen = TTGlyphPen(None)
        glyphs[name].draw(Cu2QuPen(pen, 1, reverse_direction=True))
        outlines[name] = pen.glyph()
    builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics(
        {name: source["hmtx"][name] for name in names}
    )
    hhea, os2 = source["hhea"], source["OS/2"]
    builder.setupHorizontalHeader(ascent=hhea.ascent, descent=hhea.descent)
    builder.setupNameTable({"familyName": "CJK Cell", "styleName": "Regular"})
    builder.setupOS2(
        sTypoAscender=os2.sTypoAscender,
        sTypoDescender=os2.sTypoDescender,
        usWinAscent=os2.usWinAscent,
        usWinDescent=os2.usWinDescent,
    )
    builder.setupPost()
    seed = work / "seed.ttf"
    builder.save(seed)
    out = work / "icons"
    out.mkdir()
    subprocess.run(
        [
            os.environ.get("FONTFORGE", "fontforge"),
            "-script",
            str(patcher),
            "--careful",
            "--single-width-glyphs",
            "--quiet",
            *ICON_FLAGS,
            "-out",
            str(out),
            str(seed),
        ],
        check=True,
    )
    (result,) = out.glob("*.ttf")
    return TTFont(result)


def compact(source):
    """Free glyph slots while preserving regional default forms."""
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_outline = True
    # Keep each region's default forms and other layout features.
    # Removing language switching frees slots for the new icons.
    options.layout_features = sorted(
        {
            feature.FeatureTag
            for tag in ("GSUB", "GPOS")
            for feature in source[tag].table.FeatureList.FeatureRecord
        }
        - {"locl"}
    )
    keep = set(source.getBestCmap())
    for table in source["cmap"].tables:
        if table.format == 14:
            keep.update(table.uvsDict)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=keep)
    subsetter.subset(source)


def add_icons(font, donor):
    """Copy missing mappings and their outlines into the regional font.

    Return the number of added mappings. Reject donor glyphs whose
    advance differs from the source font's ASCII cell width.
    """
    top = font["CFF "].cff.topDictIndex[0]
    strings = top.CharStrings
    order = list(font.getGlyphOrder())
    used = set(order)
    free_names = (
        f"cid{i:05d}" for i in range(1, 65535) if f"cid{i:05d}" not in used
    )
    glyphs = donor.getGlyphSet()
    existing = font.getBestCmap()
    tables = [
        t for t in font["cmap"].tables if t.isUnicode() and t.format in (4, 12)
    ]
    private = top.FDArray[0].Private
    cell = font["hmtx"][existing[65]][0]
    added = 0
    for cp, donor_name in sorted(donor.getBestCmap().items()):
        if cp in existing:
            continue
        glyph = glyphs[donor_name]
        if glyph.width != cell:
            raise ValueError(f"U+{cp:04X}: expected {cell}, got {glyph.width}")
        pen = T2CharStringPen(cell - private.nominalWidthX, glyphs)
        glyph.draw(pen)
        bounds = BoundsPen(glyphs)
        glyph.draw(bounds)
        name = next(free_names)
        strings.charStrings[name] = len(order)
        strings.charStringsIndex.append(
            pen.getCharString(private, top.GlobalSubrs)
        )
        top.FDSelect.append(0)
        order.append(name)
        font["hmtx"][name] = (
            cell,
            round(bounds.bounds[0]) if bounds.bounds else 0,
        )
        font["vmtx"][name] = font["vmtx"][existing[65]]
        for table in tables:
            if cp <= 0xFFFF or table.format == 12:
                table.cmap[cp] = name
        added += 1
    top.charset = order
    font.setGlyphOrder(order)
    return added


def rename(font, region, style):
    """Set the family, style, and PostScript names for this face."""
    family = f"Noto Sans Mono CJK {region} Nerd Font"
    ps = f"NotoSansMonoCJK{region}NF-{style}"
    full = f"{family} {style}"
    top = font["CFF "].cff.topDictIndex[0]
    font["CFF "].cff.fontNames = [ps]
    top.FamilyName, top.FullName = family, full
    for i, fd in enumerate(top.FDArray):
        fd.FontName = f"{ps}-FD{i}"
    names = font["name"]
    for ident in (1, 2, 3, 4, 5, 6, 16, 17, 18, 21, 22, 25):
        names.removeNames(nameID=ident)
    for ident, value in {
        1: family,
        2: style,
        3: f"0.100;community;{ps}",
        4: full,
        5: "Version 0.100",
        6: ps,
        16: family,
        17: style,
    }.items():
        names.setName(value, ident, 3, 1, 0x409)
    font["head"].fontRevision = 0.1
    top.CIDFontVersion = 0.1


def verify(path, base, added):
    """Compare the icon-patched intermediate with its upstream face."""
    with TTFont(path) as final, TTFont(base) as original:
        cmap, upstream = final.getBestCmap(), original.getBestCmap()
        assert len(cmap) == len(upstream) + added
        for cp, name in upstream.items():
            assert (
                cmap[cp] == name
                and final["hmtx"][name] == original["hmtx"][name]
            ), hex(cp)
        for src in original["cmap"].tables:
            if src.format == 14:
                result = final["cmap"].getcmap(src.platformID, src.platEncID)
                assert result.uvsDict == src.uvsDict
        assert final["maxp"].numGlyphs <= 65535
        glyphs = final.getGlyphSet()
        original_glyphs = original.getGlyphSet()
        for char in "骨直遍漢한あiW，":
            name = upstream[ord(char)]
            before, after = RecordingPen(), RecordingPen()
            original_glyphs[name].draw(before)
            glyphs[name].draw(after)
            assert before.value == after.value, char
        for cp in (0xE0B0, 0xF120, 0xEA60, 0xF0004):
            name = cmap[cp]
            pen = BoundsPen(glyphs)
            glyphs[name].draw(pen)
            assert pen.bounds and final["hmtx"][name][0] == 500, hex(cp)
        assert final["hmtx"][cmap[ord("中")]][0] == 1000
        print(
            f"{path.name}: {len(upstream)} source mappings, "
            f"{added} additions, "
            f"{final['maxp'].numGlyphs} glyphs",
            flush=True,
        )


def main():
    """Build and verify the requested region and weight."""
    parser = argparse.ArgumentParser()
    parser.add_argument("region", choices=["SC", "HK", "JP", "KR", "TC"])
    parser.add_argument("style", choices=["Regular", "Bold"])
    args = parser.parse_args()
    base = CACHE / f"NotoSansMonoCJK{args.region.lower()}-{args.style}.otf"
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    dest = out / f"NotoSansMonoCJK{args.region}NF-{args.style}.otf"
    with (
        tempfile.TemporaryDirectory(dir=out) as temp,
        TTFont(base, recalcTimestamp=False) as font,
    ):
        work = Path(temp)
        with patch_icons(font, CACHE / "patcher/font-patcher", work) as donor:
            compact(font)
            added = add_icons(font, donor)
        rename(font, args.region, args.style)
        candidate = work / dest.name
        font.save(candidate)
        verify(candidate, base, added)
        build_hybrid(
            candidate,
            CACHE / f"NotoSansMNerdFontMono-{args.style}.ttf",
            work / "final.otf",
        )
        (work / "final.otf").replace(dest)


if __name__ == "__main__":
    main()
