// Alternative to Vite for an offline checkout with esbuild and React available.
// FOGWRITE_NODE_MODULES may point to a shared dependency directory.
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const deps = process.env.FOGWRITE_NODE_MODULES || path.join(root, 'frontend', 'node_modules');
const esbuild = require(require.resolve('esbuild', {paths: [deps]}));
esbuild.buildSync({entryPoints: [path.join(root,'frontend/src/fogwrite.jsx')], bundle:true,
  minify:true, outfile:path.join(root,'frontend/dist/app.js'), nodePaths:[deps], jsx:'automatic',
  define:{'process.env.NODE_ENV':'"production"'}, logLevel:'info'});
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8')
  .replace('<script type="module" src="/src/fogwrite.jsx"></script>',
    '<link rel="stylesheet" href="/app.css?v=fogwrite-v1" /><script type="module" src="/app.js?v=fogwrite-v1"></script>');
fs.writeFileSync(path.join(root,'frontend/dist/index.html'), html);
