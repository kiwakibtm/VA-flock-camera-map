from pathlib import Path
import pandas as pd
import requests

ACS_YEAR = 2024
OUTPUT_FILE = Path("data/processed/acs_tracts.csv")

AREAS = {
    "710": "Norfolk city",
    "093": "Isle of Wight County",
    "650": "Hampton city",
    "036": "Charles City County",
    "760": "Richmond city",
    "087": "Henrico County",
    "540": "Charlottesville city",
}

VARS = {
    "B03002_001E": "pop_total",
    "B03002_003E": "pop_white_nh",
    "B03002_004E": "pop_black_nh",
    "B03002_012E": "pop_hispanic",
    "B19013_001E": "median_income",
}


def get_acs_tracts(api_key):
    frames = []
    for county in AREAS:
        r = requests.get(
            f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5",
            params={
                "get": "NAME," + ",".join(VARS),
                "for": "tract:*",
                "in": f"state:51 county:{county}",
                "key": api_key,
            },
            timeout=60,
        )
        r.raise_for_status()
        rows = r.json()
        frames.append(pd.DataFrame(rows[1:], columns=rows[0]))

    acs = pd.concat(frames, ignore_index=True).rename(columns=VARS)
    for col in VARS.values():
        acs[col] = pd.to_numeric(acs[col], errors="coerce")
    acs.loc[acs["median_income"] < 0, "median_income"] = None

    acs["GEOID"] = acs["state"] + acs["county"] + acs["tract"]
    acs["area"] = acs["county"].map(AREAS)
    acs["pct_black"] = 100 * acs["pop_black_nh"] / acs["pop_total"]
    acs["pct_white"] = 100 * acs["pop_white_nh"] / acs["pop_total"]
    acs["pct_hispanic"] = 100 * acs["pop_hispanic"] / acs["pop_total"]
    return acs


if __name__ == "__main__":
    api_key = Path("census_key.txt").read_text().strip()
    acs = get_acs_tracts(api_key)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    acs.to_csv(OUTPUT_FILE, index=False)

    summary = acs.groupby("area").agg(
        tracts=("GEOID", "count"),
        population=("pop_total", "sum"),
        pct_black=("pct_black", "mean"),
    )
    print(summary.round(1))
    print(f"\nSaved {len(acs)} tracts to {OUTPUT_FILE}")