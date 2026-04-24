"""WinRT screen capture via Windows.Graphics.Capture — returns numpy BGR frames."""

# Windows only. No cross-platform shims. Period.
# Requires winsdk==0.10.0 — pin this version; later versions changed the API surface.

from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import hashlib
import logging
from typing import Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# D3D11 / WinRT bootstrap helpers
# ---------------------------------------------------------------------------
# These constants and structures are needed to create an IDirect3DDevice that
# the GraphicsCapture API requires.  They replicate the minimal Win32 surface
# exposed by d3d11.dll without pulling in a third-party wrapper.

D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_SDK_VERSION = 7
DXGI_FORMAT_B8G8R8A8_UNORM = 87          # matches DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED

# IID for IDXGIDevice (used to bridge D3D11 → IDirect3DDevice via WinRT interop)
IID_IDXGIDevice = "{54ec77fa-1377-44e6-8c32-88fd5f44c84c}"

# IID for IDirect3DDevice (Windows.Graphics.DirectX.Direct3D11)
IID_IInspectable = "{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}"


def _create_d3d11_device() -> object:
    """
    Create a hardware-accelerated D3D11 device and wrap it as an IDirect3DDevice
    via the CreateDirect3D11DeviceFromDXGIDevice WinRT interop helper.

    Returns the IDirect3DDevice COM object understood by GraphicsCapture APIs,
    or raises RuntimeError if the GPU is unavailable.

    Version note (winsdk 0.10.0): The interop helper lives in
    winsdk.windows.graphics.directx.direct3d11.interop, spelled exactly:
        create_direct3d11_device_from_dxgi_device(dxgi_device)
    Later winrt package revisions renamed / moved this symbol.
    """
    d3d11 = ctypes.windll.d3d11

    # winsdk 0.10.0 — IDirect3DDevice is a Windows.Graphics.DirectX.Direct3D11 type.
    # We need a raw IUnknown wrapping the DXGI device from D3D11CreateDevice.
    class _D3D_FEATURE_LEVEL(ctypes.c_uint):
        pass

    feature_levels = (_D3D_FEATURE_LEVEL * 1)(_D3D_FEATURE_LEVEL(0xB000))  # D3D_FEATURE_LEVEL_11_0
    p_device = ctypes.c_void_p()
    p_context = ctypes.c_void_p()
    actual_level = _D3D_FEATURE_LEVEL()

    # D3D11CreateDevice signature (from d3d11.dll)
    hr = d3d11.D3D11CreateDevice(
        None,                    # pAdapter  — NULL → default adapter
        D3D_DRIVER_TYPE_HARDWARE,
        None,                    # Software module — NULL for hardware
        ctypes.c_uint(0x20),     # D3D11_CREATE_DEVICE_BGRA_SUPPORT (required by DXGI capture)
        feature_levels,
        1,
        D3D11_SDK_VERSION,
        ctypes.byref(p_device),
        ctypes.byref(actual_level),
        ctypes.byref(p_context),
    )
    if hr != 0:
        raise RuntimeError(f"D3D11CreateDevice failed: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

    # winsdk 1.0.0b10 removed the python interop helper module
    # winsdk.windows.graphics.directx.direct3d11.interop.
    # Bridge manually via Win32 API and wrap with IDirect3DDevice._from.
    # This keeps compatibility with both the existing capture pipeline and
    # current installable winsdk builds.
    create_from_dxgi = d3d11.CreateDirect3D11DeviceFromDXGIDevice
    create_from_dxgi.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    create_from_dxgi.restype = ctypes.c_long

    inspectable = ctypes.c_void_p()
    hr = create_from_dxgi(p_device, ctypes.byref(inspectable))
    if hr != 0:
        raise RuntimeError(
            f"CreateDirect3D11DeviceFromDXGIDevice failed: HRESULT=0x{hr & 0xFFFFFFFF:08X}"
        )

    from winsdk.windows.graphics.directx.direct3d11 import (  # noqa: PLC0415
        IDirect3DDevice,
    )

    return IDirect3DDevice._from(inspectable.value)


def _iid_to_bytes(iid_str: str) -> list[int]:
    """Convert a Windows GUID string '{xxxxxxxx-xxxx-...}' to a 16-byte list."""
    clean = iid_str.strip("{}")
    parts = clean.split("-")
    # GUID byte layout: data1 (LE 4B), data2 (LE 2B), data3 (LE 2B), data4 (8B big-endian)
    p1 = int(parts[0], 16).to_bytes(4, "little")
    p2 = int(parts[1], 16).to_bytes(2, "little")
    p3 = int(parts[2], 16).to_bytes(2, "little")
    p4 = bytes.fromhex(parts[3] + parts[4])
    return list(p1 + p2 + p3 + p4)


# ---------------------------------------------------------------------------
# BitBlt fallback (older windowed GDI-mode VNs)
# ---------------------------------------------------------------------------

def _capture_bitblt(hwnd: int) -> Optional[np.ndarray]:
    """
    Fallback capture using GDI BitBlt for older VNs that run in windowed GDI
    mode and do not expose a capturable DXGI surface.

    Returns a numpy BGR array of the full client area, or None on failure.
    This is synchronous — call from a thread pool executor if needed.
    """
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # Get client rect (excludes window chrome)
        rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None

        # Device contexts
        hwnd_dc = user32.GetDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)

        # BITMAPINFOHEADER for 32-bit BGR (GDI always returns BGRA)
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize",          ctypes.c_ulong),
                ("biWidth",         ctypes.c_long),
                ("biHeight",        ctypes.c_long),
                ("biPlanes",        ctypes.c_ushort),
                ("biBitCount",      ctypes.c_ushort),
                ("biCompression",   ctypes.c_ulong),
                ("biSizeImage",     ctypes.c_ulong),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed",       ctypes.c_ulong),
                ("biClrImportant",  ctypes.c_ulong),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_ulong * 3)]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height   # negative → top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0   # BI_RGB

        # Allocate DIB section
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(hwnd_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(mem_dc, bitmap)

        # BitBlt from window DC into our DIB
        BI_SRCCOPY = 0x00CC0020
        gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, BI_SRCCOPY)

        # Copy pixels into numpy (BGRA → BGR)
        arr = np.frombuffer((ctypes.c_byte * (width * height * 4)).from_address(bits.value), dtype=np.uint8)
        arr = arr.reshape((height, width, 4))[:, :, :3].copy()  # drop alpha channel

        # Cleanup
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)

        return arr

    except Exception as exc:
        log.warning("BitBlt capture failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# ScreenCapture — main class
# ---------------------------------------------------------------------------

class ScreenCapture:
    """
    Async WinRT screen capture targeting a specific HWND.

    Usage:
        cap = ScreenCapture(hwnd)
        cap.set_region(x, y, w, h)
        frame = await cap.get_frame()   # numpy BGR or None
        cap.stop()

    Design notes:
    - Uses Windows.Graphics.Capture (GraphicsCaptureItem per HWND) with
      a single-slot Direct3D11CaptureFramePool in BGRA format.
    - Frame delivery is event-driven via frame_arrived callback that resolves
      a per-call asyncio.Future — no polling loop.
    - Frame diff (MD5) is checked BEFORE cropping to avoid tensor allocation
      on static scenes.
    - BitBlt fallback is attempted automatically if WinRT session start fails.
    - stop() is idempotent and safe to call multiple times.
    """

    def __init__(self, hwnd: int) -> None:
        self._hwnd: int = hwnd
        self._region: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
        self.last_frame_hash: Optional[str] = None

        # WinRT objects — initialised lazily in _ensure_session()
        self._d3d_device = None
        self._item = None
        self._frame_pool = None
        self._session = None

        # Token for frame_arrived event handler (needed for removal on stop)
        # winsdk 0.10.0 — add_frame_arrived returns an EventRegistrationToken (int)
        self._frame_arrived_token: Optional[int] = None

        self._stopped: bool = False
        self._session_ready: bool = False

        # Fallback flag — set True if WinRT init fails
        self._use_bitblt: bool = False

        log.debug("ScreenCapture created for HWND=0x%X", hwnd)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_region(self, x: int, y: int, width: int, height: int) -> None:
        """Define the sub-region (in window client coordinates) to crop from each frame."""
        self._region = (int(x), int(y), int(width), int(height))
        log.debug("Capture region set: x=%d y=%d w=%d h=%d", x, y, width, height)

    @property
    def region(self):
        """Read-only view of the current capture region (x, y, w, h) or None."""
        return self._region

    async def get_frame(self, full: bool = False) -> Optional[np.ndarray]:
        """
        Capture one frame, run frame-diff check, optionally crop to region, return BGR ndarray.

        Args:
            full: If True, return the entire window frame without region cropping.
                  Diff check still applies. OCR pipeline uses full=False (cropped).

        Returns None if:
          - The frame is identical to the last captured frame (MD5 match)
          - The capture hardware fails
          - stop() has already been called
        Never raises — all exceptions are caught and logged.
        """
        if self._stopped:
            return None

        try:
            if self._use_bitblt:
                return await self._get_frame_bitblt(full=full)
            return await self._get_frame_winrt(full=full)
        except Exception as exc:
            log.error("get_frame error: %s", exc, exc_info=True)
            return None

    def stop(self) -> None:
        """
        Release all WinRT and GDI resources.  Idempotent — safe to call multiple times.
        """
        if self._stopped:
            return
        self._stopped = True
        self._release_winrt()
        log.debug("ScreenCapture stopped for HWND=0x%X", self._hwnd)

    # ------------------------------------------------------------------
    # WinRT session management
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> bool:
        """
        Lazily initialise the WinRT capture session on the first call.
        Falls back to BitBlt if WinRT init fails.
        Returns True if the session is ready (WinRT or BitBlt).
        """
        if self._session_ready:
            return True
        if self._use_bitblt:
            return True

        try:
            await asyncio.get_running_loop().run_in_executor(None, self._init_winrt_sync)
            self._session_ready = True
            log.info("WinRT capture session started for HWND=0x%X", self._hwnd)
            return True
        except Exception as exc:
            log.warning(
                "WinRT capture init failed for HWND=0x%X (%s) — falling back to BitBlt",
                self._hwnd, exc,
            )
            self._use_bitblt = True
            return True

    def _init_winrt_sync(self) -> None:
        """
        Synchronous WinRT initialisation — run inside an executor thread so it
        does not block the asyncio event loop.

        All symbols below are verified against winsdk 0.10.0.
        Later winrt namespace packages reorganised these imports.
        """
        # winsdk 0.10.0 — import path for GraphicsCaptureItem factory
        from winsdk.windows.graphics.capture import (           # noqa: PLC0415
            Direct3D11CaptureFramePool,
        )
        # winsdk 0.10.0 — interop helper to create a GraphicsCaptureItem from HWND
        from winsdk.windows.graphics.capture.interop import (   # noqa: PLC0415
            create_for_window,
        )
        # winsdk 0.10.0 — pixel format enum (BGRA is the only format guaranteed on all GPUs)
        from winsdk.windows.graphics.directx import (           # noqa: PLC0415
            DirectXPixelFormat,
        )

        self._d3d_device = _create_d3d11_device()

        # winsdk 0.10.0 — create_for_window takes a plain Python int (HWND)
        self._item = create_for_window(self._hwnd)

        # winsdk 0.10.0 — Direct3D11CaptureFramePool.create_free_threaded(
        #     device: IDirect3DDevice,
        #     pixel_format: DirectXPixelFormat,
        #     number_of_buffers: int,
        #     size: SizeInt32,
        # )
        # create_free_threaded is preferred over create() for non-UI-thread usage.
        self._frame_pool = Direct3D11CaptureFramePool.create_free_threaded(
            self._d3d_device,
            DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,
            1,                   # single-slot pool — we always consume frames immediately
            self._item.size,
        )

        # winsdk 0.10.0 — create_capture_session returns a GraphicsCaptureSession
        self._session = self._frame_pool.create_capture_session(self._item)

        # Suppress the yellow capture border (requires Windows 11 — silently ignored on Win10)
        # winsdk 0.10.0 — is_border_required is a settable property on GraphicsCaptureSession
        try:
            self._session.is_border_required = False
        except AttributeError:
            pass  # Not available on all versions — non-fatal

        # winsdk 0.10.0 — start_capture() begins frame delivery
        self._session.start_capture()

    # ------------------------------------------------------------------
    # WinRT frame acquisition
    # ------------------------------------------------------------------

    async def _get_frame_winrt(self, full: bool = False) -> Optional[np.ndarray]:
        """Acquire one frame from the WinRT frame pool and return it as BGR ndarray."""
        if not await self._ensure_session():
            return None

        if self._use_bitblt:
            return await self._get_frame_bitblt(full=full)

        if self._frame_pool is None:
            log.warning(
                "WinRT frame pool not available for HWND=0x%X — switching to BitBlt fallback",
                self._hwnd,
            )
            self._use_bitblt = True
            return await self._get_frame_bitblt(full=full)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Optional[np.ndarray]] = loop.create_future()

        def _on_frame_arrived(sender, _args) -> None:
            """
            winsdk 0.10.0 — frame_arrived callback receives the FramePool as sender.
            Call try_get_next_frame() on sender (the pool), not on the session.
            """
            try:
                # winsdk 0.10.0 — try_get_next_frame() returns Direct3D11CaptureFrame or None
                frame = sender.try_get_next_frame()
                if frame is None:
                    if not future.done():
                        future.set_result(None)
                    return
                # Convert on the thread-pool thread so the event loop stays free
                arr = self._frame_to_numpy(frame)
                frame.close()   # winsdk 0.10.0 — Direct3D11CaptureFrame is IClosable
                if not future.done():
                    loop.call_soon_threadsafe(future.set_result, arr)
            except Exception as exc:
                if not future.done():
                    loop.call_soon_threadsafe(future.set_exception, exc)

        # winsdk 0.10.0 — add_frame_arrived returns an EventRegistrationToken (int)
        token = self._frame_pool.add_frame_arrived(_on_frame_arrived)

        try:
            # Give WinRT up to 2 s to deliver a frame before timing out
            raw_frame = await asyncio.wait_for(future, timeout=2.0)
        except asyncio.TimeoutError:
            log.warning("WinRT frame_arrived timed out for HWND=0x%X", self._hwnd)
            raw_frame = None
        finally:
            # winsdk 0.10.0 — remove_frame_arrived(token) deregisters the handler
            try:
                self._frame_pool.remove_frame_arrived(token)
            except Exception:
                pass

        if raw_frame is None:
            return None

        return self._apply_diff_and_crop(raw_frame, full=full)

    def _frame_to_numpy(self, frame) -> Optional[np.ndarray]:
        """
        Convert a Direct3D11CaptureFrame to a numpy array in BGR format.

        Conversion path:
            Direct3D11CaptureFrame.surface
                → SoftwareBitmap.create_copy_from_surface_async  (run synchronously via .get())
                → bitmap.lock_buffer(READ_WRITE)
                → IMemoryBufferReference
                → numpy uint8 BGRA
                → drop alpha → BGR

        winsdk 0.10.0 note: SoftwareBitmap.create_copy_from_surface_async is an
        IAsyncOperation[SoftwareBitmap].  Call .get() to block on the result inside
        this executor thread (we are already off the event loop thread).
        """
        try:
            from winsdk.windows.graphics.imaging import (       # noqa: PLC0415
                BitmapBufferAccessMode,
                SoftwareBitmap,
            )

            # winsdk 0.10.0 — frame.surface is an IDirect3DSurface
            # create_copy_from_surface_async is a static async factory on SoftwareBitmap
            bitmap = SoftwareBitmap.create_copy_from_surface_async(frame.surface).get()

            # winsdk 0.10.0 — lock_buffer returns a BitmapBuffer
            buf = bitmap.lock_buffer(BitmapBufferAccessMode.READ_WRITE)
            # winsdk 0.10.0 — create_reference() on BitmapBuffer returns IMemoryBufferReference
            ref = buf.create_reference()

            # Map IMemoryBufferReference to a numpy array.
            # winsdk 0.10.0 — primary path: np.array(ref) works when the WinRT object
            # exposes the buffer protocol directly (most common case).
            # Fallback: use ctypes address mapping via ref.capacity / ref.data for
            # runtimes where the buffer protocol is not bridged.
            try:
                arr = np.array(ref, dtype=np.uint8)
            except Exception:
                capacity = ref.capacity
                raw = (ctypes.c_byte * capacity).from_address(
                    ctypes.addressof(ctypes.cast(ref.data, ctypes.POINTER(ctypes.c_byte)).contents)
                )
                arr = np.frombuffer(raw, dtype=np.uint8)

            h = bitmap.pixel_height
            w = bitmap.pixel_width
            arr = arr.reshape((h, w, 4))[:, :, :3].copy()   # BGRA → BGR

            ref.close()
            buf.close()
            bitmap.close()

            return arr

        except Exception as exc:
            log.error("_frame_to_numpy failed: %s", exc, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # BitBlt fallback
    # ------------------------------------------------------------------

    async def _get_frame_bitblt(self, full: bool = False) -> Optional[np.ndarray]:
        """Run _capture_bitblt in a thread-pool executor (blocking GDI call)."""
        loop = asyncio.get_running_loop()
        raw_frame = await loop.run_in_executor(None, _capture_bitblt, self._hwnd)
        if raw_frame is None:
            return None
        return self._apply_diff_and_crop(raw_frame, full=full)

    # ------------------------------------------------------------------
    # Shared post-processing: diff check + region crop
    # ------------------------------------------------------------------

    def _apply_diff_and_crop(self, frame: np.ndarray, full: bool = False) -> Optional[np.ndarray]:
        """
        1. MD5 frame diff check — return None if frame is unchanged.
        2. Crop to self._region if set and full=False.
        3. Update self.last_frame_hash with the new hash.

        The hash is computed on the full (uncropped) frame to detect motion
        anywhere in the window, not just the selected region.
        """
        # Frame diff — mirrors the pattern from instructions.md / capture_pipeline.js
        new_hash = hashlib.md5(frame.tobytes()).hexdigest()
        if new_hash == self.last_frame_hash:
            return None   # identical frame — skip
        self.last_frame_hash = new_hash

        # Sub-region crop (skip when full=True for preview)
        if not full and self._region is not None:
            rx, ry, rw, rh = self._region
            h, w = frame.shape[:2]
            # Clamp to frame bounds
            rx = max(0, rx)
            ry = max(0, ry)
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            frame = frame[ry:ry + rh, rx:rx + rw]

        return frame

    # ------------------------------------------------------------------
    # Resource cleanup
    # ------------------------------------------------------------------

    def _release_winrt(self) -> None:
        """Close all WinRT COM objects in the correct order."""
        # winsdk 0.10.0 — close() on GraphicsCaptureSession stops frame delivery
        for attr in ("_session", "_frame_pool", "_item", "_d3d_device"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        self._session_ready = False
