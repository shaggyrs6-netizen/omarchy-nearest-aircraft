import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui
import "UiSafe.js" as Safe

ColumnLayout {
    id: root
    objectName: "aircraftCard"
    property var svc: null
    property bool settingsMode: false
    property var changeSquawks: null
    property var changeAlertRange: null
    property bool alertRangeError: false
    property bool squawkError: false
    signal settingsRequested()
    function saveSquawks(enabled, codes) {
        squawkError = !changeSquawks || !changeSquawks(enabled, codes.join(","))
    }
    property bool panelOpen: true
    property bool editHome: false
    property bool inputError: false
    property var changeRange: null
    property var changeTracking: null
    property string alertLabel: ""
    property color alertColor: Commons.Color.accent
    property bool trackingError: false
    readonly property string savedTails: svc ? svc.watchTails : ""
    onSavedTailsChanged: if (tailInput && !tailInput.activeFocus) tailInput.text = savedTails
    property string rangeError: ""
    readonly property string savedRangeText: svc ? String(svc.rangeMiles) : ""
    onSavedRangeTextChanged: if (rangeInput && !rangeInput.activeFocus) rangeInput.text = savedRangeText
    readonly property bool inputFocused: latitude.activeFocus || longitude.activeFocus || rangeInput.activeFocus || tailInput.activeFocus || trackerPicker.popupOpen || watchRangePicker.popupOpen || squawkRangePicker.popupOpen
    readonly property bool configured: svc && svc.data.configured === true
    readonly property bool fresh: svc && svc.fresh
    readonly property var aircraft: fresh ? svc.aircraft : null
    readonly property string atcCode: root.aircraft ? Safe.plain(root.aircraft.atcCode, 4) : ""
    readonly property string atcHint: root.aircraft ? Safe.atcHint(root.aircraft.atcHint, root.aircraft.atcCode) : ""
    readonly property string liveAtcDirectory: Safe.liveAtcDirectory(root.atcHint, root.aircraft ? root.aircraft.atcCode : "")
    readonly property bool liveAtcCoverageUnverified: liveAtcDirectory !== "" && !Safe.liveAtcDirectoryChecked(liveAtcDirectory)
    readonly property bool liveAtcFeedUnlisted: atcHint === "memphisSmyrna" || atcHint === "memphisClarksville"
    readonly property bool demo: svc && svc.demo
    readonly property bool showHome: !demo && (editHome || !configured)
    spacing: Style.space(10)
    LayoutMirroring.enabled: I18n.rightToLeft
    LayoutMirroring.childrenInherit: true
    Translations { id:strings; directory:Qt.resolvedUrl("i18n") }
    onPanelOpenChanged: {
        rangeError = ""
        trackingError = false
        squawkError = false
        alertRangeError = false
        tailInput.text = savedTails
        rangeInput.text = savedRangeText
        if (!panelOpen) {
            latitude.text = ""
            longitude.text = ""
            editHome = false
            inputError = false
        }
    }
    function applyRange() {
        var value = Number(rangeInput.text)
        if (!Safe.number(value) || Math.floor(value) !== value || value < 1 || value > 100)
            rangeError = "range.error"
        else
            rangeError = changeRange(value) ? "" : "range.saveError"
    }
    Connections {
        target: root.svc
        function onControlFinished(success) {
            if(success) { latitude.text=""; longitude.text=""; root.editHome=false }
            root.inputError=!success
        }
    }
    PlainText { Layout.fillWidth:true; text:root.settingsMode ? strings.t("settings.title") : root.demo ? strings.t("title.demo") : strings.t("title"); font.pixelSize:Style.font.subtitle; font.bold:true }
    PlainText {
        Layout.fillWidth:true
        visible: !root.settingsMode && !root.fresh
        text: strings.t("state." + (!svc ? "loading" : svc.data.state === "ok" ? "stale" : svc.data.state),strings.t("state.error"))
    }
    ColumnLayout {
        visible: !root.settingsMode && root.fresh
        Layout.fillWidth:true
        spacing: Style.space(8)
        PlainText { Layout.fillWidth:true; visible:root.alertLabel !== ""; text:root.alertLabel; color:root.alertColor; font.bold:true }
        PlainText { Layout.fillWidth:true; text:aircraft ? Safe.plain(aircraft.displayId,24) : ""; font.pixelSize:Style.font.title; font.bold:true; color:Commons.Color.accent }
        PlainText {
            Layout.fillWidth:true
            text: !aircraft ? "" : strings.t("details.position")
                .arg(I18n.formatNumber(aircraft.distanceMi,1)).arg(Safe.plain(aircraft.direction,3))
                .arg(Safe.number(aircraft.altitudeFt) ? I18n.formatNumber(Math.round(aircraft.altitudeFt),0) : "?")
                .arg(strings.t(aircraft.altitudeBasis === "geometric" ? "alt.geometric" : "alt.barometric"))
        }
        PlainText { Layout.fillWidth:true; text:aircraft ? strings.t("details.identity").arg(Safe.plain(aircraft.tail,24)||"?").arg(Safe.plain(aircraft.callsign,16)||"?").arg(Safe.plain(aircraft.aircraftType,12)||"?") : "" }
        PlainText { Layout.fillWidth:true; text:aircraft ? strings.t("details.age").arg(I18n.formatNumber(Math.max(0,Math.floor(svc.now-aircraft.positionTime)),0)) : ""; opacity:.72 }
        PlainText { Layout.fillWidth:true; text:aircraft ? strings.t("identity."+aircraft.idKind) : ""; opacity:.72; font.pixelSize:Style.font.bodySmall }
        PlainText { Layout.fillWidth:true; visible:aircraft && aircraft.military; text:strings.t("details.military"); font.pixelSize:Style.font.bodySmall }
    }
    Ui.Button {
        visible:!root.settingsMode
        objectName:"openDefaultTracker"
        Layout.fillWidth:true
        text:strings.t("links.open").arg(trackerPicker.currentLabel())
        bordered:true
        focusable:true
        enabled:root.fresh
        onClicked:if (svc) svc.visit(svc.defaultTracker)
    }
    RowLayout {
        visible:!root.settingsMode
        Layout.fillWidth:true
        Ui.Button { objectName:"openFr24"; visible:trackerPicker.value !== "fr24"; Layout.fillWidth:true; text:strings.t("links.fr24"); bordered:true; focusable:true; enabled:root.fresh; onClicked:if(svc) svc.visit("fr24") }
        Ui.Button { objectName:"openAdsbx"; visible:trackerPicker.value !== "adsbx"; Layout.fillWidth:true; text:strings.t("links.adsbx"); bordered:true; focusable:true; enabled:root.fresh; onClicked:if(svc) svc.visit("adsbx") }
    }
    PlainText {
        visible:!root.settingsMode && root.atcHint !== ""
        Layout.fillWidth:true
        objectName:"atcFrequency"
        text: {
            if (!root.atcHint) return ""
            var label = strings.t("atc." + root.atcHint)
            if (!label.includes("%1")) return label
            var facility = Safe.plain(root.aircraft.atcName, 64)
            return label.arg(facility ? facility + " (" + root.atcCode + ")" : root.atcCode)
        }
        font.pixelSize:Style.font.bodySmall
        opacity:.72
    }
    PlainText {
        objectName:"liveAtcCoverage"
        visible:!root.settingsMode && (root.liveAtcFeedUnlisted || root.liveAtcCoverageUnverified)
        Layout.fillWidth:true
        text:strings.t(root.liveAtcFeedUnlisted ? "atc.liveatcUnlisted" : "atc.liveatcUnverified")
        font.pixelSize:Style.font.bodySmall
        opacity:.72
    }
    Ui.Button {
        objectName:"openLiveAtc"
        visible:!root.settingsMode && root.atcHint !== ""
        Layout.fillWidth:true
        text:root.liveAtcCoverageUnverified ? strings.t("links.liveatcCheck")
            : strings.t("links.liveatc." + root.liveAtcDirectory, strings.t("links.liveatc"))
        bordered:true
        focusable:true
        onClicked:if (root.aircraft) Qt.openUrlExternally(Safe.liveAtcUrl(root.atcHint, root.aircraft.atcCode))
    }
    PlainText {
        visible:!root.settingsMode && svc && svc.data.wideAlertUnavailable === true
        Layout.fillWidth:true
        text:strings.t("alerts.wideUnavailable")
        font.pixelSize:Style.font.bodySmall
    }
    Ui.Button {
        visible:!root.settingsMode
        Layout.fillWidth:true
        text:strings.t("settings.title")
        focusable:true
        onClicked:root.settingsRequested()
    }
    ColumnLayout {
        visible:root.settingsMode
        Layout.fillWidth:true
        spacing:Style.space(8)
        Ui.Dropdown {
            id:trackerPicker
            objectName:"defaultTracker"
            Layout.fillWidth:true
            label:strings.t("links.default")
            value:svc ? svc.defaultTracker : "adsbx"
            options:[
                {value:"adsbx", label:"ADS-B Exchange"},
                {value:"fr24", label:"Flightradar24"},
                {value:"radarbox", label:"AirNav Radar (RadarBox)"},
                {value:"flightaware", label:"FlightAware"}
            ]
            enabled:root.changeTracking !== null && svc !== null
            onChanged:function(provider) { root.trackingError = !root.changeTracking(svc.watchTails, provider) }
        }
        Ui.Toggle {
            objectName:"squawkEnabled"
            Layout.fillWidth:true
            label:strings.t("alerts.enabled")
            checked:root.svc && root.svc.squawkEnabled
            enabled:root.svc !== null && root.changeSquawks !== null
            onClicked:root.saveSquawks(!checked, root.svc.squawkCodes)
        }
        Repeater {
            objectName:"squawkOptions"
            model:["7500", "7600", "7700"]
            delegate: Ui.Toggle {
                required property string modelData
                objectName:"squawk" + modelData
                Layout.fillWidth:true
                label:strings.t("alerts.code." + modelData)
                checked:root.svc && root.svc.squawkCodes.includes(modelData)
                enabled:root.svc && root.svc.squawkEnabled && root.changeSquawks !== null
                onClicked: {
                    var selected = root.svc.squawkCodes
                    root.saveSquawks(true, checked ? selected.filter(code => code !== modelData) : selected.concat(modelData))
                }
            }
        }
        Ui.Dropdown {
            id:squawkRangePicker
            objectName:"squawkRange"
            Layout.fillWidth:true
            label:strings.t("alerts.squawkRange")
            value:svc && svc.squawkAnyRange ? "any" : "local"
            options:[{value:"local", label:strings.t("alerts.selectedRange")}, {value:"any", label:strings.t("alerts.anyRange")}]
            enabled:svc !== null && svc.squawkEnabled && root.changeAlertRange !== null
            onChanged:function(value) { root.alertRangeError = !root.changeAlertRange("squawkAnyRange", value === "any") }
        }
        PlainText { Layout.fillWidth:true; visible:root.squawkError; text:strings.t("alerts.error") }
        RowLayout {
            Layout.fillWidth:true
            PlainText { text:strings.t("range.label") }
            Ui.TextField { id:rangeInput; objectName:"rangeInput"; Layout.fillWidth:true; text:root.savedRangeText; onTextEdited:root.rangeError=""; maximumLength:3; selectByMouse:true }
            PlainText { text:"mi" }
            Ui.Button { objectName:"applyRange"; text:strings.t("range.apply"); bordered:true; focusable:true; enabled:!root.demo && root.changeRange !== null; onClicked:root.applyRange() }
        }
        PlainText { Layout.fillWidth:true; text:root.rangeError ? strings.t(root.rangeError) : strings.t("range.hint"); font.pixelSize:Style.font.bodySmall; opacity:.72 }
        PlainText { text:strings.t("watch.label") }
        RowLayout {
            Layout.fillWidth:true
            Ui.TextField {
                id:tailInput
                objectName:"watchTails"
                Layout.fillWidth:true
                maximumLength:511
                placeholderText:strings.t("watch.hint")
                selectByMouse:true
            }
            Ui.Button {
                text:strings.t("range.apply")
                bordered:true
                focusable:true
                enabled:root.changeTracking !== null && svc !== null
                onClicked:root.trackingError = !root.changeTracking(tailInput.text, svc.defaultTracker)
            }
        }
        PlainText { Layout.fillWidth:true; visible:root.trackingError; text:strings.t("watch.error") }
        Ui.Dropdown {
            id:watchRangePicker
            objectName:"watchRange"
            Layout.fillWidth:true
            label:strings.t("alerts.watchRange")
            value:svc && svc.watchAnyRange ? "any" : "local"
            options:[{value:"local", label:strings.t("alerts.selectedRange")}, {value:"any", label:strings.t("alerts.anyRange")}]
            enabled:svc !== null && root.changeAlertRange !== null
            onChanged:function(value) { root.alertRangeError = !root.changeAlertRange("watchAnyRange", value === "any") }
        }
        PlainText { Layout.fillWidth:true; text:strings.t("alerts.watchPrivacy"); font.pixelSize:Style.font.bodySmall; opacity:.72 }
        PlainText { Layout.fillWidth:true; visible:root.alertRangeError; text:strings.t("alerts.rangeError") }
    }
    PlainText { Layout.fillWidth:true; text:strings.t("coverage"); font.pixelSize:Style.font.bodySmall; opacity:.72 }
    RowLayout {
        visible: root.configured && !root.demo && !root.showHome
        Layout.fillWidth:true
        Ui.Button { Layout.fillWidth:true; text:svc && svc.data.state === "paused" ? strings.t("resume") : svc && (svc.data.state === "blocked" || svc.data.state === "error") ? strings.t("retry") : strings.t("pause"); focusable:true; enabled:svc && !svc.busy; onClicked:svc.setEnabled(svc.data.state === "paused" || svc.data.state === "blocked" || svc.data.state === "error") }
        Ui.Button { Layout.fillWidth:true; text:strings.t("home.change"); focusable:true; onClicked:root.editHome=true }
    }
    ColumnLayout {
        visible: root.showHome
        Layout.fillWidth:true
        spacing:Style.space(8)
        PlainText { Layout.fillWidth:true; text:strings.t("home.title"); font.bold:true }
        PlainText { Layout.fillWidth:true; text:strings.t("home.instructions"); font.pixelSize:Style.font.bodySmall }
        Ui.TextField { id:latitude; Layout.fillWidth:true; placeholderText:strings.t("home.latitude"); selectByMouse:true; maximumLength:24 }
        Ui.TextField { id:longitude; Layout.fillWidth:true; placeholderText:strings.t("home.longitude"); selectByMouse:true; maximumLength:24 }
        PlainText { Layout.fillWidth:true; text:strings.t("home.privacy"); font.pixelSize:Style.font.bodySmall; opacity:.8 }
        PlainText { Layout.fillWidth:true; visible:root.inputError; text:strings.t("home.error"); color:Commons.Color.accent }
        Ui.Button {
            Layout.fillWidth:true
            text:strings.t("home.save")
            enabled:svc && !svc.busy
            focusable:true
            onClicked: {
                root.inputError=latitude.text.trim()==="" || longitude.text.trim()==="" || !svc.saveHome(Number(latitude.text),Number(longitude.text))
            }
        }
        Ui.Button { visible:root.configured; text:strings.t("cancel"); focusable:true; onClicked:{root.editHome=false;latitude.text="";longitude.text=""} }
    }
    RowLayout {
        Layout.fillWidth:true
        PlainText { Layout.fillWidth:true; text:strings.t("source"); font.pixelSize:Style.font.bodySmall; opacity:.72 }
        Ui.Button { text:"adsb.fi ↗"; focusable:true; fontSize:Style.font.bodySmall; onClicked:Qt.openUrlExternally("https://adsb.fi/") }
    }
}
