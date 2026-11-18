import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "shaggyrs6.nearest-aircraft"
    ipcTarget: "shaggyrs6.nearest-aircraft"
    required property var widget
    KeyboardPanel {
        id: popup
        anchorItem: root.widget.anchorItem
        owner: root.widget
        bar: root.widget.bar
        open: root.opened
        focusTarget: keys
        contentWidth: fittedContentWidth(Style.space(480))
        contentHeight: fittedContentHeight(card.implicitHeight,Style.space(680))
        PanelKeyCatcher {
            id: keys
            anchors.fill: parent
            blocked: card.inputFocused
            onCloseRequested: root.widget.close()
            Flickable {
                id: scroll
                anchors.fill:parent
                contentWidth:width
                contentHeight:card.implicitHeight
                clip:true
                boundsBehavior:Flickable.StopAtBounds
                Controls.ScrollBar.vertical: Controls.ScrollBar {}
                Connections {
                    target:root.widget
                    function onSettingsModeChanged() { scroll.contentY = 0 }
                    function onOpenedChanged() { if (root.widget.opened) scroll.contentY = 0 }
                }
                AircraftCard { id:card; settingsMode:root.widget.settingsMode; changeSquawks:root.widget.setSquawks; onSettingsRequested:root.widget.openSettings(); width:scroll.width; svc:root.widget.svc; panelOpen:root.opened; changeRange:root.widget.setRange; changeTracking:root.widget.setTracking; alertLabel:root.widget.alertLabel; alertColor:root.widget.alertColor }
            }
        }
    }
}
