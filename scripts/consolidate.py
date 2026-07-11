#!/usr/bin/env python3
"""
Flattens the raw per-race CSVs (in data/<year>/<Office>/<District>_<id>.csv)
into a small number of "tidy" long-format CSVs that are easy to pivot/filter
in Google Sheets:

    Year, Office, District, City_Town, Ward, Precinct, Candidate, Party, Votes

Usage:
    python scripts/consolidate.py

Output:
    data/tidy/<year>_tidy.csv       (one per year found under data/)
    data/tidy/all_years_tidy.csv    (everything combined)

Each precinct row in a raw race CSV becomes one tidy row per candidate
(plus one row each for "All Others" and "Blanks"), so you can pivot by
Year, Office, District, Candidate, or Party in Sheets.
"""

import csv
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TIDY_DIR = os.path.join(DATA_DIR, "tidy")

FIELDNAMES = ["Year", "Office", "District", "City_Town", "Ward", "Precinct",
              "Candidate", "Party", "Votes"]


def clean_number(val):
    val = (val or "").replace(",", "").strip()
    if not val or not re.match(r"^-?\d+$", val):
        return None
    return int(val)


def parse_race_csv(path, year, office, district):
    """Yields tidy row dicts for one race's precinct CSV."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if len(rows) < 3:
        return

    header = rows[0]
    party_row = rows[1]
    data_rows = rows[2:]

    # Header: City/Town, Ward, Pct, <candidates...>, All Others, Blanks, Total Votes Cast
    n_meta = 3
    n_trailing = 3
    candidates = header[n_meta: len(header) - n_trailing]
    parties = party_row[n_meta: n_meta + len(candidates)]
    parties += [""] * (len(candidates) - len(parties))  # pad if short

    col_names = candidates + ["All Others", "Blanks"]
    col_parties = parties + ["", ""]

    for row in data_rows:
        if not row or not row[0]:
            continue
        city = row[0].strip()
        if city.upper() == "TOTALS":
            continue  # skip the summary row; recompute totals in Sheets instead
        ward = row[1].strip() if len(row) > 1 else ""
        pct = row[2].strip() if len(row) > 2 else ""

        vote_cells = row[n_meta: n_meta + len(col_names)]
        for name, party, raw_votes in zip(col_names, col_parties, vote_cells):
            votes = clean_number(raw_votes)
            if votes is None:
                continue
            yield {
                "Year": year,
                "Office": office,
                "District": district,
                "City_Town": city,
                "Ward": ward,
                "Precinct": pct,
                "Candidate": name,
                "Party": party,
                "Votes": votes,
            }


def district_from_filename(filename):
    # e.g. "2nd_Essex_165491.csv" -> "2nd Essex"
    stem = filename.rsplit(".", 1)[0]
    stem = re.sub(r"_\d+$", "", stem)  # drop trailing _<id>
    return stem.replace("_", " ")


def main():
    os.makedirs(TIDY_DIR, exist_ok=True)
    years = sorted(
        d for d in os.listdir(DATA_DIR)
        if d.isdigit() and os.path.isdir(os.path.join(DATA_DIR, d))
    )
    if not years:
        print(f"No year folders found under {DATA_DIR} "
              f"(expected e.g. data/2024, data/2022, ...)")
        return

    all_years_path = os.path.join(TIDY_DIR, "all_years_tidy.csv")
    all_writer_file = open(all_years_path, "w", newline="", encoding="utf-8")
    all_writer = csv.DictWriter(all_writer_file, fieldnames=FIELDNAMES)
    all_writer.writeheader()

    grand_total = 0
    for year in years:
        year_dir = os.path.join(DATA_DIR, year)
        year_tidy_path = os.path.join(TIDY_DIR, f"{year}_tidy.csv")
        with open(year_tidy_path, "w", newline="", encoding="utf-8") as yf:
            year_writer = csv.DictWriter(yf, fieldnames=FIELDNAMES)
            year_writer.writeheader()
            count = 0
            for office in sorted(os.listdir(year_dir)):
                office_dir = os.path.join(year_dir, office)
                if not os.path.isdir(office_dir):
                    continue
                for filename in sorted(os.listdir(office_dir)):
                    if not filename.endswith(".csv"):
                        continue
                    district = district_from_filename(filename)
                    path = os.path.join(office_dir, filename)
                    for tidy_row in parse_race_csv(path, year, office.replace("_", " "), district):
                        year_writer.writerow(tidy_row)
                        all_writer.writerow(tidy_row)
                        count += 1
        print(f"{year}: {count} rows -> {year_tidy_path}")
        grand_total += count

    all_writer_file.close()
    print(f"\nAll years combined: {grand_total} rows -> {all_years_path}")


if __name__ == "__main__":
    main()
