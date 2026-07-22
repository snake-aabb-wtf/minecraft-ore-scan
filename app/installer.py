import hashlib
import json
import urllib.request
from pathlib import Path
from .constants import MANIFEST_URL, RCON_PASSWORD, RCON_PORT, VERSION_TYPE_OPTIONS


SERVER_DOWNLOAD_ATTEMPTS = 3


def fetch_versions(version_type="release"):
    valid_types = {version_type for version_type, _ in VERSION_TYPE_OPTIONS}
    if version_type not in valid_types:
        raise ValueError(f"不支持的版本类型: {version_type}")

    with urllib.request.urlopen(MANIFEST_URL, timeout=30) as resp:
        manifest = json.loads(resp.read().decode("utf-8"))
    versions = [v for v in manifest["versions"] if v["type"] == version_type]
    return manifest, versions


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_if_exists(path: Path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def download_server(server_dir: Path, version_id: str, manifest: dict, progress_callback=None):
    server_dir.mkdir(parents=True, exist_ok=True)
    server_jar = server_dir / "server.jar"
    partial_jar = server_dir / "server.jar.part"

    version_info = next((v for v in manifest["versions"] if v["id"] == version_id), None)
    if not version_info:
        raise RuntimeError(f"找不到版本 {version_id}")

    with urllib.request.urlopen(version_info["url"], timeout=30) as resp:
        version_data = json.loads(resp.read().decode("utf-8"))

    server_download = version_data.get("downloads", {}).get("server")
    if not server_download:
        raise RuntimeError(f"版本 {version_id} 没有可用的 server.jar 下载信息")

    server_url = server_download["url"]
    server_size = server_download["size"]
    expected_sha1 = server_download.get("sha1")
    if not expected_sha1:
        raise RuntimeError(f"版本 {version_id} 的 server.jar 缺少 Mojang SHA-1 校验值")

    for attempt in range(1, SERVER_DOWNLOAD_ATTEMPTS + 1):
        _remove_if_exists(partial_jar)
        try:
            if progress_callback:
                def reporthook(block_num, block_size, total_size):
                    downloaded = block_num * block_size
                    pct = min(100, int(downloaded * 100 / total_size))
                    progress_callback(pct, downloaded, total_size)
                urllib.request.urlretrieve(server_url, partial_jar, reporthook=reporthook)
            else:
                urllib.request.urlretrieve(server_url, partial_jar)

            actual_sha1 = _sha1_file(partial_jar)
            if actual_sha1.lower() != expected_sha1.strip().lower():
                _remove_if_exists(server_jar)
                raise RuntimeError(
                    f"server.jar SHA-1 校验失败 (expected={expected_sha1}, actual={actual_sha1})"
                )

            partial_jar.replace(server_jar)
            break
        except Exception as e:
            _remove_if_exists(partial_jar)
            if attempt == SERVER_DOWNLOAD_ATTEMPTS:
                raise RuntimeError(
                    f"server.jar 下载或 SHA-1 校验失败，已尝试 {SERVER_DOWNLOAD_ATTEMPTS} 次: {e}"
                ) from e

    write_eula(server_dir)
    write_default_properties(server_dir)
    return server_size


def write_eula(server_dir: Path):
    with open(server_dir / "eula.txt", "w", encoding="utf-8") as f:
        f.write("eula=true\n")


def write_default_properties(server_dir: Path):
    props = {
        "server-port": "25565",
        "enable-rcon": "true",
        "rcon.password": RCON_PASSWORD,
        "rcon.port": str(RCON_PORT),
        "online-mode": "false",
        "gamemode": "spectator",
        "difficulty": "peaceful",
        "spawn-protection": "0",
        "max-players": "1",
        "view-distance": "10",
        "simulation-distance": "10",
    }
    with open(server_dir / "server.properties", "w", encoding="utf-8") as f:
        for k, v in props.items():
            f.write(f"{k}={v}\n")


def update_server_properties(props_path: Path, seed: str):
    props = {}
    if props_path.exists():
        with open(props_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    props[k] = v
    props["level-seed"] = seed
    props["enable-rcon"] = "true"
    props["rcon.password"] = RCON_PASSWORD
    props["rcon.port"] = str(RCON_PORT)
    props["online-mode"] = "false"
    with open(props_path, "w", encoding="utf-8") as f:
        for k, v in props.items():
            f.write(f"{k}={v}\n")


def find_installed_servers(minecraft_dir: Path):
    servers = []
    if minecraft_dir.exists():
        for d in minecraft_dir.iterdir():
            if d.is_dir() and (d / "server.jar").exists():
                servers.append(d)
    return servers
