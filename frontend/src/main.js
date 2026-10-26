import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

async function verifySession() {
  try {
    const res = await fetch('/api/me');
    if (!res.ok) {
      window.location.href = '/landing.html';
      return;
    }
    const data = await res.json();
    document.getElementById('current-username').innerText = data.username;
    
    // Proceed with booting the 3D application
    initScene();
    fetchBuildingList();
  } catch (err) {
    window.location.href = '/landing.html';
  }
}

verifySession();

// Configuration settings
const CONFIG = {
  apiBase: '/api',
  explodedMultiplier: 2.2, // Increases vertical gap between floors to maintain visibility
  baseOpacity: 0.35,
  highlightOpacity: 0.85,
  roomColor: 0x475569,
  pathColor: 0x38bdf8,
  startColor: 0x22c55e,
  endColor: 0xef4444
};

// Scene State
let scene, camera, renderer, controls;
let buildingData = null;
let roomMeshes = {};       // Maps room name -> array of Mesh objects
let floorGroups = {};      // Maps floor name -> THREE.Group
let currentPathLine = null;
let currentStartMesh = null;
let currentEndMesh = null;
let labelRenderer;



function initScene() {
  const container = document.getElementById('canvas-container');

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1117);

  // Orthographic-style camera setup for architectural clarity
  camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
  );
  camera.position.set(40, 50, 60);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;

  // Scene Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
  scene.add(ambientLight);

  const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
  dirLight.position.set(20, 40, 20);
  scene.add(dirLight);

  labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.domElement.style.position = 'absolute';
  labelRenderer.domElement.style.top = '0px';
  labelRenderer.domElement.style.pointerEvents = 'none'; // Crucial so OrbitControls still work
  container.appendChild(labelRenderer.domElement);

  window.addEventListener('resize', onWindowResize);
  setupUIEvents();
  animate();
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
}

function onWindowResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
}

// Data Fetching & Population
let currentBuildingId = null;

// Replace fetchBuilding() with these new multi-building functions
async function fetchBuildingList() {
  try {
    const res = await fetch(`${CONFIG.apiBase}/buildings`);
    const buildings = await res.json();
    
    const bSelect = document.getElementById('building-select');
    bSelect.innerHTML = '<option value="">Choose a building...</option>';
    
    buildings.forEach(b => {
      bSelect.add(new Option(b.name, b.id));
    });
    
    // Add event listener to load building when selected
    bSelect.addEventListener('change', (e) => {
      if (e.target.value) {
        currentBuildingId = e.target.value;
        loadBuilding(currentBuildingId);
      }
    });
  } catch (err) {
    console.error('Failed to load buildings list:', err);
  }
}

async function loadBuilding(buildingId) {
  try {
    // Clear existing 3D models and UI state
    clearCurrentScene();
    
    const res = await fetch(`${CONFIG.apiBase}/building/${buildingId}`);
    buildingData = await res.json();

    renderBuilding(buildingData);
    populateRoomSelectors(buildingData);
  } catch (err) {
    console.error(`Failed to load data for ${buildingId}:`, err);
  }
}

function clearCurrentScene() {
  // Remove floor groups from the scene
  Object.values(floorGroups).forEach(group => {
    scene.remove(group);
  });
  
  // Remove route path if it exists
  if (currentPathLine) {
    scene.remove(currentPathLine);
    currentPathLine.geometry.dispose();
    currentPathLine.material.dispose();
    currentPathLine = null;
  }
  
  // Wipe internal state and HTML labels
  floorGroups = {};
  roomMeshes = {};
  document.getElementById('start-room').innerHTML = '<option value="">Select origin...</option>';
  document.getElementById('end-room').innerHTML = '<option value="">Select destination...</option>';
  document.getElementById('route-info').classList.add('hidden');
  
  // Clear CSS2D labels
  while (labelRenderer.domElement.firstChild) {
    labelRenderer.domElement.removeChild(labelRenderer.domElement.firstChild);
  }
}

// Update the calculatePath function to include the buildingId
async function calculatePath() {
  const startRoom = document.getElementById('start-room').value;
  const endRoom = document.getElementById('end-room').value;

  if (!currentBuildingId || !startRoom || !endRoom) return;

  try {
    const res = await fetch(`${CONFIG.apiBase}/navigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        building_id: currentBuildingId,
        start: startRoom, 
        end: endRoom 
      })
    });

    const result = await res.json();
    if (result.success) renderRoute(result);
  } catch (err) {
    console.error(err);
  }
}

function populateRoomSelectors(data) {
  const startSelect = document.getElementById('start-room');
  const endSelect = document.getElementById('end-room');
  const roomNames = new Set();

  for (const [floorName, floor] of Object.entries(data)) {
    if (floorName === 'stair_connections') continue;
    for (const box of floor.shoeboxes || []) {
      if (box.name) roomNames.add(box.name);
    }
  }

  const sortedRooms = Array.from(roomNames).sort();
  sortedRooms.forEach((room) => {
    startSelect.add(new Option(room, room));
    endSelect.add(new Option(room, room));
  });
}

// 3D Geometry Rendering
// 3D Geometry Rendering with Structural Approximations
function renderBuilding(data) {
  // Sort floor names by initial IFC elevation to compute exploded offsets
  const floorEntries = Object.entries(data)
    .filter(([key]) => key !== 'stair_connections')
    .sort((a, b) => a[1].elevation - b[1].elevation);

  floorEntries.forEach(([floorName, floorData], floorIndex) => {
    const floorGroup = new THREE.Group();
    floorGroups[floorName] = floorGroup;

    // Apply exploded spacing along the Three.js Y-axis
    const explodedY = floorIndex * 8.0 * CONFIG.explodedMultiplier;
    floorGroup.position.y = explodedY;

    let minFloorX = Infinity, maxFloorX = -Infinity;
    let minFloorZ = Infinity, maxFloorZ = -Infinity;

    // 1. Render Rooms (Approximating Walls via Edges and Volume)
    (floorData.shoeboxes || []).forEach((box) => {
      // Track outer bounds for the floor slab
      minFloorX = Math.min(minFloorX, box.min[0]);
      maxFloorX = Math.max(maxFloorX, box.max[0]);
      minFloorZ = Math.min(minFloorZ, box.min[1]); // IFC Y maps to Three Z
      maxFloorZ = Math.max(maxFloorZ, box.max[1]);

      // IFC [X, Y, Z] -> Three.js [X=X, Y=Z, Z=Y]
      const dx = box.max[0] - box.min[0];
      const dy = box.max[2] - box.min[2]; // Height
      const dz = box.max[1] - box.min[1]; // Depth

      const cx = (box.min[0] + box.max[0]) / 2;
      const cy = dy / 2;
      const cz = (box.min[1] + box.max[1]) / 2;

      const geometry = new THREE.BoxGeometry(dx, dy, dz);
      
      // Lower opacity for the room body to make it look like empty air bounded by walls
      const material = new THREE.MeshStandardMaterial({
        color: CONFIG.roomColor,
        transparent: true,
        opacity: 0.15, 
        depthWrite: false 
      });

      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(cx, cy, cz);
      mesh.userData = { name: box.name, floor: floorName };

      // Emphasize the edges to act as physical wall boundaries
      const wireGeo = new THREE.EdgesGeometry(geometry);
      const wireMat = new THREE.LineBasicMaterial({
        color: 0x64748b, // Solid slate color for walls
        transparent: true,
        opacity: 0.6
      });
      const wireframe = new THREE.LineSegments(wireGeo, wireMat);
      mesh.add(wireframe);

      if (box.name) {
        const labelDiv = document.createElement('div');
        labelDiv.className = 'room-label';
        // Check for common messy IFC prefixes and clean them up if necessary
        labelDiv.textContent = box.name; 
        
        const roomLabel = new CSS2DObject(labelDiv);
        // Position it slightly above the center of the room to prevent overlapping the route path
        roomLabel.position.set(0, cy + 0.4, 0); 
        mesh.add(roomLabel); // Attach label to the room mesh so it moves with the exploded floor
      }


      floorGroup.add(mesh);

      if (!roomMeshes[box.name]) roomMeshes[box.name] = [];
      roomMeshes[box.name].push(mesh);
    });

    // 2. Render the Concrete Floor Slab
    if (minFloorX !== Infinity) {
      const padding = 1.0; // Extend slab slightly beyond the outer rooms
      const slabW = (maxFloorX - minFloorX) + padding * 2;
      const slabD = (maxFloorZ - minFloorZ) + padding * 2;
      const slabCx = minFloorX + (maxFloorX - minFloorX) / 2;
      const slabCz = minFloorZ + (maxFloorZ - minFloorZ) / 2;

      const slabGeo = new THREE.BoxGeometry(slabW, 0.2, slabD);
      const slabMat = new THREE.MeshStandardMaterial({
        color: 0x1e293b, // Dark base color
        transparent: true,
        opacity: 0.75
      });
      const slabMesh = new THREE.Mesh(slabGeo, slabMat);
      
      // Position slightly below Y=0 so it doesn't clip with the room bottoms
      slabMesh.position.set(slabCx, -0.1, slabCz); 
      floorGroup.add(slabMesh);
    }
    

    // 3. Render Stair & Elevator Shafts
    (floorData.nodes || []).forEach(node => {
      if (node.type === "stair") {
        const shaftHeight = 3.5; // Approximate typical floor height
        const shaftGeo = new THREE.BoxGeometry(2.5, shaftHeight, 2.5);
        const shaftMat = new THREE.MeshStandardMaterial({
          color: 0xf59e0b, // Amber highlight for vertical connections
          transparent: true,
          opacity: 0.4
        });
        const shaftMesh = new THREE.Mesh(shaftGeo, shaftMat);
        
        // node.pos contains [X, Y] from the IFC grid, mapped to Three's [X, Z]
        shaftMesh.position.set(node.pos[0], shaftHeight / 2, node.pos[1]);
        
        // Add a strong wireframe to make the shaft stand out
        const shaftWireMat = new THREE.LineBasicMaterial({ color: 0xd97706, opacity: 0.8 });
        const shaftWireframe = new THREE.LineSegments(new THREE.EdgesGeometry(shaftGeo), shaftWireMat);
        shaftMesh.add(shaftWireframe);

        const labelDiv = document.createElement('div');
        labelDiv.className = 'stair-label';
        labelDiv.textContent = 'Stairs';
        
        const stairLabel = new CSS2DObject(labelDiv);
        stairLabel.position.set(0, shaftHeight / 2 + 0.6, 0); // Float above the amber box
        shaftMesh.add(stairLabel);

        floorGroup.add(shaftMesh);
      }
    });

    scene.add(floorGroup);
  });
}



function renderRoute(routeData) {
  // Clear previous path line
  if (currentPathLine) {
    scene.remove(currentPathLine);
    currentPathLine.geometry.dispose();
    currentPathLine.material.dispose();
    currentPathLine = null;
  }

  // Reset room styles
  resetRoomHighlights();

  const points = [];
  const floorsInPath = new Set();

  routeData.path.forEach((node) => {
    floorsInPath.add(node.floor);
    const floorGroup = floorGroups[node.floor];
    const floorY = floorGroup ? floorGroup.position.y : 0;

    // Position path points slightly elevated off the floor plane
    points.push(new THREE.Vector3(node.pos[0], floorY + 0.25, node.pos[1]));
  });

  // Construct glowing route line
  const curve = new THREE.CatmullRomCurve3(points, false, 'catmullrom', 0.05);
  const tubeGeometry = new THREE.TubeGeometry(curve, points.length * 6, 0.12, 8, false);
  const tubeMaterial = new THREE.MeshBasicMaterial({
    color: CONFIG.pathColor,
    wireframe: false
  });

  currentPathLine = new THREE.Mesh(tubeGeometry, tubeMaterial);
  scene.add(currentPathLine);

  // Highlight origin and destination rooms
  highlightRoom(routeData.start, CONFIG.startColor);
  highlightRoom(routeData.end, CONFIG.endColor);

  // Update UI Stats
  document.getElementById('distance-value').innerText = routeData.total_distance;
  document.getElementById('segment-count').innerText = routeData.path.length;
  document.getElementById('route-info').classList.remove('hidden');
}

function highlightRoom(roomName, colorHex) {
  const meshes = roomMeshes[roomName];
  if (!meshes) return;

  meshes.forEach((mesh) => {
    mesh.material.color.setHex(colorHex);
    mesh.material.opacity = CONFIG.highlightOpacity;
  });
}

function resetRoomHighlights() {
  Object.values(roomMeshes).flat().forEach((mesh) => {
    mesh.material.color.setHex(CONFIG.roomColor);
    mesh.material.opacity = CONFIG.baseOpacity;
  });
}

// UI Controls
function setupUIEvents() {
  document.getElementById('find-path-btn').addEventListener('click', calculatePath);

  const btn3D = document.getElementById('view-3d-btn');
  const btn2D = document.getElementById('view-2d-btn');

  btn3D.addEventListener('click', () => {
    btn3D.classList.add('active');
    btn2D.classList.remove('active');
    camera.position.set(40, 50, 60);
    controls.target.set(0, 0, 0);
  });

  btn2D.addEventListener('click', () => {
    btn2D.classList.add('active');
    btn3D.classList.remove('active');
    camera.position.set(0, 100, 0); // Orthographic top-down vantage
    controls.target.set(0, 0, 0);
  });

  const profileIcon = document.getElementById('profile-icon');
  const profileDropdown = document.getElementById('profile-dropdown');
  const logoutBtn = document.getElementById('logout-btn');

  profileIcon.addEventListener('click', () => {
    profileDropdown.classList.toggle('hidden');
  });

  logoutBtn.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/landing.html';
  });
}