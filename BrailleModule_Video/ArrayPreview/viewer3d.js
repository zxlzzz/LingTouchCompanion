import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';

// The diffuse lights and the reflection panels describe the same studio.
const STUDIO_TARGET = new THREE.Vector3(0, 42, -15);
const STUDIO_LIGHTS = [
  { colour: 0xfff9ef, intensity: 3.6, width: 130, height: 180, position: [-110, 220, 95], reflection: 4.2 },
  { colour: 0xeaf1ff, intensity: 1.2, width: 95, height: 180, position: [130, 140, -100], reflection: 1.8 },
];

function studioReflection(renderer) {
  const studio = new THREE.Scene();
  studio.background = new THREE.Color().setRGB(.16, .17, .18);
  for (const light of STUDIO_LIGHTS) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(light.width, light.height),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(light.colour).multiplyScalar(light.reflection), side: THREE.DoubleSide }));
    panel.position.fromArray(light.position).sub(STUDIO_TARGET); panel.lookAt(0, 0, 0); studio.add(panel);
  }
  const generator = new THREE.PMREMGenerator(renderer);
  const target = generator.fromScene(studio, .035, .1, 1000);
  studio.traverse(node => { node.geometry?.dispose(); node.material?.dispose(); });
  generator.dispose();
  return target;
}

// Stable surface detail stays in object/world space as the camera moves.
const relief = `
varying vec3 vFinishPosition;
varying vec3 vFinishWorld;
varying vec3 vFinishNormal;
uniform float finishSeed;
uniform vec3 finishCavity;
uniform float finishTipExposure;
uniform float finishNoseHeight;
uniform float finishHeadRadius;
float hashFinish(vec3 p) { p = fract(p * .1031); p += dot(p, p.yzx + 33.33); return fract((p.x + p.y) * p.z); }
float noiseFinish(vec3 p) {
  vec3 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
  return mix(mix(mix(hashFinish(i), hashFinish(i+vec3(1,0,0)),f.x),mix(hashFinish(i+vec3(0,1,0)),hashFinish(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hashFinish(i+vec3(0,0,1)),hashFinish(i+vec3(1,0,1)),f.x),mix(hashFinish(i+vec3(0,1,1)),hashFinish(i+vec3(1,1,1)),f.x),f.y),f.z);
}
vec3 reliefNormal(vec3 surf, vec3 n, float height) {
  vec3 sx = dFdx(surf), sy = dFdy(surf);
  vec3 r1 = cross(sy,n), r2 = cross(n,sx);
  float det = dot(sx,r1);
  vec3 grad = sign(det)*(dFdx(height)*r1+dFdy(height)*r2);
  return normalize(abs(det)*n-grad);
}
float filamentWave(float coordinate, float spacing) {
  float phase = coordinate / spacing;
  // Suppress subpixel layer patterns to keep distant views stable.
  float resolved = 1. - smoothstep(.22,.70,fwidth(phase));
  return cos(6.2831853 * phase) * resolved;
}
`;

function finish(material, kind, seed = 0, cavity = new THREE.Vector3(), tipExposure = 0, noseHeight = 0, headRadius = 1.6) {
  material.onBeforeCompile = shader => {
    shader.uniforms.finishSeed = { value: seed };
    shader.uniforms.finishCavity = { value: cavity };
    shader.uniforms.finishTipExposure = { value: tipExposure };
    shader.uniforms.finishNoseHeight = { value: noseHeight };
    shader.uniforms.finishHeadRadius = { value: headRadius };
    shader.vertexShader = 'varying vec3 vFinishPosition; varying vec3 vFinishWorld; varying vec3 vFinishNormal;\n' + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvFinishPosition = position * 1000.0; vFinishWorld = (modelMatrix * vec4(position,1.0)).xyz; vFinishNormal = normalize(mat3(modelMatrix)*normal);');
    shader.fragmentShader = relief + shader.fragmentShader;
    let colour = '', rough = '', height = '';
    if (kind === 'pin') {
      colour = 'diffuseColor.rgb *= 1. + (noiseFinish(vFinishPosition*3.2+finishSeed*19.)-.5)*.025;';
      rough = 'roughnessFactor = clamp(roughnessFactor + (noiseFinish(vFinishPosition*3.8+finishSeed*17.3)-.5)*.06,.19,.36);';
      height = 'float finishHeight = noiseFinish(vFinishPosition*1.7+vec3(finishSeed*17.3,finishSeed*8.1,finishSeed*13.7))*.0085 + noiseFinish(vFinishPosition*32.+finishSeed*19.)*.00012;';
      // Crown and stem move through a fixed aperture. Area lights do not cast
      // Three.js shadows: trace to the mouth for the light's centre and edges.
      // At rest, the crown is below the mouth; raised portions see the studio.
      shader.fragmentShader = shader.fragmentShader.replace('#include <aomap_fragment>', `#include <aomap_fragment>
        float pinDepth = max(0.,finishCavity.y-vFinishWorld.y);
        vec2 pinPoint = vFinishWorld.xz-finishCavity.xz;
        float pinKeyVisibility = 0.;
        float pinFillVisibility = 0.;
        for (int lightSample=0;lightSample<5;lightSample++) {
          vec2 sampleOffset = vec2(0.);
          if (lightSample==1) sampleOffset=vec2(-45.,0.);
          if (lightSample==2) sampleOffset=vec2(45.,0.);
          if (lightSample==3) sampleOffset=vec2(0.,-60.);
          if (lightSample==4) sampleOffset=vec2(0.,60.);
          vec3 keyRay = vec3(-110.,220.,95.)+vec3(sampleOffset.x,0.,sampleOffset.y)-vFinishWorld;
          vec3 fillRay = vec3(130.,140.,-100.)+vec3(sampleOffset.x,0.,sampleOffset.y)-vFinishWorld;
          vec2 keyExit = pinPoint+keyRay.xz*pinDepth/max(.01,keyRay.y);
          vec2 fillExit = pinPoint+fillRay.xz*pinDepth/max(.01,fillRay.y);
          pinKeyVisibility += (1.-smoothstep(.79,.89,length(keyExit)))/5.;
          pinFillVisibility += (1.-smoothstep(.79,.89,length(fillExit)))/5.;
        }
        float pinDirectVisibility = mix(.22,1.,pinKeyVisibility*.76+pinFillVisibility*.24);
        float pinAmbientVisibility = mix(.52,1.,smoothstep(-.40,.22,vFinishWorld.y-finishCavity.y));
        reflectedLight.directDiffuse *= pinDirectVisibility;
        reflectedLight.directSpecular *= pinDirectVisibility;
        reflectedLight.indirectDiffuse *= pinAmbientVisibility;
        reflectedLight.indirectSpecular *= pinAmbientVisibility;
        #ifdef USE_CLEARCOAT
          clearcoatSpecularDirect *= pinDirectVisibility;
          clearcoatSpecularIndirect *= pinAmbientVisibility;
        #endif
      `);
    } else if (kind === 'housing') {
      colour = 'diffuseColor.rgb *= 1. + (noiseFinish(vFinishWorld*18.)-.5)*.016;';
      rough = 'roughnessFactor = .46 + (noiseFinish(vFinishWorld*15.)-.5)*.035;';
      height = 'float finishHeight = noiseFinish(vFinishWorld*24.)*.00045;';
    } else if (kind === 'enclosure') {
      colour = `float plaTop = smoothstep(.55,.94,abs(vFinishNormal.y));
        float plaLayers = filamentWave(vFinishWorld.y,.20);
        float plaRoads = filamentWave(dot(vFinishWorld.xz,vec2(.7071068,.7071068)),.42);
        float plaRidges = mix(plaLayers,plaRoads,plaTop);
        diffuseColor.rgb *= 1. + plaRidges*.004 + (noiseFinish(vFinishWorld*12.)-.5)*.004;`;
      rough = 'roughnessFactor = clamp(.53 + (noiseFinish(vFinishWorld*12.)-.5)*.024 - plaRidges*.008,.50,.56);';
      height = 'float finishHeight = mix(plaLayers*.0035,plaRoads*.0014,plaTop) + noiseFinish(vFinishWorld*28.)*.0002;';
      // Local visibility in the existing round bore. The 2 mm deep wall receives
      // less ambient light toward the bottom; the outer face keeps its material.
      shader.fragmentShader = shader.fragmentShader.replace('#include <aomap_fragment>', `#include <aomap_fragment>
        float boreRadius = length(vFinishWorld.xz - finishCavity.xz);
        float boreDepth = finishCavity.y - vFinishWorld.y;
        float boreWall = (1. - smoothstep(2.50,2.57,boreRadius)) * smoothstep(0.,.30,boreDepth);
        float boreVisibility = 1. - boreWall * .38 * smoothstep(0.,1.4,boreDepth);
        reflectedLight.indirectDiffuse *= boreVisibility;
        reflectedLight.indirectSpecular *= boreVisibility;
        // Area lights have no Three.js shadow map. Approximate their geometric
        // visibility inside this bore using the actual opening and stem radii.
        vec3 boreLight = normalize(vec3(-110.,220.,95.) - vFinishWorld);
        vec2 borePoint = vFinishWorld.xz - finishCavity.xz;
        vec2 exitPoint = borePoint + boreLight.xz * max(0.,boreDepth) / boreLight.y;
        float rimVisibility = 1. - smoothstep(2.28,2.72,length(exitPoint));
        float tipReach = max(0.,boreDepth + finishTipExposure) / boreLight.y;
        float closestStem = 10.;
        for (int sampleIndex=0; sampleIndex<9; sampleIndex++) {
          float rayReach = tipReach * float(sampleIndex) / 8.;
          float tipDepth = finishCavity.y + finishTipExposure - vFinishWorld.y - boreLight.y*rayReach;
          float nosePosition = clamp(1. - tipDepth/max(.0001,finishNoseHeight),0.,1.);
          float neckRadius = mix(finishHeadRadius,1.60,smoothstep(finishNoseHeight,finishNoseHeight+.65,tipDepth));
          float stemRadius = neckRadius * sqrt(max(0.,1. - nosePosition*nosePosition));
          closestStem = min(closestStem,length(borePoint+boreLight.xz*rayReach)-stemRadius);
        }
        float stemVisibility = smoothstep(-.10,.14,closestStem);
        float boreKeyVisibility = mix(1.,mix(.40,1.,rimVisibility*stemVisibility),boreWall);
        reflectedLight.directDiffuse *= boreKeyVisibility;
        reflectedLight.directSpecular *= boreKeyVisibility;
      `);
    } else if (kind === 'switch') {
      colour = 'diffuseColor.rgb *= mix(.98,1.02,noiseFinish(vFinishPosition*24.));';
      rough = 'roughnessFactor = mix(.45,.475,noiseFinish(vFinishPosition*26.));';
      height = 'float switchSide = 1. - smoothstep(.5,.9,abs(vFinishNormal.y)); float seam = exp(-pow(vFinishPosition.x/.025,2.))*switchSide; float finishHeight = noiseFinish(vFinishPosition*24.)*.00014 + noiseFinish(vFinishPosition*60.)*.00003 + seam*.0008;';
    } else {
      colour = 'diffuseColor.rgb *= mix(.93,1.06,noiseFinish(vFinishWorld*.75));';
      rough = 'roughnessFactor = mix(.40,.51,noiseFinish(vFinishWorld*.9));';
      height = 'float finishHeight = noiseFinish(vFinishWorld*20.)*.0007;';
    }
    // Derivative perturbation affects reflection, not mesh shape or pin motion.
    shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', '#include <color_fragment>\n' + colour);
    shader.fragmentShader = shader.fragmentShader.replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\n' + rough);
    shader.fragmentShader = shader.fragmentShader.replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\n' + height + '\nnormal = reliefNormal(-vViewPosition, normal, finishHeight);');
  };
  material.customProgramCacheKey = () => `array-finish-5-${kind}`;
  return material;
}

export async function createViewer({ canvas, view, labels, assets, onChange, onPin }) {
  RectAreaLightUniformsLib.init();
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = 1.32;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.VSMShadowMap;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#e6e7e4');
  const environment = studioReflection(renderer);
  scene.environment = environment.texture; scene.environmentIntensity = .65;
  const camera = new THREE.PerspectiveCamera(26, 16 / 11, .05, 4000);
  camera.position.fromArray(assets.scene.camera.position_mm);
  const controls = new OrbitControls(camera, canvas);
  controls.target.fromArray(assets.scene.camera.target_mm);
  controls.enableDamping = true;
  controls.dampingFactor = .12;
  controls.rotateSpeed = .55;
  controls.zoomSpeed = .8;
  controls.minDistance = 20;
  controls.maxDistance = 1800;
  controls.screenSpacePanning = true;
  controls.update(); controls.saveState();
  controls.addEventListener('change', onChange);
  controls.addEventListener('start', () => { canvas.style.cursor = 'grabbing'; onChange(); });
  controls.addEventListener('end', () => { canvas.style.cursor = 'grab'; onChange(); });

  scene.add(new THREE.HemisphereLight(0xe5edf5, 0x9c968c, .38));
  for (const light of STUDIO_LIGHTS) {
    const area = new THREE.RectAreaLight(light.colour, light.intensity, light.width, light.height);
    area.position.fromArray(light.position); area.lookAt(STUDIO_TARGET); scene.add(area);
  }
  const shadow = new THREE.DirectionalLight(0xfff9ef, .38);
  shadow.position.fromArray(STUDIO_LIGHTS[0].position); shadow.target.position.copy(STUDIO_TARGET);
  shadow.castShadow = true; shadow.shadow.mapSize.set(2048, 2048);
  Object.assign(shadow.shadow.camera, { left: -65, right: 65, top: 65, bottom: -65, near: .5, far: 800 });
  shadow.shadow.bias = -.00001; shadow.shadow.normalBias = .015;
  shadow.shadow.radius = 3; shadow.shadow.blurSamples = 12;
  scene.add(shadow, shadow.target);
  const tableMaterial = new THREE.MeshStandardMaterial({ color: new THREE.Color().setRGB(.88, .90, .90), roughness: .85 });
  const table = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000), tableMaterial);
  table.rotation.x = -Math.PI / 2; table.position.y = -.025;
  table.receiveShadow = true; scene.add(table);

  const bytes = Uint8Array.from(atob(assets.model), c => c.charCodeAt(0));
  const gltf = await new GLTFLoader().parseAsync(bytes.buffer, '');
  const model = gltf.scene; model.scale.setScalar(1000); scene.add(model);
  model.updateMatrixWorld(true);
  const pins = Array(90), roots = Array(15), meshes = [], enclosureMeshes = [], switchMeshes = [];
  let enclosureVisible = true;
  const housing = finish(new THREE.MeshPhysicalMaterial({ color: new THREE.Color().setRGB(.022,.025,.027), roughness: .46, specularIntensity: .5, metalness: 0 }), 'housing');
  const switchCentre = new THREE.Vector3(assets.scene.switch.hole_centre_cad_xz_mm[1],assets.scene.enclosure.touch_plane_height_mm,64-assets.scene.switch.hole_centre_cad_xz_mm[0]);
  const enclosure = finish(new THREE.MeshPhysicalMaterial({ color: new THREE.Color().setRGB(.66,.645,.60), roughness: .53, specularIntensity: .5, metalness: 0 }), 'enclosure', 0, switchCentre, assets.scene.switch.exposed_height_above_faceplate_mm, assets.scene.switch.actuator_head_height_mm, assets.scene.switch.actuator_head_diameter_mm/2);
  const switchPlastic = finish(new THREE.MeshPhysicalMaterial({ color: new THREE.Color().setRGB(.013,.015,.016), roughness: .46, specularIntensity: .5, metalness: 0 }), 'switch');
  const switchSteel = new THREE.MeshStandardMaterial({ color: new THREE.Color().setRGB(.48,.49,.50), roughness: .36, metalness: .90 });
  const internal = new THREE.MeshStandardMaterial({ color: '#242728', roughness: .47 });
  model.traverse(node => {
    if (node.userData.control_module && !node.userData.control_dot && node.name.startsWith('Module_')) roots[node.userData.control_module-1] = node;
    if (node.userData.control_dot) {
      const index = (node.userData.control_module-1)*6+node.userData.control_dot-1;
      if (pins[index]) throw new Error('DUPLICATE_PIN');
      const seed = ((index*2654435761)>>>0)/4294967296;
      const aperture = node.getWorldPosition(new THREE.Vector3());
      pins[index] = { node, rest: node.position.clone(), axis: new THREE.Vector3(0,1,0), height: 0 };
      node.traverse(part => {
        if (!part.isMesh) return;
        part.userData.pinIndex = index;
        part.material = finish(new THREE.MeshPhysicalMaterial({
          color: new THREE.Color().setRGB(.21+seed*.012,.235+seed*.012,.245+seed*.012),
          roughness: .22+seed*.095, specularIntensity: .9, ior: 1.48, metalness: 0,
          clearcoat: .06, clearcoatRoughness: .26,
        }), 'pin', seed, aperture);
        part.castShadow = false; part.receiveShadow = true;
      });
    }
    if (!node.isMesh) return;
    meshes.push(node);
    if (node.userData.enclosure_part || node.name.startsWith('Enclosure_')) enclosureMeshes.push(node);
    if (node.userData.switch_part) switchMeshes.push(node);
    if (node.userData.pinIndex != null) return;
    node.material = node.userData.switch_part ? (node.userData.switch_part === 'steel' ? switchSteel : switchPlastic) : node.userData.enclosure_part || node.name.startsWith('Enclosure_') ? enclosure : node.name.includes('Housing') || node.material?.name?.includes('housing') ? housing : internal;
    node.castShadow = true; node.receiveShadow = true;
  });
  if (pins.filter(Boolean).length !== 90 || roots.filter(Boolean).length !== 15) throw new Error('INVALID_MODEL_MAPPING');
  model.updateMatrixWorld(true);
  for (const pin of pins) {
    // Convert world vertical to each parent frame, independent of glTF axes.
    pin.axis.copy(new THREE.Vector3(0,1,0).transformDirection(pin.node.parent.matrixWorld.clone().invert()));
  }

  const anchors = roots.map((root, index) => {
    const label = document.createElement('span'); label.className = 'label'; label.textContent = `M${index+1}`; labels.appendChild(label);
    return { root, label, local: new THREE.Vector3(0,.0206,0) };
  });
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  const activePointers = new Set(); let gesture = null;
  canvas.addEventListener('pointerdown', event => {
    view.focus({ preventScroll: true }); activePointers.add(event.pointerId);
    if (event.button === 0 && activePointers.size === 1) gesture = { id: event.pointerId, x: event.clientX, y: event.clientY, dragged: false };
    else if (gesture) gesture.dragged = true;
  });
  canvas.addEventListener('pointermove', event => {
    if (gesture && gesture.id === event.pointerId && Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y)>5) gesture.dragged = true;
  });
  canvas.addEventListener('pointerup', event => {
    activePointers.delete(event.pointerId);
    const click = gesture && gesture.id === event.pointerId && !gesture.dragged && event.button === 0;
    gesture = null;
    if (!click) return;
    const bounds = canvas.getBoundingClientRect();
    pointer.set((event.clientX-bounds.left)/bounds.width*2-1,1-(event.clientY-bounds.top)/bounds.height*2);
    raycaster.setFromCamera(pointer,camera);
    const hit = raycaster.intersectObjects(meshes.filter(mesh => mesh.visible),false)[0];
    view.dataset.lastHit = hit?.object.name || '';
    view.dataset.lastPointer = `${event.clientX},${event.clientY}`;
    if (hit && hit.object.userData.pinIndex != null) onPin(hit.object.userData.pinIndex);
  });
  canvas.addEventListener('pointercancel', () => { activePointers.clear(); gesture = null; });
  canvas.addEventListener('contextmenu', event => event.preventDefault());
  // Arrow keys rotate a focused viewer; +/- zoom. Form editing stays untouched.
  view.addEventListener('keydown', event => {
    if (event.target !== view && event.target !== canvas) return;
    const offset = camera.position.clone().sub(controls.target), spherical = new THREE.Spherical().setFromVector3(offset);
    if (event.key === 'ArrowLeft') spherical.theta -= .12;
    else if (event.key === 'ArrowRight') spherical.theta += .12;
    else if (event.key === 'ArrowUp') spherical.phi -= .12;
    else if (event.key === 'ArrowDown') spherical.phi += .12;
    else if (event.key === '+' || event.key === '=') spherical.radius *= .9;
    else if (event.key === '-') spherical.radius /= .9;
    else return;
    event.preventDefault(); spherical.makeSafe(); spherical.radius = THREE.MathUtils.clamp(spherical.radius,controls.minDistance,controls.maxDistance);
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    controls.update(); onChange();
  });

  const projected = new THREE.Vector3(), world = new THREE.Vector3();
  function draw(heights) {
    pins.forEach((pin,index) => {
      pin.height = heights[index]; pin.node.position.copy(pin.rest).addScaledVector(pin.axis,heights[index]/1000);
    });
    model.updateMatrixWorld(true);
    const moving = controls.update();
    camera.updateMatrixWorld();
    if (!labels.hidden) for (const anchor of anchors) {
      world.copy(anchor.local); anchor.root.localToWorld(world); projected.copy(world).project(camera);
      anchor.label.hidden = projected.z < -1 || projected.z > 1 || Math.abs(projected.x)>1 || Math.abs(projected.y)>1;
      anchor.label.style.left = `${(projected.x*.5+.5)*100}%`;
      anchor.label.style.top = `${(-projected.y*.5+.5)*100}%`;
    }
    renderer.render(scene,camera);
    const offset = camera.position.clone().sub(controls.target), spherical = new THREE.Spherical().setFromVector3(offset);
    view.dataset.yaw = THREE.MathUtils.radToDeg(spherical.theta).toFixed(3);
    view.dataset.pitch = THREE.MathUtils.radToDeg(spherical.phi).toFixed(3);
    view.dataset.distance = spherical.radius.toFixed(3);
    view.dataset.ready = 'true';
    return moving;
  }
  function resize() {
    const width = Math.max(1,view.clientWidth), height = Math.max(1,view.clientHeight);
    renderer.setSize(width,height,false);
    camera.aspect = width/height;
    camera.fov = THREE.MathUtils.radToDeg(2*Math.atan(Math.tan(THREE.MathUtils.degToRad(assets.scene.camera.horizontal_fov_degrees/2))/camera.aspect));
    camera.updateProjectionMatrix(); onChange();
  }
  function reset() {
    // Drain inertial rotation/panning before restoring the saved camera.
    controls.enableDamping = false; controls.update(); controls.reset();
    controls.enableDamping = true; onChange();
  }
  function frameBounds(bounds,direction,margin=1.13) {
    const centre = bounds.getCenter(new THREE.Vector3()); direction.normalize();
    const right = new THREE.Vector3().crossVectors(direction.clone().negate(),camera.up).normalize();
    const up = new THREE.Vector3().crossVectors(right,direction.clone().negate()).normalize();
    const vertical = Math.tan(THREE.MathUtils.degToRad(camera.fov/2)), horizontal = vertical*camera.aspect;
    let distance = 0;
    for (const x of [bounds.min.x,bounds.max.x]) for (const y of [bounds.min.y,bounds.max.y]) for (const z of [bounds.min.z,bounds.max.z]) {
      const point = new THREE.Vector3(x,y,z).sub(centre);
      distance = Math.max(distance,point.dot(direction)+Math.abs(point.dot(right))/horizontal,point.dot(direction)+Math.abs(point.dot(up))/vertical);
    }
    controls.target.copy(centre); camera.position.copy(centre).addScaledVector(direction,distance*margin);
  }
  function setView(mode) {
    controls.enableDamping = false; controls.update();
    const shadowExtent = mode === 'whole' ? 240 : 65;
    Object.assign(shadow.shadow.camera, { left: -shadowExtent, right: shadowExtent, top: shadowExtent, bottom: -shadowExtent });
    shadow.shadow.camera.updateProjectionMatrix(); shadow.shadow.needsUpdate = true;
    if (mode === 'whole') {
      frameBounds(new THREE.Box3().setFromObject(model),new THREE.Vector3(.85,1.3,.80),1.12);
    } else if (mode === 'switch') {
      if (enclosureVisible) {
        controls.target.copy(switchCentre); camera.position.copy(controls.target).add(new THREE.Vector3(6,19,10));
      } else {
        const bounds = new THREE.Box3(); switchMeshes.forEach(mesh => bounds.expandByObject(mesh));
        frameBounds(bounds,new THREE.Vector3(.36,.25,.80),1.3);
      }
    } else {
      // Frame the tactile face and the button together, rather than the volume
      // underneath the pins. Bounds retain the original array and enclosure.
      frameBounds(new THREE.Box3(new THREE.Vector3(-17,52,-18),new THREE.Vector3(17,56,23)),new THREE.Vector3(.15,1.2,.80),1.05);
    }
    camera.zoom = 1; camera.updateProjectionMatrix(); controls.update(); controls.saveState();
    controls.enableDamping = true; view.dataset.mode = mode; onChange();
  }
  function setEnclosureVisible(visible) {
    enclosureVisible = Boolean(visible);
    enclosureMeshes.forEach(mesh => { mesh.visible = enclosureVisible; });
    view.dataset.enclosureVisible = String(enclosureVisible);
    shadow.shadow.needsUpdate = true;
    if (view.dataset.mode === 'switch') setView('switch');
    else onChange();
  }
  const observer = new ResizeObserver(resize); observer.observe(view);
  resize();
  setView('near');
  view.dataset.enclosureVisible = 'true';
  return { draw, resize, reset, setView, setEnclosureVisible };
}
