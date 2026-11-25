# Nearest Aircraft v0.2.1

## Nationwide U.S. LiveATC lookup

Right-click the bar widget for the LiveATC directory relevant to the displayed aircraft. Your saved location still sets your search radius. If a distant watched aircraft triggers an Any range alert, the popup uses that aircraft's location to choose the directory.

The lookup runs locally with FAA data for 4,721 public-use airports and 23 upper-airspace facilities. A low-altitude match can suggest an airport, tower, approach or departure. A high-altitude match can suggest a Center. The popup leaves the frequency unknown unless it has enough evidence for a specific estimate. It labels feed availability as unverified when the directory has not been checked.

The existing watchlist, squawk alerts, search radius and default tracker carry over when updating from the previous release.

## Screenshots

These captures use simulated aircraft. The Miami airport and Miami Center directory listings were checked.

| Case | Popup destination | Screenshot |
| --- | --- | --- |
| Miami arrival | Miami International approach (KMIA) | [Miami arrival](screenshots/miami-arrival.png) |
| South Florida overflight | Miami Center (ZMA) | [South Florida overflight](screenshots/south-florida-overflight.png) |
| Distant watched aircraft | Atlanta Final Approach (KATL) | [Distant watched aircraft](screenshots/distant-watched-aircraft.png) |

[FAA airport data](https://catalog.data.gov/dataset/aviation-facilities) · [FAA upper airspace boundaries](https://www.arcgis.com/home/item.html?id=67885972e4e940b2aa6d74024901c561)
