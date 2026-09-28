cmake_minimum_required(VERSION 3.20)
project(pet_core LANGUAGES CXX)

set(PET_BUILD_INPUTS
    ${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt
    ${CMAKE_CURRENT_SOURCE_DIR}/include/pet_core.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/collision_internal.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/c_api.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/collision.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/pet_build_id.h.in)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${PET_BUILD_INPUTS})
set(PET_HASH_INPUT "")
foreach(PET_INPUT IN LISTS PET_BUILD_INPUTS)
    file(SHA256 ${PET_INPUT} PET_INPUT_HASH)
    file(RELATIVE_PATH PET_INPUT_NAME ${CMAKE_CURRENT_SOURCE_DIR} ${PET_INPUT})
    string(APPEND PET_HASH_INPUT "${PET_INPUT_NAME}:${PET_INPUT_HASH}\n")
endforeach()
string(TOUPPER "${CMAKE_BUILD_TYPE}" PET_BUILD_TYPE_UPPER)
set(PET_CONFIG_FLAG_NAME "CMAKE_CXX_FLAGS_${PET_BUILD_TYPE_UPPER}")
string(APPEND PET_HASH_INPUT "compiler=${CMAKE_CXX_COMPILER_ID}${CMAKE_CXX_COMPILER_VERSION}\n")
string(APPEND PET_HASH_INPUT "flags=${CMAKE_CXX_FLAGS};${${PET_CONFIG_FLAG_NAME}}\n")
string(APPEND PET_HASH_INPUT "lto=${CMAKE_INTERPROCEDURAL_OPTIMIZATION}\n")
string(SHA256 PET_SOURCE_HASH "${PET_HASH_INPUT}")
string(SUBSTRING ${PET_SOURCE_HASH} 0 16 PET_SOURCE_HASH_SHORT)
set(PET_BUILD_ID "collision-core/2.0+${PET_SOURCE_HASH_SHORT}-${CMAKE_CXX_COMPILER_ID}${CMAKE_CXX_COMPILER_VERSION}-${CMAKE_BUILD_TYPE}")
configure_file(src/pet_build_id.h.in ${CMAKE_CURRENT_BINARY_DIR}/pet_build_id.h @ONLY)

add_library(pet_core SHARED src/collision.cpp src/c_api.cpp)
target_compile_features(pet_core PRIVATE cxx_std_20)
target_compile_definitions(pet_core PRIVATE PET_CORE_BUILD)
target_include_directories(pet_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_include_directories(pet_core PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
set_target_properties(pet_core PROPERTIES PREFIX "" OUTPUT_NAME "pet_core")

include(CTest)
if(BUILD_TESTING)
    add_executable(pet_core_tests tests/test_core.cpp)
    target_compile_features(pet_core_tests PRIVATE cxx_std_20)
    target_link_libraries(pet_core_tests PRIVATE pet_core)
    add_test(NAME pet_core_tests COMMAND pet_core_tests)
endif()

install(TARGETS pet_core RUNTIME DESTINATION pet/native/_bin LIBRARY DESTINATION pet/native/_bin)
