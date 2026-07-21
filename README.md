# Minecraft Ore Scan App

A GUI tool that automates Minecraft Java Edition world generation and ore scanning. Download Vanilla server → pre-generate chunks by seed → scan for ores → export to Excel — all in one automated pipeline.

> 🤖 This project was developed by **TRAE AI** (https://trae.ai) — an AI-powered IDE and coding assistant.

## Features

- 🖥️ **Graphical Interface** — No command line needed, everything configurable through GUI
- 📦 **Auto Server Download** — Select Minecraft version, auto-download Vanilla server jar from Mojang
- 🌍 **Custom World Generation** — Input any seed and chunk radius, automatically pre-generate the world
- ⛏️ **Ore Scanning** — Directly reads Anvil `.mca` region files, decodes NBT block states
- 📊 **Excel Export** — Distance-sorted ore coordinates (by Euclidean distance to origin), auto-split sheets over 1M rows
- 🔄 **Dimension Support** — Overworld, Nether, and The End (ore list auto-filters per dimension)
- 💾 **Disk Space Guard** — Configurable minimum free disk space threshold to prevent filling the drive
- 🔌 **RCON Integration** — Built-in RCON client with auto-reconnect for server control

## Supported Ores

| Dimension | Ores |
|-----------|------|
| Overworld | Diamond, Deepslate Diamond, Iron, Deepslate Iron, Gold, Deepslate Gold, Coal, Deepslate Coal, Copper, Deepslate Copper, Redstone, Deepslate Redstone, Lapis, Deepslate Lapis, Emerald, Deepslate Emerald |
| Nether | Ancient Debris, Nether Quartz Ore, Nether Gold Ore |
| The End | _(no overworld ores)_ |

## Requirements

- Python 3.10+
- Java Runtime Environment (JRE) — required to run the Minecraft server
- Python packages: `nbtlib`, `openpyxl` (install via `pip install -r requirements.txt`)

## Usage

1. Double-click `启动程序.bat` (or run `python main.py`)
2. On first launch, select a Minecraft version in the **Server Installation Wizard** and click install
3. Configure:
   - **World Seed** — leave empty for random
   - **Target Dimension** — Overworld / Nether / The End
   - **Chunk Radius** — square area centered at origin
   - **Origin Coordinates** — reference point for distance sorting
   - **Output Excel** — output filename (saved in the app directory)
   - **Select Ores** — check which ores to scan for
   - **Disk Space Threshold** — minimum free GB (default 8, leave empty for no limit)
4. Click **开始扫描** (Start Scan)
5. The pipeline runs automatically: download server → start server → pre-generate chunks → stop server → scan ores → export Excel

## Project Structure

```
Ore Scan App/
├── app/
│   ├── __init__.py
│   ├── constants.py      # Ore lists, dimension configs, constants
│   ├── rcon.py           # RCON client with auto-reconnect
│   ├── installer.py      # Minecraft server download & setup
│   ├── world.py          # Server process, chunk pregen, Anvil scanning
│   ├── excel.py          # Excel export with auto-split sheets
│   └── gui.py            # Tkinter GUI (wizard + main panel + management)
├── docs/                 # Documentation (Chinese)
├── legacy/               # Original reference scripts
├── Minecraft/            # Server installations (git-ignored)
├── main.py               # Entry point
├── requirements.txt
└── 启动程序.bat          # Launcher script
```

## How It Works

1. **Server Download**: Queries Mojang's version manifest API, downloads the official `server.jar`
2. **World Generation**: Starts the server in headless mode, uses RCON `/forceload` commands in batches to generate chunks, verifies chunk files exist on disk
3. **Ore Scanning**: Reads `.mca` (Anvil) region files directly:
   - Parses region headers to locate chunk sector offsets
   - Decompresses zlib/gzip chunk NBT data
   - Decodes packed block states using correct Minecraft bit-packing rules (no cross-long-boundary splits)
   - Matches palette indices against target block IDs
   - Calculates world coordinates from chunk + section + local positions
4. **Excel Export**: Sorts ores by distance to origin, writes via openpyxl write-only mode, auto-creates new sheets when exceeding Excel's 1,048,575 row limit

## License

MIT License — see [LICENSE](LICENSE) file for details.
