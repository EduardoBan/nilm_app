/**
 * Native TypeScript Compiler & Bundler for NILM Frontend using Node 22
 */
const fs = require('fs');
const path = require('path');
const { stripTypeScriptTypes } = require('node:module');

const srcDir = path.join(__dirname, '..', 'frontend', 'src');
const distDir = path.join(__dirname, '..', 'frontend', 'dist');

if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

console.log('📦 Compiling TypeScript files using Node 22 Native Type Stripper...');

const chartEngineCode = fs.readFileSync(path.join(srcDir, 'components', 'ChartEngine.ts'), 'utf-8');
const apiCode = fs.readFileSync(path.join(srcDir, 'services', 'api.ts'), 'utf-8');
const appCode = fs.readFileSync(path.join(srcDir, 'app.ts'), 'utf-8');

// Strip TypeScript from each file
const cleanChartEngine = stripTypeScriptTypes(chartEngineCode)
  .replace(/export\s+/g, '')
  .replace(/import\s+[\s\S]*?from\s+['"][^'"]+['"];?/g, '');

const cleanApi = stripTypeScriptTypes(apiCode)
  .replace(/export\s+/g, '')
  .replace(/import\s+[\s\S]*?from\s+['"][^'"]+['"];?/g, '');

const cleanApp = stripTypeScriptTypes(appCode)
  .replace(/export\s+/g, '')
  .replace(/import\s+[\s\S]*?from\s+['"][^'"]+['"];?/g, '');

const bundle = `/**
 * NILM Industrial Energy Analytics Dashboard - Compiled Bundle
 * Generated from TypeScript sources: src/app.ts, src/components/ChartEngine.ts, src/services/api.ts
 */
(function() {
  'use strict';

  // --- ChartEngine Component ---
  ${cleanChartEngine}

  // --- NILM API Service ---
  ${cleanApi}

  // --- Application Controller ---
  ${cleanApp}

})();
`;

const outputPath = path.join(distDir, 'bundle.js');
fs.writeFileSync(outputPath, bundle, 'utf-8');

console.log(`✅ Build successful! Output: ${outputPath} (${(fs.statSync(outputPath).size / 1024).toFixed(1)} KB)`);
