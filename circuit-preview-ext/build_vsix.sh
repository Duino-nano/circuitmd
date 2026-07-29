#!/bin/bash
# circuit-preview 拡張を .vsix にパッケージして VSCode にインストールする。
# 使い方: ./build_vsix.sh               vsix作成 + インストール
#         ./build_vsix.sh --no-install  vsix作成のみ（dist/ に出力）
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(python3 -c "import json; print(json.load(open('package.json'))['version'])")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/extension" dist
cp package.json extension.js render_svg.py "$WORK/extension/"

cat > "$WORK/[Content_Types].xml" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="js" ContentType="application/javascript"/>
  <Default Extension="py" ContentType="text/x-python"/>
  <Default Extension="vsixmanifest" ContentType="text/xml"/>
</Types>
EOF

cat > "$WORK/extension.vsixmanifest" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="circuit-preview" Version="$VERSION" Publisher="kyouhei"/>
    <DisplayName>Circuit Preview</DisplayName>
    <Description xml:space="preserve">Markdownプレビューで circuit フェンス（schemdraw記法）を回路図としてレンダリング</Description>
    <Categories>Other</Categories>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
EOF

OUT="$PWD/dist/circuit-preview-$VERSION.vsix"
rm -f "$OUT"
(cd "$WORK" && zip -q -r -X "$OUT" "[Content_Types].xml" extension.vsixmanifest extension/)
echo "作成: $OUT"

if [[ "${1:-}" != "--no-install" ]]; then
  CODE=$(command -v code || true)
  if [[ -z "$CODE" && -x "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" ]]; then
    CODE="/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
  fi
  if [[ -n "$CODE" ]]; then
    "$CODE" --install-extension "$OUT"
    echo "インストール完了。VSCodeのウィンドウを再読み込みしてください（⌘⇧P → ウィンドウの再読み込み）"
  else
    echo "code CLI が見つかりません。VSCodeの拡張ビューから手動でインストールしてください: $OUT"
  fi
fi
