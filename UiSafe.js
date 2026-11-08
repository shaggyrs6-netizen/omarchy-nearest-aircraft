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
    return false
}

function rangeMiles(value) { return number(value) && Math.floor(value) === value && value >= 1 && value <= 100 ? value : 70 }
