import cv2
import numpy as np
import sys

# Preprocessing module-level constants matching instructions.md
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_SIZE = (8, 8)
BILATERAL_D = 9
BILATERAL_SIGMA_COLOR = 75
BILATERAL_SIGMA_SPACE = 75
ADAPTIVE_BLOCK_SIZE = 31
ADAPTIVE_C = 10

def preprocess_for_ocr(image: np.ndarray, debug: bool = False) -> np.ndarray:
    """
    Apply OpenCV preprocessing pipeline for mobile model fallback pass.
    Note: debug mode is for parameter tuning only. It will pause execution using cv2.waitKey(0) at each stage.
    """
    # a. Grayscale conversion
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if debug:
        cv2.imshow("Stage 1: Grayscale", gray)
        cv2.waitKey(0)

    # b. CLAHE — handles gradients better than global histogram eq
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_SIZE)
    gray = clahe.apply(gray)
    if debug:
        cv2.imshow("Stage 2: CLAHE", gray)
        cv2.waitKey(0)

    # c. Bilateral filter — removes background noise, preserves text edges
    gray = cv2.bilateralFilter(gray, d=BILATERAL_D, sigmaColor=BILATERAL_SIGMA_COLOR, sigmaSpace=BILATERAL_SIGMA_SPACE)
    if debug:
        cv2.imshow("Stage 3: Bilateral filter", gray)
        cv2.waitKey(0)

    # d. Adaptive threshold — handles semi-transparent textboxes
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=ADAPTIVE_BLOCK_SIZE, C=ADAPTIVE_C
    )
    if debug:
        cv2.imshow("Stage 4: Adaptive threshold", binary)
        cv2.waitKey(0)

    # e. Invert if predominantly white (want dark text on white)
    if np.mean(binary) > 127:
        binary = cv2.bitwise_not(binary)
        if debug:
            cv2.imshow("Stage 5: Inverted", binary)
            cv2.waitKey(0)
    elif debug:
        cv2.imshow("Stage 5: Not Inverted", binary)
        cv2.waitKey(0)

    # f. Morphological opening — clean up outline/shadow artifacts
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    if debug:
        cv2.imshow("Stage 6: Morphological opening", binary)
        cv2.waitKey(0)

    # g. Convert back to BGR
    result = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    if debug:
        cv2.imshow("Stage 7: Final BGR", result)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m core.vision <path_to_image>")
        sys.exit(1)

    img_path = sys.argv[1]
    img = cv2.imread(img_path)
    if img is None:
        print(f"Error: Could not load image from '{img_path}'.")
        sys.exit(1)

    print("Running preprocessing... (Close windows to proceed)")
    
    # Run in debug mode if "--debug" is passed as second argument
    do_debug = len(sys.argv) > 2 and sys.argv[2] == "--debug"
    
    processed = preprocess_for_ocr(img, debug=do_debug)
    
    if not do_debug:
        cv2.imshow("Before OCR Preprocessing", img)
        cv2.imshow("After OCR Preprocessing", processed)
        print("Press any key to exit.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
