# models/paddle — Manual Model Placement Required

The ONNX model files and character dictionary **cannot be bundled in this repository** due to their size. They must be downloaded and placed here manually before running desktopOCR.

## Required Files

Place the following 3 files inside `models/paddle/`:

| File | Description | Size |
|---|---|---|
| `PP-OCRv5_server_det_infer.onnx` | PP-OCRv5 server detection model | ~86 MB |
| `PP-OCRv5_server_rec_infer.onnx` | PP-OCRv5 server recognition model | ~82 MB |
| `japan_dict.txt` | PP-OCRv5 character dictionary | ~73 KB |

## Source

All three files are available from:

**<https://huggingface.co/marsena/paddleocr-onnx-models>**

Download the files from that repository and place them directly into `models/paddle/` with the exact filenames listed above. The application will not start if any of these files are missing.
