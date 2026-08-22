cmake_minimum_required(VERSION 3.24)
project(aria_cpp VERSION 0.1.0 LANGUAGES CXX C)

# ─────────────────────────────────────────────
#  Global settings
# ─────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Put all binaries in a predictable location
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Default build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "" FORCE)
endif()

# ─────────────────────────────────────────────
#  FetchContent — third-party libraries
# ─────────────────────────────────────────────
include(FetchContent)

# ── JUCE 8 ──────────────────────────────────
FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        8.0.4
    GIT_SHALLOW    TRUE
)

# ── Tracktion Engine 9 ──────────────────────
FetchContent_Declare(
    tracktion_engine
    GIT_REPOSITORY https://github.com/Tracktion/tracktion_engine.git
    GIT_TAG        main
    GIT_SHALLOW    TRUE
)

# ── llama.cpp ────────────────────────────────
FetchContent_Declare(
    llama_cpp
    GIT_REPOSITORY https://github.com/ggerganov/llama.cpp.git
    GIT_TAG        master
    GIT_SHALLOW    TRUE
)

# ── nlohmann/json ────────────────────────────
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.11.3
    GIT_SHALLOW    TRUE
)

# ── clap-juce-extensions (CLAP plugin hosting)
FetchContent_Declare(
    clap_juce_extensions
    GIT_REPOSITORY https://github.com/free-audio/clap-juce-extensions.git
    GIT_TAG        main
    GIT_SHALLOW    TRUE
)

# ── Catch2 (tests only) ──────────────────────
FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG        v3.6.0
    GIT_SHALLOW    TRUE
)

# llama.cpp options (disable server/tests to keep build fast)
set(LLAMA_BUILD_TESTS   OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER  OFF CACHE BOOL "" FORCE)

# nlohmann — header-only, no tests
set(JSON_BuildTests     OFF CACHE BOOL "" FORCE)
set(JSON_Install        OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(
    JUCE
    tracktion_engine
    llama_cpp
    nlohmann_json
    clap_juce_extensions
    Catch2
)

# ─────────────────────────────────────────────
#  JUCE application
# ─────────────────────────────────────────────
juce_add_gui_app(aria_cpp
    VERSION                 ${PROJECT_VERSION}
    PRODUCT_NAME            "ARIA"
    COMPANY_NAME            "ARIA Music AI"
    BUNDLE_ID               "com.aria.daw"
    NEEDS_MIDI_INPUT        TRUE
    NEEDS_MIDI_OUTPUT       TRUE
    MICROPHONE_PERMISSION_ENABLED TRUE
    AUDIO_DEVICE_REQUIRED   TRUE

    # macOS / Windows icons (add files to resources/ and list here)
    # ICON_BIG   resources/icons/aria_icon_512.png
    # ICON_SMALL resources/icons/aria_icon_32.png
)

# Embed resource files so juce::File::loadFileAsString() works in release builds
juce_add_binary_data(aria_resources
    SOURCES
        resources/agents/CHAT.md
        resources/agents/PRODUCER.md
        resources/agents/CONDUCTOR.md
        resources/agents/TRACK.md
        resources/schemas/song_schema.json
)

# ─────────────────────────────────────────────
#  Source files
# ─────────────────────────────────────────────
target_sources(aria_cpp PRIVATE
    src/main.cpp

    # Core
    src/core/SongDocument.cpp
    src/core/AudioEngine.cpp
    src/core/InstrumentRegistry.cpp

    # Agents
    src/agents/AgentOrchestrator.cpp
    src/agents/ChatAgent.cpp
    src/agents/ProducerAgent.cpp
    src/agents/ConductorAgent.cpp
    src/agents/TrackAgent.cpp

    # LLM runtime
    src/llm/LLMRuntime.cpp

    # Plugin hosting
    src/plugins/PluginHost.cpp
    src/plugins/PluginRegistry.cpp

    # UI
    src/ui/MainWindow.cpp
    src/ui/IRAPanel.cpp
    src/ui/PianoRollWindow.cpp
    src/ui/MixerPanel.cpp
)

target_include_directories(aria_cpp PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# ─────────────────────────────────────────────
#  JUCE compile definitions
# ─────────────────────────────────────────────
target_compile_definitions(aria_cpp PRIVATE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_APPLICATION_NAME_STRING="$<TARGET_PROPERTY:aria_cpp,JUCE_PRODUCT_NAME>"
    JUCE_APPLICATION_VERSION_STRING="$<TARGET_PROPERTY:aria_cpp,JUCE_VERSION>"
    JUCE_DISPLAY_SPLASH_SCREEN=0
    # Suppress llama.cpp deprecation noise on MSVC
    $<$<CXX_COMPILER_ID:MSVC>:_SILENCE_ALL_CXX23_DEPRECATION_WARNINGS>
)

# ─────────────────────────────────────────────
#  Link libraries
# ─────────────────────────────────────────────
target_link_libraries(aria_cpp PRIVATE
    # JUCE modules
    juce::juce_audio_basics
    juce::juce_audio_devices
    juce::juce_audio_formats
    juce::juce_audio_processors
    juce::juce_audio_utils
    juce::juce_core
    juce::juce_data_structures
    juce::juce_events
    juce::juce_graphics
    juce::juce_gui_basics
    juce::juce_gui_extra

    # Tracktion Engine
    tracktion::tracktion_engine
    tracktion::tracktion_graph

    # LLM
    llama

    # JSON (header-only)
    nlohmann_json::nlohmann_json

    # CLAP
    clap_juce_extensions::clap_juce_extensions

    # Embedded resources
    aria_resources

    # Recommended JUCE flags
    juce::juce_recommended_config_flags
    juce::juce_recommended_lto_flags
    juce::juce_recommended_warning_flags
)

# ─────────────────────────────────────────────
#  Platform-specific
# ─────────────────────────────────────────────
if(WIN32)
    # Use the static CRT in Release to simplify distribution
    set_property(TARGET aria_cpp PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    target_link_libraries(aria_cpp PRIVATE winmm.lib)
endif()

if(APPLE)
    target_link_libraries(aria_cpp PRIVATE
        "-framework CoreAudio"
        "-framework CoreMIDI"
        "-framework AudioUnit"
        "-framework AudioToolbox"
        "-framework Accelerate"
    )
    set_target_properties(aria_cpp PROPERTIES
        MACOSX_BUNDLE TRUE
        XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY ""
        XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED NO
    )
endif()

# ─────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────
enable_testing()

juce_add_console_app(aria_tests
    PRODUCT_NAME "ARIA Tests"
)

target_sources(aria_tests PRIVATE
    tests/SongDocumentTests.cpp
    tests/LLMRuntimeTests.cpp
    tests/AgentPipelineTests.cpp

    # Pull in production sources needed by tests
    src/core/SongDocument.cpp
    src/core/InstrumentRegistry.cpp
    src/agents/AgentOrchestrator.cpp
    src/agents/ChatAgent.cpp
    src/agents/ProducerAgent.cpp
    src/agents/ConductorAgent.cpp
    src/agents/TrackAgent.cpp
    src/llm/LLMRuntime.cpp
)

target_include_directories(aria_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_compile_definitions(aria_tests PRIVATE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    CATCH_CONFIG_MAIN
)

target_link_libraries(aria_tests PRIVATE
    juce::juce_core
    juce::juce_data_structures
    nlohmann_json::nlohmann_json
    llama
    Catch2::Catch2WithMain
    juce::juce_recommended_warning_flags
)

include(CTest)
include(Catch)
catch_discover_tests(aria_tests)

# ─────────────────────────────────────────────
#  Headless plugin scanner (child process)
# ─────────────────────────────────────────────
juce_add_console_app(aria_plugin_scan
    PRODUCT_NAME "ARIA Plugin Scanner"
)

target_sources(aria_plugin_scan PRIVATE
    src/plugins/PluginScannerMain.cpp
    src/plugins/PluginRegistry.cpp
)

target_include_directories(aria_plugin_scan PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_compile_definitions(aria_plugin_scan PRIVATE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
)

target_link_libraries(aria_plugin_scan PRIVATE
    juce::juce_core
    juce::juce_audio_processors
    nlohmann_json::nlohmann_json
    juce::juce_recommended_warning_flags
)
