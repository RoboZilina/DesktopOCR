import onnxruntime as ort
import numpy as np

MODELS = [
    ("det", "models/paddle/det.onnx", "models_optimized/det_opt.onnx", (1, 3, 960, 960)),
    ("rec", "models/paddle/rec.onnx", "models_optimized/rec_opt.onnx", (1, 3, 48, 320)),
]

def validate(orig_path, opt_path, input_shape):
    print(f"\nValidating: {orig_path} vs {opt_path}")

    sess_orig = ort.InferenceSession(orig_path, providers=["CPUExecutionProvider"])
    sess_opt = ort.InferenceSession(opt_path, providers=["CPUExecutionProvider"])

    dummy = np.random.rand(*input_shape).astype(np.float32)
    input_name = sess_orig.get_inputs()[0].name

    out_orig = sess_orig.run(None, {input_name: dummy})
    out_opt = sess_opt.run(None, {input_name: dummy})

    for i, (a, b) in enumerate(zip(out_orig, out_opt)):
        diff = np.abs(a - b).max()
        print(f"Output {i}: max abs diff = {diff}")

    print("Match:", all(np.allclose(a, b, atol=1e-5) for a, b in zip(out_orig, out_opt)))

if __name__ == "__main__":
    for name, orig, opt, shape in MODELS:
        print("\n==============================")
        print(f"MODEL: {name}")
        print("==============================")
        validate(orig, opt, shape)
