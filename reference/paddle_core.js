export { fetchWithProgress } from '../utils/fetch_utils.js?v=3.8.4';

// Shared resources for zero-churn tensor conversion
let sharedCanvas = null;
let sharedCtx = null;
let detInputBuffer = null;
let recInputBuffer = null;

// canvas: HTMLCanvasElement, inputSize: [H, W], normalize: { mean: number[], std: number[] }, outBuffer: Float32Array (optional)
export function canvasToFloat32Tensor(canvas, inputSize, normalize, outBuffer) {
    if (!canvas || !inputSize || !normalize) return null;
    
    try {
        const [targetH, targetW] = inputSize;

        // Lazy initialization of shared canvas
        if (!sharedCanvas) {
            sharedCanvas = document.createElement('canvas');
            sharedCtx = sharedCanvas.getContext('2d', { willReadFrequently: true });
        }

        sharedCanvas.width = targetW;
        sharedCanvas.height = targetH;
        sharedCtx.fillStyle = '#000000';
        sharedCtx.fillRect(0, 0, targetW, targetH);

        if (targetH === 48) {
            const scale = targetH / canvas.height;
            const resW = Math.min(targetW, Math.round(canvas.width * scale));
            sharedCtx.drawImage(canvas, 0, 0, canvas.width, canvas.height, 0, 0, resW, targetH);
        } else {
            sharedCtx.drawImage(canvas, 0, 0, targetW, targetH);
        }

        const imageData = sharedCtx.getImageData(0, 0, targetW, targetH);
        const { data } = imageData;

        const mean = normalize.mean;
        const std = normalize.std;

        // Determine which buffer to use
        let chw;
        const size = 3 * targetH * targetW;
        
        if (outBuffer) {
            chw = outBuffer;
        } else if (targetH === 960 && targetW === 960) {
            if (!detInputBuffer) detInputBuffer = new Float32Array(size);
            chw = detInputBuffer;
        } else if (targetH === 48 && targetW === 320) {
            if (!recInputBuffer) recInputBuffer = new Float32Array(size);
            chw = recInputBuffer;
        } else {
            chw = new Float32Array(size);
        }

        let idx = 0;
        for (let y = 0; y < targetH; y++) {
            for (let x = 0; x < targetW; x++) {
                const i = (y * targetW + x) * 4;
                const r = data[i] / 255;
                const g = data[i + 1] / 255;
                const b = data[i + 2] / 255;

                chw[0 * targetH * targetW + idx] = (b - mean[2]) / std[2];
                chw[1 * targetH * targetW + idx] = (g - mean[1]) / std[1];
                chw[2 * targetH * targetW + idx] = (r - mean[0]) / std[0];
                idx++;
            }
        }

        // If outBuffer was injected, we return it as is (Zero-Copy)
        if (outBuffer) return chw;

        // Fallback for internal shared buffers (Legacy Copy logic)
        if (chw === detInputBuffer || chw === recInputBuffer) {
            return chw.slice();
        }
        return chw;
    } catch (err) {
        console.error("PaddleOCR: Tensor conversion error:", err);
        return null;
    }
}

// Preserve aspect ratio, max width/height
export function resizeCanvas(sourceCanvas, maxWidth, maxHeight) {
    if (!sourceCanvas) return null;

    const srcW = sourceCanvas.width;
    const srcH = sourceCanvas.height;
    if (srcW === 0 || srcH === 0) return null;

    const scale = Math.min(maxWidth / srcW, maxHeight / srcH, 1);
    const dstW = Math.round(srcW * scale);
    const dstH = Math.round(srcH * scale);

    const dst = document.createElement('canvas');
    dst.width = dstW;
    dst.height = dstH;
    const ctx = dst.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(sourceCanvas, 0, 0, dstW, dstH);

    return { canvas: dst, scaleX: dstW / srcW, scaleY: dstH / srcH };
}

// Crop a box from the original canvas
// box: [x1, y1, x2, y2] in original coordinates
export function cropBoxFromCanvas(canvas, box) {
    if (!canvas || !box) return null;

    const [x1, y1, x2, y2] = box;

    let w = Math.round(x2 - x1);
    let h = Math.round(y2 - y1);

    // Hard guards for crop sizes
    if (isNaN(w) || isNaN(h) || w <= 0 || h <= 0) return null;

    if (w < 4) w = 4;
    if (h < 4) h = 4;

    const dst = document.createElement('canvas');
    dst.width = w;
    dst.height = h;

    const ctx = dst.getContext('2d');

    try {
        ctx.drawImage(
            canvas,
            x1, y1, Math.max(1, Math.round(x2-x1)), Math.max(1, Math.round(y2-y1)),
            0, 0, w, h
        );
    } catch (e) {
        console.error("PaddleOCR: Crop draw error:", e);
        return null;
    }

    return dst;
}

// Orchestrate detection + recognition
export async function runPaddleOCR(paddle, canvas, updateStatus) {
    if (!paddle || !canvas) return [];

    try {
        updateStatus('PaddleOCR: detecting text…');
        // Yield for UI paint
        await new Promise(r => setTimeout(r, 0));
        const { boxes } = await paddle.detect(canvas);

        if (!boxes || boxes.length === 0) {
            return [];
        }

        updateStatus(`PaddleOCR: recognizing ${boxes.length} line(s)…`);
        // Yield for UI paint
        await new Promise(r => setTimeout(r, 0));

        const results = [];
        for (const box of boxes) {
            const crop = cropBoxFromCanvas(canvas, box);
            if (!crop) continue;

            const result = await paddle.recognize(crop);
            if (result && result.text && result.text.trim()) {
                results.push({ box, text: result.text.trim() });
            }
            // Explicitly Clear Crop Canvas
            crop.width = 0; crop.height = 0;
        }

        updateStatus('PaddleOCR: done.');
        return results;
    } catch (err) {
        console.error("PaddleOCR: Pipeline error:", err);
        updateStatus('PaddleOCR: Error.');
        return [];
    }
}
