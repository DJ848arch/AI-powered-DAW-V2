#include "MainWindow.h"
#include "IRAPanel.h"
#include "MixerPanel.h"
#include "PianoRollWindow.h"

namespace aria {

enum MenuIDs {
    FileNew = 1,
    FileOpen,
    FileSave,
    FileSaveAs,
    FileExportWAV,
    EditUndo,
    EditRedo,
    ViewPianoRoll,
    ViewMixer,
    ViewIRAPanel,
    TransportPlay,
    TransportStop,
    TransportLoop,
    HelpAbout = 1000,
};

MainWindow::MainWindow(const juce::String& name,
                       AudioEngine&        audioEngine,
                       AgentOrchestrator&  orchestrator,
                       PluginHost&         pluginHost)
    : juce::DocumentWindow(name,
                           juce::Desktop::getInstance().getDefaultLookAndFeel()
                               .findColour(juce::ResizableWindow::backgroundColourId),
                           juce::DocumentWindow::allButtons),
      audioEngine_(audioEngine),
      orchestrator_(orchestrator),
      pluginHost_(pluginHost)
{
    setUsingNativeTitleBar(true);
    setResizable(true, true);
    setResizeLimits(900, 600, 10000, 10000);

    // Main content component
    contentComponent_ = std::make_unique<juce::Component>();
    contentComponent_->setSize(1200, 800);

    // IRA Panel (left sidebar)
    iraPanel_   = std::make_unique<IRAPanel>(orchestrator_);
    // Mixer Panel (bottom)
    mixerPanel_ = std::make_unique<MixerPanel>();
    // Piano Roll (centre)
    pianoRoll_  = std::make_unique<PianoRollWindow>();

    contentComponent_->addAndMakeVisible(iraPanel_.get());
    contentComponent_->addAndMakeVisible(mixerPanel_.get());
    contentComponent_->addAndMakeVisible(pianoRoll_.get());

    setContentOwned(contentComponent_.release(), true);

    setupMenuBar();
    setupKeyboardShortcuts();
    setupTransportCallbacks();

    centreWithSize(1200, 800);
    setVisible(true);
}

MainWindow::~MainWindow()
{
    juce::MenuBarModel::setMacMainMenu(nullptr);
}

void MainWindow::closeButtonPressed()
{
    audioEngine_.shutdown();
    juce::JUCEApplicationBase::getInstance()->systemRequestedQuit();
}

juce::StringArray MainWindow::getMenuBarNames()
{
    return {"File", "Edit", "View", "Transport", "Help"};
}

juce::PopupMenu MainWindow::getMenuForIndex(int idx, const juce::String& /*name*/)
{
    juce::PopupMenu menu;
    switch (idx) {
        case 0: // File
            menu.addItem(FileNew,      "New Project",       true, false, juce::KeyPress('n', juce::ModifierKeys::commandModifier, 0));
            menu.addItem(FileOpen,     "Open Project...",   true, false, juce::KeyPress('o', juce::ModifierKeys::commandModifier, 0));
            menu.addSeparator();
            menu.addItem(FileSave,     "Save",              true, false, juce::KeyPress('s', juce::ModifierKeys::commandModifier, 0));
            menu.addItem(FileSaveAs,   "Save As...");
            menu.addSeparator();
            menu.addItem(FileExportWAV,"Export WAV...");
            break;
        case 1: // Edit
            menu.addItem(EditUndo, "Undo", true, false, juce::KeyPress('z', juce::ModifierKeys::commandModifier, 0));
            menu.addItem(EditRedo, "Redo", true, false, juce::KeyPress('z', juce::ModifierKeys::commandModifier | juce::ModifierKeys::shiftModifier, 0));
            break;
        case 2: // View
            menu.addItem(ViewPianoRoll, "Piano Roll",  true, false, juce::KeyPress(juce::KeyPress::F2Key));
            menu.addItem(ViewMixer,     "Mixer",        true, false, juce::KeyPress('m', juce::ModifierKeys::commandModifier, 0));
            menu.addItem(ViewIRAPanel,  "IRA Assistant",true, false, juce::KeyPress(juce::KeyPress::F1Key));
            break;
        case 3: // Transport
            menu.addItem(TransportPlay, "Play / Pause", true, false, juce::KeyPress(juce::KeyPress::spaceKey));
            menu.addItem(TransportStop, "Stop",         true, false, juce::KeyPress(juce::KeyPress::escapeKey));
            menu.addItem(TransportLoop, "Toggle Loop",  true, false, juce::KeyPress('l', juce::ModifierKeys::commandModifier, 0));
            break;
        case 4: // Help
            menu.addItem(HelpAbout, "About ARIA");
            break;
    }
    return menu;
}

void MainWindow::menuItemSelected(int id, int /*topLevelMenuIndex*/)
{
    switch (id) {
        case TransportPlay:
            if (audioEngine_.isPlaying()) audioEngine_.pause();
            else                          audioEngine_.play();
            break;
        case TransportStop:
            audioEngine_.stop();
            break;
        case TransportLoop: {
            auto doc = audioEngine_.currentDoc();
            bool newState = !doc->loopRegion().enabled;
            audioEngine_.setLoopRegion(newState,
                doc->loopRegion().startBar,
                doc->loopRegion().endBar);
            break;
        }
        case HelpAbout:
            juce::AlertWindow::showMessageBoxAsync(
                juce::MessageBoxIconType::InfoIcon,
                "ARIA",
                "ARIA — AI-Assisted DAW\nVersion 0.1.0\n\nBuilt on JUCE + Tracktion Engine + llama.cpp");
            break;
        default:
            break;
    }
}

void MainWindow::onNewDocumentGenerated(std::shared_ptr<SongDocument> doc)
{
    audioEngine_.atomicSwapDoc(doc);
    // TODO: refresh arrangement view, piano roll, mixer from new doc
}

void MainWindow::onPlaybackTick()
{
    double beats = audioEngine_.currentPositionBeats();
    if (pianoRoll_)
        pianoRoll_->setPlayheadBeat(beats);
}

void MainWindow::setupMenuBar()
{
#if JUCE_MAC
    juce::MenuBarModel::setMacMainMenu(this);
#else
    menuBar_ = std::make_unique<juce::MenuBarComponent>(this);
    if (getContentComponent())
        getContentComponent()->addAndMakeVisible(menuBar_.get());
#endif
}

void MainWindow::setupKeyboardShortcuts()
{
    // Keyboard shortcuts are handled via MenuBarModel on Desktop.
    // Additional shortcuts can be registered here if needed.
}

void MainWindow::setupTransportCallbacks()
{
    // Timer for playback position updates (~50ms)
    class PlaybackTimer : public juce::Timer {
    public:
        PlaybackTimer(MainWindow& w) : owner_(w) {}
        void timerCallback() override { owner_.onPlaybackTick(); }
        MainWindow& owner_;
    };
    playbackTimer_ = std::make_unique<PlaybackTimer>(*this);
    playbackTimer_->startTimer(50);
}

} // namespace aria
