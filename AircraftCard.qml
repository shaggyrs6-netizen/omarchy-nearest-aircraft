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
    property bool panelOpen: true
    property bool editHome: false
    property bool inputError: false
    property var changeRange: null
    property string rangeError: ""
    readonly property string savedRangeText: svc ? String(svc.rangeMiles) : ""
    onSavedRangeTextChanged: if (rangeInput && !rangeInput.activeFocus) rangeInput.text = savedRangeText
    readonly property bool inputFocused: latitude.activeFocus || longitude.activeFocus || rangeInput.activeFocus
    readonly property bool configured: svc && svc.data.configured === true
    readonly property bool fresh: svc && svc.fresh
    readonly property var aircraft: fresh ? svc.aircraft : null
    readonly property bool demo: svc && svc.demo
    readonly property bool showHome: !demo && (editHome || !configured)
    spacing: Style.space(10)
    LayoutMirroring.enabled: I18n.rightToLeft
    LayoutMirroring.childrenInherit: true
    Translations { id:strings; directory:Qt.resolvedUrl("i18n") }
    onPanelOpenChanged: {
        rangeError = ""
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
    PlainText { Layout.fillWidth:true; text:root.demo ? strings.t("title.demo") : strings.t("title"); font.pixelSize:Style.font.subtitle; font.bold:true }
    PlainText {
        Layout.fillWidth:true
        visible: !root.fresh
        text: strings.t("state." + (!svc ? "loading" : svc.data.state === "ok" ? "stale" : svc.data.state),strings.t("state.error"))
    }
    ColumnLayout {
        visible: root.fresh
        Layout.fillWidth:true
        spacing: Style.space(8)
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
    RowLayout {
        Layout.fillWidth:true
        Ui.Button { objectName:"openFr24"; Layout.fillWidth:true; text:strings.t("links.fr24"); bordered:true; focusable:true; enabled:root.fresh; onClicked:if(svc) svc.visit("fr24") }
        Ui.Button { objectName:"openAdsbx"; Layout.fillWidth:true; text:strings.t("links.adsbx"); bordered:true; focusable:true; enabled:root.fresh; onClicked:if(svc) svc.visit("adsbx") }
    }
    PlainText { Layout.fillWidth:true; text:strings.t("links.note"); font.pixelSize:Style.font.bodySmall; opacity:.72 }
    RowLayout {
        Layout.fillWidth:true
        PlainText { text:strings.t("range.label") }
        Ui.TextField { id:rangeInput; objectName:"rangeInput"; Layout.fillWidth:true; text:root.savedRangeText; onTextEdited:root.rangeError=""; maximumLength:3; selectByMouse:true }
        PlainText { text:"mi" }
        Ui.Button { objectName:"applyRange"; text:strings.t("range.apply"); bordered:true; focusable:true; enabled:!root.demo && root.changeRange !== null; onClicked:root.applyRange() }
    }
    PlainText { Layout.fillWidth:true; text:root.rangeError ? strings.t(root.rangeError) : strings.t("range.hint"); font.pixelSize:Style.font.bodySmall; opacity:.72 }
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
