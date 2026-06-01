# Thin wrapper around the NDK's own CMake toolchain file, so presets and the
# orchestrator can reference one stable path. Point ANDROID_NDK_HOME (or
# ANDROID_NDK_ROOT) at the NDK install and pass -DANDROID_ABI / -DANDROID_PLATFORM
# when configuring.
if(DEFINED ENV{ANDROID_NDK_HOME})
    set(_ndk_root "$ENV{ANDROID_NDK_HOME}")
elseif(DEFINED ENV{ANDROID_NDK_ROOT})
    set(_ndk_root "$ENV{ANDROID_NDK_ROOT}")
else()
    message(FATAL_ERROR
        "Android build requires the NDK: set ANDROID_NDK_HOME to its install root.")
endif()

set(_ndk_toolchain "${_ndk_root}/build/cmake/android.toolchain.cmake")
if(NOT EXISTS "${_ndk_toolchain}")
    message(FATAL_ERROR "NDK toolchain file not found at ${_ndk_toolchain}")
endif()

include("${_ndk_toolchain}")
