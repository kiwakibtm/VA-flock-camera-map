import re
from pathlib import Path
import pandas as pd
import folium
import geopandas as gpd
from branca.element import Element
from folium.plugins import HeatMap 

CAMERAS_FILE = Path("Data/Raw/alpr.geojson")
COUNTIES_FILE = Path("Data/Raw/cb_2024_us_county_500k.shp")
LPR_FILE = Path("Data/Raw/VA_LPR_DATA.csv")
TRACTS_FILE = Path("Data/processed/tracts.geojson")
OUT_MAP = Path("output/alpr_heatmap.html")
TRAFFIC_FILE = Path("Data/Raw/VA_TRAFFIC.csv")

AREAS = {
    "710": ("Norfolk city", 1, "Norfolk (117)"),
    "093": ("Isle of Wight County", 1, "Isle of Wight CO (046)"),
    "650": ("Hampton city", 2, "Hampton (111)"),
    "036": ("Charles City County", 2, "Charles City CO (018)"),
    "760": ("Richmond city", 3, "Richmond City (120)"),
    "087": ("Henrico County", 3, "Henrico CO (043)"),
}

def load_counties() -> gpd.GeoDataFrame:
    c = gpd.read_file(COUNTIES_FILE)
    c = c[(c["STATEFP"] == "51") & (c["COUNTYFP"].isin(AREAS))].to_crs(4326)
    c["area"] = c["COUNTYFP"].map(lambda k: AREAS[k][0])
    c["pair"] = c["COUNTYFP"].map(lambda k: AREAS[k][1])
    return c[["COUNTYFP", "area", "pair", "geometry"]]
 
 
def load_cameras(counties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    cams = gpd.read_file(CAMERAS_FILE)
    cams = cams[cams.geometry.geom_type == "Point"].to_crs(4326)
    keep = [c for c in ["id", "operator", "surveillance:zone", "geometry"] if c in cams.columns]
    cams = cams[keep]
    return gpd.sjoin(cams, counties[["COUNTYFP", "area", "geometry"]], predicate="within").drop(
        columns="index_right"
    )
 
 
COORD_RE = re.compile(r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
 
 
def load_stops(path) -> pd.DataFrame:
    stops = pd.read_csv(path, dtype=str)
    juris_to_fips = {v[2]: k for k, v in AREAS.items()}
    stops = stops[stops["Jurisdiction"].isin(juris_to_fips)].copy()
    stops["COUNTYFP"] = stops["Jurisdiction"].map(juris_to_fips)
    xy = stops["Location"].fillna("").str.extract(COORD_RE)
    stops["lat"] = pd.to_numeric(xy[0], errors="coerce")
    stops["lon"] = pd.to_numeric(xy[1], errors="coerce")
    return stops
 
 
def area_stats(counties, cams, stops, tracts) -> pd.DataFrame:
    s = counties[["COUNTYFP", "area", "pair"]].copy()
    s["cameras"] = s["COUNTYFP"].map(cams["COUNTYFP"].value_counts()).fillna(0).astype(int)
    police = cams[cams.get("operator", pd.Series(dtype=str)).fillna("").str.contains(
        "Police|Sheriff", case=False)]
    s["police_cameras"] = s["COUNTYFP"].map(police["COUNTYFP"].value_counts()).fillna(0).astype(int)
    s["lpr_stops"] = s["COUNTYFP"].map(stops["COUNTYFP"].value_counts()).fillna(0).astype(int)
    if tracts is not None:
        pop = tracts.groupby("county")["pop_total"].sum()
        s["population"] = s["COUNTYFP"].map(pop)
        s["cams_per_10k"] = (10000 * s["cameras"] / s["population"]).round(1)
    return s.sort_values(["pair", "area"])

def add_basemaps(m):
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics",
        name="Satellite",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Dark",
        show=False,
    ).add_to(m)
 
 
def add_tract_layer(m, tracts, column, name, colors, show):
    folium.Choropleth(
        geo_data=tracts.__geo_interface__,
        data=tracts,
        columns=["GEOID", column],
        key_on="feature.properties.GEOID",
        fill_color=colors,
        fill_opacity=0.6,
        line_color="white",
        line_weight=0.4,
        line_opacity=0.6,
        nan_fill_color="#888888",
        nan_fill_opacity=0.3,
        name=name,
        show=show,
    ).add_to(m)
 
 
def add_legend_and_stats(m, stats):
    rows = ""
    for _, r in stats.iterrows():
        pair = f"Pair {r['pair']}" if r["pair"] else "Comparison"
        per = f" · {r['cams_per_10k']}/10k" if "cams_per_10k" in r and pd.notna(r["cams_per_10k"]) else ""
        rows += (
            f"<tr><td><b>{r['area']}</b><br><span style='color:#aaa'>{pair}</span></td>"
            f"<td style='text-align:right'>{r['cameras']}{per}<br>"
            f"<span style='color:#aaa'>{r['police_cameras']} police · {r['lpr_stops']} hit stops</span></td></tr>"
        )
 
    html = f"""
    <div style="position:fixed; bottom:24px; left:12px; z-index:9999; background:rgba(20,20,25,.88);
                color:#fff; padding:12px 14px; border-radius:8px; font:13px/1.5 Arial, sans-serif; width:230px">
      <div style="font-weight:bold; font-size:15px; margin-bottom:6px">Legend</div>
      <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;
           background:#f5c542;border:1px solid #333"></span> ALPR camera (DeFlock)</div>
      <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;
           background:#e74c3c;border:1px solid #333"></span> Camera-hit stop (2026)</div>
      <div style="margin-top:6px">Camera density</div>
      <div style="height:10px;border-radius:3px;background:linear-gradient(90deg,#fde0c5,#f08a4b,#c0392b)"></div>
      <div style="margin-top:6px">Traffic crime density</div>
      <div style="height:10px;border-radius:3px;background:linear-gradient(90deg,#27C8F5,#27B0F5,#2768F5,#2A27F5)"></div>
      <div style="margin-top:6px">Median household income</div>
      <div style="height:10px;border-radius:3px;background:linear-gradient(90deg,#ffffcc,#41b6c4,#253494)"></div>
      <div style="display:flex;justify-content:space-between;color:#aaa;font-size:11px"><span>lower</span><span>higher</span></div>
      <div style="margin-top:4px"><span style="display:inline-block;width:18px;border-top:1px solid #fff"></span>
           Census tract boundary</div>
    </div>
    <div style="position:fixed; top:12px; left:60px; z-index:9999; background:rgba(20,20,25,.88);
                color:#fff; padding:12px 14px; border-radius:8px; font:12px/1.4 Arial, sans-serif; width:300px">
      <div style="font-weight:bold; font-size:15px; margin-bottom:6px">Cameras by study area</div>
      <table style="width:100%; border-collapse:collapse">{rows}</table>
      <div style="color:#aaa; font-size:10px; margin-top:6px">Cameras: DeFlock (crowdsourced). Income/race: ACS 2020–2024.
        Hit stops: VA Community Policing data, Jan–Sep 2026.</div>
    </div>
    """
    m.get_root().html.add_child(Element(html))

def build_map() -> folium.Map:
    counties = load_counties()
    cams = load_cameras(counties)
    stops = load_stops(LPR_FILE)
    traffic = load_stops(TRAFFIC_FILE)
    tracts = None
    if TRACTS_FILE.exists():
        tracts = gpd.read_file(TRACTS_FILE)
        tracts["county"] = tracts["GEOID"].str[2:5]
    else:
        print(f"Note: {TRACTS_FILE} not found — run get_tracts.py to add the income/race layers")
 
    m = folium.Map(tiles=None)
    # Zoom so all study areas fit on screen
    minx, miny, maxx, maxy = counties.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]], padding=(20, 20))
    add_basemaps(m)
 
    if tracts is not None:
        add_tract_layer(m, tracts, "median_income", "Median household income", "YlGnBu", True)
        add_tract_layer(m, tracts, "pct_black", "% Black residents", "Purples", False)
        add_tract_layer(m, tracts, "pct_white", "% White residents", "Greens", False)
        add_tract_layer(m, tracts, "pct_hispanic", "% Hispanic residents", "Oranges", False)
    folium.GeoJson(
        counties,
        name="Study area outlines",
        style_function=lambda _: {"color": "#ffffff", "weight": 2.5, "fillOpacity": 0, "dashArray": "6 4"},
        tooltip=folium.GeoJsonTooltip(fields=["area"], aliases=["Area"]),
    ).add_to(m)
    HeatMap(
        [[p.y, p.x] for p in cams.geometry],
        name="Camera density (heat)",
        radius=22,
        blur=18,
        min_opacity=0.25,
        gradient={0.2: "#fde0c5", 0.5: "#f08a4b", 0.8: "#e74c3c", 1.0: "#c0392b"},
    ).add_to(m)
    cam_layer = folium.FeatureGroup(name="ALPR cameras").add_to(m)
    for _, r in cams.iterrows():
        folium.CircleMarker(
            [r.geometry.y, r.geometry.x],
            radius=4.5, color="#333", weight=1, fill=True, fill_color="#f5c542", fill_opacity=0.95,
            tooltip=f"{r['area']}<br>Operator: {r.get('operator') or 'unknown'}",
        ).add_to(cam_layer)
    mapped = stops.dropna(subset=["lat", "lon"])
    stop_layer = folium.FeatureGroup(name="Camera-hit stops").add_to(m)
    for _, r in mapped.iterrows():
        folium.CircleMarker(
            [r["lat"], r["lon"]],
            radius=6, color="#fff", weight=1.5, fill=True, fill_color="#e74c3c", fill_opacity=0.95,
            tooltip=f"{r['Stop Date']}<br>{r['Race']}<br>{r['Action Taken']}",
        ).add_to(stop_layer)

    trafficed = traffic.dropna(subset=["lat", "lon"])
    HeatMap(
        trafficed[["lat", "lon"]].values.tolist(),
        name="Traffic crimes (heat)",
        radius=22,
        blur=18,
        min_opacity=0.25,
        gradient={0.2: "#27C8F5", 0.5: "#27B0F5", 0.8: "#2768F5", 1.0: "#2A27F5"}
    ).add_to(m)
 
    folium.LayerControl(collapsed=False).add_to(m)
 
    stats = area_stats(counties, cams, stops, tracts)
    add_legend_and_stats(m, stats)
 
    print(stats.to_string(index=False))
    print(f"\n{len(cams)} cameras and {len(mapped)} of {len(stops)} hit stops drawn")
    return m
 
 
if __name__ == "__main__":
    OUT_MAP.parent.mkdir(parents=True, exist_ok=True)
    build_map().save(OUT_MAP)
    print(f"Saved {OUT_MAP} — open it in your browser")