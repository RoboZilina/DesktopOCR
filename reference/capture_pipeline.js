/**
 * js/core/capture_pipeline.js
 * Capture Pipeline - OCR frame capture and processing functions.
 * Gold v3.8 Compliance
 */

/**
 * Main capture frame processing function.
 * Captures a frame from the video stream and processes it through the OCR pipeline.
 * @param {Object} rect - Optional selection rectangle, defaults to window.selectionRect
 */
async function captureFrame(rect = null) {
    // Hardening v3.4: Null-selection guard (Fixes denormalizeSelection TypeError)
    if (!rect && !window.selectionRect) return;

    // Hardening v3.8: Combined readiness and processing lock
    if (window.isProcessing || !window.EngineManager.isReady()) return;
    
    const myGen = ++window.captureGeneration;
    let lockReleased = false;
    
    // Helper to release lock safely
    const releaseLock = () => {
        if (!lockReleased) {
            window.isProcessing = false;
            lockReleased = true;
        }
    };
    
    window.isProcessing = true;
    
    // Engine Pinning: Lock current instance and ID to ensure consistency throughout the slice cycle
    const pinnedEngine = window.EngineManager.getEngineInstance();
    const pinnedInfo = window.EngineManager.getInfo() || { id: null, capabilities: {} };
    const pinnedCaps = pinnedInfo.capabilities || {};
    const pinnedId = pinnedInfo.id || null;
    
    window.logTrace(`Capture started. Gen: ${myGen} | Engine: ${pinnedId}`);

    const vWidth = window.vnVideo.videoWidth, vHeight = window.vnVideo.videoHeight;
    const sel = window.denormalizeSelection(rect, window.vnVideo, window.selectionOverlay);
    const cx_ = Math.max(0, Math.floor(sel.x)), cy_ = Math.max(0, Math.floor(sel.y));
    const cw_ = Math.max(1, Math.min(vWidth - cx_, Math.floor(sel.w))), ch_ = Math.max(1, Math.min(vHeight - cy_, Math.floor(sel.h)));

    const rawCropCanvas = document.createElement('canvas');
    rawCropCanvas.width = cw_; rawCropCanvas.height = ch_;
    rawCropCanvas.getContext('2d').drawImage(window.vnVideo, cx_, cy_, cw_, ch_, 0, 0, cw_, ch_);

    window.EngineManager._notifyStatus(window.STATUS.PROCESSING, '🟡 Processing...', null, pinnedId);
    await new Promise(r => setTimeout(r, 0)); // yield to browser for repaint
    
    const mode = window.modeSelector.value;
    
    try {
        // Tesseract Multi-Pass Branch
        if (pinnedId === 'tesseract' && mode === 'multi') {
            const preStart = performance.now();
            const canvases = window.applyTesseractPreprocessing(rawCropCanvas, mode);
            window.perfStats.preprocess = performance.now() - preStart;
            const results = [];

            // 1. First Pass: Early exit if result is highly confident and clean
            const infStart = performance.now();
            const first = await window.EngineManager.runOCR(canvases[0], { engineInstance: pinnedEngine });
            
            // Generation Check (Critical for preventing UI ghosting)
            if (window.captureGeneration !== myGen) {
                canvases.forEach(c => { c.width = 0; c.height = 0; });
                releaseLock();
                return;
            }

            const firstDensity = window.scoreJapaneseDensity(first.text);
            if (first.confidence > 85 && firstDensity > 5) {
                window.addOCRResultToUI(first.text);
                window.updateDebugThumb(canvases[0]);
                window.perfStats.inference = performance.now() - infStart;
                canvases.forEach(c => { c.width = 0; c.height = 0; });
                if (window.updatePerformanceStatus) window.updatePerformanceStatus();
                releaseLock();
                return;
            }

            // 2. Otherwise: Continue with the remaining 4 passes for Analyst voting
            results.push({ text: first.text, confidence: first.confidence });
            for (let i = 1; i < canvases.length; i++) {
                window.setOCRStatus('processing', `Analyst: Pass ${i + 1}/5...`);
                // Pinning: Pass pinnedEngine to runOCR
                const r = await window.EngineManager.runOCR(canvases[i], { engineInstance: pinnedEngine });
                if (window.captureGeneration !== myGen) {
                    canvases.forEach(c => { c.width = 0; c.height = 0; });
                    releaseLock();
                    return;
                }
                results.push({ text: r.text, confidence: r.confidence });
            }

            const finalText = pickBestMultiPassResult(results);
            window.addOCRResultToUI(finalText);
            const bestIndex = findBestMultiPassIndex(results);
            window.updateDebugThumb(canvases[bestIndex]);
            window.showMultiPassOverlay(results, finalText);
            window.perfStats.inference = performance.now() - infStart;
            window.setOCRStatus('ready', '🟢 Analyst Complete');
            canvases.forEach(c => { c.width = 0; c.height = 0; });
            if (window.updatePerformanceStatus) window.updatePerformanceStatus();
            return;
        }

        // Generic Pipeline Branch (Paddle / Manga / Tesseract Single)
        const lineCount = window.getSetting('paddleLineCount') || 1;
        const preStart = performance.now();
        const canvases = await preprocessForEngine(pinnedId, rawCropCanvas, mode, lineCount);
        window.perfStats.preprocess = performance.now() - preStart;
        
        if (window.captureGeneration !== myGen) {
            canvases.forEach(c => { c.width = 0; c.height = 0; });
            releaseLock();
            return;
        }

        const ocrLines = [];
        let totalConfidence = 0;
        let confidenceCount = 0;
        const inferenceResults = [];
        const infStart = performance.now();

        for (let i = 0; i < canvases.length; i++) {
            const clean = canvases[i];
            if (!clean.width || !clean.height) {
                inferenceResults.push(null);
                continue;
            }

            // Debug Thumbnail
            if (i === 0) {
                if (pinnedCaps.isMultiLine) window.updateDebugThumb(rawCropCanvas);
                else window.updateDebugThumb(canvases[0]);
            }

            try {
                window.setOCRStatus(window.STATUS.PROCESSING, `Processing (${i + 1}/${canvases.length})`, (i + 1) / canvases.length);
                // Pinning: Pass pinnedEngine instance to runOCR
                const result = await window.EngineManager.runOCR(clean, { engineInstance: pinnedEngine });
                if (window.captureGeneration !== myGen) {
                    releaseLock();
                    canvases.forEach(c => { c.width = 0; c.height = 0; });
                    return;
                }
                inferenceResults.push(result);
            } catch (error) {
                console.error(`[GEN ${myGen}] [INFERENCE-ERROR] Execution failed for slice:`, i, error);
                window.EngineManager.emitError(error);
                inferenceResults.push({ text: window.EngineManager.handleError(error), confidence: null });
            }
        }
        window.perfStats.inference = performance.now() - infStart;

        if (window.captureGeneration !== myGen) {
            releaseLock();
            canvases.forEach(c => { c.width = 0; c.height = 0; });
            return;
        }

        inferenceResults.forEach(result => {
            if (!result) return;
            const { text, confidence } = result;
            if (confidence !== null) {
                totalConfidence += confidence;
                confidenceCount++;
            }
            const cleanText = window.normalizePaddleText(text);
            if (cleanText) ocrLines.push(cleanText);
        });

        if (window.captureGeneration !== myGen) {
            releaseLock();
            canvases.forEach(c => { c.width = 0; c.height = 0; });
            return;
        }

        // Post-processing
        const finalText = window.EngineManager.postprocess(ocrLines);
        const avgConfidence = confidenceCount > 0 ? (totalConfidence / confidenceCount) : null;

        if (finalText) {
            window.addOCRResultToUI(finalText, avgConfidence);
            window.setOCRStatus('ready', '🟢 OCR Complete');
        } else {
            window.setOCRStatus('ready', '⚪ No text detected');
        }
        window.logTrace(`Capture Cycle Complete. Gen: ${myGen}`);

        canvases.forEach(c => {
            if (c && c !== rawCropCanvas) {
                c.width = 0; c.height = 0;
            }
        });
    } catch (err) {
        console.error("Frame-level OCR Error:", err);
        window.EngineManager.emitError(err);
    }
    finally {
        if (rawCropCanvas) {
            rawCropCanvas.width = 0; rawCropCanvas.height = 0;
        }

        // Always release the lock synchronously to prevent race conditions
        releaseLock();

        // Small cooldown to prevent rapid-fire re-triggering - UI updates only
        setTimeout(() => {
            // Always refresh UI heartbeat after a capture attempt to avoid leaving stale "processing" state.
            try {
                if (window.EngineManager.isReady()) {
                    const statusText = (window.captureGeneration === myGen) ? window.EngineManager.getReadyStatus() : 'Ready';
                    window.setOCRStatus(window.STATUS.READY, statusText);
                } else {
                    window.setOCRStatus(window.STATUS.IDLE, 'idle');
                }
            } catch (e) {
                console.warn("[CAPTURE] UI update failed:", e);
            }
            window.updateCaptureButtonState();
        }, 100);
    }
}

/**
 * Unified preprocessing entry point. Delegates to the active engine's preprocess function.
 * @param {string} engineId - Active engine ID (used for trace logging only)
 * @param {HTMLCanvasElement} rawCanvas - The original crop
 * @param {string} mode - Preprocessing mode (adaptive, multi, etc.)
 * @param {number} lineCount - Number of lines (for Paddle)
 * @returns {HTMLCanvasElement[]} Array of one or more preprocessed canvases.
 */
async function preprocessForEngine(engineId, rawCanvas, mode, lineCount) {
    window.logTrace('preprocessForEngine called with engineId = ' + engineId);
    
    // Look up explicit engine instance by ID if available
    let engineToUse = window.EngineManager.getEngineInstance();
    if (engineId && typeof window.EngineManager.getEngineMetadata === 'function') {
        const meta = window.EngineManager.getEngineMetadata(engineId);
        if (meta && meta.instance) engineToUse = meta.instance;
    }
    
    if (engineToUse && typeof engineToUse.preprocess === 'function') {
        try {
            return await engineToUse.preprocess(rawCanvas, mode, lineCount);
        } catch (err) {
            if (window.VNOCR_DEBUG) console.warn("[ENGINE] Instance preprocess failed, trying registry fallback:", err);
        }
    }
    
    // Fallback 1: Try registry entry preprocess
    const entry = window.VNOCR_ENGINES[engineId];
    if (entry && typeof entry.preprocess === 'function') {
        try {
            return await entry.preprocess(rawCanvas, mode, lineCount);
        } catch (err) {
            if (window.VNOCR_DEBUG) console.warn("[ENGINE] Registry preprocess failed, using raw canvas fallback:", err);
        }
    }
    
    // Final Fallback: Clone raw canvas to prevent pipeline from destroying original
    if (window.VNOCR_DEBUG) console.debug("[ENGINE] No preprocess available, returning cloned canvas");
    const cloned = document.createElement('canvas');
    cloned.width = rawCanvas.width;
    cloned.height = rawCanvas.height;
    cloned.getContext('2d').drawImage(rawCanvas, 0, 0);
    return [cloned];
}

/**
 * Pick the best result from multiple OCR passes using majority vote and confidence scoring.
 * @param {Array} results - Array of {text, confidence} objects
 * @returns {string} The best text result
 */
function pickBestMultiPassResult(results) {
    // 1. Majority vote
    const counts = {};
    for (const r of results) {
        counts[r.text] = (counts[r.text] || 0) + 1;
    }
    const majority = Object.entries(counts).find(([t, c]) => c >= 3);
    if (majority && majority[1] >= 3) return majority[0];

    // 2. Highest confidence
    const bestByConf = results.reduce((a, b) =>
        a.confidence > b.confidence ? a : b
    );

    // 3. Density fallback
    const bestByDensity = results.reduce((a, b) =>
        window.scoreJapaneseDensity(a.text) > window.scoreJapaneseDensity(b.text) ? a : b
    );

    // 4. Weighted score fallback
    let bestWeighted = results[0];
    for (const r of results) {
        if (weightedScore(r) > weightedScore(bestWeighted)) {
            bestWeighted = r;
        }
    }
    return bestWeighted.text;
}

/**
 * Calculate a weighted score for a result based on confidence and Japanese character density.
 * @param {Object} result - Object with text and confidence
 * @returns {number} Weighted score
 */
function weightedScore(result) {
    const density = Math.max(0, window.scoreJapaneseDensity(result.text));
    return result.confidence * 0.7 + density * 0.3;
}

/**
 * Find the index of the best result in a multi-pass result array.
 * @param {Array} results - Array of result objects
 * @returns {number} Index of the best result
 */
function findBestMultiPassIndex(results) {
    let best = 0;
    let bestScore = -Infinity;
    results.forEach((r, i) => {
        const score = weightedScore(r);
        if (score > bestScore) {
            bestScore = score;
            best = i;
        }
    });
    return best;
}

export { captureFrame, preprocessForEngine, pickBestMultiPassResult, weightedScore, findBestMultiPassIndex };
