"""Package verified regional fonts and their licenses."""

from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    """Bundle each region and write the SHA-256 checksums."""
    root = Path(__file__).resolve().parents[1]
    dist = root / "dist"
    notices = sorted(p for p in (root / "licenses").rglob("*") if p.is_file())
    hashes = []
    for region in ("SC", "JP", "HK", "TC", "KR"):
        archive = dist / f"NotoSansMonoCJK{region}NF.zip"
        fonts = [
            dist / f"NotoSansMonoCJK{region}NF-{style}.otf"
            for style in ("Regular", "Bold")
        ]
        with ZipFile(archive, "w", ZIP_DEFLATED) as z:
            for font in fonts:
                z.write(font, font.name)
            z.write(root / "README.md", "README.md")
            for p in notices:
                z.write(p, p.relative_to(root))
        hashes.append(
            f"{sha256(archive.read_bytes()).hexdigest()}  {archive.name}"
        )
    (dist / "SHA256SUMS").write_text("\n".join(hashes) + "\n")


if __name__ == "__main__":
    main()
