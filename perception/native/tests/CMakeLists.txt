# 感知部分的主机测试。由 core/CMakeLists.txt 在 LINGTOUCH_BUILD_TESTS 打开时加入。
function(lingtouch_add_perception_test name)
  add_executable(${name} ${ARGN})
  target_link_libraries(${name} PRIVATE lingtouch_engine)
  target_include_directories(${name} PRIVATE "${LINGTOUCH_ROOT}/core/tests" "${CMAKE_CURRENT_SOURCE_DIR}")
  target_compile_definitions(${name} PRIVATE LINGTOUCH_SOURCE_ROOT="${LINGTOUCH_ROOT}"
                                             LINGTOUCH_TEST_TMP="${CMAKE_CURRENT_BINARY_DIR}")
  lingtouch_target_defaults(${name})
  add_test(NAME ${name} COMMAND ${name})
endfunction()

lingtouch_add_perception_test(test_uvc_assembler test_uvc_assembler.cpp)
lingtouch_add_perception_test(test_cs30_protocol test_cs30_protocol.cpp)
lingtouch_add_perception_test(test_calibration test_calibration.cpp)
lingtouch_add_perception_test(test_depth_geometry test_depth_geometry.cpp)
lingtouch_add_perception_test(test_geometry_synthetic test_geometry_synthetic.cpp)
lingtouch_add_perception_test(test_reference_frames test_reference_frames.cpp)
lingtouch_add_perception_test(test_engine test_engine.cpp)

# 已提交的启动序列表必须仍与 perception/cs30/startup_sequence.json 一致
find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
  add_test(NAME startup_sequence_up_to_date
           COMMAND ${Python3_EXECUTABLE} "${LINGTOUCH_ROOT}/perception/native/tools/gen_startup_sequence.py" --check)
endif()

# 主机小工具：对任意一帧原始深度打印栅格和平面检查（PC 上 independent_proof.py 存下的 .raw 也能用）
add_executable(lt_frame_tool "${LINGTOUCH_ROOT}/perception/native/tools/lt_frame_tool.cpp")
target_link_libraries(lt_frame_tool PRIVATE lingtouch_engine)
lingtouch_target_defaults(lt_frame_tool)
