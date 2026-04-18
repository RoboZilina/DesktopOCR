/**
 * js/core/engine_manager.js
 * EngineManager Singleton - Central source of truth for engine lifecycle and identity.
 * Gold v3.8 Compliance
 */

import { STATUS } from './status.js?v=3.8.4';

// EngineManager (Singleton)
// Central source of truth for engine lifecycle and identity.
// ============================

/* eslint-disable no-unused-expressions */
const EngineManager = ((engines) => {

    // Internal State Machine (Gold v3.8 Compliance)
    const engineMetadata = new Map(); // id -> { instance, state, loadPromise }

    // Memory guard: evict heavy engines when switching
    function evictOtherEngines(activeId) {
        const KEEP_CACHED = new Set(['paddle', 'tesseract']); // engines allowed to stay in memory

        for (const [id, meta] of engineMetadata.entries()) {
            if (id === activeId) continue;          // never evict active engine
            if (KEEP_CACHED.has(id)) continue;      // keep paddle/tesseract cached

            if (meta.instance) {
                try {
                    meta.instance.dispose?.();
                } catch (e) {
                    console.warn(`[ENGINE] dispose failed for ${id}`, e);
                }
            }

            engineMetadata.delete(id);
        }
    }

    let currentEngineId = 'tesseract'; // Default starting point
    let currentEngine = null;
    let switchingLock = false;
    let currentCapabilities = {};
    let currentInfo = { id: 'tesseract', capabilities: {} };

    // Fixed Labels for Status Formatting
    const ENGINE_LABELS = {
        'tesseract': 'Tesseract',
        'paddle': 'PaddleOCR',
        'manga': 'MangaOCR'
    };

    // Status listeners (UI will subscribe later)
    const statusListeners = new Set();
    const listeners = { ready: [], loading: [], error: [] };
    let isReady = false;

    // Subscribe to status updates
    function onStatusChange(listener) {
        statusListeners.add(listener);
        return () => statusListeners.delete(listener);
    }

    // Subscribe to specific events
    function onReady(fn) { listeners.ready.push(fn); return () => { listeners.ready = listeners.ready.filter(f => f !== fn); }; }
    function onLoading(fn) { listeners.loading.push(fn); return () => { listeners.loading = listeners.loading.filter(f => f !== fn); }; }
    function onError(fn) { listeners.error.push(fn); return () => { listeners.error = listeners.error.filter(f => f !== fn); }; }

    function emit(type, payload) {
        if (listeners[type]) {
            listeners[type].forEach(fn => fn(payload));
        }
    }

    /**
     * Unified Status Broadcaster
     * Formats outgoing text as "[Engine] — [Status]"
     */
    function notifyStatus(state, text, progress = null, targetId = null) {
        const id = targetId || currentEngineId;
        const label = ENGINE_LABELS[id] || id;

        // Guard: ensure text is a string
        const safeText = String(text || '');

        // Format logic: Only prepend engine name if it's not already there
        const statusText = safeText.includes('—') ? safeText : `${label} — ${safeText}`;

        if (state === STATUS.READY) emit('ready', statusText);
        if (state === STATUS.LOADING || state === STATUS.DOWNLOADING || state === STATUS.WARMING) emit('loading', statusText);
        if (state === STATUS.ERROR) emit('error', statusText);

        for (const fn of statusListeners) {
            try { fn({ state, text: statusText, progress, engineId: id }); } catch { }
        }
    }

    /**
     * State-Aware Engine Loader
     * Implements promise deduplication and background readiness.
     */
    async function getOrLoadEngine(id, isSilent = false) {
        // Bug #9 fix: gate stack trace behind debug flag (was unconditional console.trace)
        if (window.VNOCR_DEBUG) console.trace(`[ENGINE] getOrLoadEngine(${id})`);

        let meta = engineMetadata.get(id);

        if (!meta) {
            meta = { instance: null, state: 'not_loaded', loadPromise: null };
            engineMetadata.set(id, meta);
        }

        // 1. Cache/Deduplication Hit
        if (meta.state === 'ready') return meta.instance;
        if (meta.state === 'loading') return meta.loadPromise;

        // 2. Start Loading Lifecycle (all engines load on the main thread)
        // ONNX InferenceSession objects are not transferable across Worker boundaries,
        // so a Worker-based preload cannot hand off a live session to the main thread.
        // All engines load via cooperative async scheduling. Tesseract always anchors
        // interactivity first; Paddle/Manga preload silently in the background.
        meta.state = 'loading';
        const loadStartTime = performance.now();

        // ATOMIC FIX: Create and assign promise synchronously BEFORE any await
        // This ensures concurrent callers see the loadPromise immediately
        const loadPromise = (async () => {
            try {
                const registryEntry = engines[id];
                if (!registryEntry) throw new Error(`Unknown engine: ${id}`);

                const reporter = (state, text, progress) => {
                    // Update internal state tracking
                    if (state === STATUS.READY) meta.state = 'ready';
                    
                    // Broadcast to UI if active or forced, or if state is ERROR, or if debug flag is set
                    if (!isSilent || id === currentEngineId || state === STATUS.ERROR || window.VNOCR_DEBUG) {
                        notifyStatus(state, text, progress, id);
                    }
                };

                const instance = registryEntry.factory({ reportStatus: reporter });
                
                if (instance && typeof instance.load === 'function') {
                    await instance.load();
                }

                await _warmUpEngine(instance, id);

                meta.instance = instance;
                meta.state = 'ready';
                
                // Observability: log successful load completion (gated by VNOCR_DEBUG)
                const loadDuration = Math.round(performance.now() - loadStartTime);
                if (window.VNOCR_DEBUG) {
                    console.debug(`[ENGINE-METRIC] ${id} loaded successfully in ${loadDuration}ms (silent: ${isSilent})`);
                }
                // Telemetry hook for opt-in collection
                if (window.VNOCR_TELEMETRY && typeof window.VNOCR_TELEMETRY === 'function') {
                    window.VNOCR_TELEMETRY({ type: 'engine_loaded', engineId: id, duration: loadDuration, silent: isSilent });
                }
                
                return instance;
            } catch (err) {
                meta.state = 'error';
                meta._lastError = err?.message; // Capture for finally block
                throw err;
            } finally {
                meta.loadPromise = null; // Always clear promise in both success and error paths

                // Observability: log error transition with timing (gated by VNOCR_DEBUG)
                // Note: Only log if we came from catch (meta.state === 'error')
                if (meta.state === 'error' && meta._lastError) {
                    const loadDuration = Math.round(performance.now() - loadStartTime);
                    const errorMsg = meta._lastError;
                    if (window.VNOCR_DEBUG) {
                        console.warn(`[ENGINE-METRIC] ${id} failed after ${loadDuration}ms:`, errorMsg);
                    }
                    if (window.VNOCR_TELEMETRY && typeof window.VNOCR_TELEMETRY === 'function') {
                        window.VNOCR_TELEMETRY({ type: 'engine_error', engineId: id, duration: loadDuration, error: errorMsg });
                    }
                    meta._lastError = null; // Clean up
                }
            }
        })();

        // ATOMIC FIX: Assign immediately so concurrent callers see it
        meta.loadPromise = loadPromise;

        return loadPromise;
    }

    /**
     * Main thread loading fallback for heavy engines when worker fails.
     */
    async function loadEngineMainThread(id, isSilent = false) {
        let meta = engineMetadata.get(id);
        if (!meta) {
            meta = { instance: null, state: 'not_loaded', loadPromise: null };
            engineMetadata.set(id, meta);
        }

        meta.state = 'loading';

        try {
            const registryEntry = engines[id];
            if (!registryEntry) throw new Error(`Unknown engine: ${id}`);

            const reporter = (state, text, progress) => {
                if (state === STATUS.READY) meta.state = 'ready';
                if (!isSilent || id === currentEngineId || state === STATUS.ERROR || window.VNOCR_DEBUG) {
                    notifyStatus(state, text, progress, id);
                }
            };

            const instance = registryEntry.factory({ reportStatus: reporter });

            if (instance && typeof instance.load === 'function') {
                await instance.load();
            }

            await _warmUpEngine(instance, id);

            meta.instance = instance;
            meta.state = 'ready';

            return instance;
        } catch (err) {
            meta.state = 'error';
            throw err;
        }
    }

    async function _warmUpEngine(engine, id) {
        if (engine._warmedUp) return;
        try {
            if (engine && typeof engine.warmUp === 'function') {
                if (window.VNOCR_DEBUG) console.debug(`[ENGINE] Warming up ${id.toUpperCase()}...`);
                await engine.warmUp();
            }
            engine._warmedUp = true;
        } catch (err) {
            console.warn(`[ENGINE] Warm-up failed for ${id}:`, err);
        }
    }

    /**
     * High-level switch with persistence and locking.
     * Atomic update: only sets currentEngineId after successful load.
     */
    async function switchEngine(registryEntry) {
        const id = registryEntry.id;

        if (switchingLock) {
            if (window.VNOCR_DEBUG) console.warn("[TRACE] Ignored overlapping engine switch");
            return;
        }
        switchingLock = true;

        const previousEngineId = currentEngineId;

        try {
            // Advance currentEngineId BEFORE the load begins.
            // The isSilent reporter guard in getOrLoadEngine() checks (id === currentEngineId).
            // If we set this only after the await, every download progress tick is silently
            // dropped because the engine appears to be a background preload. Setting it here
            // makes all progress (0% → 100%) flow through to the status pill in real time.
            currentEngineId = id;

            const meta = engineMetadata.get(id);
            if (!meta || meta.state !== 'ready') {
                notifyStatus('loading', 'Loading…', 0, id);
            }

            const instance = await getOrLoadEngine(id);

            // Load succeeded — finalize engine state
            currentEngine = instance;

            // Update Metadata for Pipeline compatibility
            currentCapabilities = {
                supportsModes: registryEntry.supportsModes || false,
                supportsMultiPass: registryEntry.supportsMultiPass || false,
                isMultiLine: registryEntry.isMultiLine || false
            };
            currentInfo = { id, capabilities: currentCapabilities };

            isReady = true;
            notifyStatus('ready', 'Ready', null, id);
            return currentEngine;
        } catch (err) {
            // Roll back to previous engine on failure so the UI doesn't get stuck
            // pointing at an engine that never loaded.
            currentEngineId = previousEngineId;
            isReady = false;
            const errorMsg = err?.message || 'Unknown error';
            notifyStatus(STATUS.ERROR, `🔴 Load Failed: ${errorMsg}`, null, id);
            throw err;
        } finally {
            switchingLock = false;
        }
    }

    /**
     * Load engine in Web Worker.
     * Spawns worker, listens for postMessage, resolves with payload.
     */
    async function loadEngineInWorker(id) {
        const workerPath = id === 'paddle'
            ? '/js/paddle/paddle_preload_worker.js?v=3.8.4'
            : '/js/manga/manga_preload_worker.js?v=3.8.4';

        return new Promise((resolve, reject) => {
            const worker = new Worker(workerPath, { type: 'module' });

            worker.onmessage = (e) => {
                const { type, payload, error } = e.data;
                if (type === 'ready') {
                    worker.terminate();
                    resolve(payload);
                } else if (type === 'error') {
                    worker.terminate();
                    reject(new Error(error));
                }
            };

            worker.onerror = (err) => {
                worker.terminate();
                reject(err);
            };

            worker.postMessage({ command: 'load', id });
        });
    }

    /**
     * Rehydrate engine from worker payload.
     * Constructs instance, applies payload, returns ready instance.
     */
    async function rehydrateEngine(id, payload) {
        const registryEntry = engines[id];
        if (!registryEntry) throw new Error(`Unknown engine: ${id}`);

        const reporter = (state, text, progress) => {
            notifyStatus(state, text, progress, id);
        };

        const instance = registryEntry.factory({ reportStatus: reporter });

        if (instance.rehydrate && typeof instance.rehydrate === 'function') {
            await instance.rehydrate(payload);
        } else {
            if (typeof instance.load === 'function') await instance.load();
            if (typeof instance.warmUp === 'function') await instance.warmUp();
        }

        return instance;
    }

    /**
     * Silent background pre-warming of the Paddle engine.
     *
     * Strategy:
     *   - Spawns the existing paddle_preload_worker to fetch model files and create
     *     ONNX sessions entirely inside a Worker context (off the main thread).
     *   - Main thread is never blocked — no ONNX session creation, no UI freezes.
     *   - The worker warms the browser and Service Worker cache so that when the
     *     user later switches to Paddle, only ONNX session creation remains
     *     (network fetch is a cache hit ≈ instant).
     *   - Worker result is intentionally discarded: ONNX sessions are not transferable
     *     across threads. The cache-warmth is the only goal.
     *
     * Exclusions:
     *   - Paddle is the saved/active engine → handled by globalInitialize via
     *     switchEngineModular (non-silent, locks capture button).
     *   - MangaOCR is never silently preloaded — only loaded if explicitly selected
     *     (cost: ~450 MB + 1.2 GB VRAM; user must opt-in).
     *   - Tesseract is already loaded synchronously at startup (no-op here).
     */
    async function preloadCoreEngines() {
        if (window.VNOCR_DEBUG) console.debug('[ENGINE] Starting Paddle cache-warm via worker...');

        try {
            // Fire-and-forget: we do not call rehydrateEngine() — we only want
            // the worker to populate the browser/SW cache, not to store a transferable
            // engine instance (ONNX sessions are NOT transferable across threads).
            await loadEngineInWorker('paddle');
            if (window.VNOCR_DEBUG) console.debug('[ENGINE] Paddle cache-warm complete (worker).');
        } catch (err) {
            // Non-critical: first user-initiated Paddle switch will just be a cache-cold load.
            if (window.VNOCR_DEBUG) console.warn('[ENGINE] Paddle worker cache-warm failed:', err.message);
        }
    }

    /**
     * Disposes a single engine by ID, releasing its ONNX sessions and resetting
     * its metadata state. Safe to call even if the engine is not loaded.
     * @param {string} id - Engine ID: 'paddle', 'manga', or 'tesseract'
     */
    async function disposeEngine(id) {
        const meta = engineMetadata.get(id);
        if (!meta) return;

        const engine = meta.instance;
        if (engine && typeof engine.dispose === 'function') {
            try {
                await engine.dispose();
                if (window.VNOCR_DEBUG) console.debug(`[ENGINE] Disposed: ${id}`);
            } catch (err) {
                console.error(`[ENGINE] dispose failed for ${id}:`, err);
            }
        }

        engineMetadata.set(id, { instance: null, state: 'not_loaded', loadPromise: null });

        // If we disposed the currently active engine, clear the active state.
        if (currentEngineId === id) {
            currentEngine = null;
            currentEngineId = null;
            isReady = false;
            notifyStatus('idle', 'Engine unloaded');
        }
    }

    async function disposeAllEngines() {
        if (window.VNOCR_DEBUG) console.debug("[ENGINE] Purging engine cache...");
        await Promise.allSettled(
            Array.from(engineMetadata.entries()).map(async ([id, meta]) => {
                const engine = meta?.instance;
                if (engine && typeof engine.dispose === 'function') {
                    try {
                        await engine.dispose();
                        if (window.VNOCR_DEBUG) console.debug(`[TRACE] Engine Disposed: ${id}`);
                    } catch (err) {
                        console.error(`Engine dispose error (${id}):`, err);
                    }
                }
                engineMetadata.set(id, { instance: null, state: 'not_loaded', loadPromise: null });
            })
        );
        currentEngine = null;
        currentEngineId = null;
        currentInfo = { id: null, capabilities: {} };
        isReady = false;
        notifyStatus('idle', 'All engines cleared');
    }

    // Unified OCR entry point
    async function runOCR(canvas, options = {}) {
        // Gold v3.8: Support instance pinning for multi-slice stability
        let engine = currentEngine;
        let engineId = currentEngineId || 'tesseract';
        
        // If options contains engineInstance (internal pin), use it directly
        if (options && options.engineInstance) {
            engine = options.engineInstance;
        }
        
        // If options contains explicit engineId, use that for loading
        if (options && typeof options.engineId === 'string') {
            engineId = options.engineId;
        }

        // Auto-recovery: if no engine loaded, try to load the target engine
        if (!engine || typeof engine.recognize !== 'function') {
            if (window.VNOCR_DEBUG) console.debug(`[ENGINE] runOCR: Engine not ready, attempting auto-load for ${engineId}`);
            try {
                // Check if switching is in progress to avoid race conditions
                if (switchingLock) {
                    throw new Error('Engine switch in progress - please retry');
                }
                engine = await getOrLoadEngine(engineId);
                // Update current engine if we're loading the current one
                if (engineId === currentEngineId) {
                    currentEngine = engine;
                }
            } catch (loadErr) {
                console.error(`[ENGINE] Auto-load failed for ${engineId}:`, loadErr);
                notifyStatus(STATUS.ERROR, `Load failed: ${loadErr.message}`, null, engineId);
                throw new Error(`Engine load failed: ${loadErr.message}`);
            }
        }

        if (!engine || typeof engine.recognize !== 'function') {
            notifyStatus(STATUS.ERROR, 'No engine available', null, engineId);
            throw new Error('No engine available');
        }

        try {
            notifyStatus(STATUS.PROCESSING, '🟡 Processing...', null, engineId);
            const result = await engine.recognize(canvas, (typeof options === 'object' ? options : {}));
            return result;
        } catch (err) {
            notifyStatus(STATUS.ERROR, 'OCR failed', null, engineId);
            throw err;
        }
    }



    // Unified preprocessing entry point
    async function preprocess(canvas, mode, lineCount) {
        const id = currentEngineId;
        const entry = engines[id];
        if (entry && typeof entry.preprocess === 'function') {
            return await entry.preprocess(canvas, mode, lineCount);
        }
        return [canvas];
    }

    // Unified post-processing entry point
    function postprocess(results) {
        const id = currentEngineId;
        const entry = engines[id];
        if (entry && typeof entry.postprocess === 'function') {
            return entry.postprocess(results);
        }
        return results.join(' ').trim();
    }

    function getReadyStatus() {
        const id = currentEngineId || 'tesseract';
        const entry = engines[id];
        return entry?.readyStatus || '🟢 OCR Ready';
    }

    function handleError(error) {
        const id = currentEngineId;
        const entry = engines[id];
        if (entry && typeof entry.handleError === 'function') {
            return entry.handleError(error);
        }
        console.error("Unhandleable error:", error);
        return "[OCR Error]";
    }

    // Initialize Defaults
    engineMetadata.set('tesseract', { instance: null, state: 'idle', loadPromise: null });

    return {
        onReady, onLoading, onError, onStatusChange,
        switchEngine, preloadCoreEngines, disposeAllEngines, disposeEngine,
        getOrLoadEngine, evictOtherEngines, loadEngineInWorker, rehydrateEngine, loadEngineMainThread,
        runOCR, preprocess, postprocess, notifyStatus, _notifyStatus: notifyStatus,
        isReady: () => isReady,
        getEngineMetadata: (id) => engineMetadata.get(id), // New state inspection
        getInfo: () => currentInfo || { id: null, capabilities: {} },
        getEngineInstance: () => currentEngine,
        getReadyStatus,
        emitError: (err) => emit('error', err),
        handleError: (err) => {
            console.error("[ENGINE-ERROR]", err);
            return "🔴 OCR ERROR";
        }
    };

})(window.VNOCR_ENGINES);

export { EngineManager };
