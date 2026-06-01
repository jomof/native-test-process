# Thin wrapper around the wasi-sdk CMake toolchain file. Point WASI_SDK_PATH at
# the wasi-sdk install root (the one containing share/cmake/wasi-sdk.cmake).
if(NOT DEFINED ENV{WASI_SDK_PATH})
    message(FATAL_ERROR
        "WASM build requires wasi-sdk: set WASI_SDK_PATH to its install root.")
endif()

set(_wasi_toolchain "$ENV{WASI_SDK_PATH}/share/cmake/wasi-sdk.cmake")
if(NOT EXISTS "${_wasi_toolchain}")
    message(FATAL_ERROR "wasi-sdk toolchain file not found at ${_wasi_toolchain}")
endif()

include("${_wasi_toolchain}")
