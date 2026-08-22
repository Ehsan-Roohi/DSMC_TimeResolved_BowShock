cmake_minimum_required(VERSION 3.15)

project(OpenFOAMMUIDSMCNS VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(BUILD_MUI_GATE0 "Build the MUI MPMD Gate-0 executable" ON)
option(BUILD_CORE_TESTS "Build dependency-free core tests" ON)

add_library(muiFoamCore INTERFACE)
target_include_directories(
    muiFoamCore
    INTERFACE
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

if(BUILD_CORE_TESTS)
    enable_testing()
    add_executable(test_breakdown tests/test_breakdown.cpp)
    target_link_libraries(test_breakdown PRIVATE muiFoamCore)
    add_test(NAME breakdown_indicator COMMAND test_breakdown)
endif()

if(BUILD_MUI_GATE0)
    find_package(MPI REQUIRED)
    find_package(MUI REQUIRED)

    add_executable(mui_state_exchange src/gate0/mui_state_exchange.cpp)
    target_include_directories(mui_state_exchange PRIVATE ${MPI_INCLUDE_PATH})
    if(MUI_BASE_DIR)
        target_include_directories(mui_state_exchange PRIVATE ${MUI_INCLUDE_DIR})
    endif()
    target_link_libraries(
        mui_state_exchange
        PRIVATE
            muiFoamCore
            MUI::MUI
            ${MPI_CXX_LIBRARIES}
            ${MPI_C_LIBRARIES}
    )
endif()
