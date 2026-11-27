"""Combine a regional CFF font with matching Western lettering."""

import unicodedata as ud
from collections import defaultdict
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

CELL = 600
HAN_SCALE = 1.03
CJK_MIDLINE = 380


def western(cp):
    """Return whether a code point is eligible for the Western donor."""
    name = ud.name(chr(cp), "")
    return (
        0x20 <= cp <= 0x7E
        or 0xA0 <= cp <= 0xFF
        or name.startswith(("LATIN ", "GREEK ", "CYRILLIC "))
    )


def is_han(cp):
    """Identify Han ideographs, including the ideographic zero."""
    return cp == 0x3007 or ud.name(chr(cp), "").startswith(
        ("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-")
    )


def build(base, donor, destination):
    """Write a verified hybrid OTF using the donor of matching weight.

    The base is a regional, icon-patched CFF font. Use a second reader
    for its original outlines and metrics while rewriting the output.
    Replace the destination only after the saved font passes validation.
    """
    destination = Path(destination)
    with (
        TTFont(base, recalcTimestamp=False) as font,
        TTFont(base) as original,
        TTFont(donor) as latin,
    ):
        _write_hybrid(font, original, latin, destination)


def _write_hybrid(font, original, latin, destination):
    """Fit outlines to the terminal grid and verify the saved font."""
    assert original["head"].unitsPerEm == latin["head"].unitsPerEm == 1000
    assert original["OS/2"].usWeightClass == latin["OS/2"].usWeightClass
    source = original.getGlyphSet()
    west = latin.getGlyphSet()
    cmap = original.getBestCmap()
    reference = latin.getBestCmap()
    han_shapes = {name for cp, name in cmap.items() if is_han(cp)}
    for table in original["cmap"].tables:
        if table.format == 14:
            for variants in table.uvsDict.values():
                han_shapes.update(
                    name for cp, name in variants if name and is_han(cp)
                )
    top = font["CFF "].cff.topDictIndex[0]
    strings = top.CharStrings
    order = list(font.getGlyphOrder())
    private = top.FDArray[0].Private
    used = set(order)
    free = (
        f"cid{i:05d}" for i in range(1, 65535) if f"cid{i:05d}" not in used
    )
    # One glyph can map to both ASCII and full-width code points.
    # Preserve its regional glyph ID when separating the outlines.
    targets = defaultdict(lambda: defaultdict(list))
    for cp, name in cmap.items():
        key = ("base", name)
        if ud.name(chr(cp), "").startswith("HALFWIDTH HANGUL"):
            key = ("half-hangul", name)
        elif cp in reference:
            if 0x2500 <= cp <= 0x259F:
                key = ("box", reference[cp])
            elif 0x300 <= cp <= 0x36F:
                key = ("accent", reference[cp])
            elif western(cp) and ud.category(chr(cp)) != "Cf":
                key = ("latin", reference[cp])
        targets[name][key].append(cp)

    tables = [
        t for t in font["cmap"].tables if t.isUnicode() and t.format in (4, 12)
    ]

    def append_glyph():
        """Reserve a free CID for a separate outline."""
        name = next(free)
        strings.charStrings[name] = len(order)
        strings.charStringsIndex.append(None)
        top.FDSelect.append(0)
        order.append(name)
        return name

    def write(name, kind, srcname, cps):
        """Store the transformed outline and its horizontal metrics."""
        glyphs = west if kind in ("latin", "box", "accent") else source
        glyph = glyphs[srcname]
        old = glyph.width
        sx = sy = 1
        dx = dy = 0
        if kind == "box":
            # Fit all connected tiles to the same cell and line metrics.
            width = CELL
            sy = (1160 + 288) / (973 + 240)
            dy = -288 + 240 * sy
        elif kind == "accent":
            # Draw a zero-width accent over the preceding Latin cell.
            ink = BoundsPen(glyphs)
            glyph.draw(ink)
            width = 0
            if ink.bounds:
                dx = -CELL / 2 - (ink.bounds[0] + ink.bounds[2]) / 2
        elif kind == "half-hangul":
            width = CELL
            sx = CELL / old
        elif kind == "latin":
            width = CELL
        elif not old or (
            cps
            and all(ud.category(chr(cp)) in ("Mn", "Me", "Cf") for cp in cps)
        ):
            width = 0
        elif cps and all(ud.category(chr(cp)) == "Co" for cp in cps):
            width = CELL
            sx = CELL / old
            if 0xE0B0 in cps:
                ink = BoundsPen(glyphs)
                glyph.draw(ink)
                sx = CELL / ink.bounds[2]
        else:
            wide = any(
                ud.east_asian_width(chr(cp)) in ("F", "W") for cp in cps
            )
            width = 2 * CELL if wide or old > 700 else CELL
            if srcname in han_shapes:
                sx = sy = HAN_SCALE
                dy = (1 - sy) * CJK_MIDLINE
            dx = (width - old * sx) / 2
        shape = T2CharStringPen(width - private.nominalWidthX, glyphs)
        recording = DecomposingRecordingPen(glyphs)
        glyph.draw(recording)
        matrix = (sx, 0, 0, sy, dx, dy)
        recording.replay(TransformPen(shape, matrix))
        bounds = BoundsPen(None)
        recording.replay(TransformPen(bounds, matrix))
        idx = strings.charStrings[name]
        strings.charStringsIndex[idx] = shape.getCharString(
            private, top.GlobalSubrs
        )
        top.FDSelect.gidArray[idx] = 0
        font["hmtx"][name] = (
            width,
            round(bounds.bounds[0]) if bounds.bounds else 0,
        )

    for name in list(order):
        groups = targets.get(name) or {("base", name): []}
        for i, ((kind, srcname), cps) in enumerate(sorted(groups.items())):
            target = name if i == 0 else append_glyph()
            write(target, kind, srcname, cps)
            if target != name:
                font["vmtx"][target] = font["vmtx"][name]
                for t in tables:
                    for cp in cps:
                        if cp in t.cmap:
                            t.cmap[cp] = target

    # Include Western letters missing from the regional font.
    for cp in sorted(reference.keys() - cmap.keys()):
        if western(cp):
            target = append_glyph()
            write(target, "latin", reference[cp], [cp])
            font["vmtx"][target] = font["vmtx"][cmap[65]]
            for t in tables:
                if cp <= 0xFFFF or t.format == 12:
                    t.cmap[cp] = target

    top.charset = order
    font.setGlyphOrder(order)
    names = font["name"]
    copyright_text = (
        names.getDebugName(0) + "\n" + latin["name"].getDebugName(0)
    )
    names.removeNames(nameID=0)
    names.setName(copyright_text, 0, 3, 1, 0x409)
    font["OS/2"].xAvgCharWidth = CELL
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    font.save(temp)
    with TTFont(temp) as result:
        _verify_hybrid(result, original, latin)
    temp.replace(destination)


def _verify_hybrid(result, original, latin):
    """Check mappings, names, advances, and outline bounds."""
    cmap = original.getBestCmap()
    reference = latin.getBestCmap()
    source = original.getGlyphSet()
    west = latin.getGlyphSet()
    assert cmap.keys() <= result.getBestCmap().keys()
    for ident in (1, 2, 3, 4, 6, 16, 17):
        assert result["name"].getDebugName(ident) == original[
            "name"
        ].getDebugName(ident)
    updated = result.getBestCmap()
    metrics = result["hmtx"]
    for cp in list(range(32, 127)) + [0xE0B0, 0xF120, 0xFF71, 0xFFBE, 0x2500]:
        assert metrics[updated[cp]][0] == CELL, hex(cp)
    for cp in list(range(0xAC00, 0xD7A4)) + [ord("中"), 0xFF0C]:
        assert metrics[updated[cp]][0] == 2 * CELL, hex(cp)
    assert metrics[updated[0x301]][0] == 0

    def bounds(glyphs, name):
        """Return the outline bounds in font units."""
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        return pen.bounds

    final_glyphs = result.getGlyphSet()
    for cp in range(33, 127):
        ink = bounds(final_glyphs, updated[cp])
        donor_ink = bounds(west, reference[cp])
        assert (
            max(abs(a - b) for a, b in zip(ink, donor_ink, strict=True)) <= 1
        ), hex(cp)
    for char in "茶道骨直한글":
        cp = ord(char)
        ink = bounds(final_glyphs, updated[cp])
        prior = bounds(source, cmap[cp])
        scale = HAN_SCALE if is_han(cp) else 1
        half_advance = source[cmap[cp]].width / 2
        expected = (
            CELL + (prior[0] - half_advance) * scale,
            CJK_MIDLINE + (prior[1] - CJK_MIDLINE) * scale,
            CELL + (prior[2] - half_advance) * scale,
            CJK_MIDLINE + (prior[3] - CJK_MIDLINE) * scale,
        )
        assert (
            max(abs(a - b) for a, b in zip(ink, expected, strict=True)) <= 1.1
        ), char
