---
name: circuitmd
description: >
  Markdownの```circuitフェンスに回路図をテキストで記述するスキル（circuitmd / schemdraw）。
  「回路図を描いて」「回路図を書いて」「配線図を作って」「この回路を図にして」
  「circuit記法」「回路をMarkdownに」「回路図が重なる・崩れた」「回路図をSVG/PNGにして」
  「Playgroundのリンクを作って」など、電子回路の図示・回路ドキュメント作成・
  回路図の修正やレンダリングを求められたときに必ず使用する。
---

# circuitmd — Markdownに回路図を書く

リポジトリ: https://github.com/Duino-nano/circuitmd ／ Playground: https://duino-nano.github.io/circuitmd/

```circuit フェンスに回路をテキストで書くと、schemdrawベースの教科書品質な回路図として
レンダリングされる。**フェンスのテキストが唯一のソース**であり、部品・定数・接続が
曖昧さなく記述されるため、AIはこの記法で回路を読み書きする。

## 表示系統（どれで見せるか）

| 環境 | 方法 |
|---|---|
| VSCode | 拡張 circuit-preview がプレビューでリアルタイム描画（Python不要・WASM同梱） |
| GitHub | `circuitmd.py render` が生成したSVGリンクで表示。**Action導入済みリポジトリならGitHub上で編集→自動更新** |
| ブラウザのみ | Playground（下記の共有リンク生成） |
| CLI | `circuitmd.py render <file.md>`（要 `pip install schemdraw`） |

## 記法リファレンス

基本は簡易DSL。1行=1部品。書式: `部品[:変数名] ラベル 方向 [@接続先] [オプション]`

````
```circuit
title: LED駆動回路
電源 3.3V ↑
抵抗 330Ω →
LED LED1 ↓ loc=下
線 ←
GND
```
````

- **方向**: `→ ← ↑ ↓`（`right/left/up/down`・`右/左/上/下` でも可）
- **部品名**: 日本語・略号・英語いずれも可（大文字小文字は不問）。
  `抵抗/R/resistor` `コンデンサ/C/capacitor` `電解コンデンサ/CP/polarcap` `コイル/L/inductor`
  `LED` `ダイオード/D/diode` `ツェナー/ZD/zener` `ショットキー/SBD/schottky`
  `スイッチ/SW/switch` `ボタン/BTN/button` `電源/V/source` `電池/BAT/battery`
  `GND/ground` `VDD/VCC` `点/DOT/dot` `線/W/line` `NPN` `PNP` `NMOS` `PMOS`
  `オペアンプ/OPAMP/opamp` `モータ/MOTOR/motor` `スピーカ/SPK/speaker` `水晶/XTAL/crystal`
  `ヒューズ/FUSE/fuse` `可変抵抗/POT/potentiometer` `ランプ/LAMP/lamp`
  ※`トランジスタ`/`FET` は曖昧なので不可 → NPN/PNP/NMOS/PMOS から選ぶ
- **接続**: `@Q1.base` `@(2,1.5)`（座標はスペースなし）。アンカーはBJTが `.base/.collector/.emitter`、
  FETが `.gate/.drain/.source`、2端子素子が `.start/.end`
- **変数名**: 先頭ラベル語が英数字名なら変数になる（`NPN Q1` → `@Q1.base` で参照）。
  表示しない名前は `点:b1` の形式で付ける
- **分岐**: `分岐` で現在位置を保存 → 枝を描く → `合流` で復帰
- **オプション**: `loc=下`（ラベル位置） `len=1.5`（長さ） `tox=@X.end` `toy=@Y.end`（座標合わせ）
  `ofst=0.4`（ラベルを線から離す） `rev`（左右反転） `flip`（上下反転）
- 1行目 `title: 回路名` は画像のalt（省略可）
- ラベルの単位はΩ・µなどUnicode直書き（`$...$` のLaTeX記法は不可）
- **ラベル内に単独の `→ ← ↑ ↓` を書かない**（方向指定として解釈される）。
  矢印付き文字列は `VOUT→LOAD` のように空白なしで書く
- **配線は斜めにしない**。接続先の座標を揃え `tox=`/`toy=` で直交させる（斜めだと警告が出る）
- **素のschemdraw記法（Python）と行単位で混在可**: `elm.` で始まる行は自動で `d += ` が付く。
  `q1 = d.add(elm.BjtNpn(circle=True).anchor('base').at((0,0)))` のような行もそのまま書ける。
  IC定義は `elm.Ic(pins=[elm.IcPin(name='OUT', side='right'), ...])`

## レイアウト規範（重なり防止）

ツールがラベル重なりを自動回避し、解消できない場合はrender時に `[警告]` を出す。
警告が出たラベル・最初から詰まりそうな箇所は以下で調整する:

- 縦素子のラベルは デフォルト=左 / `loc=下`=右。**隣接する縦素子はラベルを左右交互に**
- 長いレール（電源線）のラベルは素子列の真上を避け `ofst=0.4〜0.5` で線から離す
- `elm.Ic` の中央ラベル（loc='center'）は原則禁止 → `loc='top'`＋横ofstで箱の外へ。
  ピン名が角で衝突するときは `IcPin(..., pos=0.3)`（辺沿い相対位置0〜1）で明示配置。
  `w=`/`h=` を増やしてもピン間隔は広がらない（`pinspacing=1.5` とposが正解）
- 横向き素子のラベルが平行する上のレールに当たるときは素子の行自体を下げる
  （FETのドレインに縦スタブ0.7を入れる等）。行間は1.4unit以上
- 左右反転は `.reverse()`。`.flip()` は上下反転（トランジスタのC/Eが入れ替わる）
- ラベルの `ofst=(x,y)` タプルは素子ローカル座標系で直感に反するため使わない。
  `loc=` 付け替え・`\n` 2行化・スタブ挿入で調整する
- 並列素子（還流ダイオード等）は `線 → len=1.5` で横にオフセットしてから描く
- 日本語ラベルは英数字の約2倍幅。長い和文ラベルの隣に素子列を置かない（列間2〜2.5unit）

## 描画の落とし穴（素のschemdraw記法を混ぜるとき）

実際の設計書作成で踏んだもの。図が「なぜか回る・二重になる・向きが逆」になったら疑う。

- **要素は直前の描画方向を継承して回転する**。直前が `線 ↓` の状態で `elm.NFet()` を置くと
  FETが90度倒れる → **`.right()` を明示**してから `.reverse()` / `.anchor()` を付ける。
  （DSLの `NMOS Q1` 等はツールが自動で `.right()` を補うので発生しない）
  `elm.NFet()` は既定でゲートが**右**（左にしたいなら `.right().reverse()`）
- **`elm.Label(label='X')` はテキストが二重描画される** → `elm.Label().at(...).label('X')` の
  メソッド形式で書く
- **`elm.Ic` の `IcPin(pos=)` は複数ピン構成だと効かないことがある** → IC名がピンのリード線と
  重なるなら、独立した `elm.Label()` を箱の脇に置く
- **ツェナー/TVSを `↓`（レール→GND）で描くとカソードがGND側**になる（保護素子として逆向き）
  → `rev` を付けてカソードを電源側にする

## AIの作業手順（必ず守る）

1. 回路をフェンスに書く（接続関係の一文をフェンス前のプレーンテキストにも添える）
2. `circuitmd.py render <file.md>` を実行（SVG生成＋リンク自動挿入。冪等）
   - CLI本体の場所: **このスキルフォルダ内に `circuitmd.py` が同梱されていればそれを使う**
     （claude.aiアップロード用zip等）。symlink導入なら
     `"$(readlink -f ~/.claude/skills/circuitmd)/../../circuitmd.py"` がリポジトリ内の本体。
     いずれも無ければ `git clone https://github.com/Duino-nano/circuitmd`（要 `pip install schemdraw`）
3. **PNG化して必ず目視検証してから納品する**（macOSの例。qlmanageは横長図を
   正方形クロップするので使わない）:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
     --screenshot=/tmp/check.png --window-size=1400,900 "file://$PWD/circuits/xxx.svg"
   pkill -f "Google Chrome.*--headless"   # 後始末（残留するとブラウザ自動操作を横取りする）
   ```
   `--screenshot` は撮影後に自プロセスが終了するが、`--remote-debugging-port` を使う場合は
   必ず後始末する。macOSに `timeout` コマンドは無いので前置しない（コマンドごと失敗する）
4. `[警告]` が出たラベルだけ上記の規範で調整して再render
5. GitHubで見せる場合はSVG（circuits/）ごとコミット

renderするとフェンスは `<details><summary>回路コード</summary>` で自動的に包まれ、
その下に画像リンクが入る（GitHubでは回路図＋「▶ 回路コード」の1行だけが見える形）。
**この `<details>` は手で外さない**——再renderで戻る。編集は展開したフェンスをそのまま直す。
VSCodeプレビューでは拡張が自動で展開表示するので、ライブ編集の見え方は変わらない。

## 図をユーザーに表示する方法（環境別）

**実行環境あり（Claude Code等）**: renderしたSVGをそのまま見せられない場合は、
SVGを埋め込んだHTMLをArtifactとして公開するか、PNG化して開く。

**実行環境なし（claude.aiチャット等）**: Playgroundの共有リンクを生成して返す。
回路コードをUTF-8のままbase64エンコードし、以下のURLにする（計算のみ・実行不要）:

```
https://duino-nano.github.io/circuitmd/#code=<base64>
```

例（Pythonなら）: `base64.b64encode(code.encode('utf-8')).decode()`
リンクを開くとブラウザ内で描画される（スマホ可・初回のみエンジン取得で数秒）。

## 新しいリポジトリへの導入（GitHub上で編集→自動更新）

`.github/workflows/render.yml` を1つ置くだけ:

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

以後、GitHubのWebエディタでフェンスを編集→Commitすると、約30〜60秒でSVGが自動更新される。

## トラブルシューティング

- **`N行目: NameError: name 'em' is not defined`** など → フェンス内の該当行を修正
  （エラーはブロック内の行番号で報告される）
- **図がGitHubで古いまま** → render未実行。Action導入済みならpush後1分待つ。
  未導入ならローカルで `render` してSVGをコミット
- **VSCodeプレビューで「エンジン起動中…」のまま** → 数秒待つ（WASM初回ロード）。
  変わらなければウィンドウ再読み込み
- **拡張更新が効かない** → vsix再インストール後は必ず「開発者: ウィンドウの再読み込み」
- **部品がDSLに無い** → 素のschemdraw記法で書く（elm.Ic、elm.Opamp等。混在可）
