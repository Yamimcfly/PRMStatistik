import json
from pathlib import Path

import pandas as pd


def main() -> None:
    config = json.loads(Path("config.json").read_text(encoding="utf-8"))
    paths = config.get("paths", {})

    mapping_path = Path(paths.get("destination_mapping_file", "data/Destination_3letter.xlsx"))
    data_dir = Path(paths.get("data_dir", "data"))

    source_csv = Path("data/airports.csv")
    if not source_csv.exists():
        raise FileNotFoundError("data/airports.csv not found")

    full_df = pd.read_csv(source_csv)

    full_output = data_dir / "airports_full.csv"
    full_output.parent.mkdir(parents=True, exist_ok=True)
    full_df.to_csv(full_output, index=False)

    cols = {c.lower(): c for c in full_df.columns}
    iata_col = cols.get("iata") or cols.get("code")
    name_col = cols.get("name")
    city_col = cols.get("city")

    if not iata_col or not name_col:
        raise ValueError(
            f"Expected columns IATA/Code and Name, got: {list(full_df.columns)}"
        )

    map_df = full_df[[iata_col, name_col]].rename(columns={iata_col: "IATA", name_col: "Name"})
    map_df = map_df.dropna(subset=["IATA", "Name"]).copy()
    if city_col:
        city_df = full_df[[iata_col, city_col]].rename(columns={iata_col: "IATA", city_col: "Name"})
        city_df = city_df.dropna(subset=["IATA", "Name"]).copy()
        map_df = pd.concat([map_df, city_df], ignore_index=True)
    map_df["IATA"] = map_df["IATA"].astype(str).str.strip().str.upper()
    map_df["Name"] = map_df["Name"].astype(str).str.strip()
    map_df = map_df[map_df["IATA"].str.len() == 3]
    map_df = map_df.drop_duplicates(subset=["IATA", "Name"], keep="first")
    map_df = map_df.sort_values(by=["IATA", "Name"])

    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    target_path = mapping_path
    try:
        if target_path.exists():
            with pd.ExcelWriter(
                target_path,
                engine="openpyxl",
                mode="a",
                if_sheet_exists="replace",
            ) as writer:
                map_df.to_excel(writer, sheet_name="Destinations", index=False)
        else:
            with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
                map_df.to_excel(writer, sheet_name="Destinations", index=False)
    except PermissionError:
        fallback = data_dir / "Destination_3letter.generated.xlsx"
        with pd.ExcelWriter(fallback, engine="openpyxl") as writer:
            map_df.to_excel(writer, sheet_name="Destinations", index=False)
        target_path = fallback

    print(f"Wrote mapping file: {target_path}")
    print(f"Wrote full dataset: {full_output}")


if __name__ == "__main__":
    main()
