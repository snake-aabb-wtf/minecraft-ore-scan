import shutil
import sys
import time

from pregen import Rcon, saved_count

MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
MIN_CHUNK = -150
MAX_CHUNK = 149
TARGET_EXPECTED = 300 * 300


def ranges(start, end, width):
    result = []
    current = start
    while current <= end:
        result.append((current, min(current + width - 1, end)))
        current += width
    return result


def main():
    x_ranges = ranges(MIN_CHUNK, MAX_CHUNK, 25)
    z_ranges = ranges(MIN_CHUNK, MAX_CHUNK, 10)
    batches = [(xs, xe, zs, ze)
               for zs, ze in z_ranges
               for xs, xe in x_ranges]
    total_saved = sum(saved_count(*batch) for batch in batches)
    print(f"Target: {TARGET_EXPECTED} chunks, currently saved: {total_saved}", flush=True)

    rcon = Rcon()
    try:
        for number, (xs, xe, zs, ze) in enumerate(batches, 1):
            free = shutil.disk_usage(".").free
            if free < MIN_FREE_BYTES:
                raise RuntimeError(f"Only {free} bytes remain on the target drive")

            expected = (xe - xs + 1) * (ze - zs + 1)
            count = saved_count(xs, xe, zs, ze)
            before = count
            if count < expected:
                block_x1, block_z1 = xs * 16, zs * 16
                block_x2, block_z2 = xe * 16 + 15, ze * 16 + 15
                add = f"forceload add {block_x1} {block_z1} {block_x2} {block_z2}"
                print(f"Batch {number}/{len(batches)} x={xs}..{xe}, z={zs}..{ze}", flush=True)
                print(rcon.command(add), flush=True)

                started = time.monotonic()
                last_save = 0.0
                last_report = 0.0
                while count < expected:
                    now = time.monotonic()
                    if now - last_save >= 5.0:
                        rcon.command("save-all flush")
                        last_save = time.monotonic()
                    count = saved_count(xs, xe, zs, ze)
                    if now - last_report >= 5.0:
                        print(f"  saved {count}/{expected}, elapsed {int(now - started)}s", flush=True)
                        last_report = now
                    if now - started > 900:
                        raise TimeoutError(f"Batch {number} did not finish: {count}/{expected}")
                    time.sleep(2.0)

                rcon.command("save-all flush")
                remove = f"forceload remove {block_x1} {block_z1} {block_x2} {block_z2}"
                print(rcon.command(remove), flush=True)
            else:
                print(f"Batch {number}/{len(batches)} already saved ({count}/{expected})", flush=True)

            total_saved += expected - before
            print(f"Progress: {total_saved}/{TARGET_EXPECTED}", flush=True)

        rcon.command("save-all flush")
        print("Generation complete; saved all target chunks.", flush=True)
    finally:
        rcon.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
