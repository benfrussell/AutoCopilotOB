cmake_minimum_required(VERSION 2.8)
project(dji-interface)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -pthread -g -O0 -Wno-psabi")
set(ONBOARDSDK_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../osdk-core")
set(MODULES_HEADER_DIR "${ONBOARDSDK_SOURCE}/modules/inc/payload")
set(FLIGHT_MODULES_HEADER_DIR "${ONBOARDSDK_SOURCE}/modules/inc/flight")

include_directories(${ONBOARDSDK_SOURCE}/api/inc)
include_directories(${ONBOARDSDK_SOURCE}/utility/inc)
include_directories(${ONBOARDSDK_SOURCE}/hal/inc)
include_directories(${ONBOARDSDK_SOURCE}/protocol/inc)
include_directories(${ONBOARDSDK_SOURCE}/platform/linux/inc)
include_directories(${MODULES_HEADER_DIR})
include_directories(${FLIGHT_MODULES_HEADER_DIR})
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/common)
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/nlohmann)
include_directories(${PROJECT_BINARY_DIR})

find_package(cppzmq)

FILE(GLOB SOURCE_FILES *.hpp *.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/common/dji_linux_environment.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/common/dji_linux_helpers.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/nlohmann/json.hpp
        )

add_executable(${PROJECT_NAME} ${SOURCE_FILES})

target_link_libraries(${PROJECT_NAME} djiosdk-core)

target_link_libraries(${PROJECT_NAME} cppzmq)

