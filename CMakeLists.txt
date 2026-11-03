cmake_minimum_required(VERSION 3.12)
project(cafepad C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

include_directories(include)

# Platform-specific configurations
if(WIN32)
    add_definitions(-D_WIN32 -DUSE_HIDAPI)
    find_package(hidapi REQUIRED)
    set(EXTRA_LIBS hidapi::hidapi)
elseif(APPLE)
    add_definitions(-D__APPLE__ -DUSE_HIDAPI)
    find_package(hidapi REQUIRED)
    set(EXTRA_LIBS hidapi::hidapi)
elseif(UNIX)
    # Native Linux L2CAP (BlueZ) + HIDRAW
    set(EXTRA_LIBS m bluetooth)
endif()

# Shared library
add_library(cafepad_shared SHARED src/cafepad.c)
set_target_properties(cafepad_shared PROPERTIES OUTPUT_NAME cafepad)
target_link_libraries(cafepad_shared PRIVATE ${EXTRA_LIBS})

# Static library
add_library(cafepad_static STATIC src/cafepad.c)
set_target_properties(cafepad_static PROPERTIES OUTPUT_NAME cafepad)
target_link_libraries(cafepad_static PRIVATE ${EXTRA_LIBS})

# Example executable
add_executable(test_controller examples/test_controller.c)
target_link_libraries(test_controller PRIVATE cafepad_static ${EXTRA_LIBS})

# Install rules
include(GNUInstallDirs)
install(TARGETS cafepad_shared cafepad_static
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(FILES include/cafepad.h include/wiiupro.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
