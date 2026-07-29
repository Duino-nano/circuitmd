#!/usr/bin/env python3
"""circuit-preview 拡張用のスタンドアロンSVGレンダラ。

標準入力の ```circuit フェンス内容（簡易DSL＋schemdraw記法）をSVGにして標準出力へ出す。
circuitmd.py の svg サブコマンドと同じ変換ルール。

macOSのTCC（フォルダアクセス制限）でVSCodeの子プロセスから Documents 配下の
circuitmd.py が読めない環境でも動くよう、拡張パッケージ内に同梱して使う。
本家 circuitmd.py の変換ルール（transform / translate_dsl）を変えたらこちらも合わせること。
"""

import math
import re
import sys
import traceback

AUTO_PREFIX_RE = re.compile(r"^(elm|logic|flow|dsp)\.|^\(")
TITLE_RE = re.compile(r"^title:\s*(.*)$")

# ---- 簡易DSL（circuitmd.py と同一内容） ----
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
DSL_OPT_RE = re.compile(r"^(len|loc|tox|toy)=(.+)$")
IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
RESERVED_NAMES = {"d", "elm", "logic", "flow", "dsp", "math", "schemdraw"}


def _dsl_ref(val):
    return val[1:] if val.startswith("@") else val


def translate_dsl(line):
    """DSL行を schemdraw のPython 1行に変換する。DSLでなければ None。"""
    if line[:1] in (" ", "\t"):
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

    calls = []
    label_parts = []
    label_loc = None
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
            else:  # tox / toy
                calls.append(f".{key}({_dsl_ref(val)})")
        else:
            label_parts.append(tok)

    if label_parts:
        text = " ".join(label_parts).replace("'", "\\'")
        loc_arg = f", loc='{label_loc}'" if label_loc else ""
        calls.append(f".label('{text}'{loc_arg})")
        if not name and IDENT_RE.match(label_parts[0]) and label_parts[0] not in RESERVED_NAMES:
            name = label_parts[0]

    expr = "elm." + comp + "".join(calls)
    if name and IDENT_RE.match(name) and name not in RESERVED_NAMES:
        return f"{name} = d.add({expr})"
    return f"d += {expr}"


def transform(code_lines):
    """フェンス内テキストを実行用Pythonソースに変換する（行数不変）。"""
    out = []
    in_meta = True
    for line in code_lines:
        if in_meta:
            if TITLE_RE.match(line):
                out.append("# meta: " + line)
                continue
            in_meta = False
        dsl = translate_dsl(line)
        if dsl is not None:
            out.append(dsl)
        elif line.startswith("+= "):
            out.append("d " + line)
        elif AUTO_PREFIX_RE.match(line):
            out.append("d += " + line)
        else:
            out.append(line)
    return "\n".join(out)


def main():
    code_lines = sys.stdin.read().splitlines()
    try:
        import schemdraw
    except ImportError:
        sys.exit("schemdraw が見つかりません: pip3 install --break-system-packages schemdraw")
    schemdraw.use("svg")
    schemdraw.config(bgcolor="white")
    from schemdraw import dsp, elements as elm, flow, logic

    d = schemdraw.Drawing()
    ns = {
        "schemdraw": schemdraw,
        "elm": elm,
        "logic": logic,
        "flow": flow,
        "dsp": dsp,
        "math": math,
        "d": d,
    }
    compile_name = "<circuit>"
    try:
        exec(compile(transform(code_lines), compile_name, "exec"), ns)
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
    sys.stdout.write(d.get_imagedata("svg").decode("utf-8"))


main()
