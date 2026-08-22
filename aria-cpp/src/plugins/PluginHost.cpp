#include "PluginHost.h"
#include <juce_audio_formats/juce_audio_formats.h>

namespace aria {

PluginHost::PluginHost()
{
    formatManager_.addDefaultFormats();
}

PluginHost::~PluginHost() = default;

juce::File PluginHost::cacheFile()
{
    return juce::File::getSpecialLocation(juce::File::userHomeDirectory)
        .getChildFile(".aria-cpp")
        .getChildFile("plugin_cache.xml");
}

void PluginHost::loadCachedRegistry()
{
    auto file = cacheFile();
    if (!file.existsAsFile()) return;

    if (auto xml = juce::parseXML(file)) {
        knownPlugins_.recreateFromXml(*xml);
        buildRegistryFromKnownList();
        juce::Logger::writeToLog("[PluginHost] Loaded " +
            juce::String(registry_.size()) + " cached plugins");
    }
}

void PluginHost::startScan(ScanProgressCallback progressCallback)
{
    if (scanning_.exchange(true)) return;

    juce::Thread::launch([this, progressCallback] {
        // TODO: spawn aria_plugin_scan child process for safety
        // For now, scan in-process (may crash on bad plugins)
        juce::PluginDirectoryScanner scanner(
            knownPlugins_,
            formatManager_,
            formatManager_.getFormat(0)->getDefaultLocationsToSearch(),
            true,  // search recursively
            juce::File()
        );

        juce::String pluginBeingScanned;
        int count = 0;
        while (scanner.scanNextFile(true, pluginBeingScanned)) {
            ++count;
            if (progressCallback)
                progressCallback(pluginBeingScanned, count, scanner.getEstimatedProgressFraction() > 0 ?
                    static_cast<int>(count / scanner.getEstimatedProgressFraction()) : 100);
        }

        // Save to cache
        auto cacheDir = cacheFile().getParentDirectory();
        cacheDir.createDirectory();
        if (auto xml = knownPlugins_.createXml())
            xml->writeToFile(cacheFile(), {});

        buildRegistryFromKnownList();
        scanning_.store(false);

        juce::Logger::writeToLog("[PluginHost] Scan complete: " +
            juce::String(registry_.size()) + " plugins found");
    });
}

bool PluginHost::isScanning() const noexcept { return scanning_.load(); }

const std::vector<ScannedPlugin>& PluginHost::allPlugins() const noexcept
{
    return registry_;
}

const ScannedPlugin* PluginHost::findPlugin(const juce::String& uniqueId) const
{
    for (auto& p : registry_)
        if (p.uniqueId == uniqueId) return &p;
    return nullptr;
}

std::unique_ptr<juce::AudioPluginInstance>
PluginHost::loadPlugin(const juce::String& uniqueId,
                        double sampleRate,
                        int    blockSize)
{
    auto* desc = knownPlugins_.getTypeForIdentifierString(uniqueId);
    if (!desc) {
        juce::Logger::writeToLog("[PluginHost] Plugin not found: " + uniqueId);
        return nullptr;
    }

    juce::String errorMessage;
    auto instance = formatManager_.createPluginInstance(
        *desc, sampleRate, blockSize, errorMessage);

    if (!instance)
        juce::Logger::writeToLog("[PluginHost] Failed to load plugin: " + errorMessage);

    return instance;
}

void PluginHost::buildRegistryFromKnownList()
{
    registry_.clear();
    for (int i = 0; i < knownPlugins_.getNumTypes(); ++i) {
        auto* desc = knownPlugins_.getType(i);
        ScannedPlugin p;
        p.uniqueId      = knownPlugins_.getTypeForIndex(i)->createIdentifierString();
        p.name          = desc->name;
        p.manufacturer  = desc->manufacturerName;
        p.format        = desc->pluginFormatName;
        p.filePath      = desc->fileOrIdentifier;
        p.isInstrument  = desc->isInstrument;
        p.isEffect      = !desc->isInstrument;
        registry_.push_back(p);
    }
}

} // namespace aria
