"""app.world 的单元测试：维度映射、预生成分块、Anvil location/读取、
packed block states 解码与 scan_chunk 坐标还原（含负坐标）。

所有 fixture 均为内存构造，不启动服务端、不访问网络。
"""
import gzip
import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import nbtlib
from nbtlib import Byte, Compound, File, List, Long, LongArray, String

from app.world import (
    chunk_ranges,
    get_dimension_prefix,
    get_region_dir,
    location_entry_exists,
    read_chunk_payload,
    saved_count,
    scan_all_regions,
    scan_chunk,
    scan_region,
    unpack_indices,
)


# ---------- NBT fixture helpers ----------

def nbt_section(y, palette_names, data_longs=None):
    """构造一个 section 的 nbtlib Compound（block_states.palette/data）。"""
    palette = List[Compound]([Compound({"Name": String(name)}) for name in palette_names])
    block_states = {"palette": palette}
    if data_longs is not None:
        block_states["data"] = LongArray([Long(v) for v in data_longs])
    return Compound({"Y": Byte(y), "block_states": Compound(block_states)})


def nbt_chunk_raw(sections):
    """把 sections 列表序列化为 scan_chunk 可解析的 NBT 字节流。"""
    root = File({"sections": List[Compound](sections)})
    buf = io.BytesIO()
    root.write(buf)
    return buf.getvalue()


# ---------- Anvil .mca fixture helpers ----------

def write_mca(path, chunks):
    """构造最小 .mca：location table + timestamp + 未压缩 chunk payload。

    chunks: {(local_x, local_z): payload_bytes}，payload 为未压缩 NBT。
    """
    header = bytearray(4096)
    sector = 2
    payloads = bytearray()
    for (lx, lz), data in chunks.items():
        entry = 4 * (lx + lz * 32)
        header[entry] = (sector >> 16) & 0xFF
        header[entry + 1] = (sector >> 8) & 0xFF
        header[entry + 2] = sector & 0xFF
        header[entry + 3] = 1  # 1 sector
        chunk_record = struct.pack(">i", len(data) + 1) + bytes([3]) + data
        payloads += chunk_record
        sector += 1
    path.write_bytes(bytes(header) + bytearray(4096) + bytes(payloads))


# ---------- 维度与分块 ----------

class DimensionMappingTest(unittest.TestCase):
    def test_region_dirs(self):
        world_dir = Path("world")
        self.assertEqual(get_region_dir(world_dir, "minecraft:overworld"), world_dir / "region")
        self.assertEqual(get_region_dir(world_dir, "minecraft:the_nether"), world_dir / "DIM-1" / "region")
        self.assertEqual(get_region_dir(world_dir, "minecraft:the_end"), world_dir / "DIM1" / "region")

    def test_invalid_dimension_raises(self):
        with self.assertRaises(ValueError):
            get_region_dir(Path("world"), "minecraft:unknown")

    def test_dimension_prefixes(self):
        self.assertEqual(get_dimension_prefix("minecraft:overworld"), "")
        self.assertEqual(
            get_dimension_prefix("minecraft:the_nether"),
            "execute in minecraft:the_nether run ",
        )
        self.assertEqual(
            get_dimension_prefix("minecraft:the_end"),
            "execute in minecraft:the_end run ",
        )


class ChunkRangesTest(unittest.TestCase):
    def test_positive_range(self):
        self.assertEqual(chunk_ranges(0, 10, 4), [(0, 3), (4, 7), (8, 10)])

    def test_negative_range(self):
        self.assertEqual(chunk_ranges(-10, -1, 4), [(-10, -7), (-6, -3), (-2, -1)])

    def test_single_batch(self):
        self.assertEqual(chunk_ranges(-3, 3, 20), [(-3, 3)])


# ---------- location table ----------

class LocationEntryTest(unittest.TestCase):
    def _write(self, entries):
        header = bytearray(4096)
        for (lx, lz), offset in entries.items():
            entry = 4 * (lx + lz * 32)
            header[entry] = (offset >> 16) & 0xFF
            header[entry + 1] = (offset >> 8) & 0xFF
            header[entry + 2] = offset & 0xFF
        return bytes(header)

    def test_entry_with_offset_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            (region_dir / "r.0.0.mca").write_bytes(self._write({(0, 0): 2}))
            self.assertTrue(location_entry_exists(region_dir, 0, 0))

    def test_zero_offset_means_not_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            (region_dir / "r.0.0.mca").write_bytes(self._write({(0, 0): 0}))
            self.assertFalse(location_entry_exists(region_dir, 0, 0))

    def test_missing_file_returns_false(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertFalse(location_entry_exists(Path(temp_dir), 0, 0))

    def test_negative_chunk_maps_to_negative_region(self):
        # chunk=-1 -> region=-1, local=31（floor division，不能向零截断）
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            (region_dir / "r.-1.-1.mca").write_bytes(self._write({(31, 31): 2}))
            self.assertTrue(location_entry_exists(region_dir, -1, -1))
            self.assertFalse(location_entry_exists(region_dir, 0, 0))


class SavedCountTest(unittest.TestCase):
    def test_counts_saved_chunks_in_range(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            # chunk (0,0) 已保存（region 0.0 entry 0）
            header = bytearray(4096)
            header[0] = 0
            header[1] = 0
            header[2] = 2
            (region_dir / "r.0.0.mca").write_bytes(bytes(header) + bytearray(4096))
            # 范围 0..1 × 0..1 = 4 个 chunk，只有 (0,0) 有 entry
            self.assertEqual(saved_count(region_dir, 0, 1, 0, 1), 1)


# ---------- read_chunk_payload ----------

def _mca_with_payload(payload_bytes, comp_type):
    """构造含单个未保存 chunk 的 .mca：payload 记录在 sector 2。"""
    header = bytearray(4096)
    header[0] = 0
    header[1] = 0
    header[2] = 2
    header[3] = 1
    record = struct.pack(">i", len(payload_bytes) + 1) + bytes([comp_type]) + payload_bytes
    return bytes(header) + bytearray(4096) + record


class ReadChunkPayloadTest(unittest.TestCase):
    def _read(self, payload_bytes, comp_type):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.0.0.mca"
            path.write_bytes(_mca_with_payload(payload_bytes, comp_type))
            with path.open("rb") as f:
                return read_chunk_payload(f, 2)

    def test_gzip(self):
        self.assertEqual(self._read(gzip.compress(b"hello"), 1), b"hello")

    def test_zlib(self):
        self.assertEqual(self._read(zlib.compress(b"hello"), 2), b"hello")

    def test_uncompressed(self):
        self.assertEqual(self._read(b"hello", 3), b"hello")

    def test_invalid_compression_type_returns_none(self):
        self.assertIsNone(self._read(b"hello", 9))

    def test_non_positive_length_returns_none(self):
        # 记录头 length=0 -> read_chunk_payload 返回 None
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.0.0.mca"
            record = struct.pack(">i", 0)
            path.write_bytes(bytearray(4096) + bytearray(4096) + record)
            with path.open("rb") as f:
                self.assertIsNone(read_chunk_payload(f, 2))

    def test_oversized_length_returns_none(self):
        # 恶意声明超大 length（>64MB）应被拒绝，避免分配巨量缓冲
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.0.0.mca"
            record = struct.pack(">i", 0x7FFFFFFF) + bytes([1])
            path.write_bytes(bytearray(4096) + bytearray(4096) + record)
            with path.open("rb") as f:
                self.assertIsNone(read_chunk_payload(f, 2))

    def test_truncated_comp_byte_returns_none(self):
        # 只有 length 字段，没有 compression 字节
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.0.0.mca"
            record = struct.pack(">i", 5)
            path.write_bytes(bytearray(4096) + bytearray(4096) + record)
            with path.open("rb") as f:
                self.assertIsNone(read_chunk_payload(f, 2))


# ---------- unpack_indices（packed block states） ----------

class UnpackIndicesTest(unittest.TestCase):
    # bits=4（palette<=16）时 values_per_long=16，完整数组 256 个 long；
    # bits=5（palette 17..32）时 values_per_long=12，完整数组 342 个 long。

    def test_palette_size_2_bits_4(self):
        # bits=4, values_per_long=16；long0=0x10 -> 槽0=0, 槽1=1
        values = unpack_indices([0x10] + [0] * 255, 2)
        self.assertEqual(values[:3], [0, 1, 0])
        self.assertEqual(len(values), 4096)

    def test_palette_size_17_bits_5(self):
        # (17-1).bit_length()=5 -> values_per_long=12
        # long0 槽0 = 3（低 5 位）
        values = unpack_indices([3] + [0] * 341, 17)
        self.assertEqual(values[0], 3)
        self.assertEqual(len(values), 4096)

    def test_negative_long_is_treated_as_unsigned(self):
        # -1 的无符号位模式全 1；bits=4 时槽0 = 0xF = 15
        values = unpack_indices([-1] + [0] * 255, 2)
        self.assertEqual(values[0], 15)

    def test_cross_long_boundary_not_merged(self):
        # bits=5, vpl=12：index 12 在 long1 槽 0（不跨 long 合并 bit）
        values = unpack_indices([0, 0x10] + [0] * 340, 17)
        self.assertEqual(values[11], 0)
        # long1 槽0 低 5 位 = 0x10 & 31 = 16
        self.assertEqual(values[12], 16)


# ---------- scan_chunk ----------

class ScanChunkTest(unittest.TestCase):
    def test_packed_data_with_negative_chunk_coords(self):
        # palette: [stone, diamond_ore]；index 1 -> diamond
        # index 1 -> lx=1, lz=0, ly=0；chunk (3,-2) -> world (49, 0, -32)
        raw = nbt_chunk_raw([nbt_section(0, ["minecraft:stone", "minecraft:diamond_ore"], [0x10] + [0] * 255)])
        hits = scan_chunk(raw, 3, -2, {"minecraft:diamond_ore"})
        self.assertEqual(hits, [(49, 0, -32, "minecraft:diamond_ore")])

    def test_palette_without_data_uses_index_zero(self):
        # 无 data：整个 section 使用 palette index 0
        raw = nbt_chunk_raw([nbt_section(0, ["minecraft:stone"])])
        hits = scan_chunk(raw, 0, 0, {"minecraft:diamond_ore"})
        self.assertEqual(hits, [])

        raw_diamond = nbt_chunk_raw([nbt_section(5, ["minecraft:diamond_ore"])])
        hits = scan_chunk(raw_diamond, 0, 0, {"minecraft:diamond_ore"})
        self.assertEqual(len(hits), 4096)
        # 第一个方块：section y=5 -> world_y = 5*16 + 0 = 80
        self.assertIn((0, 80, 0, "minecraft:diamond_ore"), hits)

    def test_target_not_in_palette_skips_section(self):
        raw = nbt_chunk_raw([nbt_section(0, ["minecraft:stone"])])
        self.assertEqual(scan_chunk(raw, 0, 0, {"minecraft:iron_ore"}), [])

    def test_non_target_indices_are_skipped(self):
        # 损坏数据：槽1 的值 5 超出了 palette 长度（2），也非目标索引
        # （target_indices={1}）。scan_chunk 应跳过这些位置而不抛异常。
        raw = nbt_chunk_raw([nbt_section(0, ["minecraft:stone", "minecraft:diamond_ore"], [0x50] + [0] * 255)])
        # 0x50 -> 槽0 = 0（stone，非目标），槽1 = 5（越界且非目标）
        hits = scan_chunk(raw, 0, 0, {"minecraft:diamond_ore"})
        self.assertEqual(hits, [])

    def test_section_y_mapping(self):
        # section y=-1 -> world_y = -16..-1；index 0 -> world_y = -16
        raw = nbt_chunk_raw([nbt_section(-1, ["minecraft:diamond_ore"])])
        hits = scan_chunk(raw, 0, 0, {"minecraft:diamond_ore"})
        self.assertEqual(hits[0], (0, -16, 0, "minecraft:diamond_ore"))


# ---------- scan_region / scan_all_regions ----------

class ScanRegionTest(unittest.TestCase):
    def test_filters_to_requested_range(self):
        # region 0.0 存 chunk (0,0)（diamond）与 chunk (1,0)（stone）
        chunk_00 = nbt_chunk_raw([nbt_section(0, ["minecraft:diamond_ore"])])
        chunk_10 = nbt_chunk_raw([nbt_section(0, ["minecraft:stone"])])
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            write_mca(region_dir / "r.0.0.mca", {(0, 0): chunk_00, (1, 0): chunk_10})
            # 只请求 chunk 0..0 -> 只命中 (0,0)
            hits = scan_region(region_dir / "r.0.0.mca", 0, 0, {"minecraft:diamond_ore"})
            self.assertEqual(len(hits), 4096)
            self.assertEqual(hits[0][0:3], (0, 0, 0))

    def test_corrupt_region_invokes_error_callback(self):
        # header 有效、length 合法，但 payload 是损坏的 gzip -> 解压抛异常
        data = bytearray(4096 + 4096 + 128)
        data[0] = 0
        data[1] = 0
        data[2] = 2
        data[3] = 1
        struct.pack_into(">i", data, 8192, 100)  # length 在合法范围内
        data[8196] = 1  # gzip
        data[8197:8197 + 99] = b"\x00" * 99  # 垃圾 payload
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "r.0.0.mca"
            path.write_bytes(data)
            errors = []
            result = scan_region(path, 0, 0, {"minecraft:diamond_ore"}, error_callback=errors.append)
            self.assertEqual(result, [])
            self.assertTrue(errors)
            self.assertIn("r.0.0.mca", errors[0])


class ScanAllRegionsTest(unittest.TestCase):
    def test_scans_existing_regions_and_ignores_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            chunk = nbt_chunk_raw([nbt_section(0, ["minecraft:diamond_ore"])])
            write_mca(region_dir / "r.0.0.mca", {(0, 0): chunk})
            hits = scan_all_regions(region_dir, 0, 0, {"minecraft:diamond_ore"})
            self.assertEqual(len(hits), 4096)

    def test_running_check_cancels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            region_dir = Path(temp_dir)
            chunk = nbt_chunk_raw([nbt_section(0, ["minecraft:diamond_ore"])])
            write_mca(region_dir / "r.0.0.mca", {(0, 0): chunk})
            hits = scan_all_regions(
                region_dir, 0, 0, {"minecraft:diamond_ore"}, running_check=lambda: False
            )
            self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
