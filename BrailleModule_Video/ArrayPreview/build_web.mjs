import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
let esbuild, dependencyPath;
if (!process.argv.includes('--page-only')) {
try { esbuild = require('esbuild'); dependencyPath = join(root,'node_modules'); }
catch { esbuild = require('./.3d-work/node_modules/esbuild'); dependencyPath = join(root,'.3d-work/node_modules'); }
await mkdir(join(root,'vendor'),{recursive:true});
await esbuild.build({
  entryPoints: [join(root,'viewer3d.js')], bundle: true, minify: true,
  format: 'iife', globalName: 'Braille3D', target: 'es2020',
  outfile: join(root,'vendor/viewer.bundle.js'), nodePaths: [dependencyPath],
  legalComments: 'eof',
});
await copyFile(join(dependencyPath,'three/LICENSE'),join(root,'vendor/THREE-LICENSE.txt'));
await copyFile(join(dependencyPath,'esbuild/LICENSE.md'),join(root,'vendor/ESBUILD-LICENSE.md'));
}
const template = await readFile(join(root,'index.template.html'),'utf8');
const scene = JSON.parse(await readFile(join(root,'assets/scene.json'),'utf8'));
const assets = {
  scene,
  motion: JSON.parse(await readFile(join(root,'assets/motion.json'),'utf8')),
  model: (await readFile(join(root,'assets',scene.model_file || 'ModuleArray.glb'))).toString('base64'),
};
const bundle = await readFile(join(root,'vendor/viewer.bundle.js'),'utf8');
const controls = await readFile(join(root,'controls.js'),'utf8');
const page = template.replace('<!-- SCENE_ASSETS -->', () => '<script id="sceneAssets" type="application/json">'+JSON.stringify(assets)+'</script>')
  .replace('<!-- VIEWER_BUNDLE -->', () => '<script>'+bundle.replaceAll('</script','<\\/script')+'</script>')
  .replace('<!-- ARRAY_CONTROLS -->', () => '<script>'+controls.replaceAll('</script','<\\/script')+'</script>');
await writeFile(join(root,'index.html'),page,'utf8');
console.log('Offline interactive preview built ('+Buffer.byteLength(page)+' bytes).');
