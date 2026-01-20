cmake_minimum_required(VERSION 3.16)
PROJECT(autofuse)
set(CMAKE_SKIP_RPATH TRUE)
set(CMAKE_CXX_STANDARD 17)

find_package(Python REQUIRED COMPONENTS Interpreter Development)
if(NOT Python_EXECUTABLE OR NOT EXISTS "${Python_EXECUTABLE}")
    message(FATAL_ERROR "Python executable not found or invalid: '${Python_EXECUTABLE}'")
endif()
include_directories(${Python_INCLUDE_DIRS})

execute_process(
    COMMAND ${Python_EXECUTABLE} -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE PYBIND11_GET_DIR_RESULT
)

if(NOT PYBIND11_GET_DIR_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to get pybind11 CMake directory. Python error: ${PYBIND11_GET_DIR_RESULT}")
endif()

set(pybind11_DIR "${PYBIND11_CMAKE_DIR}")
find_package(pybind11 REQUIRED)

if (DEFINED ENV{ASCEND_HOME_PATH})
    set(ASCEND_PATH $ENV{ASCEND_HOME_PATH})
else ()
    set(ASCEND_PATH /usr/local/Ascend/cann)
endif()

set (ASCEND_INCLUDE_DIR ${ASCEND_PATH}/include)

add_library(execute_graph SHARED
    ${CMAKE_SOURCE_DIR}/csrc/execute_graph.cpp
)

set_target_properties(execute_graph
    PROPERTIES
    OUTPUT_NAME ExecuteGraph_C
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/lib64
    PREFIX ""
)

target_include_directories(execute_graph PRIVATE
    ${ASCEND_INCLUDE_DIR}
)

target_link_libraries(execute_graph PRIVATE
    pybind11::module
    Python::Python
    ${ASCEND_PATH}/lib64/libge_runner.so
)

target_compile_options(
    execute_graph PRIVATE
    -fPIC
    -fstack-protector-all
    -ftrapv
    -Werror=uninitialized
    -Werror=return-type
    -Wall
    -D_FORTIFY_SOURCE=2
    $<$<NOT:$<STREQUAL:${CMAKE_BUILD_TYPE},Debug>>:-O2>
)

target_link_options(
    execute_graph PRIVATE
    -Wl,-z,relro,-z,now,-z,noexecstack
    -s
)