"""OIDN 2.x C API, CPU device only; caller keeps HDR before tonemapping."""

import ctypes as C

import numpy as np

OIDN_DEVICE_TYPE_CPU = 1
OIDN_FORMAT_FLOAT3 = 3
BUFFER_NAMES = (("color", "HdrColor"), ("albedo", "Albedo"), ("normal", "Normal"))


def denoise(library, buffers, threads=4):
    lib = C.CDLL(library)
    ptr, integer, size, string = C.c_void_p, C.c_int, C.c_size_t, C.c_char_p

    def bind(name, args, result=None):
        f = getattr(lib, name)
        f.argtypes = args
        f.restype = result
        return f

    device = bind("oidnNewDevice", [integer], ptr)(OIDN_DEVICE_TYPE_CPU)
    if not device:
        raise RuntimeError("OIDN could not create CPU device")
    get_error = bind("oidnGetDeviceError", [ptr, C.POINTER(string)], integer)
    release_device = bind("oidnReleaseDevice", [ptr])
    release_filter = bind("oidnReleaseFilter", [ptr])
    filt = None

    def check():
        message = string()
        code = get_error(device, C.byref(message))
        if code:
            raise RuntimeError(f"OIDN {code}: {message.value!r}")

    try:
        bind("oidnSetDeviceInt", [ptr, string, integer])(device, b"numThreads", threads)
        bind("oidnCommitDevice", [ptr])(device)
        check()
        filt = bind("oidnNewFilter", [ptr, string], ptr)(device, b"RT")
        check()
        if not filt:
            raise RuntimeError("OIDN failed to create RT filter")
        arrays = {
            oidn_name: np.ascontiguousarray(buffers[sapien_name][..., :3], dtype=np.float32)
            for oidn_name, sapien_name in BUFFER_NAMES
        }
        arrays["output"] = np.empty_like(arrays["color"])
        set_image = bind(
            "oidnSetSharedFilterImage",
            [ptr, string, ptr, integer, size, size, size, size, size],
        )
        for name, a in arrays.items():
            h, w, _ = a.shape
            set_image(filt, name.encode(), a.ctypes.data, OIDN_FORMAT_FLOAT3,
                      w, h, 0, a.strides[1], a.strides[0])
        bind("oidnSetFilterBool", [ptr, string, C.c_bool])(filt, b"hdr", True)
        bind("oidnCommitFilter", [ptr])(filt)
        check()
        bind("oidnExecuteFilter", [ptr])(filt)
        check()
        if not np.isfinite(arrays["output"]).all():
            raise ValueError("Nonfinite OIDN output")
        return arrays["output"]
    finally:
        if filt:
            release_filter(filt)
        release_device(device)
