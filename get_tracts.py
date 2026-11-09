from pathlib import Path
import pandas as pd
import folium
import geopandas as gpd

from get_census import AREAS

TRACTS_url = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_51_tract_500k.zip"
ACS_TRACTS_FILE = Path("Data/processed/acs_tracts.csv")
OUT_GEOJSON_FILE = Path("Data/processed/tracts.geojson")
OUT_MAP = Path("Data/processed/tracts_map.html")

def load_tracts() -> gpd.GeoDataFrame:
    shapes = gpd.read_file(TRACTS_url)
    shapes = shapes[shapes["COUNTYFP"].isin(AREAS)].to_crs("EPSG:4326")

    acs = pd.read_csv(ACS_TRACTS_FILE, dtype={"GEOID": str, "state": str, "county": str, "tract": str})
    tracts = shapes[["GEOID", "geometry"]].merge(acs, on="GEOID", how="left")
    missing = tracts["pop_total"].isna().sum()
    if missing: 
        print(f"Note: {missing} tracts shapes had no census row (usually water-only tracts).")
    return tracts

def make_map(tracts: gpd.GeoDataFrame) -> folium.Map:
    m = folium.Map(location=[37.4, -77.2], zoom_start=8, tiles="OpenStreetMap")
    folium.Choropleth(
        geo_data=tracts.__geo_interface__,
        data=tracts,
        columns=["GEOID", "pct_black"],
        key_on="feature.properties.GEOID",
        fill_color="Purples",
        fill_opacity=0.7,
        line_opacity=0.2,
        nan_fill_color="#dddddd",
        legend_name="% Black (non-Hispanic)",
        name = "% Black",
    ).add_to(m)
    folium.Choropleth(
        geo_data=tracts.__geo_interface__,
        data=tracts,
        columns=["GEOID", "median_income"],
        key_on="feature.properties.GEOID",
        fill_color="YlGn",
        fill_opacity=0.7,
        line_opacity=0.2,
        nan_fill_color="#dddddd",
        legend_name="Median Household Income ($)",
        name="Median Income",
        show=False
    ).add_to(m)

    folium.GeoJson(
        tracts,
        style_function=lambda _: { "fillOpacity": 0, "weight": 0},
        tooltip=folium.GeoJsonTooltip(
            fields=["NAME", "area", "pop_total", "pct_black", "pct_white", "median_income"],
            aliases=["Tract Name:", "Area:", "Total Population:", "% Black:", "% White:", "Median Household Income ($):"],
            localize=True,
        ),
        control=False
    ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m
if __name__ == "__main__":
    print("Downloading tract boundries...")
    tracts = load_tracts()
    for col in ["pct_black", "pct_white", "pct_hispanic"]:
        tracts[col] = tracts[col].round(1)
    OUT_GEOJSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    tracts.to_file(OUT_GEOJSON_FILE, driver="GeoJSON")
    print(f"Saved {len(tracts)} tracts to {OUT_GEOJSON_FILE}")
    OUT_MAP.parent.mkdir(parents=True, exist_ok=True)
    make_map(tracts).save(OUT_MAP)
    print(f"Saved map to {OUT_MAP} - open in a browser to view.")
    