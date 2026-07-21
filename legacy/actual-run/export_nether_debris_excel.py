import math
import sys
from pathlib import Path

from openpyxl import Workbook

import scan_diamonds as scanner


MIN_CHUNK = -250
MAX_CHUNK = 249
MAX_DATA_ROWS = 1_048_575
REGION_DIR = Path("world") / "DIM-1" / "region"
OUTPUT = Path("nether_ancient_debris_sorted.xlsx")


def main():
    scanner.TARGET_BLOCKS = {"minecraft:ancient_debris"}
    positions = []
    scanned = 0
    regions = 0
    for region_z in range(MIN_CHUNK // 32, MAX_CHUNK // 32 + 1):
        for region_x in range(MIN_CHUNK // 32, MAX_CHUNK // 32 + 1):
            path = REGION_DIR / f"r.{region_x}.{region_z}.mca"
            if not path.exists():
                continue
            regions += 1
            scanned += scanner.scan_region_file(path, MIN_CHUNK, MAX_CHUNK, positions)
            print(f"scanned regions={regions}, chunks={scanned}, debris={len(positions)}", flush=True)

    print("sorting by distance to Nether (0,64,0)", flush=True)
    rows = [
        (x, y, z, x * x + (y - 64) * (y - 64) + z * z)
        for x, y, z, _ in positions
    ]
    rows.sort(key=lambda row: (row[3], row[1], row[0], row[2]))

    workbook = Workbook(write_only=True)
    sheet_number = 0
    sheet = None
    row_in_sheet = MAX_DATA_ROWS
    headers = ["X", "Y", "Z", "Type", "DistanceTo_(0,64,0)"]

    for x, y, z, distance_squared in rows:
        if row_in_sheet >= MAX_DATA_ROWS:
            sheet_number += 1
            sheet = workbook.create_sheet(f"AncientDebris_{sheet_number}")
            sheet.append(headers)
            row_in_sheet = 0
        sheet.append([x, y, z, "远古残骸", math.sqrt(distance_squared)])
        row_in_sheet += 1

    workbook.save(OUTPUT)
    print(f"wrote {len(rows)} rows in {sheet_number} sheets to {OUTPUT}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
