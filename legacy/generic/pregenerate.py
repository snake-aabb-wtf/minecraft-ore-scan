"""Pregenerate a centered chunk square with a vanilla server through RCON."""

import argparse
import shutil
import socket
import struct
import sys
import time
from pathlib import Path


DIMENSION_PREFIX = {
    "minecraft:overworld": "",
    "minecraft:the_nether": "execute in minecraft:the_nether run ",
    "minecraft:the_end": "execute in minecraft:the_end run ",
}


def packet(request_id, packet_type, body):
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("ascii") + b"\0\0"
    return struct.pack("<i", len(payload)) + payload


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise ConnectionError("RCON connection closed")
        data.extend(part)
    return bytes(data)


def recv_packet(sock):
    size = struct.unpack("<i", recv_exact(sock, 4))[0]
    data = recv_exact(sock, size)
    request_id, packet_type = struct.unpack("<ii", data[:8])
    return request_id, packet_type, data[8:-2].decode("ascii", "replace")


class Rcon:
    def __init__(self, host, port, password, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.sock.sendall(packet(1, 3, password))
        request_id, _, _ = recv_packet(self.sock)
        if request_id == -1:
            self.close()
            raise RuntimeError("RCON authentication failed")

    def command(self, command):
        self.sock.sendall(packet(2, 2, command))
        request_id, _, body = recv_packet(self.sock)
        if request_id != 2:
            raise RuntimeError(f"Unexpected RCON response for {command!r}: {request_id}")
        return body

    def close(self):
        self.sock.close()


def chunk_ranges(start, end, width):
    result = []
    current = start
    while current <= end:
        result.append((current, min(current + width - 1, end)))
        current += width
    return result


def dimension_paths(level_name, dimension):
    world = Path(level_name)
    if dimension == "minecraft:overworld":
        return world / "region", ""
    if dimension == "minecraft:the_nether":
        return world / "DIM-1" / "region", DIMENSION_PREFIX[dimension]
    if dimension == "minecraft:the_end":
        return world / "DIM1" / "region", DIMENSION_PREFIX[dimension]
    raise ValueError("Only the overworld, Nether, and End are supported")


def location_entry(region_dir, chunk_x, chunk_z):
    region_x, local_x = divmod(chunk_x, 32)
    region_z, local_z = divmod(chunk_z, 32)
    path = region_dir / f"r.{region_x}.{region_z}.mca"
    try:
        with path.open("rb") as region:
            region.seek(4096 + 4 * (local_x + local_z * 32))
            entry = region.read(4)
    except FileNotFoundError:
        return False
    if len(entry) != 4:
        return False
    offset = (entry[0] << 16) | (entry[1] << 8) | entry[2]
    return offset != 0


def saved_count(region_dir, xs, xe, zs, ze):
    return sum(
        location_entry(region_dir, chunk_x, chunk_z)
        for chunk_z in range(zs, ze + 1)
        for chunk_x in range(xs, xe + 1)
    )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level-name", default="world")
    parser.add_argument("--dimension", choices=sorted(DIMENSION_PREFIX), default="minecraft:overworld")
    parser.add_argument("--min-chunk", type=int, required=True)
    parser.add_argument("--max-chunk", type=int, required=True)
    parser.add_argument("--x-width", type=int, default=25)
    parser.add_argument("--z-height", type=int, default=10)
    parser.add_argument("--rcon-host", default="127.0.0.1")
    parser.add_argument("--rcon-port", type=int, default=25575)
    parser.add_argument("--rcon-password", required=True)
    parser.add_argument("--rcon-timeout", type=int, default=180)
    parser.add_argument("--batch-timeout", type=int, default=900)
    parser.add_argument("--min-free-gb", type=float, default=8)
    parser.add_argument("--stop-after-complete", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.min_chunk > args.max_chunk:
        raise ValueError("--min-chunk must be <= --max-chunk")
    if args.x_width <= 0 or args.z_height <= 0:
        raise ValueError("batch dimensions must be positive")
    if args.x_width * args.z_height > 256:
        raise ValueError("a /forceload rectangle cannot exceed 256 chunks")

    region_dir, dimension_prefix = dimension_paths(args.level_name, args.dimension)
    x_ranges = chunk_ranges(args.min_chunk, args.max_chunk, args.x_width)
    z_ranges = chunk_ranges(args.min_chunk, args.max_chunk, args.z_height)
    batches = [(xs, xe, zs, ze) for zs, ze in z_ranges for xs, xe in x_ranges]
    expected_total = (args.max_chunk - args.min_chunk + 1) ** 2
    total_saved = sum(saved_count(region_dir, *batch) for batch in batches)
    print(f"target={expected_total} chunks, currently_saved={total_saved}", flush=True)

    min_free_bytes = int(args.min_free_gb * 1024 ** 3)
    rcon = Rcon(args.rcon_host, args.rcon_port, args.rcon_password, args.rcon_timeout)
    try:
        for number, (xs, xe, zs, ze) in enumerate(batches, 1):
            if shutil.disk_usage(Path.cwd()).free < min_free_bytes:
                raise RuntimeError("free disk space fell below --min-free-gb")
            expected = (xe - xs + 1) * (ze - zs + 1)
            count = saved_count(region_dir, xs, xe, zs, ze)
            before = count
            block_x1, block_z1 = xs * 16, zs * 16
            block_x2, block_z2 = xe * 16 + 15, ze * 16 + 15
            add = f"{dimension_prefix}forceload add {block_x1} {block_z1} {block_x2} {block_z2}"
            remove = f"{dimension_prefix}forceload remove {block_x1} {block_z1} {block_x2} {block_z2}"
            if count < expected:
                print(f"batch={number}/{len(batches)} chunks={xs}..{xe},{zs}..{ze}", flush=True)
                print(rcon.command(add), flush=True)
                started = time.monotonic()
                last_save = 0.0
                last_report = 0.0
                try:
                    while count < expected:
                        now = time.monotonic()
                        if now - last_save >= 5:
                            rcon.command("save-all flush")
                            last_save = time.monotonic()
                        count = saved_count(region_dir, xs, xe, zs, ze)
                        if now - last_report >= 10:
                            print(f"  saved={count}/{expected} elapsed={int(now - started)}s", flush=True)
                            last_report = now
                        if now - started > args.batch_timeout:
                            raise TimeoutError(f"batch {number} timed out at {count}/{expected}")
                        time.sleep(2)
                    rcon.command("save-all flush")
                finally:
                    print(rcon.command(remove), flush=True)
            else:
                print(f"batch={number}/{len(batches)} already_saved={count}/{expected}", flush=True)
            total_saved += expected - before
            print(f"progress={total_saved}/{expected_total}", flush=True)

        rcon.command("save-all flush")
        print("generation_complete", flush=True)
        if args.stop_after_complete:
            print(rcon.command("stop"), flush=True)
    finally:
        rcon.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
