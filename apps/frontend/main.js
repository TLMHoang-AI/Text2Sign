import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { SkeletonHelper } from 'three';

// ── State ───────────────────────────────────────────────
let renderer, scene, camera, controls;
let mixer = null, clock, animAction = null;
let model = null, skeletonHelper = null;
let isPlaying = false;
let animDuration = 0;
let frameId = null;
let lastFpsTime = 0, fpsCount = 0;

// Subtitle state
let currentTimings = [];

// Auth state
let authToken = localStorage.getItem('fbx_auth_token') || null;
let currentUser = null;
let authMode = 'login'; // 'login' or 'signup'

const HOST = window.location.hostname;
const isLocal = (HOST === 'localhost' || HOST === '127.0.0.1' || HOST.startsWith('192.168.'));
const API_BASE = isLocal ? `http://${HOST}:8000` : 'https://api.text2sign.io.vn';


// ── Init Three.js ────────────────────────────────────────
function initThree() {
    const canvas = document.getElementById('viewport');

    // Renderer
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f0f1a);
    scene.fog = new THREE.Fog(0x0f0f1a, 20, 80);

    // Camera
    camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
    camera.position.set(0, 1.6, 4.5);

    // Clock
    clock = new THREE.Clock();

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.target.set(0, 1.0, 0);
    controls.minDistance = 0.5;
    controls.maxDistance = 30;
    controls.userData = {}; // Initialize userData for controls
    controls.update();

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(5, 10, 5);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.set(2048, 2048);
    dirLight.shadow.camera.near = 0.1;
    dirLight.shadow.camera.far = 50;
    dirLight.shadow.camera.left = -5;
    dirLight.shadow.camera.right = 5;
    dirLight.shadow.camera.top = 5;
    dirLight.shadow.camera.bottom = -5;
    scene.add(dirLight);

    // Fill light (rim from behind)
    const rimLight = new THREE.DirectionalLight(0x4FACFE, 0.4);
    rimLight.position.set(-3, 5, -5);
    scene.add(rimLight);

    const fillLight = new THREE.HemisphereLight(0x6C63FF, 0x0f0f1a, 0.3);
    scene.add(fillLight);

    // Grid
    const grid = new THREE.GridHelper(20, 40, 0x333355, 0x1a1a2e);
    grid.name = 'grid';
    scene.add(grid);

    // Ground plane (shadow receiver)
    const groundGeo = new THREE.PlaneGeometry(20, 20);
    const groundMat = new THREE.ShadowMaterial({ opacity: 0.25 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // Resize
    resizeRenderer();
    window.addEventListener('resize', resizeRenderer);

    // Start loop
    renderLoop();
}

function resizeRenderer() {
    const wrap = document.querySelector('.viewport-wrapper');
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
}

// ── Render Loop ──────────────────────────────────────────
function renderLoop() {
    frameId = requestAnimationFrame(renderLoop);

    const delta = clock.getDelta();

    // FPS counter
    fpsCount++;
    const now = performance.now();
    if (now - lastFpsTime >= 500) {
        const fps = Math.round(fpsCount / ((now - lastFpsTime) / 1000));
        document.getElementById('fpsCounter').textContent = fps + ' FPS';
        fpsCount = 0;
        lastFpsTime = now;
    }

    // Update animation mixer
    if (mixer && isPlaying) {
        mixer.update(delta);
        updateTimelineUI();
    }

    // Update subtitle highlights
    if (animAction && currentTimings && currentTimings.length > 0) {
        const t = animAction.time;
        const subtitleDisplay = document.getElementById('subtitleDisplay');
        if (subtitleDisplay && !subtitleDisplay.classList.contains('hidden')) {
            const spans = subtitleDisplay.querySelectorAll('span');
            spans.forEach((span, idx) => {
                const w = currentTimings[idx];
                if (w && t >= w.start_time && t < w.end_time) {
                    span.classList.add('highlight');
                } else {
                    span.classList.remove('highlight');
                }
            });
        }
    }

    controls.update();
    renderer.render(scene, camera);
}

// ── FBX Loader ───────────────────────────────────────────
function loadFBX(file) {
    showLoading(true);

    const url = URL.createObjectURL(file);
    const loader = new FBXLoader();

    loader.load(
        url,
        (fbx) => {
            URL.revokeObjectURL(url);

            // Remove old model
            if (model) {
                scene.remove(model);
                if (skeletonHelper) {
                    scene.remove(skeletonHelper);
                    skeletonHelper = null;
                }
                if (mixer) {
                    mixer.stopAllAction();
                    mixer = null;
                    animAction = null;
                }
            }

            model = fbx;

            // Scale & position
            const box = new THREE.Box3().setFromObject(model);
            const size = box.getSize(new THREE.Vector3());
            const center = box.getCenter(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 2.0 / maxDim;
            model.scale.setScalar(scale);

            // Re-compute center after scale
            box.setFromObject(model);
            const newCenter = box.getCenter(new THREE.Vector3());
            const newMin = box.min;
            model.position.sub(newCenter);
            model.position.y -= newMin.y - (newMin.y - newCenter.y);
            // Ensure character stands on grid
            box.setFromObject(model);
            model.position.y -= box.min.y;

            // Shadows
            model.traverse((child) => {
                if (child.isMesh) {
                    child.castShadow = true;
                    child.receiveShadow = true;
                    // Improve material quality
                    if (child.material) {
                        const mats = Array.isArray(child.material) ? child.material : [child.material];
                        mats.forEach(m => {
                            if (m.isMeshPhongMaterial || m.isMeshStandardMaterial) {
                                m.envMapIntensity = 0.5;
                            }
                        });
                    }
                }
            });

            scene.add(model);

            // Animation
            mixer = new THREE.AnimationMixer(model);
            if (model.animations && model.animations.length > 0) {
                animAction = mixer.clipAction(model.animations[0]);
                animAction.play();
                animAction.paused = true;
                isPlaying = false;
                animDuration = model.animations[0].duration;
                showPlaybackBar(true);
                setPlayPauseIcon(false);
            } else {
                showPlaybackBar(false);
            }

            // Camera: frame the model (since it's scaled to ~2.0)
            const modelHeight = size.y * scale;
            const camDist = 2.5; // Always distance 2.5 for a 2.0 unit model

            camera.position.set(0, modelHeight * 0.6, camDist);
            controls.target.set(0, modelHeight * 0.6, 0);
            controls.update();

            // Store original positions for reset 
            camera.userData.defaultPos = camera.position.clone();
            controls.userData.defaultTarget = controls.target.clone();

            // Skeleton helper
            skeletonHelper = new THREE.SkeletonHelper(model);
            skeletonHelper.visible = document.getElementById('showSkeleton').checked;
            scene.add(skeletonHelper);

            showLoading(false);
        },
        (xhr) => {
            if (xhr.total > 0) {
                const pct = (xhr.loaded / xhr.total) * 100;
                document.getElementById('loadingBar').style.width = pct + '%';
            }
        },
        (err) => {
            if (url.startsWith('blob:')) URL.revokeObjectURL(url);
            console.error('FBX load error:', err);
            showLoading(false);
            alert('❌ Lỗi khi load file FBX: ' + err.message);
        }
    );
}

// ── UI Helpers ───────────────────────────────────────────
function showLoading(show) {
    document.getElementById('loadingOverlay').classList.toggle('hidden', !show);
    if (show) document.getElementById('loadingBar').style.width = '0%';
}
function showPlaybackBar(show) { document.getElementById('playbackBar').classList.toggle('hidden', !show); }

function setPlayPauseIcon(playing) {
    document.getElementById('playIcon').style.display = playing ? 'none' : 'block';
    document.getElementById('pauseIcon').style.display = playing ? 'block' : 'none';
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m + ':' + String(s).padStart(2, '0');
}

function updateTimelineUI() {
    if (!animAction) return;
    const t = animAction.time;
    const dur = animDuration;
    document.getElementById('currentTime').textContent = formatTime(t);
    document.getElementById('totalTime').textContent = formatTime(dur);
    const slider = document.getElementById('timeline');
    if (!slider.matches(':active')) {
        slider.value = dur > 0 ? t / dur : 0;
    }
}

// ── Event Wiring ─────────────────────────────────────────
function setupEvents() {
    const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
    const sidebar = document.querySelector('.sidebar');

    if (toggleSidebarBtn && sidebar) {
        toggleSidebarBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
        });
    }

    // Chat Box Submit Logic
    const submitTextBtn = document.getElementById('submitTextBtn');
    const aiInputText = document.getElementById('aiInputText');
    if (submitTextBtn && aiInputText) {
        submitTextBtn.addEventListener('click', async () => {
            const text = aiInputText.value.trim();
            if (!text) return;

            submitTextBtn.disabled = true;
            submitTextBtn.textContent = 'Processing...';

            const subtitleDisplay = document.getElementById('subtitleDisplay');
            if (subtitleDisplay) {
                subtitleDisplay.classList.add('hidden');
                subtitleDisplay.textContent = '';
            }

            // Helper: poll task until done or error
            async function pollTask(taskId, intervalMs = 500) {
                while (true) {
                    const res = await fetch(`${API_BASE}/tasks/${taskId}`);
                    const data = await res.json().catch(() => ({}));
                    if (data.status === 'done') return data.result;
                    if (data.status === 'error') throw new Error(data.error || 'Task failed');
                    await new Promise(r => setTimeout(r, intervalMs));
                }
            }

            try {
                console.log('Sending text to translation API:', text);
                submitTextBtn.textContent = 'Creating animations...';

                // Step 1: Submit translate job → get task_id immediately
                const translateRes = await fetch(`${API_BASE}/translate`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${authToken}`
                    },
                    body: JSON.stringify({ sentence: text })
                });

                const submitted = await translateRes.json().catch(() => ({}));
                if (!translateRes.ok) {
                    throw new Error('API Error: ' + (submitted.detail || translateRes.statusText));
                }

                const taskId = submitted.task_id;
                if (!taskId) throw new Error('No task_id returned from server.');
                console.log('[Task] submitted:', taskId);
                fetchHistory(); // Refresh to show pending status

                // Step 2: Poll until done
                let dots = 0;
                const dotTimer = setInterval(() => {
                    dots = (dots + 1) % 4;
                    submitTextBtn.textContent = 'Processing' + '.'.repeat(dots + 1);
                }, 500);

                let result;
                try {
                    result = await pollTask(taskId);
                } finally {
                    clearInterval(dotTimer);
                }

                // Step 3: Extract output
                const outputFiles = result.output_files || [];
                if (outputFiles.length === 0) throw new Error('Pipeline returned no FBX file.');

                const subtitleText = result.subtitle_text || '';
                const subtitleTimings = result.subtitle_timings || [];

                currentTimings = [];
                if (subtitleDisplay) {
                    subtitleDisplay.innerHTML = '';
                    if (subtitleTimings.length > 0) {
                        currentTimings = subtitleTimings;
                        subtitleTimings.forEach(w => {
                            const span = document.createElement('span');
                            span.textContent = w.text + ' ';
                            subtitleDisplay.appendChild(span);
                        });
                        subtitleDisplay.classList.remove('hidden');
                    } else if (subtitleText) {
                        subtitleDisplay.textContent = subtitleText;
                        subtitleDisplay.classList.remove('hidden');
                    }
                }

                // Step 4: Download & load FBX
                const fbxName = outputFiles[0];
                console.log('Output FBX:', fbxName);
                submitTextBtn.textContent = 'Loading FBX...';

                const fbxRes = await fetch(`${API_BASE}/fbx/${fbxName}`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                if (!fbxRes.ok) throw new Error('Error loading FBX file: ' + fbxRes.status);
                const blob = await fbxRes.blob();
                const file = new File([blob], fbxName, { type: 'application/octet-stream' });
                handleFile(file);

                submitTextBtn.disabled = false;
                submitTextBtn.textContent = 'CREATE ANIMATIONS';
                if (typeof fetchHistory === 'function') fetchHistory();
            } catch (err) {
                console.error(err);
                alert("Error: " + err.message);
                submitTextBtn.disabled = false;
                submitTextBtn.textContent = 'CREATE ANIMATIONS';
                if (typeof fetchHistory === 'function') fetchHistory();
            }
        });
    }

    // Drag & drop on viewport
    const viewport = document.querySelector('.viewport-wrapper');
    viewport.addEventListener('dragover', (e) => e.preventDefault());
    viewport.addEventListener('drop', (e) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file && file.name.toLowerCase().endsWith('.fbx')) handleFile(file);
    });

    // Play / Pause
    document.getElementById('playPauseBtn').addEventListener('click', togglePlayPause);

    // Stop
    document.getElementById('stopBtn').addEventListener('click', () => {
        if (!animAction) return;
        animAction.stop();
        animAction.play();
        mixer.update(0);
        animAction.paused = false;
        isPlaying = false;
        animAction.paused = true;
        setPlayPauseIcon(false);
        updateTimelineUI();
    });

    // Timeline scrub
    const timelineSlider = document.getElementById('timeline');
    timelineSlider.addEventListener('input', () => {
        if (!animAction) return;
        animAction.time = parseFloat(timelineSlider.value) * animDuration;
        mixer.update(0);
        updateTimelineUI();
    });

    // Speed
    document.getElementById('speedSelect').addEventListener('change', (e) => {
        if (animAction) animAction.timeScale = parseFloat(e.target.value);
    });

    // Auto rotate
    document.getElementById('autoRotate').addEventListener('change', (e) => {
        controls.autoRotate = e.target.checked;
    });

    // Rotate speed
    const rotateSpeedSlider = document.getElementById('rotateSpeed');
    rotateSpeedSlider.addEventListener('input', (e) => {
        controls.autoRotateSpeed = parseFloat(e.target.value);
        document.getElementById('rotateSpeedVal').textContent = parseFloat(e.target.value).toFixed(1);
    });

    // Reset camera
    document.getElementById('resetCameraBtn').addEventListener('click', () => {
        if (camera.userData.defaultPos) {
            camera.position.copy(camera.userData.defaultPos);
            controls.target.copy(controls.userData.defaultTarget);
        } else {
            camera.position.set(0, 1.2, 2.5);
            controls.target.set(0, 1.2, 0);
        }
        controls.update();
    });

    // Show grid
    document.getElementById('showGrid').addEventListener('change', (e) => {
        const grid = scene.getObjectByName('grid');
        if (grid) grid.visible = e.target.checked;
    });

    // Show skeleton
    document.getElementById('showSkeleton').addEventListener('change', (e) => {
        if (skeletonHelper) skeletonHelper.visible = e.target.checked;
    });

    // Background color
    document.getElementById('bgColor').addEventListener('input', (e) => {
        const col = new THREE.Color(e.target.value);
        scene.background = col;
        scene.fog = new THREE.Fog(e.target.value, 20, 80);
        document.body.style.setProperty('--bg', e.target.value);
    });

    // Fullscreen
    document.getElementById('fullscreenBtn').addEventListener('click', () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    });

    // Keyboard shortcuts
    window.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) {
            e.preventDefault();
            togglePlayPause();
        }
        if (e.code === 'KeyR' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) {
            if (camera.userData.defaultPos) {
                camera.position.copy(camera.userData.defaultPos);
                controls.target.copy(controls.userData.defaultTarget);
            } else {
                camera.position.set(0, 1.2, 2.5);
                controls.target.set(0, 1.2, 0);
            }
            controls.update();
        }
    });

    // ── AUTH EVENTS ────────────────────────────────────
    const authBtn = document.getElementById('authBtn');
    const authModal = document.getElementById('authModal');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const authForm = document.getElementById('authForm');
    const toggleAuthMode = document.getElementById('toggleAuthMode');
    const logoutBtn = document.getElementById('logoutBtn');

    if (authBtn) authBtn.addEventListener('click', () => {
        authModal.classList.add('active');
    });

    if (closeModalBtn) closeModalBtn.addEventListener('click', () => {
        authModal.classList.remove('active');
    });

    if (toggleAuthMode) toggleAuthMode.addEventListener('click', () => {
        authMode = authMode === 'login' ? 'signup' : 'login';
        document.getElementById('modalTitle').textContent = authMode === 'login' ? 'Login' : 'Signup';
        document.getElementById('authSubmitBtn').textContent = authMode === 'login' ? 'Login' : 'Signup';
        toggleAuthMode.innerHTML = authMode === 'login'
            ? "Don't have an account? <span>Signup</span>"
            : "Already have an account? <span>Login</span>";
    });

    if (authForm) authForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('usernameInput').value;
        const password = document.getElementById('passwordInput').value;

        try {
            if (authMode === 'signup') {
                const res = await fetch(`${API_BASE}/users/signup`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                if (!res.ok) throw new Error(await res.text());
                alert('Signup successful! Please login.');
                toggleAuthMode.click();
            } else {
                const formData = new FormData();
                formData.append('username', username);
                formData.append('password', password);

                const res = await fetch(`${API_BASE}/users/login`, {
                    method: 'POST',
                    body: formData
                });
                if (!res.ok) throw new Error('Invalid username or password');
                const data = await res.json();
                authToken = data.access_token;
                localStorage.setItem('fbx_auth_token', authToken);
                authModal.classList.remove('active');
                await checkAuthState();
            }
        } catch (err) {
            alert('Auth error: ' + err.message);
        }
    });

    if (logoutBtn) logoutBtn.addEventListener('click', () => {
        authToken = null;
        currentUser = null;
        localStorage.removeItem('fbx_auth_token');
        updateAuthUI();
    });

    // Dashboard Events
    const viewAllBtn = document.getElementById('viewAllHistoryBtn');
    const dashboard = document.getElementById('historyDashboard');
    const closeDashBtn = document.getElementById('closeDashboardBtn');

    if (viewAllBtn && dashboard) {
        viewAllBtn.addEventListener('click', () => {
            dashboard.classList.add('active');
        });
    }

    if (closeDashBtn && dashboard) {
        closeDashBtn.addEventListener('click', () => {
            dashboard.classList.remove('active');
        });
    }

    // Sidebar Resizing
    const resizer = document.getElementById('sidebarResizer');
    let isResizing = false;

    if (resizer && sidebar) {
        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            resizer.classList.add('resizing');
            e.preventDefault();
        });

        window.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            let newWidth = e.clientX;
            if (newWidth < 250) newWidth = 250;
            if (newWidth > 600) newWidth = 600;
            
            sidebar.style.width = `${newWidth}px`;
            // Update the CSS variable so other elements can react if needed
            document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
        });

        window.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = 'default';
                resizer.classList.remove('resizing');
            }
        });
    }
}

// ── Auth Logic ──────────────────────────────────────────
async function checkAuthState() {
    if (!authToken) {
        updateAuthUI();
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/users/me`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('Session expired');
        currentUser = await res.json();
        updateAuthUI();
        fetchHistory();
    } catch (err) {
        authToken = null;
        localStorage.removeItem('fbx_auth_token');
        updateAuthUI();
    }
}

function updateAuthUI() {
    const authBtn = document.getElementById('authBtn');
    const userProfile = document.getElementById('userProfile');
    const historySection = document.getElementById('historySection');
    const submitTextBtn = document.getElementById('submitTextBtn');

    if (currentUser) {
        if (authBtn) authBtn.classList.add('hidden');
        if (userProfile) userProfile.classList.remove('hidden');
        const nameDisplay = document.getElementById('userNameDisplay');
        if (nameDisplay) nameDisplay.textContent = currentUser.username;
        if (historySection) historySection.classList.remove('hidden');
        if (submitTextBtn) {
            submitTextBtn.disabled = false;
            submitTextBtn.title = "";
        }
    } else {
        if (authBtn) authBtn.classList.remove('hidden');
        if (userProfile) userProfile.classList.add('hidden');
        if (historySection) historySection.classList.add('hidden');
        if (submitTextBtn) {
            submitTextBtn.disabled = true;
            submitTextBtn.title = "Please login to create animations";
        }
    }
}

async function fetchHistory() {
    if (!authToken) return;
    try {
        const res = await fetch(`${API_BASE}/users/history`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        const data = await res.json();
        renderHistory(data);
        renderDashboard(data);
    } catch (err) {
        console.error('History fetch error:', err);
    }
}

function renderHistory(items) {
    const list = document.getElementById('historyList');
    if (!list) return;
    list.innerHTML = '';
    
    // Only show max 3 items as requested
    const displayItems = items.slice(0, 3);
    const viewAllBtn = document.getElementById('viewAllHistoryBtn');
    
    if (displayItems.length === 0) {
        list.innerHTML = '<p class="text-muted" style="font-size: 12px; text-align: center;">No history yet.</p>';
        if (viewAllBtn) viewAllBtn.style.display = 'none';
        return;
    }

    if (viewAllBtn && items.length > 3) {
        viewAllBtn.style.display = 'block';
    } else if (viewAllBtn) {
        viewAllBtn.style.display = 'none';
    }
    
    const now = new Date();
    
    displayItems.forEach(item => {
        const div = document.createElement('div');
        div.className = 'history-item';
        
        const createdAt = new Date(item.created_at);
        const dateStr = createdAt.toLocaleString();
        
        // Timeout logic: if pending for > 5 mins, show as timeout/error
        let status = item.status;
        const diffMin = (now - createdAt) / 1000 / 60;
        if (status === 'pending' && diffMin > 5) {
            status = 'timeout';
        }
        
        const isDone = status === 'done';
        const isError = status === 'error' || status === 'timeout';
        
        div.innerHTML = `
            <div class="history-text" title="${item.sentence}">${item.sentence}</div>
            <div class="history-meta">
                <span>${dateStr}</span>
                <span class="badge ${isError ? 'badge-error' : ''}" style="min-width:auto; ${isError ? 'color:#ef4444;border-color:#ef444433' : ''}">${status}</span>
            </div>
            ${(item.videos && isDone) ? `
                <div class="history-actions">
                    <button class="btn btn-sm btn-primary btn-load-hist" data-filename="${item.videos}">View</button>
                    <a href="${API_BASE}/fbx/${item.videos}" class="btn btn-sm btn-download" download>Download</a>
                </div>
            ` : ''}
        `;
        list.appendChild(div);
    });

    // Add event listeners for load buttons
    list.querySelectorAll('.btn-load-hist').forEach(btn => {
        btn.addEventListener('click', async () => {
            const filename = btn.getAttribute('data-filename');
            try {
                showLoading(true);
                const res = await fetch(`${API_BASE}/fbx/${filename}`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                if (!res.ok) throw new Error('File not found');
                const blob = await res.blob();
                const file = new File([blob], filename, { type: 'application/octet-stream' });
                handleFile(file);
            } catch (err) {
                alert('Error loading file: ' + err.message);
                showLoading(false);
            }
        });
    });
}

function renderDashboard(items) {
    const tableBody = document.getElementById('dashboardTableBody');
    const emptyMsg = document.getElementById('dashboardEmpty');
    const dashboard = document.getElementById('historyDashboard');
    if (!tableBody) return;

    tableBody.innerHTML = '';
    if (items.length === 0) {
        if (emptyMsg) emptyMsg.style.display = 'block';
        return;
    }
    if (emptyMsg) emptyMsg.style.display = 'none';

    const now = new Date();

    items.forEach(item => {
        const createdAt = new Date(item.created_at);
        const dateStr = createdAt.toLocaleString();
        
        let status = item.status;
        const diffMin = (now - createdAt) / 1000 / 60;
        if (status === 'pending' && diffMin > 5) {
            status = 'timeout';
        }

        const isDone = status === 'done';
        const isError = status === 'error' || status === 'timeout';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><div style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${item.sentence}">${item.sentence}</div></td>
            <td><span class="badge ${isError ? 'badge-error' : ''}" style="${isError ? 'color:#ef4444;border-color:#ef444433' : ''}">${status}</span></td>
            <td>${dateStr}</td>
            <td>
                <div class="history-actions" style="justify-content: flex-start; gap: 8px;">
                    ${(item.videos && isDone) ? `
                        <button class="btn btn-sm btn-primary btn-load-hist-dash" data-filename="${item.videos}">View</button>
                        <a href="${API_BASE}/fbx/${item.videos}" class="btn btn-sm btn-download" download>Download</a>
                    ` : '-'}
                </div>
            </td>
        `;
        tableBody.appendChild(tr);
    });

    // Add listeners for dashboard "View" buttons
    tableBody.querySelectorAll('.btn-load-hist-dash').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (dashboard) dashboard.classList.remove('active');
            const filename = btn.getAttribute('data-filename');
            try {
                showLoading(true);
                const res = await fetch(`${API_BASE}/fbx/${filename}`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                if (!res.ok) throw new Error('File not found');
                const blob = await res.blob();
                const file = new File([blob], filename, { type: 'application/octet-stream' });
                handleFile(file);
            } catch (err) {
                alert('Error loading file: ' + err.message);
                showLoading(false);
            }
        });
    });
}

function handleFile(file) {
    loadFBX(file);
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function togglePlayPause() {
    if (!animAction) return;
    if (isPlaying) {
        animAction.paused = true;
        isPlaying = false;
    } else {
        animAction.paused = false;
        isPlaying = true;
    }
    setPlayPauseIcon(isPlaying);
}

// ── Bootstrap ────────────────────────────────────────────
initThree();
setupEvents();
checkAuthState();
loadDefaultFBX();

function loadDefaultFBX() {
    const defaultUrl = 'fbx_only_backend/XBOTXBOT.fbx';
    showLoading(true);

    fetch(defaultUrl)
        .then(res => {
            if (!res.ok) throw new Error('Default FBX not found');
            return res.blob();
        })
        .then(blob => {
            const file = new File([blob], 'XBOTXBOT.fbx', { type: '' });
            handleFile(file);
        })
        .catch(err => {
            console.warn('Could not load default FBX:', err);
            showLoading(false);
            showWelcome();
        });
}
