# LingTouch 端侧核心的顶层 CMake（C++17，无平台依赖）。
#
# 主机上编译并运行测试：
#   cmake -S core -B build/core && cmake --build build/core && ctest --test-dir build/core --output-on-failure
# 安卓、鸿蒙外壳在各自的 native CMakeLists 里 add_subdirectory 本目录，链接 lingtouch_engine。
cmake_minimum_required(VERSION 3.16)
project(lingtouch_core LANGUAGES C CXX)

get_filename_component(LINGTOUCH_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  set(LINGTOUCH_IS_TOP_LEVEL ON)
else()
  set(LINGTOUCH_IS_TOP_LEVEL OFF)
endif()
option(LINGTOUCH_BUILD_TESTS "Build host tests and tools" ${LINGTOUCH_IS_TOP_LEVEL})
option(LINGTOUCH_WITH_LIBUSB "Build the libusb CS30 transport (Android, desktop Linux)" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Threads REQUIRED)

# 安卓和鸿蒙要对同一帧算出完全一致的栅格：禁止编译器把 a*b+c 合并成 FMA，不用 fast-math。
function(lingtouch_target_defaults target)
  if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(${target} PRIVATE -ffp-contract=off -fno-fast-math -Wall -Wextra)
  elseif(MSVC)
    target_compile_options(${target} PRIVATE /fp:precise /utf-8 /W4)
  endif()
endfunction()

# 默认参数唯一来源：config/lingtouch_defaults.conf，编译时原样嵌入。
set(LINGTOUCH_DEFAULT_CONFIG "${CMAKE_CURRENT_SOURCE_DIR}/config/lingtouch_defaults.conf")
file(READ "${LINGTOUCH_DEFAULT_CONFIG}" LINGTOUCH_DEFAULT_CONFIG_TEXT)
configure_file(src/default_config.inc.in "${CMAKE_CURRENT_BINARY_DIR}/generated/default_config.inc" @ONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${LINGTOUCH_DEFAULT_CONFIG}")

add_library(lingtouch_base STATIC
  src/types.cpp
  src/config.cpp
  src/tactile_legacy.cpp)
target_include_directories(lingtouch_base
  PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
  PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
lingtouch_target_defaults(lingtouch_base)

# 视觉同学：CS30 取流协议、拆帧、几何、0/1/2
add_subdirectory("${LINGTOUCH_ROOT}/perception/native" "${CMAKE_CURRENT_BINARY_DIR}/perception")
# 对话 agent 同学：本次只有接口
add_subdirectory("${LINGTOUCH_ROOT}/agent/native" "${CMAKE_CURRENT_BINARY_DIR}/agent")

# 给外壳调用的门面
add_library(lingtouch_engine STATIC src/engine.cpp src/report_json.cpp)
target_link_libraries(lingtouch_engine PUBLIC lingtouch_base lingtouch_perception lingtouch_agent Threads::Threads)
lingtouch_target_defaults(lingtouch_engine)

if(LINGTOUCH_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
  add_subdirectory("${LINGTOUCH_ROOT}/perception/native/tests" "${CMAKE_CURRENT_BINARY_DIR}/perception_tests")
endif()
