# 核心的主机测试（云端和本机都能跑）。
function(lingtouch_add_test name)
  add_executable(${name} ${ARGN})
  target_link_libraries(${name} PRIVATE lingtouch_engine)
  target_include_directories(${name} PRIVATE "${LINGTOUCH_ROOT}/core/tests")
  target_compile_definitions(${name} PRIVATE LINGTOUCH_SOURCE_ROOT="${LINGTOUCH_ROOT}")
  lingtouch_target_defaults(${name})
  add_test(NAME ${name} COMMAND ${name})
endfunction()

lingtouch_add_test(test_tactile_legacy test_tactile_legacy.cpp)
lingtouch_add_test(test_config test_config.cpp)

# 已提交的测试向量必须仍与 frame_converter.py 一致（需要 Python 和 numpy；缺 numpy 时跳过）
find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
  add_test(NAME legacy_vectors_up_to_date
           COMMAND ${Python3_EXECUTABLE} "${LINGTOUCH_ROOT}/core/tools/gen_legacy_vectors.py" --check)
  set_tests_properties(legacy_vectors_up_to_date PROPERTIES SKIP_RETURN_CODE 77)
endif()
