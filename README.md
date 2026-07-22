# Minecraft 矿物扫描器

Minecraft Ore Scan 是一个面向 Windows 的 Python/Tkinter 桌面工具，用于扫描 Minecraft Java 原版服务端生成的世界区块，并将指定矿物方块的世界坐标导出为按距离排序的 Excel 文件。

工具的主入口是根目录的 main.py。GUI 将服务端安装、世界生成、Anvil region 文件扫描和 Excel 导出串联为一条流水线。扫描结果来自服务端实际保存的方块状态，不依赖矿物是否暴露在空气中，也不尝试推断矿脉或玩家可见性。

## 主要能力

- 从 Mojang 官方版本清单获取 release 版本，并下载对应的原版 server.jar。
- 按 seed 和区块半径创建或复用服务端世界。
- 通过本机 Source RCON 分批执行 forceload，等待目标区块写入 Anvil region 文件。
- 直接解析 .mca 文件中的区块 payload、NBT、section、block_states.palette 和 block_states.data。
- 支持主世界、下界和末地的 region 路径及 RCON 维度命令。
- 按指定三维原点计算欧氏距离，并以稳定排序写入 Excel。
- 使用 openpyxl 的 write-only 模式导出，超过单 worksheet 数据行限制时自动拆分工作表。
- 在预生成开始前和批次之间检查最低剩余磁盘空间。
- RCON 命令失败时支持有限次数的重新连接和重试。

## 系统要求

当前实现以 Windows 为目标平台。

- Windows。
- Python 3.10 或更高版本。
- Java JRE 或 JDK，并且 java 命令位于 PATH 中。
- 支持 Tkinter 的 Python 安装。
- Python 依赖：
  - nbtlib 2.0.0 或更高版本
  - openpyxl 3.1.0 或更高版本

安装依赖：

    python -m pip install -r requirements.txt

启动程序：

    python main.py

也可以运行根目录下的 启动程序.bat。批处理文件会切换到自身所在目录，检查 nbtlib 和 openpyxl 是否可以导入，并在缺少依赖时执行 requirements.txt 安装。

## 运行目录和生成文件

源码运行时，程序目录为仓库根目录；如果以打包形式运行，程序目录为可执行文件所在目录。程序使用以下目录布局：

    <程序目录>/
    ├── Minecraft/
    │   └── <Minecraft 版本>/
    │       ├── server.jar
    │       ├── eula.txt
    │       ├── server.properties
    │       └── world/
    └── <输出 Excel 文件>

Minecraft 服务端安装目录由 GUI 自动创建。服务端世界位于具体版本目录内，而不是仓库根目录下的 world/。

以下内容由程序生成，并已在 .gitignore 中排除：

- Minecraft/ 服务端目录
- world/ 和 world_backup_*/ 世界目录
- server.jar、eula.txt、server.properties
- 日志文件
- .xlsx 和 .xls 输出文件

不要将真实世界、服务端 JAR、服务端配置或扫描结果强制加入 Git。

## 使用流程

### 1. 安装服务端

首次启动时，如果 Minecraft/ 下没有包含 server.jar 的版本目录，程序会显示服务端安装向导。

向导通过以下 Mojang API 获取版本清单：

    https://launchermeta.mojang.com/mc/game/version_manifest_v2.json

程序只显示 release 类型版本的前 50 项。选择版本后，程序读取该版本详情中的 server 下载地址，将 JAR 写入 Minecraft/<version>/server.jar，并生成默认的 eula.txt 和 server.properties。

当前下载流程没有对 JAR 执行 SHA-1 校验。生产或大范围扫描前，应自行确认下载文件来源、大小和完整性。

### 2. 配置扫描参数

主页面提供以下参数：

| 参数 | 含义和约束 |
| --- | --- |
| 世界种子 | 空值表示不指定新 seed；非空值会在已有世界存在时先备份该世界 |
| 目标维度 | minecraft:overworld、minecraft:the_nether 或 minecraft:the_end |
| 区块半径 | GUI 范围为 1 到 500，实际扫描范围为 -radius..radius-1 |
| 原点坐标 | 形式为 X,Y,Z，三个值都必须是整数 |
| 输出 Excel | 输出文件名或路径；GUI 以程序目录为相对基准 |
| 目标矿物 | 按当前维度显示可选矿物，匹配使用 block ID |
| 磁盘空间阈值 | 最低剩余空间，单位为 GB；空值或非正数表示不限制，默认 8 GB |

半径的实际区块数量为：

    side = 2 * radius
    total_chunks = side * side

例如 radius=50 对应区块坐标 -50..49，即 100×100 个区块。

如果服务端目录中已经存在 world/：

- seed 非空：将现有目录重命名为 world_backup_<Unix 时间戳>，随后创建新世界。
- seed 为空：复用现有世界。
- server.properties 中的 level-seed 不会覆盖已有 level.dat 的世界 seed。

### 3. 自动执行扫描流水线

点击开始扫描后，后台线程依次执行：

1. 切换到具体服务端目录，并检查 server.jar。
2. 更新 server.properties。
3. 启动无界面服务端。
4. 通过 RCON 连续确认服务端已经就绪。
5. 分批强制加载目标区块，等待区块写入 region 文件。
6. 保存并停止服务端。
7. 扫描已经保存的 region 文件。
8. 计算距离、排序并导出 Excel。
9. 恢复工作目录，关闭 RCON，回收服务端进程并恢复 GUI 状态。

GUI 的网络、Java、RCON、区块生成、文件扫描和 Excel 写入都在后台线程执行。停止操作通过取消标志和 RCON stop 尝试进行；对于正在执行的批次，服务端退出可能需要等待当前操作完成。

## 服务端配置

安装或扫描前，程序会写入或覆盖以下关键属性：

| 属性 | 当前值 | 用途 |
| --- | --- | --- |
| server-port | 25565 | Minecraft 服务端端口 |
| enable-rcon | true | 启用 RCON |
| rcon.password | ore_scan_local | GUI 使用的临时密码 |
| rcon.port | 25575 | RCON 端口 |
| online-mode | false | 离线模式生成本地扫描世界 |
| gamemode | spectator | 默认游戏模式 |
| difficulty | peaceful | 默认难度 |
| spawn-protection | 0 | 关闭出生点保护 |
| max-players | 1 | 最大玩家数 |
| view-distance | 10 | 服务端视距 |
| simulation-distance | 10 | 模拟距离 |

服务端使用以下命令启动：

    java -Xmx2G -Xms1G -jar server.jar nogui

RCON 密码是源码中的固定默认值，不是安全凭据。该服务端只应在本机临时运行，不要将 RCON 或 Minecraft 端口暴露到公网。扫描结束后应检查服务端配置，按需要关闭 RCON 或恢复正常服务端配置。

## 支持的维度和矿物

矿物匹配使用原始 Minecraft block ID；中文名称只用于 GUI 和 Excel 展示。

### 主世界

- minecraft:diamond_ore：钻石矿
- minecraft:deepslate_diamond_ore：深板岩钻石矿
- minecraft:iron_ore：铁矿
- minecraft:deepslate_iron_ore：深层铁矿
- minecraft:gold_ore：金矿
- minecraft:deepslate_gold_ore：深层金矿
- minecraft:coal_ore：煤矿
- minecraft:deepslate_coal_ore：深层煤矿
- minecraft:copper_ore：铜矿
- minecraft:deepslate_copper_ore：深层铜矿
- minecraft:redstone_ore：红石矿
- minecraft:deepslate_redstone_ore：深层红石矿
- minecraft:lapis_ore：青金石矿
- minecraft:deepslate_lapis_ore：深层青金石矿
- minecraft:emerald_ore：绿宝石矿
- minecraft:deepslate_emerald_ore：深层绿宝石矿

GUI 默认选择：

    minecraft:diamond_ore
    minecraft:deepslate_diamond_ore

### 下界

- minecraft:ancient_debris：远古残骸
- minecraft:nether_quartz_ore：下界石英矿
- minecraft:nether_gold_ore：下界金矿

GUI 默认选择以上全部三种矿物。

### 末地

当前 END_ORES 为空，GUI 不提供常规矿物选项。若要扫描其他方块，必须同时修改 constants.py 中的维度矿物配置，并确认目标 Minecraft 版本实际存在对应 block ID。

## 技术实现

### 模块结构

    app/
    ├── constants.py   # 矿物列表、维度映射、API 和 RCON 常量
    ├── installer.py   # Mojang 版本清单、JAR 下载、服务端属性
    ├── rcon.py        # Source RCON 客户端和重连逻辑
    ├── world.py       # Java 进程、预生成、Anvil/NBT 扫描
    ├── excel.py       # 距离排序和 Excel 分表导出
    └── gui.py         # Tkinter 安装向导和扫描控制器

根目录 main.py 只负责创建 Tk 根窗口并启动 OreScanGUI。

### 维度目录

服务端世界的 region 目录按以下规则映射：

| 维度 ID | region 目录 |
| --- | --- |
| minecraft:overworld | world/region/ |
| minecraft:the_nether | world/DIM-1/region/ |
| minecraft:the_end | world/DIM1/region/ |

下界和末地的 RCON 命令会附加对应的 execute in <dimension> run 前缀，以确保 forceload 命令作用于目标维度。

### 区块预生成

GUI 将 radius 转换为：

    min_chunk = -radius
    max_chunk = radius - 1

app/world.py 使用 20×8 区块批次，即每批最多 160 个区块，低于 Minecraft /forceload 的 256 区块限制。每批的处理顺序为：

1. 通过 region location header 统计已经保存的区块。
2. 对未完成批次发送 forceload add。
3. 周期性发送 save-all flush。
4. 轮询目标区块的 location entry，直到全部出现非零 sector offset。
5. 再次执行保存，并发送 forceload remove。
6. 检查下一批次。

region 目录会在预生成开始时自动创建。磁盘剩余空间低于阈值时，预生成会抛出错误并停止。

### Anvil 文件定位

Anvil region 文件的命名格式为 r.<regionX>.<regionZ>.mca。每个文件包含最多 32×32 个区块，sector 大小为 4096 字节。

区块坐标必须使用 Python 的 floor division 语义转换：

    region_x, local_x = divmod(chunk_x, 32)
    region_z, local_z = divmod(chunk_z, 32)

区块在 location table 中的条目偏移为：

    entry = 4 * (local_x + local_z * 32)

三字节 sector offset 使用大端序读取：

    offset = (header[entry] << 16) | (header[entry + 1] << 8) | header[entry + 2]

负坐标不能使用向零截断。例如：

    chunk=-1 -> region=-1, local=31
    chunk=0  -> region=0,  local=0

offset 为 0 表示该区块没有保存数据。扫描器只将 min_chunk..max_chunk 范围内的区块加入结果。

### 区块 NBT 和压缩

区块记录由以下部分组成：

1. 4 字节大端序 payload 长度。
2. 1 字节压缩类型。
3. 压缩或未压缩的 NBT payload。

支持的压缩类型：

| 类型 | 格式 |
| --- | --- |
| 1 | gzip |
| 2 | zlib |
| 3 | 未压缩 |

NBT 由 nbtlib 解析。扫描过程是只读的，不会将 NBT 写回 region 文件。服务端必须在保存完成并停止后再扫描，避免读到正在写入的 length、sector 或压缩 payload。

### block states 解码

扫描器遍历区块的 sections[]，读取每个 section 的 block_states.palette 和可选的 block_states.data。

首先遍历 palette，根据 Name 字段找出目标 block ID 对应的 palette index。如果当前 section 不包含目标 ID，则跳过该 section 的 4096 个方块。

当 block_states 没有 data 时，表示整个 section 使用 palette index 0。存在 data 时，使用 Minecraft 的固定 long 槽位规则：

    bits = max(4, (palette_size - 1).bit_length())
    mask = (1 << bits) - 1
    values_per_long = 64 // bits

    long_index, slot = divmod(index, values_per_long)
    offset = slot * bits
    value = (data[long_index] & ((1 << 64) - 1)) >> offset
    palette_index = value & mask

不能将所有 long 拼接为跨 long 的连续 bit stream。每个 long 只包含 64 // bits 个完整值，剩余 bit 不属于下一个值。NBT LongArray 可能以有符号整数表示，读取后必须先转换为无符号位模式再移位。

section index 到世界坐标的转换为：

    local_x = index & 15
    local_z = (index >> 4) & 15
    local_y = (index >> 8) & 15

    world_x = chunk_x * 16 + local_x
    world_y = section_y * 16 + local_y
    world_z = chunk_z * 16 + local_z

### 距离计算和 Excel 输出

每个扫描结果记录为：

    (world_x, world_y, world_z, block_id)

对原点 origin=(ox, oy, oz) 计算平方距离：

    distance_squared = (x - ox) ** 2 + (y - oy) ** 2 + (z - oz) ** 2

排序键为：

    (distance_squared, y, x, z)

Excel 中显示实际距离 sqrt(distance_squared)。输出列为：

| 列 | 内容 |
| --- | --- |
| X | 方块世界 X 坐标 |
| Y | 方块世界 Y 坐标 |
| Z | 方块世界 Z 坐标 |
| Mineral | 矿物中文显示名 |
| DistanceTo_(ox,oy,oz) | 到指定三维原点的欧氏距离 |

每个矿物方块占一行，不合并相邻方块或矿脉。单个 worksheet 最多写入 1,048,575 行数据，另有一行表头；超过限制时创建 Minerals_2、Minerals_3 等 worksheet。输出使用 openpyxl 的 write-only 模式，以降低大型结果集的内存占用。

## 旧版命令行脚本

legacy/ 目录中的脚本保留早期固定任务和独立 CLI 实现：

- legacy/actual-run/：固定范围的预生成、钻石/远古残骸扫描和 Excel 处理脚本。
- legacy/generic/pregenerate.py：带 argparse 参数的通用区块预生成器。
- legacy/generic/scan_to_excel.py：带 argparse 参数的通用 Anvil 扫描和 Excel 导出器。
- legacy/references/ore-names.md：block ID 与显示名参考。

这些脚本不是 GUI 的导入依赖，默认批次、参数和错误处理与 app/ 下的当前实现可能不同。详细参数说明见 docs/说明文档.md；Anvil/NBT 算法背景见 docs/矿物扫描技术说明.md。

## 限制和风险

- 大范围预生成会产生大量服务端世界数据，并消耗较长时间、磁盘空间和内存。radius=500 对应 1000×1000 个区块，运行前必须确认资源充足。
- 预生成的是区块方形，不是任意方块多边形。区块边界内的所有方块都属于扫描范围。
- 扫描结果依赖世界已经生成并正确保存。日志中的预生成进度不应替代对 location table 的独立核验。
- 扫描结果是实际保存的方块状态，包含地下和不可见矿物，不等价于玩家能够直接发现的矿物。
- server.properties 的 seed 只对新建世界有效；已有 level.dat 不会因为重新写入 level-seed 而改变。
- 当前服务端下载不校验 SHA-1。
- RCON 使用固定默认密码和端口，且当前实现面向本机临时使用；不要将其暴露到公网。
- 仓库没有自动化测试套件、格式化配置、静态检查配置或 CI。修改扫描算法后应使用小型临时 world fixture 验证 region header、NBT 压缩、palette、packed long、负坐标和空结果。
- 当没有找到矿物时，导出器会创建只有表头的 Minerals_1；当前函数返回的 worksheet 数量统计可能显示为 0，这是现有实现边界。

## 开发和验证

建议在仓库根目录执行：

    python -m compileall -q .
    python -c "import tkinter, nbtlib, openpyxl; print('imports: OK')"
    git diff --check

修改范围建议：

- 修改 GUI 或线程流程时，保持耗时操作在后台线程，Tk 控件通过 root.after() 更新。
- 修改 Anvil/NBT 扫描逻辑时，保持负坐标 divmod 语义、固定 long 槽位解码和 section 坐标还原规则。
- 修改服务端配置时，不要把临时 RCON 密码写入日志或提交到 Git。
- 修改 Excel 导出时，验证零结果、排序、worksheet 行数边界和输出文件可被 openpyxl 重新打开。
- 新增 Python 依赖时同步修改 requirements.txt。
- 不要提交 Minecraft/、world/、world_backup_*/、*.xlsx、server.jar 或本地服务端配置。

## 项目文档

- [AGENTS.md](AGENTS.md)：面向开发者和代码代理的详细项目约束。
- [docs/说明文档.md](docs/说明文档.md)：历史任务、旧版 CLI 脚本和参数说明。
- [docs/矿物扫描技术说明.md](docs/矿物扫描技术说明.md)：Anvil region、NBT、packed block states 和距离排序的技术说明。
- [legacy/references/ore-names.md](legacy/references/ore-names.md)：矿物 block ID 与显示名映射。

## 许可证

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
