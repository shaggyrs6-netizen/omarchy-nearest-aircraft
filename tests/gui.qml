import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import "Aircraft" as Aircraft
ShellRoot {
 Aircraft.Service { id:svc; settings:({demoMode:true,rangeMiles:70}) }
 QtObject { id:mockBar
 property var shell: QtObject {
 function serviceFor(name) {return svc}
 function updateEntryInline(name,settings) {widget.settings=settings;return true}
 }
 property bool indicatorItemsRevealed:true
 property bool foregroundAnimationEnabled:true
 property string position:"bottom"
 property bool vertical:false
 property int barSize:32
 property string fontFamily:Commons.Style.font.family
 property color barForeground:Commons.Color.foreground
 property color urgent:Commons.Color.urgent
 property var activePopout:null
 function requestPopout(owner) {activePopout=owner}
 function releasePopout(owner) {activePopout=null}
 function hideTooltip(owner) {}
 function showTooltip(owner,text) {}
 }
 FloatingWindow { id:win; visible:true; implicitWidth:560; implicitHeight:100; title:"Nearest Aircraft regression test"; color:Commons.Color.background
 Aircraft.BarWidget { id:widget; objectName:"widget"; x:10;y:30;bar:mockBar;settings:({demoMode:true,rangeMiles:70}) }
 }
 TestCase {
 name:"AircraftClickAndRange"; when:win.visible
 function test_clickOpensPopup() {
 tryVerify(function(){return svc.fresh},5000)
 if(Quickshell.env("NEAREST_TEST_BAR_IMAGE")) {
 var barCaptured=false
 verify(widget.grabToImage(function(image){image.saveToFile(Quickshell.env("NEAREST_TEST_BAR_IMAGE"));barCaptured=true}))
 tryVerify(function(){return barCaptured},3000)
 }
 mouseClick(widget,widget.width/2,widget.height/2,Qt.LeftButton)
 tryCompare(widget,"opened",true,3000)
 var fr=findChild(widget,"openFr24");verify(fr!==null);verify(fr.visible);verify(fr.enabled)
 var ad=findChild(widget,"openAdsbx");verify(ad!==null);verify(ad.visible);verify(ad.enabled)
 var card=findChild(widget,"aircraftCard");verify(card!==null)
 var captured=false
 if(Quickshell.env("NEAREST_TEST_IMAGE")) {
 wait(250)
 verify(card.grabToImage(function(image){image.saveToFile(Quickshell.env("NEAREST_TEST_IMAGE"));captured=true}))
 tryVerify(function(){return captured},3000)
 }
 verify(card.changeRange(1));tryCompare(svc,"rangeMiles",1,3000)
 verify(!widget.setRange(0));verify(!widget.setRange(101))
 console.log("REGRESSION PASS: real mouse click opened popup; both tracker buttons visible/enabled; range 1 accepted and invalid bounds rejected")
 widget.close()
 }
 }
 IpcHandler {target:"preview"; function quit():void {Qt.quit()} }
}
