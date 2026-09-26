import * as THREE from 'three';
import { OrbitControls } from '/demo3d/static/vendor/controls/OrbitControls.js';
import { GLTFLoader } from '/demo3d/static/vendor/loaders/GLTFLoader.js';

const canvas = document.getElementById('view');
const select = document.getElementById('scene-select');
const welcome = document.getElementById('welcome');
const welcomeMessage = document.getElementById('welcome-message');
const sceneList = document.getElementById('scene-list');
const status = document.getElementById('status');
const resetButton = document.getElementById('reset-view');
const panel = document.getElementById('camera-panel');
const hint = document.getElementById('controls-hint');
const feedback = document.getElementById('copy-feedback');
const anchorButton = document.getElementById('copy-anchor');
const angleButton = document.getElementById('copy-angle');
const distanceButton = document.getElementById('copy-distance');
const configButton = document.getElementById('copy-config');

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
} catch (error) {
  showStatus('Браузер не смог запустить WebGL. Проверьте поддержку 3D и аппаратное ускорение.', true);
  throw error;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25;

const world = new THREE.Scene();
world.background = new THREE.Color(0x152229);
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 1000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = false;
controls.enablePan = true;
controls.minPolarAngle = 0.02;
controls.maxPolarAngle = Math.PI - 0.02;
controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;

const fillLights = new THREE.Group();
fillLights.add(new THREE.HemisphereLight(0xffffff, 0x70868a, 2.0));
const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
keyLight.position.set(1, 2, 1);
fillLights.add(keyLight);
world.add(fillLights);

const loader = new GLTFLoader();
const keys = new Set();
let catalog = [];
let currentEntry = null;
let currentModel = null;
let initialView = null;
let loadVersion = 0;
let shiftPointer = null;
let lastFrame = performance.now();

function showStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle('error', error);
  status.hidden = false;
}

function hideStatus() {
  status.hidden = true;
}

function showChooser(message = 'Откройте локацию из списка.') {
  welcomeMessage.textContent = message;
  welcome.hidden = false;
  panel.hidden = true;
  hint.hidden = true;
  resetButton.disabled = true;
  select.value = '';
}

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}
window.addEventListener('resize', resize);
resize();

function rounded(value, digits = 3) {
  const result = Number(value.toFixed(digits));
  return Object.is(result, -0) ? 0 : result;
}

function getView() {
  return {
    anchor: controls.target.toArray().map(value => rounded(value)),
    distance: rounded(controls.getDistance()),
    yaw: rounded(THREE.MathUtils.radToDeg(controls.getAzimuthalAngle()), 2),
    pitch: rounded(90 - THREE.MathUtils.radToDeg(controls.getPolarAngle()), 2),
  };
}

function updatePanel() {
  if (!currentEntry) return;
  const view = getView();
  anchorButton.textContent = view.anchor.join(' / ');
  angleButton.textContent = `${view.yaw}° / ${view.pitch}°`;
  distanceButton.textContent = String(view.distance);
}
controls.addEventListener('change', updatePanel);

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    feedback.textContent = 'Скопировано';
  } catch {
    feedback.textContent = 'Не удалось скопировать. Откройте сайт через localhost или HTTPS.';
  }
  window.setTimeout(() => { feedback.textContent = ''; }, 2500);
}
anchorButton.addEventListener('click', () => copyText(getView().anchor.join(', ')));
angleButton.addEventListener('click', () => {
  const view = getView();
  copyText(`${view.yaw}, ${view.pitch}`);
});
distanceButton.addEventListener('click', () => copyText(String(getView().distance)));
configButton.addEventListener('click', () => {
  const { anchor, distance, yaw, pitch } = getView();
  copyText(`"anchor": ${JSON.stringify(anchor)},\n"distance": ${distance},\n"yaw": ${yaw},\n"pitch": ${pitch}`);
});

function applyView(view) {
  const yaw = THREE.MathUtils.degToRad(view.yaw);
  const pitch = THREE.MathUtils.degToRad(view.pitch);
  const direction = new THREE.Vector3(
    Math.sin(yaw) * Math.cos(pitch),
    Math.sin(pitch),
    Math.cos(yaw) * Math.cos(pitch),
  );
  controls.target.fromArray(view.anchor);
  camera.position.copy(controls.target).addScaledVector(direction, view.distance);
  controls.update();
  updatePanel();
}

function disposeModel(object) {
  if (!object) return;
  world.remove(object);
  const geometrySet = new Set();
  const materialSet = new Set();
  const textureSet = new Set();
  const imageSet = new Set();
  object.traverse(node => {
    if (node.geometry) geometrySet.add(node.geometry);
    if (node.material) {
      for (const material of (Array.isArray(node.material) ? node.material : [node.material])) {
        materialSet.add(material);
      }
    }
  });
  for (const material of materialSet) {
    for (const value of Object.values(material)) {
      if (value?.isTexture) textureSet.add(value);
    }
    material.dispose();
  }
  for (const texture of textureSet) {
    if (texture.image && typeof texture.image.close === 'function') imageSet.add(texture.image);
    texture.dispose();
  }
  for (const image of imageSet) image.close();
  for (const geometry of geometrySet) geometry.dispose();
}

function setupCamera(object, entry) {
  const box = new THREE.Box3().setFromObject(object);
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  if (box.isEmpty()) {
    center.set(0, 0, 0);
    size.set(2, 2, 2);
    box.setFromCenterAndSize(center, size);
  } else {
    box.getCenter(center);
    box.getSize(size);
  }
  const radius = Math.max(size.length() / 2, 0.1);
  const yaw = entry.yaw ?? 35;
  const pitch = entry.pitch ?? 20;
  const yawRadians = THREE.MathUtils.degToRad(yaw);
  const pitchRadians = THREE.MathUtils.degToRad(pitch);
  const back = new THREE.Vector3(
    Math.sin(yawRadians) * Math.cos(pitchRadians),
    Math.sin(pitchRadians),
    Math.cos(yawRadians) * Math.cos(pitchRadians),
  );
  const forward = back.clone().negate();
  const right = forward.clone().cross(new THREE.Vector3(0, 1, 0)).normalize();
  const up = right.clone().cross(forward).normalize();
  const tanVertical = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
  const tanHorizontal = tanVertical * camera.aspect;
  let fitDistance = 0;
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) {
        const offset = new THREE.Vector3(x, y, z).sub(center);
        const depth = offset.dot(back);
        fitDistance = Math.max(
          fitDistance,
          depth + Math.abs(offset.dot(right)) / tanHorizontal,
          depth + Math.abs(offset.dot(up)) / tanVertical,
        );
      }
    }
  }
  fitDistance = Math.max(fitDistance * 1.15, 0.5);
  const distance = entry.distance ?? fitDistance;
  const anchor = entry.anchor ?? center.toArray();
  initialView = {
    anchor: [...anchor],
    distance,
    yaw,
    pitch,
  };
  camera.near = Math.max(0.005, radius / 10000);
  camera.far = Math.max(1000, radius * 100, distance * 30);
  camera.updateProjectionMatrix();
  controls.minDistance = Math.min(distance / 2, Math.max(0.03, radius * 0.002));
  controls.maxDistance = Math.max(distance * 3, radius * 25);
  applyView(initialView);
}

async function openScene(slug, updateUrl = false) {
  const entry = catalog.find(item => item.slug === slug);
  if (!entry) {
    showChooser(`Сцена «${slug}» не найдена. Выберите доступную локацию.`);
    hideStatus();
    return;
  }
  const version = ++loadVersion;
  select.value = slug;
  welcome.hidden = true;
  panel.hidden = true;
  hint.hidden = true;
  resetButton.disabled = true;
  showStatus(`Загрузка: ${entry.title}…`);
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set('scene', slug);
    window.history.pushState({}, '', url);
  }
  try {
    const gltf = await loader.loadAsync(`/demo3d/models/${slug}.glb`);
    if (version !== loadVersion) {
      disposeModel(gltf.scene);
      return;
    }
    disposeModel(currentModel);
    currentModel = gltf.scene;
    currentEntry = entry;
    world.add(currentModel);
    let importedLight = false;
    currentModel.traverse(node => { if (node.isLight) importedLight = true; });
    fillLights.visible = !importedLight;
    setupCamera(currentModel, entry);
    panel.hidden = false;
    hint.hidden = false;
    resetButton.disabled = false;
    hideStatus();
  } catch (error) {
    if (version !== loadVersion) return;
    console.error('GLB load failed:', error);
    disposeModel(currentModel);
    currentModel = null;
    currentEntry = null;
    initialView = null;
    fillLights.visible = true;
    showChooser(`Не удалось открыть «${entry.title}». Проверьте файл GLB и попробуйте другую сцену.`);
    showStatus('Ошибка загрузки GLB.', true);
  }
}

resetButton.addEventListener('click', () => {
  if (initialView) applyView(initialView);
});
select.addEventListener('change', () => {
  if (select.value) openScene(select.value, true);
  else showChooser();
});
window.addEventListener('popstate', () => {
  const slug = new URLSearchParams(window.location.search).get('scene');
  if (slug) openScene(slug);
  else showChooser();
});

// Shift + left drag is a continuous dolly gesture; OrbitControls normally pans for Shift + drag.
canvas.addEventListener('pointerdown', event => {
  if (event.pointerType === 'touch' || event.button !== 0 || !event.shiftKey) return;
  if (!currentEntry) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  shiftPointer = { id: event.pointerId, y: event.clientY };
  canvas.setPointerCapture(event.pointerId);
}, true);
canvas.addEventListener('pointermove', event => {
  if (!shiftPointer || shiftPointer.id !== event.pointerId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const delta = event.clientY - shiftPointer.y;
  shiftPointer.y = event.clientY;
  const currentDistance = controls.getDistance();
  const nextDistance = THREE.MathUtils.clamp(
    currentDistance * Math.exp(delta * 3 / Math.max(window.innerHeight, 1)),
    controls.minDistance,
    controls.maxDistance,
  );
  camera.position.sub(controls.target).multiplyScalar(nextDistance / currentDistance).add(controls.target);
  controls.update();
}, true);
function endShiftPointer(event) {
  if (!shiftPointer || shiftPointer.id !== event.pointerId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  shiftPointer = null;
  if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
}
canvas.addEventListener('pointerup', endShiftPointer, true);
canvas.addEventListener('pointercancel', endShiftPointer, true);

window.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest?.('input, textarea, select, button')) return;
  const key = event.key.toLowerCase();
  if ('wasd'.includes(key) && key.length === 1) {
    keys.add(key);
    event.preventDefault();
  }
});
window.addEventListener('keyup', event => keys.delete(event.key.toLowerCase()));
window.addEventListener('blur', () => keys.clear());
document.addEventListener('visibilitychange', () => { if (document.hidden) keys.clear(); });

function animate(now) {
  const delta = Math.min((now - lastFrame) / 1000, 0.1);
  lastFrame = now;
  if (currentEntry && keys.size) {
    const horizontal = (keys.has('d') ? 1 : 0) - (keys.has('a') ? 1 : 0);
    const vertical = (keys.has('w') ? 1 : 0) - (keys.has('s') ? 1 : 0);
    if (horizontal || vertical) {
      const forward = new THREE.Vector3();
      camera.getWorldDirection(forward);
      const right = forward.clone().cross(camera.up).normalize();
      const up = right.clone().cross(forward).normalize();
      const movement = right.multiplyScalar(horizontal).addScaledVector(up, vertical).normalize();
      movement.multiplyScalar(controls.getDistance() * 0.5 * delta);
      camera.position.add(movement);
      controls.target.add(movement);
      controls.update();
    }
  }
  renderer.render(world, camera);
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

async function start() {
  try {
    const response = await fetch('/demo3d/api/scenes', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    catalog = data.scenes;
    sceneList.replaceChildren();
    for (const entry of catalog) {
      const option = new Option(entry.title, entry.slug);
      select.add(option);
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = entry.title;
      button.addEventListener('click', () => openScene(entry.slug, true));
      sceneList.append(button);
    }
    const slug = new URLSearchParams(window.location.search).get('scene');
    if (slug) openScene(slug);
    else showChooser(catalog.length ? 'Откройте локацию из списка.' : 'Пока нет доступных сцен.');
  } catch (error) {
    console.error('Catalog load failed:', error);
    showChooser('Не удалось получить список сцен. Проверьте сервер.');
    showStatus('Ошибка загрузки списка сцен.', true);
  }
}
start();
