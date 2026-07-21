import socket
import struct
import sys
import time
from pathlib import Path

HOST = "127.0.0.1"
RCON_PORT = 25575
RCON_PASSWORD = "seedworld-local"
WORLD_REGION = Path("world") / "region"
X_RANGES = [(-50, -26), (-25, -1), (0, 24), (25, 49)]
Z_RANGES = [(-50, -41), (-40, -31), (-30, -21), (-20, -11), (-10, -1),
            (0, 9), (10, 19), (20, 29), (30, 39), (40, 49)]


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
    def __init__(self):
        self.sock = socket.create_connection((HOST, RCON_PORT), timeout=180)
        self.sock.sendall(packet(1, 3, RCON_PASSWORD))
        request_id, _, _ = recv_packet(self.sock)
        if request_id == -1:
            raise RuntimeError("RCON authentication failed")

    def command(self, command):
        self.sock.sendall(packet(2, 2, command))
        request_id, _, body = recv_packet(self.sock)
        if request_id != 2:
            raise RuntimeError(f"Unexpected RCON response for {command!r}: {request_id}")
        return body

    def close(self):
        self.sock.close()


def region_entry(cx, cz):
    rx, lx = divmod(cx, 32)
    rz, lz = divmod(cz, 32)
    path = WORLD_REGION / f"r.{rx}.{rz}.mca"
    try:
        with path.open("rb") as region:
            header = region.read(4096)
    except FileNotFoundError:
        return False
    if len(header) < 4096:
        return False
    index = 4 * (lx + lz * 32)
    offset = (header[index] << 16) | (header[index + 1] << 8) | header[index + 2]
    return offset != 0


def saved_count(xs, xe, zs, ze):
    return sum(
        region_entry(cx, cz)
        for cz in range(zs, ze + 1)
        for cx in range(xs, xe + 1)
    )


def main():
    batches = [(xs, xe, zs, ze)
               for zs, ze in Z_RANGES
               for xs, xe in X_RANGES]
    total_expected = 10000
    total_saved = sum(saved_count(*batch) for batch in batches)
    print(f"Target: 10000 chunks, currently saved in target: {total_saved}", flush=True)

    rcon = Rcon()
    try:
        for number, (xs, xe, zs, ze) in enumerate(batches, 1):
            expected = (xe - xs + 1) * (ze - zs + 1)
            count = saved_count(xs, xe, zs, ze)
            if count < expected:
                block_x1, block_z1 = xs * 16, zs * 16
                block_x2, block_z2 = xe * 16 + 15, ze * 16 + 15
                command = f"forceload add {block_x1} {block_z1} {block_x2} {block_z2}"
                print(f"Batch {number}/{len(batches)} add chunks x={xs}..{xe}, z={zs}..{ze}", flush=True)
                print(rcon.command(command), flush=True)

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
                        elapsed = int(now - started)
                        print(f"  saved {count}/{expected}, elapsed {elapsed}s", flush=True)
                        last_report = now
                    if now - started > 900:
                        raise TimeoutError(f"Batch {number} did not finish: {count}/{expected}")
                    time.sleep(2.0)

                rcon.command("save-all flush")
                remove = f"forceload remove {block_x1} {block_z1} {block_x2} {block_z2}"
                print(rcon.command(remove), flush=True)
            else:
                print(f"Batch {number}/{len(batches)} already saved ({count}/{expected})", flush=True)

            total_saved = sum(saved_count(*batch) for batch in batches)
            print(f"Progress: {total_saved}/{total_expected} target chunks saved", flush=True)

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
