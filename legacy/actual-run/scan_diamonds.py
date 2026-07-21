import argparse
import gzip
import io
import math
import struct
import sys
import zlib
from pathlib import Path

import nbtlib


TARGET_BLOCKS = {"minecraft:diamond_ore", "minecraft:deepslate_diamond_ore"}
TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


def read_string(stream):
    size = struct.unpack(">H", stream.read(2))[0]
    return stream.read(size).decode("utf-8")


def read_tag_payload(stream, tag_type):
    if tag_type == TAG_BYTE:
        return struct.unpack(">b", stream.read(1))[0]
    if tag_type == TAG_SHORT:
        return struct.unpack(">h", stream.read(2))[0]
    if tag_type == TAG_INT:
        return struct.unpack(">i", stream.read(4))[0]
    if tag_type == TAG_LONG:
        return struct.unpack(">q", stream.read(8))[0]
    if tag_type == TAG_FLOAT:
        return struct.unpack(">f", stream.read(4))[0]
    if tag_type == TAG_DOUBLE:
        return struct.unpack(">d", stream.read(8))[0]
    if tag_type == TAG_BYTE_ARRAY:
        size = struct.unpack(">i", stream.read(4))[0]
        return stream.read(size)
    if tag_type == TAG_STRING:
        return read_string(stream)
    if tag_type == TAG_LIST:
        item_type = struct.unpack(">b", stream.read(1))[0]
        size = struct.unpack(">i", stream.read(4))[0]
        return [read_tag_payload(stream, item_type) for _ in range(size)]
    if tag_type == TAG_COMPOUND:
        result = {}
        while True:
            child_type = struct.unpack(">b", stream.read(1))[0]
            if child_type == TAG_END:
                return result
            result[read_string(stream)] = read_tag_payload(stream, child_type)
    if tag_type == TAG_INT_ARRAY:
        size = struct.unpack(">i", stream.read(4))[0]
        return list(struct.unpack(f">{size}i", stream.read(size * 4)))
    if tag_type == TAG_LONG_ARRAY:
        size = struct.unpack(">i", stream.read(4))[0]
        return list(struct.unpack(f">{size}q", stream.read(size * 8)))
    raise ValueError(f"Unknown NBT tag {tag_type}")


def read_nbt(data):
    stream = io.BytesIO(data)
    root_type = struct.unpack(">b", stream.read(1))[0]
    if root_type != TAG_COMPOUND:
        raise ValueError("Chunk NBT root is not a compound")
    read_string(stream)
    return read_tag_payload(stream, root_type)


def unpack_block_indices(data, palette_size):
    bits = max(4, (palette_size - 1).bit_length())
    mask = (1 << bits) - 1
    values_per_long = 64 // bits
    values = []
    for index in range(4096):
        long_index, slot = divmod(index, values_per_long)
        offset = slot * bits
        values.append(((data[long_index] & ((1 << 64) - 1)) >> offset) & mask)
    return values


def scan_chunk(data, chunk_x, chunk_z):
    root = nbtlib.File.parse(io.BytesIO(data))
    positions = []
    for section in root.get("sections", []):
        block_states = section.get("block_states")
        if not block_states:
            continue
        palette = block_states.get("palette", [])
        target_indices = {
            index for index, state in enumerate(palette)
            if str(state.get("Name")) in TARGET_BLOCKS
        }
        if not target_indices:
            continue
        section_y = int(section.get("Y", 0))
        packed = block_states.get("data")
        if packed is None:
            indices = [0] * 4096
        else:
            indices = unpack_block_indices([int(value) for value in packed], len(palette))
        for index, palette_index in enumerate(indices):
            if palette_index not in target_indices:
                continue
            local_x = index & 15
            local_z = (index >> 4) & 15
            local_y = (index >> 8) & 15
            positions.append((
                chunk_x * 16 + local_x,
                section_y * 16 + local_y,
                chunk_z * 16 + local_z,
                str(palette[palette_index]["Name"]),
            ))
    return positions


def chunk_payload(region, sector_offset):
    region.seek(sector_offset * 4096)
    length_data = region.read(4)
    if len(length_data) != 4:
        return None
    length = struct.unpack(">i", length_data)[0]
    compression = region.read(1)[0]
    payload = region.read(length - 1)
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"Unsupported chunk compression type {compression}")


def scan_region_file(path, min_chunk, max_chunk, positions):
    name_parts = path.stem.split(".")
    region_x, region_z = int(name_parts[1]), int(name_parts[2])
    scanned = 0
    with path.open("rb") as region:
        header = region.read(4096)
        if len(header) != 4096:
            return 0
        for local_z in range(32):
            chunk_z = region_z * 32 + local_z
            if not min_chunk <= chunk_z <= max_chunk:
                continue
            for local_x in range(32):
                chunk_x = region_x * 32 + local_x
                if not min_chunk <= chunk_x <= max_chunk:
                    continue
                entry = 4 * (local_x + local_z * 32)
                sector_offset = (header[entry] << 16) | (header[entry + 1] << 8) | header[entry + 2]
                if sector_offset == 0:
                    continue
                payload = chunk_payload(region, sector_offset)
                if payload:
                    positions.extend(scan_chunk(payload, chunk_x, chunk_z))
                    scanned += 1
    return scanned


def group_veins(positions):
    remaining = {(x, y, z): name for x, y, z, name in positions}
    veins = []
    while remaining:
        start = next(iter(remaining))
        stack = [(start, remaining.pop(start))]
        component = []
        while stack:
            current, name = stack.pop()
            component.append((*current, name))
            x, y, z = current
            for neighbor in ((x - 1, y, z), (x + 1, y, z),
                             (x, y - 1, z), (x, y + 1, z),
                             (x, y, z - 1), (x, y, z + 1)):
                neighbor_name = remaining.pop(neighbor, None)
                if neighbor_name is not None:
                    stack.append((neighbor, neighbor_name))
        nearest = min(component, key=lambda p: (p[0] * p[0] + p[2] * p[2], abs(p[1])))
        veins.append({
            "size": len(component),
            "nearest": nearest[:3],
            "types": sorted({item[3] for item in component}),
            "distance_xz": math.sqrt(nearest[0] ** 2 + nearest[2] ** 2),
        })
    veins.sort(key=lambda vein: (vein["distance_xz"], vein["nearest"][1]))
    return veins


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-chunk", type=int, default=-150)
    parser.add_argument("--max-chunk", type=int, default=149)
    parser.add_argument("--world", type=Path, default=Path("world"))
    args = parser.parse_args()

    region_dir = args.world / "region"
    region_min = args.min_chunk // 32
    region_max = args.max_chunk // 32
    positions = []
    scanned = 0
    region_files = 0
    for region_z in range(region_min, region_max + 1):
        for region_x in range(region_min, region_max + 1):
            path = region_dir / f"r.{region_x}.{region_z}.mca"
            if not path.exists():
                continue
            region_files += 1
            scanned += scan_region_file(path, args.min_chunk, args.max_chunk, positions)
            print(f"scanned regions={region_files}, chunks={scanned}, ores={len(positions)}", flush=True)

    veins = group_veins(positions)
    print(f"SUMMARY chunks={scanned} ore_blocks={len(positions)} veins={len(veins)}", flush=True)
    for index, vein in enumerate(veins[:30], 1):
        x, y, z = vein["nearest"]
        print(f"{index:02d}: x={x}, y={y}, z={z}, size={vein['size']}, distance_xz={vein['distance_xz']:.1f}, types={','.join(vein['types'])}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
