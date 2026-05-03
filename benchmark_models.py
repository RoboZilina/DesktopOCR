import time
import onnxruntime as ort
import numpy as np

MODELS = [
    ("det", "models/paddle/det.onnx", "models_optimized/det_opt.onnx", (1, 3, 960, 960)),
    ("rec", "models/paddle/rec.onnx", "models_optimized/rec_opt.onnx", (1, 3, 48, 320)),
]

def benchmark(model_path, input_shape):
    print(f"\nBenchmarking: {model_path}")

    t0 = time.time()
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    load_time = (time.time() - t0) * 1000

    dummy = np.random.rand(*input_shape).astype(np.float32)

    for _ in range(3):
        session.run(None, {session.get_inputs()[0].name: dummy})

    runs = 20
    t_start = time.time()
    for _ in range(runs):
        session.run(None, {session.get_inputs()[0].name: dummy})
    t_end = time.time()

    avg_ms = (t_end - t_start) * 1000 / runs

    print(f"Load time: {load_time:.2f} ms")
    print(f"Avg inference: {avg_ms:.2f} ms")

if __name__ == "__main__":
    for name, orig, opt, shape in MODELS:
        print("\n==============================")
        print(f"MODEL: {name}")
        print("==============================")

        print("\n--- Original FP32 ---")
        benchmark(orig, shape)

        print("\n--- Optimized ---")
        benchmark(opt, shape)
