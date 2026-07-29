#!/bin/bash
# circuit-preview 拡張を .vsix にパッケージして VSCode にインストールする。
# 使い方: ./build_vsix.sh               vsix作成 + インストール
#         ./build_vsix.sh --no-install  vsix作成のみ（dist/ に出力）
#
# ローカルPythonが無い環境でも動くよう、Pyodide(Python WASM)と schemdraw wheel を
# 同梱する。取得物は dist/cache/ にキャッシュされ、2回目以降のビルドは高速。
set -euo pipefail
cd "$(dirname "$0")"

PYODIDE_VERSION="0.26.4"
SCHEMDRAW_VERSION="0.23"
CACHE="$PWD/dist/cache"
mkdir -p "$CACHE" dist

# ---- 同梱物のダウンロード（キャッシュ付き） ----
PYODIDE_TGZ="$CACHE/pyodide-$PYODIDE_VERSION.tgz"
if [[ ! -f "$PYODIDE_TGZ" ]]; then
  echo "Pyodide $PYODIDE_VERSION を取得中（約10MB・初回のみ）…"
  curl -fsSL -o "$PYODIDE_TGZ" "https://registry.npmjs.org/pyodide/-/pyodide-$PYODIDE_VERSION.tgz"
fi

WHEEL_FILE=$(ls "$CACHE"/schemdraw-"$SCHEMDRAW_VERSION"-*.whl 2>/dev/null | head -1 || true)
if [[ -z "$WHEEL_FILE" ]]; then
  echo "schemdraw $SCHEMDRAW_VERSION wheel を取得中…"
  WHEEL_URL=$(curl -fsSL "https://pypi.org/pypi/schemdraw/$SCHEMDRAW_VERSION/json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(next(u['url'] for u in d['urls'] if u['filename'].endswith('py3-none-any.whl')))")
  WHEEL_FILE="$CACHE/$(basename "$WHEEL_URL")"
  curl -fsSL -o "$WHEEL_FILE" "$WHEEL_URL"
fi

VERSION=$(python3 -c "import json; print(json.load(open('package.json'))['version'])")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/extension/pyodide"

# circuitmd.py 本体を同梱（変換ロジックの単一ソース化）
cp package.json extension.js "$WORK/extension/"
cp ../circuitmd.py "$WORK/extension/"
cp "$WHEEL_FILE" "$WORK/extension/"

# Pyodide本体（Node実行に必要なファイルのみ）
tar -xzf "$PYODIDE_TGZ" -C "$WORK"
for f in pyodide.js pyodide.mjs pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json package.json; do
  cp "$WORK/package/$f" "$WORK/extension/pyodide/"
done
rm -rf "$WORK/package"

cat > "$WORK/[Content_Types].xml" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="js" ContentType="application/javascript"/>
  <Default Extension="mjs" ContentType="application/javascript"/>
  <Default Extension="py" ContentType="text/x-python"/>
  <Default Extension="wasm" ContentType="application/wasm"/>
  <Default Extension="zip" ContentType="application/zip"/>
  <Default Extension="whl" ContentType="application/zip"/>
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
echo "作成: $OUT ($(du -h "$OUT" | cut -f1 | tr -d ' '))"

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
