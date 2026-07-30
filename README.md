# circuitmd

**Markdownに、Mermaid感覚で回路図を書く。**

.md内の ```` ```circuit ```` フェンスに回路をテキストで書くと、
[schemdraw](https://schemdraw.readthedocs.io/) ベースの教科書品質な回路図としてレンダリングされます。

- **▶ [Web Playground](https://duino-nano.github.io/circuitmd/)** … インストール不要。ブラウザで書いて即プレビュー、SVG/PNGダウンロード
- **VSCode拡張** … Markdownプレビューでフェンスをリアルタイム描画（1ブロック約50ms）。
  **Pythonのインストール不要**（WASMエンジン同梱。ローカルにPythonがあれば自動でそちらを優先）
- **CLI** … SVGファイル生成＋画像リンク自動挿入。GitHub上でもそのまま回路図が表示される

```
電源 3.3V ↑
抵抗 330Ω →
LED LED1 ↓ loc=下
線 ←
GND
```

↓ こう描画されます

![LED駆動回路](docs/sample-led.svg)

もう少し複雑な例（非安定マルチバイブレーター）:

![非安定マルチバイブレーター](docs/sample-multivibrator.svg)

記法の実例は [circuit-sample.md](circuit-sample.md) を参照（このファイル自体がツールで変換されています）。

## なぜ作ったか

- AI（Claude等）に回路を質問すると文章で返ってきてイメージしづらい。テキストベースの回路図記法があれば、AIは正確に読み書きでき、人間は図で確認できる
- Mermaidは回路図に非対応（[mermaid#2112](https://github.com/mermaid-js/mermaid/issues/2112)）
- KiCadを起動するほどでもないメモ・ドキュメント・記事に回路図を残したい

## インストール

### お試しだけなら → [Web Playground](https://duino-nano.github.io/circuitmd/)

インストール不要。ブラウザ内でPython(WASM)＋schemdrawが動くため、描画結果はローカル版と
完全に同一です。SVG/PNGのダウンロードもここでできます。

### VSCode拡張（リアルタイムプレビュー・Python不要）

```bash
git clone https://github.com/Duino-nano/circuitmd.git
cd circuitmd/circuit-preview-ext
./build_vsix.sh                # vsix作成 + インストールまで実行（ビルドにはcurl/python3を使用）
```

拡張にはWASMエンジン（Pyodide＋schemdraw）が同梱されており、**利用側の環境にPythonが
なくても動きます**。ローカルにpython3があれば自動でそちらを優先（起動が速い）。
検証用に環境変数 `CIRCUITMD_FORCE_WASM=1` でWASM経路を強制できます。

実行後、VSCodeのウィンドウを再読み込み（⌘⇧P →「開発者: ウィンドウの再読み込み」）すると、
Markdownプレビュー（⇧⌘V）で ```circuit フェンスが回路図として表示されます。編集は即反映されます。

### CLI（SVGファイル化・GitHub公開用。こちらはPython 3.10+が必要）

```bash
pip install schemdraw               # 描画エンジン（matplotlib不要のSVGバックエンドを使用）
./circuitmd.py render <file.md>     # mdと同階層の circuits/ にSVG生成＋画像リンク自動挿入
./circuitmd.py render --dir <dir>   # ディレクトリ以下を再帰処理
./circuitmd.py check <file.md>      # 構文チェックのみ
```

- 再実行しても安全（冪等）: 生成リンクはマーカー付きで置換され、SVGは内容ハッシュ名で管理、
  不要になった旧SVGは自動削除
- 生成SVGをコミットすれば、GitHub上でも回路図が表示されます（プレビュー拡張はこの
  自動リンクを隠すので二重表示になりません）

### GitHub Action（GitHub上の編集だけで図が更新される）

このリポジトリはGitHub Actionとしても使えます。`.github/workflows/render.yml` を1つ置くだけ:

```yaml
name: render circuits
on:
  push:
    branches: [main]
    paths: ["**.md"]
permissions:
  contents: write
concurrency:
  group: circuitmd-render
  cancel-in-progress: true
jobs:
  render:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Duino-nano/circuitmd@main
```

以後、**GitHubのWebエディタで ```circuit フェンスを編集してコミットするだけ**で、
Actionがクラウドでレンダリングし、SVGと画像リンクを自動コミットします（約30〜60秒）。
ローカル環境は一切不要です。入力: `dir`（対象ディレクトリ、既定 `.`）、`commit`（自動コミット、既定 `true`）。

### AIスキル（Claude用）

[`skills/circuitmd/`](skills/circuitmd/) に、AIがこの記法・レイアウト規範・検証手順を
正しく扱うためのスキル定義を同梱しています。Claude Code なら:

```bash
mkdir -p ~/.claude/skills
cp -r skills/circuitmd ~/.claude/skills/   # またはリポジトリへのsymlink
```

以後「回路図を描いて」と頼むだけで、AIがこの記法で描き、レンダリング・目視検証・
Playground共有リンク生成まで正しい手順で行います。

## 記法リファレンス

### 簡易DSL（基本）

1行=1部品。書式: `部品[:変数名] ラベル 方向 [@接続先] [オプション]`

| 要素 | 書き方 |
|---|---|
| 方向 | `→ ← ↑ ↓`（`right/left/up/down`・`右/左/上/下` でも可） |
| 部品名 | `抵抗/R` `コンデンサ/C` `電解コンデンサ/CP` `コイル/L` `LED` `ダイオード/D` `ツェナー/ZD` `スイッチ/SW` `ボタン/BTN` `電源/V` `電池/BAT` `GND` `VDD/VCC` `点/DOT` `線/W` `NPN` `PNP` `NMOS` `PMOS` `オペアンプ/OPAMP` `モータ/MOTOR` `スピーカ/SPK` `水晶/XTAL` `ヒューズ/FUSE` `可変抵抗/POT` |
| 接続 | `@Q1.base` `@(2,1.5)`（座標はスペースなし）。アンカーはBJTが `.base/.collector/.emitter`、FETが `.gate/.drain/.source`、2端子素子が `.start/.end` |
| 変数名 | 先頭ラベル語が英数字名なら変数になる（`NPN Q1` → `@Q1.base` で参照可）。表示しない名前は `点:b1` の形式 |
| 分岐 | `分岐` で現在位置を保存 → 枝を描く → `合流` で復帰（`push`/`pop` でも可） |
| オプション | `loc=下`（ラベル位置） `len=1.5`（長さ） `tox=@X.end` `toy=@Y.end`（座標合わせ） `ofst=0.4`（ラベルを線から離す） `rev`（左右反転） `flip`（上下反転） |

- 1行目に `title: 回路名` を書くと画像のaltになる（省略可）
- ラベルの単位はΩ・μなどUnicodeを直書き（`$...$` のLaTeX記法は不可）

### 素のschemdraw記法（細かい制御用）

DSLと**行単位で自由に混在**できます。

- `elm.` / `logic.` / `flow.` / `dsp.` で始まる行は自動で `d += ` が付く
- それ以外は素のPythonとして実行（`d` = `schemdraw.Drawing`）
- DSLにない要素・制御はこちらで: `elm.Ic(pins=[...])`、`elm.Opamp()`、`.anchor('base')`、
  `d.config(unit=2)` など。詳細は [schemdrawのドキュメント](https://schemdraw.readthedocs.io/) 参照

混在例（[circuit-sample.md](circuit-sample.md) のマルチバイブレーターより抜粋）:

```
d.config(unit=2)
q1 = d.add(elm.BjtNpn(circle=True).reverse().anchor('base').at((0, 0)).label('Q1', loc='left'))
GND @q1.emitter
線 ↑ @q1.collector len=1
点:c1tap
抵抗 R1 470Ω ↑ @c1tap.center
LED LED1 ↑
```

### ラベル重なりの自動回避

schemdraw 自体はラベルの衝突回避をしませんが、circuitmd は**SVG生成後に全ラベルと
配線・記号・他ラベルの衝突を検出し、重なったラベルを最小移動量で自動退避**します
（部品との対応が崩れないよう移動量は上限付き）。自動で逃がしきれない重なりは
レンダリング時に警告として報告されるので、下記のコツで手動調整してください。

```
[OK] docs/wiring.md ブロック2 → circuits/wiring-2-xxxx.svg
  [警告] ブロック2: ラベル「SW1」の重なりを自動解消できませんでした（手動調整推奨）
```

### ラベル配置のコツ（警告が出たときの手動調整）

- 縦素子のラベルは デフォルト=左 / `loc=下`=右。**隣接する縦素子はラベルを左右交互に**振ると重ならない
- 長いレール（電源線）のラベルは素子列の真上を避け、`ofst=0.4` 程度で線から離す
- `elm.Ic` の中央ラベル（`loc='center'`）はピン名と衝突しやすい → `loc='top'` で箱の外へ。
  同一辺に複数のピン名があるICは `pinspacing=1.5` 等で間隔を広げる
- 長いラベルは `\n` で2行に割ると幅が半分になる
- 日本語ラベルの文字幅・SVG余白はツール側で自動補正される（schemdraw素のままだと
  全角文字の幅が過小評価され、端のラベルが切れる）

## 仕組みと注意点

- VSCode拡張は markdown-it プラグインとして動き、フェンス内容を同梱の `render_svg.py` に
  渡してSVGを受け取り、**プレビューHTMLにインライン埋め込み**します（画像ファイルを経由
  しないため、プレビューのローカルリソース制限の影響を受けません）。内容ハッシュで
  キャッシュするため再描画は瞬時です
- レンダラを拡張に同梱しているのは、macOSのTCC（フォルダアクセス制限）でVSCodeの
  子プロセスから書類フォルダ等のスクリプトを読めないことがあるためです
- 拡張は `circuitmd.py` 本体をビルド時に同梱する方式（単一ソース）。`circuitmd.py` を
  変更したら `build_vsix.sh` を再実行するだけで反映されます
- フェンス内容は `exec()` で実行されます。**信頼できないMarkdownに対して実行しないでください**

## ライセンス

MIT
