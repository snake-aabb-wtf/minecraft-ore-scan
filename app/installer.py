import urllib.request
import json
from pathlib import Path
from .constants import MANIFEST_URL, RCON_PASSWORD, RCON_PORT, VERSION_TYPE_OPTIONS


def fetch_versions(version_type="release"):
    valid_types = {version_type for version_type, _ in VERSION_TYPE_OPTIONS}
    if version_type not in valid_types:
        raise ValueError(f"不支持的版本类型: {version_type}")

    with urllib.request.urlopen(MANIFEST_URL, timeout=30) as resp:
        manifest = json.loads(resp.read().decode("utf-8"))
    versions = [v for v in manifest["versions"] if v["type"] == version_type]
    return manifest, versions


def download_server(server_dir: Path, version_id: str, manifest: dict, progress_callback=None):
    server_dir.mkdir(parents=True, exist_ok=True)
    server_jar = server_dir / "server.jar"

    version_info = next((v for v in manifest["versions"] if v["id"] == version_id), None)
    if not version_info:
        raise RuntimeError(f"找不到版本 {version_id}")

    with urllib.request.urlopen(version_info["url"], timeout=30) as resp:
        version_data = json.loads(resp.read().decode("utf-8"))

    server_url = version_data["downloads"]["server"]["url"]
    server_size = version_data["downloads"]["server"]["size"]

    if progress_callback:
        def reporthook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            pct = min(100, int(downloaded * 100 / total_size))
            progress_callback(pct, downloaded, total_size)
        urllib.request.urlretrieve(server_url, server_jar, reporthook=reporthook)
    else:
        urllib.request.urlretrieve(server_url, server_jar)

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
