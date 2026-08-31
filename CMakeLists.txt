cmake_minimum_required(VERSION 3.15)

project(OpenFOAMMUIDSMCNS VERSION 0.8.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(BUILD_MUI_GATE0 "Build the MUI MPMD Gate-0 executable" ON)
option(BUILD_MUI_GATE1A "Build the fixed-interface Gate-1A executable" OFF)
option(BUILD_MUI_GATE3A "Build the conservative-flux Gate-3A executable" OFF)
option(BUILD_MUI_GATE3B "Build the moving-cylinder Gate-3B pilot executable" OFF)
option(BUILD_MUI_GATE3D "Build the physical-feedback Gate-3D executables" OFF)
option(BUILD_GATE3G_SCALING "Build the Gate-3G restart scaling kernel" OFF)
option(BUILD_MUI_GATE3I "Build the Gate-3I distributed-transport probe" OFF)
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

    add_executable(test_equilibrium tests/test_equilibrium.cpp)
    target_link_libraries(test_equilibrium PRIVATE muiFoamCore)
    add_test(NAME equilibrium_moment_packet COMMAND test_equilibrium)

    add_executable(test_conservative_flux tests/test_conservative_flux.cpp)
    target_link_libraries(test_conservative_flux PRIVATE muiFoamCore)
    add_test(NAME conservative_flux_restart COMMAND test_conservative_flux)

    add_executable(test_adaptive_interface tests/test_adaptive_interface.cpp)
    target_link_libraries(test_adaptive_interface PRIVATE muiFoamCore)
    add_test(NAME adaptive_interface_balance COMMAND test_adaptive_interface)

    add_executable(test_physical_feedback tests/test_physical_feedback.cpp)
    target_link_libraries(test_physical_feedback PRIVATE muiFoamCore)
    add_test(NAME physical_feedback_restart COMMAND test_physical_feedback)

    add_executable(
        test_dynamic_particle_domain tests/test_dynamic_particle_domain.cpp
    )
    target_link_libraries(test_dynamic_particle_domain PRIVATE muiFoamCore)
    add_test(NAME dynamic_particle_domain COMMAND test_dynamic_particle_domain)

    add_executable(test_kn_gl_interface tests/test_kn_gl_interface.cpp)
    target_link_libraries(test_kn_gl_interface PRIVATE muiFoamCore)
    add_test(NAME kn_gl_interface COMMAND test_kn_gl_interface)
endif()

if(BUILD_MUI_GATE0 OR BUILD_MUI_GATE1A OR BUILD_MUI_GATE3A OR BUILD_MUI_GATE3B OR BUILD_MUI_GATE3D OR BUILD_MUI_GATE3I)
    find_package(MPI REQUIRED)
    find_package(MUI REQUIRED)
elseif(BUILD_GATE3G_SCALING)
    find_package(MPI REQUIRED)
endif()

if(BUILD_GATE3G_SCALING)
    add_executable(
        dynamic_restart_scaling
        src/gate3g/dynamic_restart_scaling.cpp
    )
    target_link_libraries(
        dynamic_restart_scaling
        PRIVATE muiFoamCore MPI::MPI_CXX
    )
endif()

function(link_mui_target target_name)
    target_include_directories(${target_name} PRIVATE ${MPI_INCLUDE_PATH})
    if(MUI_BASE_DIR)
        target_include_directories(${target_name} PRIVATE ${MUI_INCLUDE_DIR})
    endif()
    target_link_libraries(
        ${target_name}
        PRIVATE
            muiFoamCore
            MUI::MUI
            ${MPI_CXX_LIBRARIES}
            ${MPI_C_LIBRARIES}
    )
endfunction()

if(BUILD_MUI_GATE0)
    add_executable(mui_state_exchange src/gate0/mui_state_exchange.cpp)
    link_mui_target(mui_state_exchange)
endif()

if(BUILD_MUI_GATE1A)
    add_executable(mui_fixed_interface src/gate1a/mui_fixed_interface.cpp)
    link_mui_target(mui_fixed_interface)
endif()

if(BUILD_MUI_GATE3A)
    add_executable(mui_conservative_flux src/gate3a/mui_conservative_flux.cpp)
    link_mui_target(mui_conservative_flux)
endif()

if(BUILD_MUI_GATE3B)
    add_executable(
        mui_moving_cylinder_flux
        src/gate3b/mui_moving_cylinder_flux.cpp
    )
    link_mui_target(mui_moving_cylinder_flux)
endif()

if(BUILD_MUI_GATE3D)
    add_executable(
        mui_physical_feedback
        src/gate3d/mui_physical_feedback.cpp
    )
    link_mui_target(mui_physical_feedback)

    add_executable(
        physical_feedback_scaling
        src/gate3d/physical_feedback_scaling.cpp
    )
    target_include_directories(physical_feedback_scaling PRIVATE ${MPI_INCLUDE_PATH})
    target_link_libraries(
        physical_feedback_scaling
        PRIVATE muiFoamCore ${MPI_CXX_LIBRARIES} ${MPI_C_LIBRARIES}
    )
endif()

if(BUILD_MUI_GATE3I)
    add_executable(
        mui_domain_decomposition_probe
        src/gate3i/mui_domain_decomposition_probe.cpp
    )
    link_mui_target(mui_domain_decomposition_probe)
endif()
