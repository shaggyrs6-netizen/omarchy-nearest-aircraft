import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "UiSafe.js" as Safe

BarWidget {
    id: root
    moduleName: "shaggyrs6.nearest-aircraft"
    property var anchorItem: button
    readonly property var svc: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
    readonly property bool fresh: svc && svc.fresh
    readonly property var aircraft: fresh ? svc.aircraft : null
    readonly property color foreground: bar ? bar.barForeground : Commons.Color.foreground
    Translations { id:strings; directory:Qt.resolvedUrl("i18n") }
    Binding { target:root.svc; property:"settings"; value:root.settings; when:root.svc !== null }

    readonly property string stateKey: !svc ? "loading" : svc.data.state === "ok" && !fresh ? "stale" : String(svc.data.state || "loading")
    readonly property string statusText: strings.t("bar." + stateKey, strings.t("bar.error"))
    readonly property string idText: aircraft ? Safe.plain(aircraft.displayId,12) : ""
    readonly property string altitudeText: aircraft && Safe.number(aircraft.altitudeFt) ? I18n.formatNumber(Math.round(aircraft.altitudeFt),0) + " ft" : "? ft"
    readonly property string distanceText: aircraft ? I18n.formatNumber(aircraft.distanceMi,1) + " mi" : ""
    implicitWidth: vertical ? barSize : Style.space(250)
    implicitHeight: vertical ? Style.space(250) : barSize

    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: ""
        labelVisible: false
        hasVisualContent: true
        pressable: true
        tooltipText: Safe.plain(root.fresh ? strings.t("tooltip.aircraft").arg(root.idText).arg(root.altitudeText).arg(root.distanceText) : root.statusText)
        onPressed: function(code) { if(code !== Qt.LeftButton) return; if(root.bar) root.bar.hideTooltip(root); root.toggle() }
        Item {
            anchors.centerIn: parent
            width: root.vertical ? parent.height : parent.width
            height: root.vertical ? parent.width : parent.height
            rotation: root.vertical ? 270 : 0
            scale: button.pressScale
            LayoutMirroring.enabled: I18n.rightToLeft
            LayoutMirroring.childrenInherit: true
            Row {
                id: readout
                visible: root.fresh
                anchors.centerIn: parent
                spacing: Style.space(5)
                PlainText {
                    id: plane
                    text:"✈"
                    anchors.verticalCenter:parent.verticalCenter
                    color:Commons.Color.accent
                    renderType:Text.NativeRendering
                }
                PlainText {
                    // Natural widths keep short flight IDs close to the numbers.
                    // Only long identifiers yield space when the readout is full.
                    width:Math.max(Style.space(28), Math.min(implicitWidth,
                        (root.vertical ? root.height : root.width) - Style.space(18)
                        - plane.implicitWidth - altitude.implicitWidth - distance.implicitWidth
                        - dividerOne.implicitWidth - dividerTwo.implicitWidth - readout.spacing * 5))
                    text:root.idText
                    wrapMode:Text.NoWrap
                    elide:Text.ElideRight
                    anchors.verticalCenter:parent.verticalCenter
                    color:root.foreground
                    font.weight:Font.DemiBold
                    renderType:Text.NativeRendering
                }
                PlainText { id:dividerOne; text:"·"; anchors.verticalCenter:parent.verticalCenter; color:root.foreground; opacity:.38 }
                PlainText { id:altitude; text:root.altitudeText; wrapMode:Text.NoWrap; anchors.verticalCenter:parent.verticalCenter; color:root.foreground; opacity:.86; renderType:Text.NativeRendering }
                PlainText { id:dividerTwo; text:"·"; anchors.verticalCenter:parent.verticalCenter; color:root.foreground; opacity:.38 }
                PlainText { id:distance; text:root.distanceText; wrapMode:Text.NoWrap; anchors.verticalCenter:parent.verticalCenter; color:root.foreground; opacity:.86; renderType:Text.NativeRendering }
            }
            PlainText { visible:!root.fresh; anchors.centerIn:parent; text:root.statusText; color:root.foreground; wrapMode:Text.NoWrap; font.pixelSize:Style.font.bodySmall }
        }
    }
    readonly property bool opened: panel.opened
    readonly property bool popoutSwitchClosing: false
    function setRange(value) {
        if (!Safe.number(value) || value !== Math.floor(value) || value<1 || value>100 || !root.bar || !root.bar.shell) return false
        if (root.settings && root.settings.rangeMiles === value) return true
        var next = Object.assign({}, root.settings, {rangeMiles:value})
        return root.bar.shell.updateEntryInline(root.moduleName, next) === true
    }
    function open() { panel.controller.show() }
    function close() { panel.controller.hide() }
    function toggle() { opened ? close() : open() }
    function closeForPopoutSwitch() { close() }
    NearestPanel { id:panel; widget:root }
}
