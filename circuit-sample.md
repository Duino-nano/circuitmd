# circuit記法サンプル集

`circuitmd.py` の動作検証用サンプル兼、```circuit フェンス記法の実例集。
編集したら `./circuitmd.py render circuit-sample.md`（このディレクトリで実行） で再生成する。

基本は簡易DSL「`部品 ラベル 方向`」で書く。1行=1部品。
方向は `→ ← ↑ ↓`（`right` や `右` でも可）、接続は `@変数.アンカー`、分岐は `分岐`／`合流`。
複雑な箇所は素のschemdraw記法（Python）と行単位で自由に混在できる。

## 1. LED駆動回路（基本形）

```circuit
title: LED駆動回路
電源 3.3V ↑
抵抗 220Ω →
LED LED1 ↓ loc=下
線 ←
GND
```

![LED駆動回路](circuits/circuit-sample-1-61fd7ded.svg)<!-- circuit:auto -->

## 2. GPIOプルアップ＋タクトスイッチ

`分岐` で現在位置を保存し、枝を描いたら `合流` で戻る。

```circuit
title: GPIOプルアップ回路
VDD 3.3V
抵抗 10kΩ ↓
点
分岐
線 GPIO4 → loc=右
合流
スイッチ SW1 ↓ loc=下
GND
```

![GPIOプルアップ回路](circuits/circuit-sample-2-55b5fb30.svg)<!-- circuit:auto -->

## 3. NPNトランジスタによるモータ駆動

先頭ラベルが英数字名（Q1など）ならその名前の変数になり、`@Q1.base` のように接続できる。
表示したくない名前は `部品:変数名` で付ける（例: `ダイオード:FW`）。

```circuit
title: NPNモータ駆動回路
NPN Q1 loc=右
抵抗 1kΩ ← @Q1.base
線 GPIO ← len=0.5 loc=左
GND @Q1.emitter
モータ M ↑ @Q1.collector
VDD 5V @M.end
点 @M.start
点 @M.end
線 → @M.start len=1.5
ダイオード:FW 1N4001 ↑ loc=下
線 ← @FW.end len=1.5
```

![NPNモータ駆動回路](circuits/circuit-sample-3-9a23684e.svg)<!-- circuit:auto -->

## 4. 非安定マルチバイブレーター（LED交互点滅）

2石のNPNトランジスタをたすき掛け（C1: Q1コレクタ→Q2ベース、C2: Q2コレクタ→Q1ベース）
した定番の発振回路。LED1とLED2が交互に点滅する。
点滅周期 T ≈ 0.693 × (R2·C1 + R3·C2) ≈ 0.65秒（約1.5Hz）。

対称レイアウトは `@(x,y)` の座標指定で組む（座標はスペースを入れず書く）。
トランジスタの向き反転（`.reverse()`=左右、`.flip()`=上下でC/Eが入れ替わる）など
細かい制御は素のschemdraw行で書き、残りはDSLで書く「混在スタイル」の例。

```circuit
title: 非安定マルチバイブレーター（LED交互点滅）
d.config(unit=2)
q1 = d.add(elm.BjtNpn(circle=True).reverse().anchor('base').at((0, 0)).label('Q1', loc='left'))
q2 = d.add(elm.BjtNpn(circle=True).anchor('base').at((7, 0)).label('Q2', loc='right'))
GND @q1.emitter
GND @q2.emitter
線 ↑ @q1.collector len=1
点:c1tap
線 ↑ @q2.collector len=1
点:c2tap
抵抗 R1 470Ω ↑ @c1tap.center
LED LED1 ↑
抵抗 R4 470Ω ↑ @c2tap.center loc=下
LED LED2 ↑ loc=下
線 @LED1.end tox=@LED2.end
点 @(3.5,LED1.end.y)
VDD 5V @(3.5,LED1.end.y)
jy = c1tap.center.y
点:b1 @(2,jy)
点:b2 @(5,jy)
点 @(2,LED1.end.y)
点 @(5,LED1.end.y)
抵抗 R2 10kΩ ↑ @b1.center toy=@LED1.end
抵抗 R3 10kΩ ↑ @b2.center toy=@LED1.end loc=下
コンデンサ C1 47µF ← @b1.center tox=@c1tap.center
コンデンサ C2 47µF → @b2.center tox=@c2tap.center
線 ↓ @b1.center toy=@q2.base
線 → tox=@q2.base
線 ↓ @b2.center len=0.8
線 ← tox=@q1.base
線 ↓ toy=@q1.base
```

![非安定マルチバイブレーター（LED交互点滅）](circuits/circuit-sample-4-67064b95.svg)<!-- circuit:auto -->
