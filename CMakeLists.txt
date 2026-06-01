cmake_minimum_required(VERSION 3.20)
project(native_test_process_fixtures CXX)

# The C++ side of the fixtures. The builder configures one build tree per
# platform (passing a toolchain file for Android/WASM) and builds the target
# it wants. Symbol *placement* (embedded vs separate) is, for ELF/Mach-O, a
# post-build binutils step in builder/symbols.py; only the Windows DWARF-vs-PDB
# fork has to be decided at compile time, which is what FIXTURE_SYMBOLS does.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# embedded|separate - only consulted on Windows (see below).
set(FIXTURE_SYMBOLS "embedded" CACHE STRING "Symbol placement: embedded|separate")

# Always -O0 with full debug info and frame pointers: faithful line tables and
# locals are the whole point of these fixtures.
add_compile_options(-g -O0 -fno-omit-frame-pointer)

# Deterministic, host-independent source paths in the debug info. This is the
# same -fdebug-prefix-map a real project uses, and it is exactly the remapping
# the DAP project's source-mapper must undo. (clang/gcc spelling.)
add_compile_options("-fdebug-prefix-map=${CMAKE_SOURCE_DIR}=.")

# Reproducible build-id so a separated .debug links back via debuglink/build-id.
if(CMAKE_SYSTEM_NAME STREQUAL "Linux" OR ANDROID)
    add_link_options(-Wl,--build-id=sha1)
endif()

# Windows is the one place the debug *format* is a compile-time choice:
#   embedded -> DWARF inside the PE (clang -gdwarf)
#   separate -> CodeView + a .pdb sidecar (needs lld-link)
if(WIN32)
    if(FIXTURE_SYMBOLS STREQUAL "separate")
        add_compile_options(-gcodeview)
        add_link_options(-g -fuse-ld=lld)
    else()
        add_compile_options(-gdwarf-5)
        add_link_options(-fuse-ld=lld)
    endif()
endif()

# WASM (wasi-sdk) has no pthreads in the default target; compile the worker
# threads out of spin.
if(CMAKE_SYSTEM_NAME STREQUAL "WASI" OR CMAKE_SYSTEM_NAME MATCHES "Emscripten")
    add_compile_definitions(FIXTURE_SINGLE_THREADED=1)
endif()

set(FIXTURES_DIR "${CMAKE_SOURCE_DIR}/fixtures")

add_executable(hello "${FIXTURES_DIR}/hello/hello.cpp")
add_executable(spin  "${FIXTURES_DIR}/spin/spin.cpp")
add_executable(crash "${FIXTURES_DIR}/crash/crash.cpp")

# spin uses std::thread except on single-threaded targets.
if(NOT (CMAKE_SYSTEM_NAME STREQUAL "WASI" OR CMAKE_SYSTEM_NAME MATCHES "Emscripten"))
    find_package(Threads REQUIRED)
    target_link_libraries(spin PRIVATE Threads::Threads)
endif()
