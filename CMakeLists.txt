cmake_minimum_required(VERSION 2.8)
project(AutoCopilotOB)

set(CMAKE_VERBOSE_MAKEFILE OFF)

set(EXECUTABLE_OUTPUT_PATH ${PROJECT_BINARY_DIR}/bin)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${PROJECT_BINARY_DIR}/libs)

add_subdirectory(osdk-core)

add_subdirectory(dji-interface)
