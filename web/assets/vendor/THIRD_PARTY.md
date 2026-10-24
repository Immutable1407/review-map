# Bundled runtime notices

- MapLibre GL JS 4.7.1 JS/CSS and the Positron style provide the map renderer and basemap styling. See ../licenses/MapLibre.LICENSE.txt.
- Instrument Serif, Newsreader, Inter and IBM Plex Mono are bundled with their SIL OFL notices under ../licenses/.
- gcoord 1.0.7 provides coordinate conversion; its MIT notice is gcoord.LICENSE.
- OpenFreeMap, OpenMapTiles and OpenStreetMap attribution remains visible on the map.

The single-file builder embeds these runtime/font notices. AMap uses the original GCJ-02 coordinates for navigation; MapLibre receives a converted WGS84 display copy.

The optional yichen-content-archive acquisition executors are NOT bundled in this directory. Their upstream attribution, inspected revision and separate license are documented in the root ATTRIBUTION.md.
