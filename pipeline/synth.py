"""Generates ODK-style sample data (with realistic defects) so the project runs without a server."""
from pathlib import Path

import numpy as np
import pandas as pd

REGIONS = {"Nakuru": (-0.30, 36.07, 1.00), "Kakamega": (0.28, 34.75, 1.10), "Meru": (0.05, 37.65, 1.05),
           "Bungoma": (0.57, 34.56, 0.95), "Narok": (-1.08, 35.87, 0.90)}
# crop: (base kg/ha, KES/kg, days to harvest, sampling weight, non-fertiliser cost KES/ha)
CROPS = {"maize": (2600, 45, 150, .40, 55000), "beans": (900, 130, 90, .25, 50000), "sorghum": (1300, 55, 120, .10, 45000),
         "potato": (12000, 30, 100, .15, 180000), "wheat": (3000, 50, 140, .10, 75000)}
SEASON_F = {"2023A": 1.0, "2023B": 0.92, "2024A": 0.68, "2024B": 1.05, "2025A": 1.12}  # 2024A: drought


def _ring(lat, lon, area_ha, bowtie=False):
    half = (area_ha * 10_000) ** 0.5 / 2 / 111_320
    dx = half / np.cos(np.radians(lat))
    p = [(lat - half, lon - dx), (lat - half, lon + dx), (lat + half, lon + dx), (lat + half, lon - dx)]
    if bowtie:
        p = [p[0], p[2], p[1], p[3]]
    p.append(p[0])
    return "; ".join(f"{a:.6f} {b:.6f} 0 5" for a, b in p)


def generate(data_dir, n=700, seed=7):
    rng = np.random.default_rng(seed)
    data_dir = Path(data_dir)
    (data_dir / "incoming").mkdir(parents=True, exist_ok=True)
    (data_dir / "reference").mkdir(parents=True, exist_ok=True)
    names = list(REGIONS)
    farmers = pd.DataFrame({"farmer_id": [f"KE-F{i:04d}" for i in range(1, 161)],
                            "region": rng.choice(names, 160)})
    farmers.to_csv(data_dir / "reference" / "farmers_master.csv", index=False)
    crops, w = list(CROPS), [v[3] for v in CROPS.values()]
    rows = []
    for k in range(n):
        f = farmers.iloc[rng.integers(160)]
        season, crop = rng.choice(list(SEASON_F)), rng.choice(crops, p=w)
        base, price, days, _, cost = CROPS[crop]
        lat0, lon0, rf = REGIONS[f.region]
        lat, lon = lat0 + rng.normal(0, .05), lon0 + rng.normal(0, .05)
        area = float(np.clip(rng.lognormal(0.1, 0.6), 0.2, 8))
        fert = 0.0 if rng.random() < .25 else float(np.clip(rng.lognormal(3.7, .5), 5, 150))
        y_ha = base * SEASON_F[season] * rf * max(0.3, 1 + .006 * (fert - 45)) * rng.lognormal(0, .18)
        year = int(season[:4])
        plant = pd.Timestamp(year, 3, 1) + pd.Timedelta(days=int(rng.integers(0, 50))) if season[-1] == "A" \
            else pd.Timestamp(year, 9, 1) + pd.Timedelta(days=int(rng.integers(0, 50)))
        harvest = plant + pd.Timedelta(days=int(days + rng.normal(0, 10)))
        row = dict(KEY=f"uuid:{k:08x}", SubmissionDate=(harvest + pd.Timedelta(days=int(rng.integers(1, 26)))).isoformat(),
                   farmer_id=f.farmer_id, region=f.region, season=season, crop=crop,
                   area_ha=round(area, 2), planting_date=plant.date().isoformat(),
                   harvest_date=harvest.date().isoformat(), yield_kg=round(y_ha * area),
                   fertilizer_kg=round(fert * area, 1),
                   input_cost=round(area * (cost + fert * 115 + rng.normal(0, 3000))),
                   price_per_kg=round(price * rng.lognormal(0, .08) * (1.15 if season == "2024A" else 1), 1),
                   plot_boundary=_ring(lat, lon, area, bowtie=rng.random() < .02),
                   plot_gps=f"{lat:.6f} {lon:.6f} 0 4")
        r = rng.random()  # inject defects: each branch is a field-team or collection problem to catch
        if r < .02: row["farmer_id"] = "KE-F9999"
        elif r < .04: row["yield_kg"] = row["yield_kg"] * 30
        elif r < .055: row["planting_date"], row["harvest_date"] = row["harvest_date"], row["planting_date"]
        elif r < .075: row["crop"] = ""
        elif r < .105: row["area_ha"] = round(area * 2, 2)
        elif r < .12: row["plot_gps"] = f"{lat + .01:.6f} {lon:.6f} 0 4"
        elif r < .13: row["planting_date"] = (plant - pd.Timedelta(days=130)).date().isoformat()
        elif r < .15: row["yield_kg"] = round(row["yield_kg"] * 3)
        if rng.random() < .04: row["crop"] = {"maize": "Corn", "potato": "Irish potato"}.get(crop, crop.upper())
        if rng.random() < .03: row["region"] = f" {f.region.lower()} "
        rows.append(row)
        if rng.random() < .01: rows.append(dict(row))  # duplicate upload
    df = pd.DataFrame(rows).sort_values("SubmissionDate")
    cut = df.SubmissionDate.iloc[int(len(df) * .65)]
    paths = [data_dir / "incoming" / "odk_batch_1.csv", data_dir / "incoming" / "odk_batch_2.csv"]
    df[df.SubmissionDate <= cut].to_csv(paths[0], index=False)
    df[df.SubmissionDate > cut].to_csv(paths[1], index=False)
    return paths
