/**
 * aria_plugin_scan — headless child process for safe plugin scanning.
 *
 * Launched by PluginHost::startScan() as a separate process.
 * If a plugin crashes during scan, only this process dies — the main
 * ARIA process is unaffected.
 *
 * Protocol:
 *   stdin:  scan directory paths, one per line
 *   stdout: scanned plugin XML lines
 *   stderr: error messages
 */

#include <juce_core/juce_core.h>
#include <juce_audio_processors/juce_audio_processors.h>

class PluginScannerApp : public juce::JUCEApplicationBase {
public:
    const juce::String getApplicationName()    override { return "ARIA Plugin Scanner"; }
    const juce::String getApplicationVersion() override { return "0.1.0"; }
    bool               moreThanOneInstanceAllowed() override { return true; }

    void initialise(const juce::String& commandLine) override
    {
        juce::ignoreUnused(commandLine);

        juce::AudioPluginFormatManager formatManager;
        formatManager.addDefaultFormats();

        juce::KnownPluginList knownPlugins;

        // Read scan paths from command-line arguments
        auto args = juce::JUCEApplicationBase::getCommandLineParameterArray();
        for (auto& path : args) {
            juce::File dir(path);
            if (!dir.isDirectory()) continue;

            juce::PluginDirectoryScanner scanner(
                knownPlugins, formatManager,
                { dir }, true, juce::File());

            juce::String name;
            while (scanner.scanNextFile(true, name)) {
                juce::Logger::writeToLog("[scan] " + name);
            }
        }

        // Write results to stdout as XML
        if (auto xml = knownPlugins.createXml()) {
            std::cout << xml->toString(juce::XmlElement::TextFormat{}) << std::endl;
        }

        quit();
    }

    void shutdown() override {}
    void systemRequestedQuit() override { quit(); }
    void anotherInstanceStarted(const juce::String&) override {}
    void suspended() override {}
    void resumed() override {}
    void unhandledException(const std::exception*, const juce::String&, int) override {}
};

START_JUCE_APPLICATION(PluginScannerApp)
