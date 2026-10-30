import { svelte } from "@sveltejs/vite-plugin-svelte";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

const repo = resolve(import.meta.dirname, "..");
const outDir = resolve(repo, "src/ui/dist");
const fonts = resolve(repo, "src/assets/fonts");

// The page runs next to a bridge that can unlock the vault and shows text that
// agents and websites wrote: nothing but its own files may run or load.
// 'unsafe-eval' is there only because pywebview builds its API stubs with
// `new Function`; the panel's own code never evaluates strings.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "media-src 'self'",
  "object-src 'none'",
  "frame-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

/** Files the build is made from; tests/test_frontend_build.py hashes the same set. */
export function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (name === "node_modules" || name.startsWith(".")) continue;
      if (statSync(path).isDirectory()) walk(path);
      else out.push(path);
    }
  };
  walk(import.meta.dirname);
  walk(fonts);
  out.push(resolve(repo, "src/assets/icon.png"));
  return out.map((p) => relative(repo, p).split("\\").join("/")).sort();
}

export function sourceHash(): string {
  const hash = createHash("sha256");
  for (const rel of sourceFiles()) {
    let data = readFileSync(resolve(repo, rel));
    if (!/\.(ttf|png)$/.test(rel)) data = Buffer.from(data.toString("utf8").replace(/\r\n/g, "\n"));
    hash.update(rel);
    hash.update("\0");
    hash.update(data);
    hash.update("\0");
  }
  return hash.digest("hex");
}

/** `npm run dev`: the mock bridge reads the real strings from strings.py. */
function devStrings(): Plugin {
  return {
    name: "cloutfox-dev-strings",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/mock-strings.json", (_req, res) => {
        const code =
          "import json,sys; sys.path.insert(0,'.'); from src.core.strings import STRINGS; " +
          "print(json.dumps({**STRINGS['en'], **STRINGS['ru']}))";
        const out = execFileSync("python3", ["-c", code], { cwd: repo });
        res.setHeader("Content-Type", "application/json");
        res.end(out);
      });
    },
  };
}

function panel(): Plugin {
  return {
    name: "cloutfox-panel",
    apply: "build",
    transformIndexHtml(html) {
      return html.replace(
        "<head>",
        `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`,
      );
    },
    closeBundle() {
      // Bundled fonts keep their licences next to them.
      mkdirSync(join(outDir, "fonts"), { recursive: true });
      for (const name of readdirSync(fonts)) {
        if (name.startsWith("OFL-")) copyFileSync(join(fonts, name), join(outDir, "fonts", name));
      }
      writeFileSync(join(outDir, ".source-hash"), sourceHash() + "\n");
    },
  };
}

export default defineConfig({
  plugins: [svelte(), panel(), devStrings()],
  base: "./",
  build: {
    outDir,
    emptyOutDir: true,
    assetsDir: "assets",
    target: "chrome118",
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // Fonts land in fonts/ beside their OFL licences.
        assetFileNames: (info) =>
          /\.ttf$/.test(info.names?.[0] ?? "") ? "fonts/[name]-[hash][extname]" : "assets/[name]-[hash][extname]",
      },
    },
  },
  server: { port: 5199, strictPort: true, fs: { allow: [repo] } },
  test: { include: ["src/**/*.test.ts"] },
});
