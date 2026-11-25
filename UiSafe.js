.pragma library

// Shared shell tooltips may use AutoText. Remove markup delimiters even when
// the backend already validated the value; no network text becomes rich text.
function plain(value, limit) {
    if (typeof value !== "string" && typeof value !== "number") return ""
    return String(value).replace(/[<>&\x00-\x1f\x7f]/g, "").slice(0, limit || 256)
}
function number(value) { return typeof value === "number" && isFinite(value) }
function current(data, now) {
    var a = data ? data.nearest : null
    return !!(data && data.state === "ok" && a && number(a.positionTime) && number(data.generatedAt)
        && now - a.positionTime <= 20 && a.positionTime - now <= 5 && now - data.generatedAt <= 30)
}
function validLink(url, provider) {
    if (typeof url !== "string") return false
    if (provider === "adsbx") return /^https:\/\/globe\.adsbexchange\.com\/(\?icao=[0-9a-f]{6})?$/.test(url)
    if (provider === "fr24") return url === "https://www.flightradar24.com/"
        || /^https:\/\/www\.flightradar24\.com\/data\/(aircraft|flights)\/[a-z0-9-]{1,24}$/.test(url)
    if (provider === "radarbox") return /^https:\/\/www\.airnavradar\.com\/data\/registration(\/[A-Z0-9][A-Z0-9-]{0,23})?$/.test(url)
    if (provider === "flightaware") return /^https:\/\/www\.flightaware\.com\/live\/(flight\/[A-Z0-9][A-Z0-9-]{0,23})?$/.test(url)
    return false
}

function rangeMiles(value) { return number(value) && Math.floor(value) === value && value >= 1 && value <= 100 ? value : 70 }

function parseWatchTails(value) {
    if (typeof value !== "string" || value.length > 511) return null
    var tails = value.toUpperCase().split(/[\s,]+/).filter(function(tail) { return tail !== "" })
    if (tails.some(function(tail) { return !/^[A-Z0-9][A-Z0-9-]{0,23}$/.test(tail) })) return null
    var normalized = Array.from(new Set(tails)).join(",")
    return normalized.length <= 511 ? normalized : null
}

function tracker(value) {
    return ["fr24", "radarbox", "flightaware"].includes(value) ? value : "adsbx"
}

function trackerUrl(aircraft, provider) {
    if (provider === "adsbx") return aircraft.adsbxUrl
    if (provider === "fr24") return aircraft.fr24Url
    if (provider === "radarbox")
        return "https://www.airnavradar.com/data/registration" + (aircraft.tail ? "/" + aircraft.tail : "")
    if (provider === "flightaware") {
        var ident = aircraft.tail || aircraft.callsign
        return "https://www.flightaware.com/live/" + (ident ? "flight/" + ident : "")
    }
    return ""
}

function squawkCodes(value) {
    var supported = ["7500", "7600", "7700"]
    if (typeof value !== "string") return supported
    var selected = value.split(",")
    return supported.filter(function(code) { return selected.includes(code) })
}

var atcDirectories = {
    kbna: ["nashville", "tower", "approachEast", "approachWest"],
    katl: ["atlanta", "atlantaTower", "atlantaTowerNorth", "atlantaFinalNorth", "atlantaApproach", "atlantaDeparture"],
    zme: ["memphis", "memphisSmyrna", "memphisClarksville"]
}

function liveAtcDirectory(hint, facility) {
    if (typeof facility === "string") {
        if (hint === "center" && /^(Z[A-Z]{2}|TJZS)$/.test(facility))
            return facility.toLowerCase()
        if (["airport", "airportTower", "airportApproach", "airportDeparture"].includes(hint)
                && /^[A-Z0-9]{3,4}$/.test(facility))
            return facility.toLowerCase()
    }
    return Object.keys(atcDirectories).find(code => atcDirectories[code].includes(hint)) || ""
}

function atcHint(value, facility) { return liveAtcDirectory(value, facility) ? value : "" }

function liveAtcUrl(hint, facility) {
    var directory = liveAtcDirectory(hint, facility)
    return directory ? "https://www.liveatc.net/search/?icao=" + directory : ""
}

function liveAtcDirectoryChecked(directory) {
    return ["kbna", "katl", "kmia", "zma", "zme", "ztl"].includes(directory)
}
