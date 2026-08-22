#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_core/juce_core.h>
#include <memory>
#include <vector>
#include <functional>

namespace aria {

struct ScannedPlugin {
    juce::String uniqueId;       // VST3 UID or CLAP id
    juce::String name;
    juce::String manufacturer;
    juce::String format;         // "VST3", "AU", "CLAP"
    juce::String filePath;
    bool         isInstrument = false;
    bool         isEffect     = false;
};

// ─────────────────────────────────────────────────────────────────────────────
//  PluginHost
//
//  Manages plugin scanning, loading, and insertion on tracks.
//  Plugin scanning is done in a child process (aria_plugin_scan) to prevent
//  crashes from misbehaving plugins from killing the main process.
// ─────────────────────────────────────────────────────────────────────────────

class PluginHost {
public:
    PluginHost();
    ~PluginHost();

    // ── Scanning ──────────────────────────────────────────────────────────────

    using ScanProgressCallback = std::function<void(const juce::String& currentPlugin,
                                                     int scanned, int total)>;

    /** Start an async plugin scan. Results saved to cache file. Non-blocking. */
    void startScan(ScanProgressCallback progressCallback = nullptr);

    /** Load cached scan results. Call at startup. */
    void loadCachedRegistry();

    /** True if a scan is in progress. */
    bool isScanning() const noexcept;

    // ── Registry ──────────────────────────────────────────────────────────────

    const std::vector<ScannedPlugin>& allPlugins() const noexcept;
    const ScannedPlugin* findPlugin(const juce::String& uniqueId) const;

    // ── Loading ───────────────────────────────────────────────────────────────

    /** Load and instantiate a plugin. Returns nullptr on failure. */
    std::unique_ptr<juce::AudioPluginInstance>
    loadPlugin(const juce::String& uniqueId,
               double sampleRate = 44100.0,
               int    blockSize  = 512);

    /** Get plugin cache file path. */
    static juce::File cacheFile();

private:
    juce::AudioPluginFormatManager   formatManager_;
    juce::KnownPluginList            knownPlugins_;
    std::vector<ScannedPlugin>       registry_;
    std::atomic<bool>                scanning_ { false };

    void buildRegistryFromKnownList();
};

} // namespace aria
