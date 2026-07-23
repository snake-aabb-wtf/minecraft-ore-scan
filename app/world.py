import struct
import gzip
import io
import shutil
import zlib
import math
import time
import subprocess
from pathlib import Path
import nbtlib


def get_dimension_prefix(dimension: str) -> str:
    return {
        "minecraft:overworld": "",
        "minecraft:the_nether": "execute in minecraft:the_nether run ",
        "minecraft:the_end": "execute in minecraft:the_end run ",
    }[dimension]


def get_region_dir(world_dir: Path, dimension: str) -> Path:
    if dimension == "minecraft:overworld":
        return world_dir / "region"
    if dimension == "minecraft:the_nether":
        return world_dir / "DIM-1" / "region"
    if dimension == "minecraft:the_end":
        return world_dir / "DIM1" / "region"
    raise ValueError(f"不支持的维度: {dimension}")


def chunk_ranges(start, end, width):
    result = []
    current = start
    while current <= end:
        result.append((current, min(current + width - 1, end)))
        current += width
    return result


def location_entry_exists(region_dir: Path, chunk_x: int, chunk_z: int) -> bool:
    region_x, local_x = divmod(chunk_x, 32)
    region_z, local_z = divmod(chunk_z, 32)
    path = region_dir / f"r.{region_x}.{region_z}.mca"
    try:
        with path.open("rb") as f:
            f.seek(4 * (local_x + local_z * 32))
            entry = f.read(4)
        if len(entry) != 4:
            return False
        offset = (entry[0] << 16) | (entry[1] << 8) | entry[2]
        return offset != 0
    except FileNotFoundError:
        return False


def saved_count(region_dir: Path, xs: int, xe: int, zs: int, ze: int) -> int:
    count = 0
    for cz in range(zs, ze + 1):
        for cx in range(xs, xe + 1):
            if location_entry_exists(region_dir, cx, cz):
                count += 1
    return count


def start_server(server_dir: Path, log_callback=None):
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        ["java", "-Xmx2G", "-Xms1G", "-jar", "server.jar", "nogui"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        cwd=str(server_dir),
        creationflags=creation_flags,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if log_callback:
        def read_output():
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        log_callback(line[:180])
            except:
                pass
        import threading
        threading.Thread(target=read_output, daemon=True).start()
    return proc


def pregenerate_chunks(rcon, dimension: str, min_chunk: int, max_chunk: int, region_dir: Path,
                       running_check=None, log_callback=None, min_free_gb: float = None):
    region_dir.mkdir(parents=True, exist_ok=True)
    dim_prefix = get_dimension_prefix(dimension)
    x_width, z_height = 20, 8
    x_ranges = chunk_ranges(min_chunk, max_chunk, x_width)
    z_ranges = chunk_ranges(min_chunk, max_chunk, z_height)
    batches = [(xs, xe, zs, ze) for zs, ze in z_ranges for xs, xe in x_ranges]
    total_batches = len(batches)
    min_free_bytes = int(min_free_gb * 1024 ** 3) if min_free_gb and min_free_gb > 0 else None

    disk = shutil.disk_usage(region_dir)
    if log_callback:
        log_callback(f"将分 {total_batches} 个批次生成 (每批 {x_width}×{z_height}={x_width*z_height} 区块)")
        if min_free_bytes:
            log_callback(f"磁盘剩余空间: {disk.free / 1024**3:.1f} GB (最低阈值 {min_free_gb} GB)")
        else:
            log_callback(f"磁盘剩余空间: {disk.free / 1024**3:.1f} GB (无最低空间限制)")
    if min_free_bytes and disk.free < min_free_bytes:
        raise RuntimeError(f"磁盘剩余空间不足: {disk.free / 1024**3:.1f} GB < {min_free_gb} GB")

    total_saved = 0
    for num, (xs, xe, zs, ze) in enumerate(batches, 1):
        if running_check and not running_check():
            return False
        if min_free_bytes:
            disk = shutil.disk_usage(region_dir)
            if disk.free < min_free_bytes:
                raise RuntimeError(f"磁盘剩余空间不足 ({disk.free / 1024**3:.1f} GB)，预生成已中止")
        expected = (xe - xs + 1) * (ze - zs + 1)
        before_count = saved_count(region_dir, xs, xe, zs, ze)
        count = before_count
        if count < expected:
            if log_callback:
                log_callback(f"批次 {num}/{total_batches}: 区块 {xs}..{xe},{zs}..{ze} (已保存: {count}/{expected})")
            bx1, bz1 = xs * 16, zs * 16
            bx2, bz2 = xe * 16 + 15, ze * 16 + 15
            add_cmd = f"{dim_prefix}forceload add {bx1} {bz1} {bx2} {bz2}"
            remove_cmd = f"{dim_prefix}forceload remove {bx1} {bz1} {bx2} {bz2}"

            for attempt in range(3):
                try:
                    rcon.command("list", retries=1)
                    break
                except Exception as e:
                    if attempt < 2:
                        if log_callback:
                            log_callback(f"  RCON 连接异常，尝试重连... (尝试 {attempt+1}/3)")
                        time.sleep(5)
                        try:
                            rcon._connect()
                        except:
                            pass
                    else:
                        raise

            if log_callback:
                log_callback("  发送 forceload 命令...")
            rcon.command(add_cmd, retries=2)
            start_time = time.monotonic()
            last_save = 0
            last_report = 0
            while count < expected:
                if running_check and not running_check():
                    return False
                now = time.monotonic()
                elapsed = int(now - start_time)
                if elapsed > 900:
                    raise RuntimeError(f"批次 {num} 超时 ({elapsed}s)")
                if now - last_save >= 10:
                    try:
                        rcon.command("save-all flush", retries=1)
                        last_save = now
                    except:
                        pass
                count = saved_count(region_dir, xs, xe, zs, ze)
                if now - last_report >= 20:
                    if log_callback:
                        log_callback(f"  进度: {count}/{expected}, {elapsed}s")
                    last_report = now
                time.sleep(4)
            try:
                rcon.command("save-all flush", retries=2)
                time.sleep(2)
                rcon.command(remove_cmd, retries=2)
            except:
                if log_callback:
                    log_callback("  警告: forceload remove 命令失败，继续下一批...")
            time.sleep(3)
            total_saved += expected - before_count
        else:
            if log_callback:
                log_callback(f"批次 {num}/{total_batches}: 已存在 {count}/{expected}，跳过")
        total_expected = (max_chunk - min_chunk + 1) ** 2
        if num % 5 == 0 or num == total_batches:
            if log_callback:
                log_callback(f"总进度: {total_saved}/{total_expected} 区块 ({num}/{total_batches} 批次完成)")
    return True


def unpack_indices(data, palette_size):
    bits = max(4, (palette_size - 1).bit_length())
    mask = (1 << bits) - 1
    vpl = 64 // bits
    values = []
    for i in range(4096):
        li, slot = divmod(i, vpl)
        off = slot * bits
        val = (data[li] & ((1 << 64) - 1)) >> off
        values.append(val & mask)
    return values


def scan_chunk(data: bytes, cx: int, cz: int, target_ids: set):
    root = nbtlib.File.parse(io.BytesIO(data))
    positions = []
    for section in root.get("sections", []):
        bs = section.get("block_states")
        if not bs:
            continue
        palette = bs.get("palette", [])
        target_indices = set()
        for idx, state in enumerate(palette):
            if str(state.get("Name")) in target_ids:
                target_indices.add(idx)
        if not target_indices:
            continue
        sy = int(section.get("Y", 0))
        packed = bs.get("data")
        if packed is None:
            indices = [0] * 4096
        else:
            indices = unpack_indices([int(v) for v in packed], len(palette))
        for i, pidx in enumerate(indices):
            if pidx not in target_indices:
                continue
            lx = i & 15
            lz = (i >> 4) & 15
            ly = (i >> 8) & 15
            wx = cx * 16 + lx
            wy = sy * 16 + ly
            wz = cz * 16 + lz
            positions.append((wx, wy, wz, str(palette[pidx]["Name"])))
    return positions


def read_chunk_payload(f, sector_offset):
    f.seek(sector_offset * 4096)
    length_data = f.read(4)
    if len(length_data) != 4:
        return None
    length = struct.unpack(">i", length_data)[0]
    if length <= 0:
        return None
    comp = f.read(1)[0]
    payload = f.read(length - 1)
    if comp == 1:
        return gzip.decompress(payload)
    elif comp == 2:
        return zlib.decompress(payload)
    elif comp == 3:
        return payload
    return None


def scan_region(path: Path, min_chunk: int, max_chunk: int, target_ids: set, error_callback=None):
    positions = []
    parts = path.stem.split(".")
    rx, rz = int(parts[1]), int(parts[2])
    try:
        with path.open("rb") as f:
            header = f.read(4096)
            if len(header) != 4096:
                return positions
            for lz in range(32):
                cz = rz * 32 + lz
                if not min_chunk <= cz <= max_chunk:
                    continue
                for lx in range(32):
                    cx = rx * 32 + lx
                    if not min_chunk <= cx <= max_chunk:
                        continue
                    entry_offset = 4 * (lx + lz * 32)
                    sector_offset = (header[entry_offset] << 16) | (header[entry_offset + 1] << 8) | header[entry_offset + 2]
                    if sector_offset == 0:
                        continue
                    payload = read_chunk_payload(f, sector_offset)
                    if payload:
                        positions.extend(scan_chunk(payload, cx, cz, target_ids))
    except Exception as e:
        if error_callback:
            error_callback(f"读取 {path.name} 时出错: {e}")
    return positions


def scan_all_regions(region_dir: Path, min_chunk: int, max_chunk: int, target_ids: set,
                     running_check=None, log_callback=None):
    positions = []
    region_min = min_chunk // 32 - 1
    region_max = max_chunk // 32 + 1
    regions_scanned = 0
    total_regions = (region_max - region_min + 1) ** 2
    for rz in range(region_min, region_max + 1):
        for rx in range(region_min, region_max + 1):
            if running_check and not running_check():
                return positions
            rpath = region_dir / f"r.{rx}.{rz}.mca"
            if not rpath.exists():
                continue
            regions_scanned += 1
            positions.extend(scan_region(rpath, min_chunk, max_chunk, target_ids))
            if regions_scanned % 5 == 0:
                if log_callback:
                    log_callback(f"扫描 region: {regions_scanned}/{total_regions}, 找到 {len(positions)} 个矿物")
    return positions
