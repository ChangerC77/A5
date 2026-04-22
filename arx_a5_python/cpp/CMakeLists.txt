cmake_minimum_required(VERSION 3.10)
project(arx_a5_python VERSION 1.0)

find_package(pybind11 REQUIRED)

include_directories(${PROJECT_SOURCE_DIR}/include)
include_directories(${PROJECT_SOURCE_DIR}/lib/arx_r5_src/include)
include_directories(${PROJECT_SOURCE_DIR}/lib/arx_hardware_interface/include)

pybind11_add_module(arx_a5 src/single_arm_interface.cpp)
pybind11_add_module(kinematic_solver src/kinematic_solver.cpp)

set(DEPEND_LIB "${CMAKE_CURRENT_SOURCE_DIR}/lib/arx_r5_src/libarx_r5a_src.so")
set(SOLVER_LIB "${CMAKE_CURRENT_SOURCE_DIR}/lib/libkinematic_solver.so")

target_include_directories(kinematic_solver PUBLIC lib/)
target_link_libraries(arx_a5 PUBLIC ${DEPEND_LIB} pybind11::module)
target_link_libraries(kinematic_solver PUBLIC ${SOLVER_LIB} pybind11::module)

set(INSTALL_LIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../arx_a5_python/lib")
set(CMAKE_INSTALL_PREFIX "${CMAKE_CURRENT_SOURCE_DIR}/../arx_a5_python" CACHE PATH "Installation Directory" FORCE)

install(FILES lib/arx_r5_src/libarx_r5a_src.so
        DESTINATION lib)
install(FILES lib/libkinematic_solver.so
        DESTINATION lib)
install(TARGETS arx_a5
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib)
install(TARGETS kinematic_solver
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib)
