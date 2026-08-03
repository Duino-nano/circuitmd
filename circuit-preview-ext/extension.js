// Circuit Preview — Markdownプレビューで ```circuit フェンスを回路図としてレンダリングする拡張。
// 描画は同梱の circuitmd.py（schemdraw）に委譲し、返ってきたSVGをプレビューHTMLに
// 直接インライン埋め込みする。内容ハッシュでキャッシュするため再描画は瞬時。
//
// レンダラは2系統:
//   1. ローカルPython（あれば優先。高速・省メモリ）
//   2. 同梱Pyodide（WASM）。Pythonが無い環境でも拡張だけで動く。
//      初回はエンジン起動に数秒かかるため、プレースホルダを返してロード完了後に
//      プレビューを自動リフレッシュする。
// 環境変数 CIRCUITMD_FORCE_WASM=1 でWASM経路を強制できる（検証用）。

const { execFileSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

// circuitmd.py 本体を拡張内に同梱して使う（ビルド時にコピーされる）。
// Documents配下を直接参照するとmacOSのTCCでVSCodeの子プロセスから読めないことが
// あるための同梱方式。svgサブコマンドは標準入力→標準出力で完結し、ファイル不要。
const SCRIPT = path.join(__dirname, "circuitmd.py");
const PYODIDE_DIR = path.join(__dirname, "pyodide");
const PYTHON_CANDIDATES = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"];
const FORCE_WASM = process.env.CIRCUITMD_FORCE_WASM === "1";

const cache = new Map(); // 内容ハッシュ → 描画済みHTML

function pythonPath() {
  if (FORCE_WASM) return null;
  for (const p of PYTHON_CANDIDATES) {
    if (fs.existsSync(p)) return p;
  }
  return null; // 見つからなければWASMへ
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function svgHtml(svg) {
  return (
    '<div class="circuit-diagram" style="background:#fff;display:inline-block;' +
    'padding:14px;border-radius:6px;max-width:100%;overflow-x:auto;margin:4px 0">' +
    svg +
    "</div>"
  );
}

function errorHtml(msg) {
  return (
    '<pre style="border:1px solid #d66;border-radius:6px;padding:10px;' +
    'color:#d66;white-space:pre-wrap">circuit描画エラー\n' +
    escapeHtml(String(msg).trim()) +
    "</pre>"
  );
}

// ---- WASMエンジン（Pyodide） ----------------------------------------------
let wasmEngine = null;        // 初期化完了後の pyodide インスタンス
let wasmLoadPromise = null;   // ロード中のPromise（多重起動防止）
let wasmLoadError = null;

function startWasmEngine() {
  if (wasmLoadPromise) return;
  wasmLoadPromise = (async () => {
    const { loadPyodide } = require(path.join(PYODIDE_DIR, "pyodide.js"));
    const py = await loadPyodide({ indexURL: PYODIDE_DIR });
    // schemdraw wheel（同梱）をsite-packagesへ展開
    const wheelName = fs.readdirSync(__dirname).find((f) => f.endsWith(".whl"));
    if (!wheelName) throw new Error("同梱のschemdraw wheelが見つかりません");
    const buf = fs.readFileSync(path.join(__dirname, wheelName));
    await py.unpackArchive(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), "wheel");
    // 同梱circuitmd.pyを読み込み
    py.FS.writeFile("/home/pyodide/circuitmd.py", fs.readFileSync(SCRIPT, "utf8"));
    py.runPython(
      "import json, circuitmd\n" +
      "def _render(text):\n" +
      "    try:\n" +
      "        svg, warns = circuitmd.render_source(text)\n" +
      "        return json.dumps({'svg': svg, 'warnings': list(warns)})\n" +
      "    except circuitmd.CircuitError as e:\n" +
      "        return json.dumps({'error': str(e)})\n"
    );
    wasmEngine = py;
  })();
  wasmLoadPromise
    .catch((e) => {
      wasmLoadError = e;
    })
    .finally(() => {
      // エンジン準備完了（or失敗）後にプレビューを再描画してプレースホルダを差し替える
      try {
        require("vscode").commands.executeCommand("markdown.preview.refresh");
      } catch (_) {
        /* markdownプレビュー以外の文脈では無視 */
      }
    });
}

function renderWithWasm(code) {
  wasmEngine.globals.set("_SRC", code);
  const res = JSON.parse(wasmEngine.runPython("_render(_SRC)"));
  if (res.error) return errorHtml(res.error);
  return svgHtml(res.svg);
}

// ---- フェンス→HTML ---------------------------------------------------------
function renderCircuit(code) {
  const key = crypto.createHash("sha1").update(code).digest("hex");
  if (cache.has(key)) return cache.get(key);

  let html;
  const py = pythonPath();
  if (py) {
    // ローカルPython経路（従来どおり）
    try {
      const svg = execFileSync(py, [SCRIPT, "svg"], {
        input: code,
        timeout: 15000,
        encoding: "utf8",
      });
      html = svgHtml(svg);
    } catch (e) {
      html = errorHtml(e.stderr ? e.stderr.toString() : e.message);
    }
  } else if (wasmEngine) {
    // WASM経路（ロード済み）
    try {
      html = renderWithWasm(code);
    } catch (e) {
      html = errorHtml(e.message || e);
    }
  } else if (wasmLoadError) {
    html = errorHtml("WASMエンジンの起動に失敗しました: " + wasmLoadError.message);
  } else {
    // WASMエンジンを起動しつつプレースホルダを返す（キャッシュしない）
    startWasmEngine();
    return (
      '<div style="border:1px dashed #888;border-radius:6px;padding:14px;color:#888">' +
      "⏳ 回路図エンジン（WASM）を起動中… 数秒後に自動で表示されます</div>"
    );
  }

  if (cache.size > 300) cache.clear(); // 雑でよい上限（1エントリ数KB）
  cache.set(key, html);
  return html;
}

exports.activate = function () {
  return {
    extendMarkdownIt(md) {
      // ```circuit フェンスをSVGに置き換える
      const defaultFence =
        md.renderer.rules.fence ||
        function (tokens, idx, options, env, self) {
          return self.renderToken(tokens, idx, options);
        };
      md.renderer.rules.fence = (tokens, idx, options, env, self) => {
        if (tokens[idx].info.trim() === "circuit") {
          return renderCircuit(tokens[idx].content);
        }
        return defaultFence(tokens, idx, options, env, self);
      };

      // render が付ける <details> は、GitHubで構文を畳んで回路図だけ見せるためのもの。
      // 編集中のプレビューでは図が見えないと困るので、circuitフェンスを含む details は
      // open 属性を足して展開状態で表示する（mdファイル自体は書き換えない）。
      md.core.ruler.push("open_circuit_details", (state) => {
        const toks = state.tokens;
        for (let i = 0; i < toks.length; i++) {
          const t = toks[i];
          if (t.type !== "html_block" || !/<details(?![^>]*\bopen\b)/.test(t.content)) continue;
          for (let j = i + 1; j < toks.length; j++) {
            if (toks[j].type === "html_block" && toks[j].content.includes("</details>")) break;
            if (toks[j].type === "fence" && toks[j].info.trim() === "circuit") {
              t.content = t.content.replace("<details", "<details open");
              break;
            }
          }
        }
      });

      // circuitmd.py render が挿入した ![...](circuits/xxx.svg)<!-- circuit:auto --> は
      // プレビューではフェンス側で描画済みなので隠す（二重表示防止）
      md.core.ruler.push("hide_circuit_auto_links", (state) => {
        for (const blockToken of state.tokens) {
          if (blockToken.type !== "inline" || !blockToken.children) continue;
          const ch = blockToken.children;
          for (let i = 0; i < ch.length; i++) {
            const next = ch[i + 1];
            if (
              ch[i].type === "image" &&
              next &&
              next.type === "html_inline" &&
              next.content.includes("circuit:auto")
            ) {
              ch[i].type = "text";
              ch[i].content = "";
              ch[i].children = null;
              next.content = "";
            }
          }
        }
      });

      return md;
    },
  };
};
