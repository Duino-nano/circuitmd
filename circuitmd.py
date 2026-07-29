#!/usr/bin/env python3
"""Markdown内の ```circuit フェンスをSVG回路図に変換するツール。

Mermaidのように「テキストで回路を書いて図でレンダリング」するための仕組み。
.md内の ```circuit ブロックに schemdraw 記法で回路を書き、このツールを実行すると
mdと同じディレクトリの circuits/ にSVGを生成し、フェンス直後に画像リンクを
自動挿入する。VSCodeのMarkdownプレビューやGitHubでそのまま回路図が見える。

依存: schemdraw（pip3 install --break-system-packages schemdraw）
      check サブコマンドだけなら schemdraw 無しでも動く。

使い方:
    circuitmd.py render <file.md> [<file2.md> ...]   # 指定mdを変換
    circuitmd.py render --dir <dir>                  # ディレクトリ以下の*.mdを再帰変換
    circuitmd.py check <file.md ...>                 # 構文チェックのみ（SVG生成・md書換なし）
    circuitmd.py check --dir <dir>
    circuitmd.py svg                                 # 標準入力の回路コード→標準出力にSVG
                                                     # （VSCodeプレビュー拡張 circuit-preview が使う）

記法（フェンス内のルール）:
    - 1行目に「title: 回路名」を書くと画像のalt文字列になる（省略可）
    - 簡易DSL行（推奨）: 「部品[:変数名] ラベル 方向 [@接続先] [オプション]」
        例: 抵抗 330Ω →  /  NPN Q1 loc=右  /  GND @Q1.emitter  /  分岐 ・ 合流
        方向: → ← ↑ ↓（right等・右左上下も可） 接続: @Q1.base や @(2,1.5)
        オプション: loc=下 len=1.5 tox=@X.end toy=@Y.end ofst=0.4(ラベルを線から離す)
                    rev(左右反転) flip(上下反転)
        先頭ラベル語が英数字名（Q1等）なら変数になり @Q1.base で参照できる
    - elm. / logic. / flow. / dsp. で始まる行は自動で「d += 」が付く（1行=1要素）
    - それ以外は素のPythonとして実行される。DSL行と自由に混在できる
    - ラベルの単位はΩ・μなどUnicodeを直接書く（$...$ のLaTeX記法は使わない）

記法リファレンスは README.md、実例集は circuit-sample.md を参照。

再実行しても安全（冪等）:
    - 生成した画像リンク行には <!-- circuit:auto --> マーカーが付き、再実行時は置換される
    - SVGファイル名は内容のハッシュ入り。内容が変わらなければ再生成しない
    - 内容変更で不要になった旧SVGは自動削除（自動生成の命名パターンに一致するものだけ）
"""

import argparse
import hashlib
import math
import re
import sys
import traceback
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

MARKER = "<!-- circuit:auto -->"
FENCE_RE = re.compile(r"^(`{3,})(\S*)\s*$")
AUTO_PREFIX_RE = re.compile(r"^(elm|logic|flow|dsp)\.|^\(")
TITLE_RE = re.compile(r"^title:\s*(.*)$")

# ---- 簡易DSL（人間が読み書きしやすい行形式。schemdraw記法と行単位で混在可） ----
# 書式:  部品[:変数名] [ラベル語...] [方向] [@接続先] [オプション]
# 例:    抵抗 330Ω →     /  NPN Q1 loc=右  /  GND @Q1.emitter  /  点:b1 @(2,1.5)
DSL_COMPONENTS = {
    "R": "Resistor()", "抵抗": "Resistor()",
    "C": "Capacitor()", "コンデンサ": "Capacitor()",
    "CP": "Capacitor(polar=True)", "電解コンデンサ": "Capacitor(polar=True)",
    "L": "Inductor()", "コイル": "Inductor()",
    "LED": "LED()",
    "D": "Diode()", "ダイオード": "Diode()",
    "ZD": "Zener()", "ツェナー": "Zener()",
    "SW": "Switch()", "スイッチ": "Switch()",
    "BTN": "Button()", "ボタン": "Button()",
    "V": "SourceV()", "電源": "SourceV()",
    "BAT": "Battery()", "電池": "Battery()",
    "GND": "Ground()", "グランド": "Ground()",
    "VDD": "Vdd()", "VCC": "Vdd()",
    "DOT": "Dot()", "点": "Dot()",
    "W": "Line()", "LINE": "Line()", "線": "Line()",
    "NPN": "BjtNpn(circle=True)", "PNP": "BjtPnp(circle=True)",
    "NMOS": "NFet()", "PMOS": "PFet()",
    "OPAMP": "Opamp()", "オペアンプ": "Opamp()",
    "MOTOR": "Motor()", "モータ": "Motor()", "モーター": "Motor()",
    "SPK": "Speaker()", "スピーカ": "Speaker()",
    "XTAL": "Crystal()", "水晶": "Crystal()",
    "FUSE": "Fuse()", "ヒューズ": "Fuse()",
    "POT": "Potentiometer()", "可変抵抗": "Potentiometer()",
}
DSL_DIRECTIONS = {
    "→": "right", "->": "right", "右": "right", "right": "right",
    "←": "left", "<-": "left", "左": "left", "left": "left",
    "↑": "up", "上": "up", "up": "up",
    "↓": "down", "下": "down", "down": "down",
}
DSL_LOC = {"上": "top", "下": "bottom", "左": "left", "右": "right"}
DSL_PUSH = {"分岐", "push"}
DSL_POP = {"合流", "戻る", "pop"}
DSL_OPT_RE = re.compile(r"^(len|loc|tox|toy|ofst)=(.+)$")
IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
RESERVED_NAMES = {"d", "elm", "logic", "flow", "dsp", "math", "schemdraw"}


def _dsl_ref(val: str) -> str:
    """@Q1.base → Q1.base、@(2,1.5) → (2,1.5)。@なしの数値はそのまま。"""
    return val[1:] if val.startswith("@") else val


def translate_dsl(line: str) -> str | None:
    """DSL行を schemdraw のPython 1行に変換する。DSLでなければ None。"""
    if line[:1] in (" ", "\t"):  # インデント行（forループ本体など）は対象外
        return None
    tokens = line.split()
    if not tokens:
        return None
    if len(tokens) == 1 and tokens[0] in DSL_PUSH:
        return "d.push()"
    if len(tokens) == 1 and tokens[0] in DSL_POP:
        return "d.pop()"

    head, _, name = tokens[0].partition(":")
    comp = DSL_COMPONENTS.get(head) or DSL_COMPONENTS.get(head.upper())
    if comp is None:
        return None

    calls: list[str] = []
    label_parts: list[str] = []
    label_loc = None
    label_ofst = None
    for tok in tokens[1:]:
        m = DSL_OPT_RE.match(tok)
        if tok in DSL_DIRECTIONS:
            calls.append(f".{DSL_DIRECTIONS[tok]}()")
        elif tok.startswith("@"):
            calls.append(f".at({_dsl_ref(tok)})")
        elif tok in ("flip", "上下反転"):
            calls.append(".flip()")
        elif tok in ("rev", "reverse", "反転", "左右反転"):
            calls.append(".reverse()")
        elif m:
            key, val = m.group(1), m.group(2)
            if key == "len":
                calls.append(f".length({val})")
            elif key == "loc":
                label_loc = DSL_LOC.get(val, val)
            elif key == "ofst":  # ラベルを線から離す。数値 or (x,y)（スペースなし）
                label_ofst = val
            else:  # tox / toy
                calls.append(f".{key}({_dsl_ref(val)})")
        else:
            label_parts.append(tok)

    if label_parts:
        text = " ".join(label_parts).replace("'", "\\'")
        loc_arg = f", loc='{label_loc}'" if label_loc else ""
        ofst_arg = f", ofst={label_ofst}" if label_ofst else ""
        calls.append(f".label('{text}'{loc_arg}{ofst_arg})")
        # 先頭ラベル語が識別子なら変数名を兼ねる（例: NPN Q1 → 変数Q1）
        if not name and IDENT_RE.match(label_parts[0]) and label_parts[0] not in RESERVED_NAMES:
            name = label_parts[0]

    expr = "elm." + comp + "".join(calls)
    if name and IDENT_RE.match(name) and name not in RESERVED_NAMES:
        return f"{name} = d.add({expr})"
    return f"d += {expr}"
LINK_FNAME_RE = re.compile(r"\(circuits/([^)]+\.svg)\)")
EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next"}


@dataclass
class Block:
    """mdファイル内の1つの ```circuit フェンスブロック。"""

    index: int  # ファイル内で何番目のcircuitブロックか（1始まり）
    fence_start: int  # 開始フェンスの行番号（0始まり）
    fence_end: int  # 閉じフェンスの行番号
    link_line: int | None  # 既存のマーカー付き画像リンク行（無ければNone）
    code: list[str] = field(default_factory=list)  # フェンス内の生テキスト


def parse_blocks(lines: list[str]) -> list[Block]:
    """行スキャンで ```circuit ブロックを収集する。

    正規表現一発ではなくステートマシンにするのは、````（4連フェンス）の中に
    書かれた ```circuit の例示を誤検出しないため。閉じ判定は「開始と同数以上の
    バッククォートのみの行」。
    """
    blocks = []
    in_fence = False
    fence_ticks = 0
    is_circuit = False
    start = 0
    code: list[str] = []

    for i, line in enumerate(lines):
        if not in_fence:
            m = FENCE_RE.match(line)
            if m:
                in_fence = True
                fence_ticks = len(m.group(1))
                is_circuit = m.group(2) == "circuit"
                start = i
                code = []
        else:
            m = FENCE_RE.match(line)
            if m and m.group(2) == "" and len(m.group(1)) >= fence_ticks:
                if is_circuit:
                    blocks.append(
                        Block(
                            index=len(blocks) + 1,
                            fence_start=start,
                            fence_end=i,
                            link_line=find_link_line(lines, i),
                            code=code,
                        )
                    )
                in_fence = False
            elif is_circuit:
                code.append(line)
    return blocks


def find_link_line(lines: list[str], fence_end: int) -> int | None:
    """閉じフェンス直後（空行を挟んで3行以内）の既存マーカー行を探す。"""
    for i in range(fence_end + 1, min(fence_end + 4, len(lines))):
        if MARKER in lines[i]:
            return i
        if lines[i].strip():  # マーカー以外の実体行が来たら打ち切り
            break
    return None


def transform(code_lines: list[str]) -> tuple[str, str]:
    """フェンス内テキストを実行用Pythonソースに変換する。(ソース, title) を返す。

    行数は絶対に変えない（エラー時の行番号をmd上の行と対応させるため）。
    """
    title = ""
    out = []
    in_meta = True  # 先頭の連続するメタ行だけ認識する
    for line in code_lines:
        if in_meta:
            m = TITLE_RE.match(line)
            if m:
                title = m.group(1).strip()
                # 「title: x」はPythonのアノテーション構文として黙って通って
                # しまうため、明示的にコメント化して無効にする
                out.append("# meta: " + line)
                continue
            in_meta = False
        dsl = translate_dsl(line)
        if dsl is not None:
            out.append(dsl)
        elif line.startswith("+= "):  # schemdraw-markdown互換の省略記法
            out.append("d " + line)
        elif AUTO_PREFIX_RE.match(line):
            out.append("d += " + line)
        else:
            out.append(line)
    return "\n".join(out), title


def hash8(src: str) -> str:
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:8]


def patch_cjk_width() -> None:
    """schemdrawの文字幅推定をCJK対応にする。

    svgtext.string_width() はASCII前提の文字幅テーブルで、全角文字を約45%に
    過小評価する（フォールバック75/1000em相当）。このままだと日本語ラベルで
    bboxが実際より狭く計算され、端のラベルが切れたり重なり判断がズレる。
    全角(W)・広角(F)文字1つにつき不足分(約0.55em)を加算して補正する。
    """
    from schemdraw.backends import svgtext

    if getattr(svgtext, "_cjk_patched", False):
        return
    orig = svgtext.string_width

    def string_width_cjk(st, fontsize=12, font="Arial"):
        base = orig(st, fontsize, font)
        wide = sum(1 for ch in st if unicodedata.east_asian_width(ch) in ("W", "F"))
        return base + wide * fontsize * 0.55

    svgtext.string_width = string_width_cjk
    svgtext._cjk_patched = True


SVG_VIEWBOX_RE = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"')

# ---- SVG後処理: ラベル重なりの自動回避 ----------------------------------
# schemdrawはラベルの衝突回避をしないため、生成後のSVGを解析して
# テキストと配線・他テキストの重なりを検出し、重なったラベルを最小移動量で
# 空き位置へ退避する。動かしきれないものは警告として報告する。

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _path_segments(d: str) -> list[tuple[float, float, float, float]]:
    """path のd属性を線分列に近似する（曲線は始点→終点の弦で代用）。"""
    segs = []
    cur = start = None
    for m in re.finditer(r"([MLCQAZmlcqaz])([^MLCQAZmlcqaz]*)", d):
        cmd, args = m.group(1).upper(), [float(v) for v in _FLOAT_RE.findall(m.group(2))]
        if cmd == "M" and len(args) >= 2:
            cur = start = (args[0], args[1])
            for i in range(2, len(args) - 1, 2):  # 暗黙のL
                nxt = (args[i], args[i + 1])
                segs.append((*cur, *nxt))
                cur = nxt
        elif cmd == "L":
            for i in range(0, len(args) - 1, 2):
                nxt = (args[i], args[i + 1])
                if cur:
                    segs.append((*cur, *nxt))
                cur = nxt
        elif cmd == "C":
            for i in range(0, len(args) - 5, 6):
                nxt = (args[i + 4], args[i + 5])
                if cur:
                    segs.append((*cur, *nxt))
                cur = nxt
        elif cmd == "Q":
            for i in range(0, len(args) - 3, 4):
                nxt = (args[i + 2], args[i + 3])
                if cur:
                    segs.append((*cur, *nxt))
                cur = nxt
        elif cmd == "A":
            for i in range(0, len(args) - 6, 7):
                nxt = (args[i + 5], args[i + 6])
                if cur:
                    segs.append((*cur, *nxt))
                cur = nxt
        elif cmd == "Z" and cur and start:
            segs.append((*cur, *start))
            cur = start
    return segs


def _seg_hits_rect(x1, y1, x2, y2, r) -> bool:
    rx0, ry0, rx1, ry1 = r
    if max(x1, x2) < rx0 or min(x1, x2) > rx1 or max(y1, y2) < ry0 or min(y1, y2) > ry1:
        return False
    if rx0 <= x1 <= rx1 and ry0 <= y1 <= ry1:
        return True
    if rx0 <= x2 <= rx1 and ry0 <= y2 <= ry1:
        return True

    def ccw(ax, ay, bx, by, cx, cy):
        return (by - ay) * (cx - ax) - (bx - ax) * (cy - ay)

    for ex0, ey0, ex1, ey1 in (
        (rx0, ry0, rx1, ry0), (rx1, ry0, rx1, ry1),
        (rx0, ry1, rx1, ry1), (rx0, ry0, rx0, ry1),
    ):
        d1 = ccw(x1, y1, x2, y2, ex0, ey0)
        d2 = ccw(x1, y1, x2, y2, ex1, ey1)
        d3 = ccw(ex0, ey0, ex1, ey1, x1, y1)
        d4 = ccw(ex0, ey0, ex1, ey1, x2, y2)
        if d1 * d2 <= 0 and d3 * d4 <= 0:
            return True
    return False


def _circle_hits_rect(cx, cy, cr, r) -> bool:
    rx0, ry0, rx1, ry1 = r
    nx = min(max(cx, rx0), rx1)
    ny = min(max(cy, ry0), ry1)
    return (cx - nx) ** 2 + (cy - ny) ** 2 <= cr * cr


class _SvgText:
    """SVG内の1ラベル（<text>と内部の<tspan>行）。"""

    def __init__(self, el):
        self.el = el
        self.x = float(el.get("x", "0"))
        self.y = float(el.get("y", "0"))
        self.fs = float(el.get("font-size", "14"))
        self.anchor = el.get("text-anchor", "start")
        self.baseline = el.get("dominant-baseline", "")
        self.lines = []  # (内容, yベースラインの相対位置)
        cum = 0.0
        tspans = [c for c in el if _localname(c.tag) == "tspan"]
        if tspans:
            for ts in tspans:
                cum += float(ts.get("dy", "0"))
                self.lines.append((ts.text or "", cum))
        else:
            self.lines.append((el.text or "", 0.0))
        self.dx = 0.0
        self.dy = 0.0

    def _width(self, s: str) -> float:
        from schemdraw.backends import svgtext

        return svgtext.string_width(s, fontsize=self.fs, font="sans")

    def bbox(self, dx=None, dy=None, pad=0.0):
        dx = self.dx if dx is None else dx
        dy = self.dy if dy is None else dy
        w = max((self._width(s) for s, _ in self.lines), default=0.0)
        if self.anchor == "middle":
            x0 = self.x - w / 2
        elif self.anchor == "end":
            x0 = self.x - w
        else:
            x0 = self.x
        ys = []
        for _, base in self.lines:
            b = self.y + base
            if self.baseline == "central":
                ys += [b - self.fs * 0.6, b + self.fs * 0.6]
            else:  # ideographic等: ベースラインが行の下端付近
                ys += [b - self.fs * 0.95, b + self.fs * 0.15]
        return (x0 + dx - pad, min(ys) + dy - pad, x0 + w + dx + pad, max(ys) + dy + pad)

    def apply(self):
        if self.dx == 0 and self.dy == 0:
            return
        self.el.set("x", f"{self.x + self.dx}")
        self.el.set("y", f"{self.y + self.dy}")
        for c in self.el:
            if _localname(c.tag) == "tspan" and c.get("x") is not None:
                c.set("x", f"{float(c.get('x')) + self.dx}")


def resolve_svg_overlaps(svg: str, margin: float = 10.0) -> tuple[str, list[str]]:
    """ラベルの重なりを自動回避したSVGと、解消できなかった警告一覧を返す。"""
    from xml.etree import ElementTree as ET

    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(svg)

    segs: list[tuple[float, float, float, float]] = []
    circles: list[tuple[float, float, float]] = []
    texts: list[_SvgText] = []
    for el in root.iter():
        name = _localname(el.tag)
        if name == "path" and el.get("d"):
            segs.extend(_path_segments(el.get("d")))
        elif name in ("polygon", "polyline") and el.get("points"):
            pts = [float(v) for v in _FLOAT_RE.findall(el.get("points"))]
            xy = list(zip(pts[0::2], pts[1::2]))
            for a, b in zip(xy, xy[1:] + ([xy[0]] if name == "polygon" else [])):
                segs.append((*a, *b))
        elif name == "line":
            segs.append(tuple(float(el.get(k, "0")) for k in ("x1", "y1", "x2", "y2")))
        elif name == "rect":
            x, y = float(el.get("x", "0")), float(el.get("y", "0"))
            w, h = float(el.get("width", "0")), float(el.get("height", "0"))
            segs += [(x, y, x + w, y), (x + w, y, x + w, y + h),
                     (x + w, y + h, x, y + h), (x, y + h, x, y)]
        elif name == "circle":
            circles.append((float(el.get("cx", "0")), float(el.get("cy", "0")),
                            float(el.get("r", "0"))))
        elif name == "ellipse":
            circles.append((float(el.get("cx", "0")), float(el.get("cy", "0")),
                            max(float(el.get("rx", "0")), float(el.get("ry", "0")))))
        elif name == "text":
            texts.append(_SvgText(el))

    def collides(t: _SvgText, dx, dy, pad) -> bool:
        r = t.bbox(dx, dy, pad)
        if any(_seg_hits_rect(*s, r) for s in segs):
            return True
        if any(_circle_hits_rect(*c, r) for c in circles):
            return True
        for o in texts:
            if o is t:
                continue
            ob = o.bbox(pad=0.5)
            if r[0] < ob[2] and r[2] > ob[0] and r[1] < ob[3] and r[3] > ob[1]:
                return True
        return False

    warnings = []
    # 大きく重なっているものから処理するため、まず衝突中のテキストを収集
    for t in texts:
        if not collides(t, t.dx, t.dy, pad=0.8):
            continue
        candidates = []
        for d in (4, 7, 10, 14, 18):
            candidates += [(0, -d), (0, d), (-d, 0), (d, 0),
                           (-d, -d), (d, -d), (-d, d), (d, d)]
        # 横スライドは同じ行に沿った移動で部品との対応が崩れにくいため、より遠くまで許す
        for d in (24, 32, 40):
            candidates += [(-d, 0), (d, 0), (0, -d)]
        for dx, dy in candidates:
            if not collides(t, dx, dy, pad=2.0):
                t.dx, t.dy = dx, dy
                break
        else:
            warnings.append(t.lines[0][0].strip() or "(無名ラベル)")
    for t in texts:
        t.apply()

    # viewBoxを再計算（移動後のラベルも含めて余白を確保）
    xs, ys = [], []
    m = SVG_VIEWBOX_RE.search(svg)
    if m:
        vx, vy, vw, vh = (float(v) for v in m.groups())
        xs += [vx, vx + vw]
        ys += [vy, vy + vh]
    for t in texts:
        b = t.bbox()
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    if xs:
        x0, y0 = min(xs) - margin, min(ys) - margin
        w, h = max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin
        root.set("viewBox", f"{x0} {y0} {w} {h}")
        root.set("width", f"{w}pt")
        root.set("height", f"{h}pt")

    out = ET.tostring(root, encoding="unicode")
    return out, warnings


def postprocess_svg(svg: str) -> tuple[str, list[str]]:
    """重なり自動回避＋余白確保。解析に失敗したら余白付与のみ行う。"""
    try:
        return resolve_svg_overlaps(svg)
    except Exception:
        return add_svg_margin(svg), []


def add_svg_margin(svg: str, margin: float = 10.0) -> str:
    """SVGのviewBoxを上下左右に広げ、端ぎりぎりのラベル切れを防ぐ（単位: pt）。"""
    m = SVG_VIEWBOX_RE.search(svg)
    if not m:
        return svg
    x, y, w, h = (float(v) for v in m.groups())
    x, y, w, h = x - margin, y - margin, w + 2 * margin, h + 2 * margin
    svg = svg[: m.start()] + f'viewBox="{x} {y} {w} {h}"' + svg[m.end() :]
    svg = re.sub(r'width="[\d.]+pt"', f'width="{w}pt"', svg, count=1)
    svg = re.sub(r'height="[\d.]+pt"', f'height="{h}pt"', svg, count=1)
    return svg


def load_schemdraw() -> dict:
    """schemdrawを遅延importしてexec用の基本namespaceを返す。"""
    try:
        import schemdraw
    except ImportError:
        sys.exit(
            "エラー: schemdraw が必要です。\n"
            "  pip3 install --break-system-packages schemdraw"
        )
    schemdraw.use("svg")  # matplotlib不要のSVGバックエンド
    # 白背景: ダークテーマのプレビュー対応 / lblofst: ラベルと線のクリアランス確保（既定0.1は近すぎる）
    schemdraw.config(bgcolor="white", lblofst=0.25)
    patch_cjk_width()
    from schemdraw import dsp, elements as elm, flow, logic

    return {
        "schemdraw": schemdraw,
        "elm": elm,
        "logic": logic,
        "flow": flow,
        "dsp": dsp,
        "math": math,
    }


def block_error_report(md_path: Path, block: Block, exc: Exception, compile_name: str) -> str:
    """例外からブロック内の行番号を特定して報告文字列を作る。"""
    lineno = None
    if isinstance(exc, SyntaxError) and exc.filename == compile_name:
        lineno = exc.lineno
    else:
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename == compile_name:
                lineno = frame.lineno  # 最後に一致したフレーム＝ブロック内の行
    msg = f"{type(exc).__name__}: {exc}"
    head = f"[NG] {md_path} ブロック{block.index} (md {block.fence_start + 1}行目〜)"
    if lineno is not None:
        report = f"{head} 内 {lineno}行目: {msg}"
        if 1 <= lineno <= len(block.code):
            report += f"\n     > {block.code[lineno - 1]}"
        return report
    return f"{head}: {msg}"


def render_block(
    block: Block, md_path: Path, out_dir: Path, base_ns: dict
) -> tuple[str | None, str, str | None, list[str]]:
    """1ブロックをSVGにする。(SVGファイル名, title, エラー文, 重なり警告) を返す。"""
    src, title = transform(block.code)
    title = title or f"circuit {block.index}"
    fname = f"{md_path.stem}-{block.index}-{hash8(src)}.svg"
    if (out_dir / fname).exists():
        return fname, title, None, []  # 内容不変なら再生成しない

    compile_name = f"<{md_path.name}#block{block.index}>"
    ns = dict(base_ns)
    ns["d"] = ns["schemdraw"].Drawing()
    try:
        code = compile(src, compile_name, "exec")
        exec(code, ns)  # 自分のドキュメント内の回路記述を実行するだけなので許容
    except Exception as exc:
        return None, title, block_error_report(md_path, block, exc, compile_name), []

    d = ns["d"]
    if not getattr(d, "elements", None):
        return None, title, f"[NG] {md_path} ブロック{block.index}: 要素が0個です（描画をスキップ）", []
    out_dir.mkdir(exist_ok=True)
    svg, warns = postprocess_svg(d.get_imagedata("svg").decode("utf-8"))
    (out_dir / fname).write_text(svg, encoding="utf-8")
    return fname, title, None, warns


def apply_links(lines: list[str], results: list[tuple[Block, str | None, str]]) -> list[str]:
    """画像リンクを挿入/置換する。行番号がずれないよう末尾のブロックから処理する。"""
    lines = list(lines)
    for block, fname, title in reversed(results):
        if fname is None:
            continue  # エラーブロックは既存リンクをそのまま残す
        safe_title = title.replace("[", "").replace("]", "")
        link = f"![{safe_title}](circuits/{fname}){MARKER}"
        if block.link_line is not None:
            lines[block.link_line] = link
        else:
            insertion = ["", link]
            nxt = block.fence_end + 1
            if nxt < len(lines) and lines[nxt].strip():
                insertion.append("")  # 直後に本文が続くなら段落を分ける
            lines[block.fence_end + 1 : block.fence_end + 1] = insertion
    return lines


def existing_svg_name(lines: list[str], block: Block) -> str | None:
    """既存リンク行から現在参照中のSVGファイル名を取り出す。"""
    if block.link_line is None:
        return None
    m = LINK_FNAME_RE.search(lines[block.link_line])
    return m.group(1) if m else None


def cleanup_svgs(out_dir: Path, stem: str, keep: set[str]) -> None:
    """自動生成パターンに一致し、今回使われなかったSVGだけを削除する。"""
    if not out_dir.is_dir():
        return
    pattern = re.compile(rf"^{re.escape(stem)}-\d+-[0-9a-f]{{8}}\.svg$")
    for f in out_dir.iterdir():
        if pattern.match(f.name) and f.name not in keep:
            f.unlink()
            print(f"  （旧SVGを削除: circuits/{f.name}）")


def check_file(md_path: Path, blocks: list[Block]) -> int:
    """構文チェックのみ。実行時エラー（NameError等）は検出できない。"""
    errors = 0
    for block in blocks:
        src, _ = transform(block.code)
        compile_name = f"<{md_path.name}#block{block.index}>"
        try:
            compile(src, compile_name, "exec")
            print(f"[OK] {md_path} ブロック{block.index}")
        except SyntaxError as exc:
            errors += 1
            print(block_error_report(md_path, block, exc, compile_name))
    return errors


def process_file(md_path: Path, check_only: bool, base_ns: dict | None) -> int:
    """1つのmdを処理してエラー数を返す。"""
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = parse_blocks(lines)
    if not blocks:
        return 0
    if check_only:
        return check_file(md_path, blocks)

    errors = 0
    keep: set[str] = set()
    results = []
    for block in blocks:
        fname, title, err, warns = render_block(block, md_path, md_path.parent / "circuits", base_ns)
        if err:
            errors += 1
            print(err)
            # エラー時は既存リンクが指すSVGを掃除対象から守る
            old = existing_svg_name(lines, block)
            if old:
                keep.add(old)
        else:
            keep.add(fname)
            print(f"[OK] {md_path} ブロック{block.index} → circuits/{fname}")
            for w in warns:
                print(f"  [警告] ブロック{block.index}: ラベル「{w}」の重なりを自動解消できませんでした（手動調整推奨）")
        results.append((block, fname, title))

    new_lines = apply_links(lines, results)
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    if new_text != text:
        md_path.write_text(new_text, encoding="utf-8")
        print(f"  （{md_path} に画像リンクを更新）")
    cleanup_svgs(md_path.parent / "circuits", md_path.stem, keep)
    return errors


def cmd_svg() -> None:
    """標準入力の回路コードをSVGにして標準出力へ。VSCodeプレビュー拡張用。"""
    code_lines = sys.stdin.read().splitlines()
    base_ns = load_schemdraw()
    src, _title = transform(code_lines)
    ns = dict(base_ns)
    ns["d"] = ns["schemdraw"].Drawing()
    compile_name = "<circuit>"
    try:
        exec(compile(src, compile_name, "exec"), ns)
    except Exception as exc:
        lineno = None
        if isinstance(exc, SyntaxError) and exc.filename == compile_name:
            lineno = exc.lineno
        else:
            for frame in traceback.extract_tb(exc.__traceback__):
                if frame.filename == compile_name:
                    lineno = frame.lineno
        msg = f"{type(exc).__name__}: {exc}"
        if lineno is not None:
            msg = f"{lineno}行目: {msg}"
            if 1 <= lineno <= len(code_lines):
                msg += f"\n> {code_lines[lineno - 1]}"
        sys.exit(msg)
    d = ns["d"]
    if not getattr(d, "elements", None):
        sys.exit("要素が0個です")
    svg, warns = postprocess_svg(d.get_imagedata("svg").decode("utf-8"))
    for w in warns:
        print(f"[警告] ラベル「{w}」の重なりを自動解消できませんでした", file=sys.stderr)
    sys.stdout.write(svg)


def iter_md_files(root: Path):
    for p in sorted(root.rglob("*.md")):
        if not EXCLUDE_DIRS.intersection(p.parts):
            yield p


def collect_targets(args) -> list[Path]:
    if args.dir:
        return list(iter_md_files(Path(args.dir)))
    if not args.files:
        sys.exit("エラー: mdファイルか --dir を指定してください")
    targets = []
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            sys.exit(f"エラー: ファイルが見つかりません: {f}")
        targets.append(p)
    return targets


def main():
    parser = argparse.ArgumentParser(description="Markdown内の```circuitフェンスをSVG回路図に変換")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("render", "SVGを生成してmdに画像リンクを挿入"),
        ("check", "構文チェックのみ（SVG生成・md書換なし）"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("files", nargs="*", help="対象のmdファイル")
        p.add_argument("--dir", help="ディレクトリ以下の*.mdを再帰処理")
    sub.add_parser("svg", help="標準入力の回路コード→標準出力にSVG（プレビュー拡張用）")

    args = parser.parse_args()
    if args.command == "svg":
        cmd_svg()
        return
    targets = collect_targets(args)
    check_only = args.command == "check"
    base_ns = None if check_only else load_schemdraw()

    errors = sum(process_file(p, check_only, base_ns) for p in targets)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
