import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import "Aircraft" as Aircraft
ShellRoot {
 Aircraft.Service {
 id:svc
 settings:({demoMode:true,rangeMiles:70})
 property string visitedTracker: ""
 function visit(provider) { visitedTracker = provider; return true }
 }
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
 function capture(item, variable) {
     var path = Quickshell.env(variable)
     if (!path) return
     var saved = false
     wait(150)
     verify(item.grabToImage(function(image) { saved = image.saveToFile(path) }))
     tryVerify(function() { return saved }, 3000)
 }
 function test_aircraftMouseButtons() {
 try {
 tryVerify(function(){return svc.fresh},5000)
 if(Quickshell.env("NEAREST_TEST_BAR_IMAGE")) {
 var barCaptured=false
 verify(widget.grabToImage(function(image){image.saveToFile(Quickshell.env("NEAREST_TEST_BAR_IMAGE"));barCaptured=true}))
 tryVerify(function(){return barCaptured},3000)
 }
 mouseClick(widget,widget.width/2,widget.height/2,Qt.LeftButton)
 compare(svc.visitedTracker,"adsbx")
 verify(!widget.opened)
 verify(findChild(widget,"watchTails") === null)
 mouseClick(widget,widget.width/2,widget.height/2,Qt.RightButton)
 tryCompare(widget,"opened",true,3000)
 var fr=findChild(widget,"openFr24");verify(fr!==null);verify(fr.visible);verify(fr.enabled)
 var ad=findChild(widget,"openDefaultTracker");verify(ad!==null);verify(ad.visible);verify(ad.enabled)
 var radio=findChild(widget,"openLiveAtc");verify(radio!==null);verify(radio.visible);verify(radio.enabled)
 var card=findChild(widget,"aircraftCard");verify(card!==null)
 var atc=findChild(widget,"atcFrequency");verify(atc!==null);verify(atc.visible)
 verify(atc.text.includes("Smyrna High"))
 verify(atc.text.includes("118.875 MHz"))
 var coverage=findChild(widget,"liveAtcCoverage");verify(coverage!==null);verify(coverage.visible)
 compare(coverage.text,"No matching LiveATC feed listed")
 verify(radio.text.includes("Browse Memphis Center feeds"))
 var demoData = svc.data
 svc.data = Object.assign({}, demoData, {nearest:Object.assign({}, demoData.nearest, {atcHint:"memphisClarksville"})})
 verify(atc.text.includes("124.125 MHz"))
 verify(coverage.visible)
 svc.data = Object.assign({}, demoData, {nearest:Object.assign({}, demoData.nearest, {atcHint:"memphis"})})
 verify(atc.text.includes("Sector frequency unknown"))
 verify(!coverage.visible)
 svc.data = Object.assign({}, demoData, {nearest:Object.assign({}, demoData.nearest, {atcHint:"approachEast", altitudeFt:6000})})
 verify(atc.text.includes("118.400 MHz"))
 verify(!coverage.visible)
 verify(radio.text.includes("Listen on LiveATC"))
 capture(card, "NEAREST_TEST_NASHVILLE_IMAGE")
 svc.data = Object.assign({}, demoData, {nearest:Object.assign({}, demoData.nearest, {atcHint:"nashville"})})
 verify(atc.text.includes("Nashville (KBNA)"))
 svc.data = Object.assign({}, demoData, {nearest:Object.assign({}, demoData.nearest, {atcHint:""})})
 verify(!atc.visible && !radio.visible)
 svc.data = demoData
 capture(card, "NEAREST_TEST_IMAGE")
 mouseClick(widget,widget.width/2,widget.height/2,Qt.MiddleButton)
 tryCompare(widget,"settingsMode",true)
 verify(widget.opened)
 verify(!radio.visible)
 verify(!coverage.visible)
 var watchRange=findChild(widget,"watchRange")
 var squawkRange=findChild(widget,"squawkRange")
 compare(watchRange.value,"local")
 compare(squawkRange.value,"local")
 var distantData = Object.assign({}, svc.data, {nearest:Object.assign({}, svc.aircraft, {distanceMi:400, watched:true, displayId:"N123AB", idKind:"tail", altitudeFt:8000, atcHint:""})})
 watchRange.changed("any")
 compare(svc.watchAnyRange,true)
 compare(svc.squawkAnyRange,false)
 svc.data=distantData
 verify(svc.fresh)
 capture(widget, "NEAREST_TEST_WATCH_IMAGE")
 capture(card, "NEAREST_TEST_ALERT_SETTINGS_IMAGE")
 svc.data=Object.assign({}, distantData, {nearest:Object.assign({}, distantData.nearest, {watched:false, emergencySquawk:"7700"})})
 verify(!svc.fresh)
 var distantSquawk=svc.data
 watchRange.changed("local")
 squawkRange.changed("any")
 compare(svc.watchAnyRange,false)
 compare(svc.squawkAnyRange,true)
 svc.data=distantSquawk
 verify(svc.fresh)
 capture(widget, "NEAREST_TEST_SQUAWK_IMAGE")
 svc.data=distantData
 verify(!svc.fresh)
 squawkRange.changed("local")
 var picker=findChild(widget,"defaultTracker")
 verify(picker.visible)
 compare(picker.options.length,4)
 var toggle=findChild(widget,"squawkEnabled")
 verify(toggle.visible && toggle.checked)
 compare(svc.activeSquawkCodes,"7500,7600,7700")
 toggle.clicked()
 compare(svc.activeSquawkCodes,"")
 compare(svc.squawkCodes.join(","),"7500,7600,7700")
 toggle.clicked()
 compare(svc.activeSquawkCodes,"7500,7600,7700")
 var code=findChild(widget,"squawkOptions").itemAt(1)
 verify(code.visible && code.checked)
 code.clicked()
 compare(svc.activeSquawkCodes,"7500,7700")
 code.clicked()
 compare(svc.activeSquawkCodes,"7500,7600,7700")
 compare(svc.defaultTracker,"adsbx")
 picker.changed("radarbox")
 compare(svc.defaultTracker,"radarbox")
 verify(card.changeTracking("n456zz, N123AB","flightaware"))
 tryCompare(svc,"watchTails","N456ZZ,N123AB")
 compare(svc.defaultTracker,"flightaware")
 verify(!card.changeTracking("N456ZZ/","radarbox"))
 compare(svc.defaultTracker,"flightaware")
 tryVerify(function(){return svc.fresh && svc.aircraft.watched === true},5000)
 var alert = Object.assign({}, svc.aircraft, {watched:true})
 svc.data = Object.assign({}, svc.data, {nearest:alert})
 compare(widget.alertLabel,"Watched aircraft")
 alert = Object.assign({}, alert, {emergencySquawk:"7700"})
 svc.data = Object.assign({}, svc.data, {nearest:alert})
 verify(widget.alertLabel.includes("7700"))
 var previousData = svc.data
 mouseClick(widget,widget.width/2,widget.height/2,Qt.LeftButton)
 compare(svc.visitedTracker,"flightaware")
 tryCompare(widget,"opened",false)
 tryVerify(function(){return findChild(widget,"watchTails") === null})
 svc.data = {state:"empty", configured:true, nearest:null}
 svc.visitedTracker = ""
 mouseClick(widget,widget.width/2,widget.height/2,Qt.LeftButton)
 tryCompare(widget,"opened",true)
 tryCompare(widget,"settingsMode",false)
 compare(svc.visitedTracker,"")
 svc.data = Object.assign({}, previousData, {nearest:alert})
 ad=findChild(widget,"openDefaultTracker")
 card=findChild(widget,"aircraftCard")
 verify(ad.visible)
 verify(ad.text.includes("FlightAware"))
 verify(card.changeRange(1));tryCompare(svc,"rangeMiles",1,3000)
 verify(!widget.setRange(0));verify(!widget.setRange(101))
 console.log("REGRESSION PASS: left-click opens saved tracker for fresh aircraft; right-click details and middle-click settings verified")
 widget.close()
 } catch (error) {
 console.error(error, error.stack)
 }
 Qt.callLater(Qt.quit)
 }
 }
 IpcHandler {target:"preview"; function quit():void {Qt.quit()} }
}
