#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root=$PWD
mkdir -p .cache
cd .cache
while read -r digest file; do
    if [[ -f $file ]] && printf '%s  %s\n' "$digest" "$file" | sha256sum --status -c -; then
        continue
    fi
    case "$file" in
        FontPatcher.zip) url=https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.1/FontPatcher.zip ;;
        NotoSansMNerdFontMono-*.ttf) url="https://raw.githubusercontent.com/ryanoasis/nerd-fonts/v3.5.1/patched-fonts/Noto/Sans-Mono/$file" ;;
        *) url="https://raw.githubusercontent.com/notofonts/noto-cjk/523d033d6cb47f4a80c58a35753646f5c3608a78/Sans/Mono/$file" ;;
    esac
    curl --fail --location --retry 3 "$url" -o "$file.part"
    printf '%s  %s\n' "$digest" "$file.part" | sha256sum -c -
    mv "$file.part" "$file"
done < "$root/inputs.sha256"
sha256sum -c "$root/inputs.sha256"
unzip -oq FontPatcher.zip -d patcher
