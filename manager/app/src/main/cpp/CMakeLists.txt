# For more information about using CMake with Android Studio, read the
# documentation: https://d.android.com/studio/projects/add-native-code.html

# Sets the minimum version of CMake required to build the native library.
cmake_minimum_required(VERSION 3.18.1)

project("kernelsu")

add_library(kernelsu
        SHARED
        jni.c
        ksu.c
        legacy.c
)

# Windows clones may materialize the uapi symlink as a text file. Include the
# repository root explicitly so the shared headers work on both hosts.
get_filename_component(KSU_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../.." ABSOLUTE)
target_include_directories(kernelsu PRIVATE . "${KSU_REPO_ROOT}")

find_library(log-lib log)

target_link_libraries(
        kernelsu
        ${log-lib}
)

find_package(cxx REQUIRED CONFIG)
link_libraries(cxx::cxx)

add_library(adbroot SHARED adbroot.cc)
target_link_libraries(adbroot ${log-lib})
