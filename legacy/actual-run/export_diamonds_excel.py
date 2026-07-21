import math
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from pregen import saved_count
from scan_diamonds import scan_region_file


MIN_CHUNK = -150
MAX_CHUNK = 149
MAX_DATA_ROWS = 1_048_575
OUTPUT = Path("diamonds_sorted.xlsx")


def main():
    region_dir = Path("world") / "region"
    positions = []
    scanned = 0
    regions = 0
    for region_z in range(MIN_CHUNK // 32, MAX_CHUNK // 32 + 1):
        for region_x in range(MIN_CHUNK // 32, MAX_CHUNK // 32 + 1):
            path = region_dir / f"r.{region_x}.{region_z}.mca"
            if not path.exists():
                continue
            regions += 1
            scanned += scan_region_file(path, MIN_CHUNK, MAX_CHUNK, positions)
            print(f"scanned regions={regions}, chunks={scanned}, ores={len(positions)}", flush=True)

    print("sorting by distance to (0,64,0)", flush=True)
    rows = [
        (x, y, z, ore, x * x + (y - 64) * (y - 64) + z * z)
        for x, y, z, ore in positions
    ]
    rows.sort(key=lambda row: (row[4], row[1], row[0], row[2]))

    workbook = Workbook(write_only=True)
    sheet_number = 0
    sheet = None
    row_in_sheet = MAX_DATA_ROWS
    headers = ["X", "Y", "Z", "OreType", "DistanceTo_(0,64,0)"]

    for x, y, z, ore, distance_squared in rows:
        if row_in_sheet >= MAX_DATA_ROWS:
            sheet_number += 1
            sheet = workbook.create_sheet(f"Diamonds_{sheet_number}")
            sheet.append(headers)
            row_in_sheet = 0
        values = [x, y, z, ore, math.sqrt(distance_squared)]
        sheet.append(values)
        row_in_sheet += 1

    workbook.save(OUTPUT)
    print(f"wrote {len(rows)} rows in {sheet_number} sheets to {OUTPUT}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
