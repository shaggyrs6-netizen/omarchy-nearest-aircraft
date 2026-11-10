import QtQuick
import Quickshell
import Quickshell.Io
import "UiSafe.js" as Safe

Item {
    id: root
    property var settings: null
    // Test harnesses can use a separate private directory. Normal settings do
    // not contain home coordinates or alter the helper's fixed HTTPS source.
    property string stateDirectory: ""
    readonly property string helper: decodeURIComponent(String(Qt.resolvedUrl("nearest.py")).replace(/^file:\/\/(localhost)?/, ""))
    readonly property int rangeMiles: Safe.rangeMiles(settings ? settings.rangeMiles : undefined)
    property bool intentionalRestart: false
    property bool ready: false
    Component.onCompleted: {
        root.ready = true
        if (root.settings !== null) root.restartReader()
    }
    onSettingsChanged: {
        if (root.ready && root.settings !== null && !reader.running && !restartTimer.running)
            root.restartReader()
    }
    readonly property bool demo: settings !== null && settings.demoMode === true
    readonly property var extraArguments: stateDirectory ? ["--state-dir", stateDirectory] : []
    property var data: ({state:"loading", configured:false, nearest:null})
    property double now: Date.now() / 1000
    readonly property bool fresh: Safe.current(data, now) && Safe.number(data.nearest.distanceMi) && data.nearest.distanceMi <= rangeMiles
    readonly property var aircraft: fresh ? data.nearest : null
    property int crashCount: 0
    property bool shuttingDown: false
    property var pendingControl: ({})
    property bool controlSucceeded: false
    property string lastAction: ""
    readonly property bool busy: controller.running
    signal controlFinished(bool success)

    function apply(line) {
        if (line.length > 16384) return
        try {
            var value = JSON.parse(line)
            if (value && value.schema === 1 && typeof value.state === "string") {
                if (value.state === "error" && root.data.configured === true)
                    value.configured = true
                root.data = value
            }
        } catch (e) { root.data = {state:"error", configured:root.data.configured === true, nearest:null} }
    }
    function issue(payload) {
        if (controller.running || root.demo) return false
        root.pendingControl = payload
        root.lastAction = payload.action
        root.controlSucceeded = false
        controller.running = true
        controlDeadline.restart()
        return true
    }
    function saveHome(latitude, longitude) {
        if (!Safe.number(latitude) || !Safe.number(longitude) || Math.abs(latitude)>90 || Math.abs(longitude)>180) return false
        return issue({action:"home", latitude:latitude, longitude:longitude})
    }
    function setEnabled(enabled) { return issue({action:enabled ? "resume" : "pause"}) }
    function visit(provider) {
        if (!root.fresh) return false
        var url = provider === "adsbx" ? root.aircraft.adsbxUrl : root.aircraft.fr24Url
        if (!Safe.validLink(url, provider)) return false
        return Qt.openUrlExternally(url)
    }
    function restartReader() {
        if (root.shuttingDown || !root.ready || root.settings === null) return
        root.data = {state:"loading", configured:root.data.configured === true, nearest:null}
        root.crashCount = 0
        if (reader.running) { root.intentionalRestart = true; reader.running = false }
        restartTimer.restart()
    }
    onDemoChanged: restartReader()
    onRangeMilesChanged: restartReader()
    Component.onDestruction: { root.shuttingDown = true; reader.running = false; controller.running = false }

    Timer { interval:1000; repeat:true; running:true; onTriggered:root.now = Date.now()/1000 }
    Timer { id:restartTimer; interval:1000; onTriggered:if (!root.shuttingDown && root.settings !== null && !reader.running && root.crashCount<3) reader.running=true }
    Timer { id:controlDeadline; interval:5000; onTriggered:if (controller.running) controller.running=false }
    Process {
        id: reader
        command: ["python3", "-B", root.helper, "worker", "--range-miles", String(root.rangeMiles)].concat(root.extraArguments).concat(root.demo ? ["--demo"] : [])
        running: false
        stdout: SplitParser { splitMarker:"\n"; onRead:function(line) { root.apply(line) } }
        onExited: function(code, status) {
            if (root.shuttingDown) return
            if (root.intentionalRestart) { root.intentionalRestart = false; return }
            root.crashCount++
            root.data = {state:"error", configured:root.data.configured === true, nearest:null}
            if (root.crashCount<3) restartTimer.restart()
        }
    }
    Process {
        id: controller
        command: ["python3", "-B", root.helper, "control"].concat(root.extraArguments)
        stdinEnabled: true
        onStarted: {
            controller.write(JSON.stringify(root.pendingControl) + "\n")
            root.pendingControl = ({})
        }
        stdout: StdioCollector {
            onStreamFinished: {
                try { root.controlSucceeded = JSON.parse(text).ok === true } catch(e) { root.controlSucceeded = false }
            }
        }
        onExited: function(code, status) {
            controlDeadline.stop()
            var success = code === 0 && root.controlSucceeded
            if (success) {
                root.data = {state:root.lastAction === "pause" ? "paused" : "loading", configured:true, nearest:null}
                if (root.lastAction !== "pause" && !reader.running) root.restartReader()
            }
            root.controlFinished(success)
        }
    }
    IpcHandler {
        target: "shaggyrs6.nearest-aircraft.service"
        function openTracker(provider: string): bool { return root.visit(provider) }
        function status(): string {
            return JSON.stringify({state:root.data.state, configured:root.data.configured === true,
                fresh:root.fresh, demo:root.demo, rangeMiles:root.rangeMiles, workerRunning:reader.running,
                displayId:root.aircraft ? Safe.plain(root.aircraft.displayId,24) : "",
                altitudeFt:root.aircraft ? root.aircraft.altitudeFt : null})
        }
    }
}
