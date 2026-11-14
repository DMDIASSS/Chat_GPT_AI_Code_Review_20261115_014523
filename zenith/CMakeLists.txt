cmake_minimum_required(VERSION 3.24)
project(zenith_sim LANGUAGES CXX)

if(WIN32)
  add_compile_definitions(NOMINMAX WIN32_LEAN_AND_MEAN)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(VENDOR_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor")
set(RLGYM_DIR "${VENDOR_DIR}/RLGymCPP")

# Add pybind11 first
add_subdirectory("${VENDOR_DIR}/pybind11" pybind11_build)

# Add RLGymCPP (which adds RocketSim)
add_subdirectory("${RLGYM_DIR}" rlgym_build)

pybind11_add_module(zenith_sim native/zenith_sim.cpp)
target_include_directories(zenith_sim PRIVATE
  "${RLGYM_DIR}/src"
  "${RLGYM_DIR}/thread_pool"
  "${RLGYM_DIR}/RocketSim/src"
)
target_link_libraries(zenith_sim PRIVATE RLGymCPP RocketSim)

if(MSVC)
  target_compile_options(zenith_sim PRIVATE /bigobj /utf-8 /O2 /openmp)
endif()
