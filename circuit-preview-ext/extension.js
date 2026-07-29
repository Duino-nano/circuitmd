// Circuit Preview — Markdownプレビューで ```circuit フェンスを回路図としてレンダリングする拡張。
// 描画は circuitmd.py の svg サブコマンド（schemdraw）に委譲し、返ってきたSVGを
// プレビューHTMLに直接インライン埋め込みする。画像ファイルを経由しないので
// プレビューのローカルリソース制限の影響を受けず、編集がリアルタイムに反映される。
// 内容ハッシュでキャッシュするため、変更のないブロックの再描画は瞬時。

const { execFileSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

// circuitmd.py 本体を拡張内に同梱して使う（ビルド時にコピーされる）。
// Documents配下を直接参照するとmacOSのTCCでVSCodeの子プロセスから読めないことが
// あるための同梱方式。svgサブコマンドは標準入力→標準出力で完結し、ファイル不要。
const SCRIPT = path.join(__dirname, "circuitmd.py");
const PYTHON_CANDIDATES = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"];

const cache = new Map(); // 内容ハッシュ → 描画済みHTML

function pythonPath() {
  for (const p of PYTHON_CANDIDATES) {
    if (fs.existsSync(p)) return p;
  }
  return "python3";
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderCircuit(code) {
  const key = crypto.createHash("sha1").update(code).digest("hex");
  if (cache.has(key)) return cache.get(key);

  let html;
  try {
    const svg = execFileSync(pythonPath(), [SCRIPT, "svg"], {
      input: code,
      timeout: 15000,
      encoding: "utf8",
    });
    html =
      '<div class="circuit-diagram" style="background:#fff;display:inline-block;' +
      'padding:14px;border-radius:6px;max-width:100%;overflow-x:auto;margin:4px 0">' +
      svg +
      "</div>";
  } catch (e) {
    const msg = e.stderr ? e.stderr.toString() : e.message;
    html =
      '<pre style="border:1px solid #d66;border-radius:6px;padding:10px;' +
      'color:#d66;white-space:pre-wrap">circuit描画エラー\n' +
      escapeHtml(msg.trim()) +
      "</pre>";
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
