// Uses existing direct dependencies (TypeScript/React) and Node's test runner.
// Compilation contains source code only; all document fixtures are synthetic.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import ts from 'typescript';
const root = fileURLToPath(new URL('../', import.meta.url));
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'wayfaro-frontend-tests-'));
try {
  fs.writeFileSync(path.join(output, 'package.json'), '{"type":"commonjs"}');
  fs.symlinkSync(path.join(root, 'node_modules'), path.join(output, 'node_modules'), 'dir');
  function compile(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const source = path.join(directory, entry.name);
      if (entry.isDirectory()) { compile(source); continue; }
      if (!/\.tsx?$/.test(entry.name) || /\.d\.ts$/.test(entry.name)) continue;
      const relative = path.relative(path.join(root, 'src'), source).replace(/\.tsx?$/, '.js');
      const destination = path.join(output, relative);
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      const text = relative === 'config.js' ? "export const API = 'https://api.example.test';" : fs.readFileSync(source, 'utf8');
      const result = ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true }, fileName: source });
      fs.writeFileSync(destination, result.outputText);
    }
  }
  compile(path.join(root, 'src'));
  const result = spawnSync(process.execPath, ['--test', '--test-concurrency=1', path.join(root, 'tests', 'analysis.test.mjs')], { env: { ...process.env, WAYFARO_TEST_BUILD: output }, stdio: 'inherit' });
  process.exitCode = result.status ?? 1;
} finally { fs.rmSync(output, { recursive: true, force: true }); }
