# AGENTS.md

本文件是 minecraft-ore-scan 仓库的项目级开发说明，供后续开发者和代码代理使用。除非用户明确要求改变行为，否则应以当前源码为准，并保持本文件描述的运行边界和数据不变量。

## 1. 项目定位

这是一个面向 Windows 的 Python/Tkinter 桌面工具，用于扫描 Minecraft Java 原版服务端生成的矿物方块。GUI 会把以下步骤串成一条流水线：

1. 从 Mojang 官方版本清单获取 release 或 snapshot 版本。
2. 下载指定版本的原版 server.jar，并在 Minecraft/<version>/ 下准备服务端目录。
3. 按用户输入的 seed 启动服务端，通过本机 RCON 分批使用 forceload 预生成区块。
4. 等待 Anvil region 文件的 location header 表明目标区块已经保存。
5. 停止服务端后，直接读取 .mca 文件，解压区块 NBT 并匹配目标矿物 block ID。
6. 将世界坐标按距离原点排序，写入一个或多个 Excel worksheet。

项目的主要使用入口是根目录的 main.py。legacy/ 下的脚本是早期固定任务和通用命令行脚本的参考实现，不是 GUI 的导入依赖，也不应在没有明确需求时当作当前主流程修改。

## 2. 仓库边界和目录结构

实际 Git 仓库根目录是当前文件所在目录 minecraft-ore-scan，不是其父目录 F:\Scan Ore。

    minecraft-ore-scan/
    ├── app/
    │   ├── __init__.py       # 包导出
    │   ├── constants.py      # 矿物、维度、Mojang API、RCON 常量
    │   ├── excel.py          # GUI 使用的 Excel 导出器
    │   ├── gui.py            # Tkinter 安装向导、扫描面板、服务端管理
    │   ├── installer.py      # 版本清单、server.jar 下载、服务端属性
    │   ├── rcon.py           # 带重连的 Source RCON 客户端
    │   └── world.py          # 服务端进程、预生成、Anvil/NBT 扫描
    ├── docs/
    │   ├── 说明文档.md       # 历史任务和通用脚本说明
    │   └── 矿物扫描技术说明.md # Anvil/NBT 和位打包算法说明
    ├── legacy/
    │   ├── actual-run/       # 早期固定范围脚本
    │   ├── generic/          # 早期通用 CLI 预生成/扫描脚本
    │   └── references/       # 矿物 ID 与显示名参考
    ├── main.py               # GUI 程序入口
    ├── requirements.txt      # Python 运行依赖
    ├── start.bat             # Windows 启动器，创建/检查 .venv、安装依赖后运行 main.py
    ├── README.md             # 面向用户的简介和使用说明
    ├── LICENSE               # MIT License
    └── .gitignore            # 生成物、服务端目录和本地配置忽略规则

以下内容通常不会进入 Git：Minecraft/、world/、world_backup_*/、日志、*.xlsx、server.jar、eula.txt 和 server.properties。这些文件可能很大，且其中可能包含本地世界、密码或服务端配置；不要为了方便调试而强制加入版本控制。

## 3. 环境和启动

### 3.1 必需环境

- Windows 是当前支持的主要平台。world.start_server() 使用 subprocess.CREATE_NO_WINDOW，并假设 java 可直接在 PATH 中调用。
- Python 3.10 或更高版本。
- Java JRE/JDK，Minecraft 原版服务端启动和世界生成都需要它。
- Python 依赖：nbtlib>=2.0.0、openpyxl>=3.1.0。
- GUI 使用标准库 Tkinter；Windows 的 Python 安装应包含 Tk 支持。

### 3.2 安装和运行

在仓库根目录执行：

    python -m pip install -r requirements.txt
    python main.py

也可以双击 start.bat。脚本会切换到自身所在目录，检查 .venv 是否存在；不存在时使用系统 Python 创建。之后使用虚拟环境的 Python 检查 nbtlib 和 openpyxl，缺少时运行 pip install -r requirements.txt，然后启动 GUI。

首次启动没有已安装的服务端时显示安装向导。版本清单来自：

    https://launchermeta.mojang.com/mc/game/version_manifest_v2.json

向导提供 Release（正式版）和 Snapshot（快照版）选择，并展示所选类型的全部版本；下载时使用完整 manifest 查找选中的版本。下载后的服务端目录通常为 Minecraft/<version>/，其中至少包含 server.jar、eula.txt 和 server.properties。

## 4. GUI 的真实运行流程

### 4.1 启动路径

main.py 创建 tkinter.Tk，设置 Windows DPI 感知，然后实例化 OreScanGUI。OreScanGUI 的程序目录规则为：

- 打包运行时：使用 sys.executable 所在目录。
- 源码运行时：使用仓库根目录。

所以服务端目录是 <程序目录>/Minecraft，Excel 输出目录是 <程序目录>，不是当前 PowerShell 的任意工作目录。current_server_dir 指向具体版本目录。

启动时如果 Minecraft 下存在任何包含 server.jar 的子目录，就选取发现列表中的第一个作为当前服务端；否则显示安装页。服务端管理页可以在已发现的目录之间切换，或回到安装页安装新版本。

### 4.2 扫描参数

主页面收集以下配置：

- seed：空字符串表示不指定新 seed；非空 seed 会触发已有 world/ 目录的备份重命名。
- dimension：minecraft:overworld、minecraft:the_nether 或 minecraft:the_end。
- radius：GUI 允许 1 到 500。实际区块范围是 -radius..radius-1，因此边长为 2 * radius，默认半径 50 代表 100×100 个区块。
- origin：逗号分隔的 X,Y,Z，用于三维欧氏距离排序。代码按整数解析，必须提供三个整数。
- output：输出文件名/路径。当前 GUI 将它与程序目录拼接；不要输入会覆盖源码或重要文件的路径。
- ores：当前维度的目标矿物 block ID 集合。
- min_free_gb：最低剩余磁盘空间，空白或非正数表示不限制；默认值为 8 GB。

矿物列表由 constants.py 按维度切换。主世界默认选择钻石矿和深板岩钻石矿；下界默认选择远古残骸、下界石英矿和下界金矿；末地当前没有可选矿物。

### 4.3 _run_pipeline 顺序

扫描线程执行下列操作，Tk 控件更新通过 root.after() 回到 GUI 线程：

1. 保存原始当前目录，并切换到具体服务端目录。服务端相对路径、world/ 和日志都以该目录为基准。
2. 检查 server.jar 是否存在。
3. 更新 server.properties：写入 level-seed、开启 RCON、设置固定本机密码/端口，并将 online-mode 设为 false。
4. 如果已有 world/ 且 seed 非空，则把它重命名为 world_backup_<Unix 时间戳>；如果 seed 为空，则复用已有世界。server.properties 中的 seed 不会覆盖已有 level.dat 的世界 seed。
5. 使用 Java 启动：

       java -Xmx2G -Xms1G -jar server.jar nogui

6. 最多等待约 180 次轮询，每次间隔 3 秒。RCON 连续成功至少两次后，发送 seed 验证服务端可用，并额外等待 15 秒稳定服务端。
7. 调用 pregenerate_chunks()。每批默认 20×8=160 个区块，低于 Minecraft /forceload 的 256 区块限制。流程是加入强制加载、周期性 save-all flush、轮询 region location header、移除强制加载。
8. 预生成完成后再次保存，发送 stop，等待服务端退出；服务端没有按时退出时会被终止。
9. 调用 scan_all_regions() 扫描目标区块，然后调用 export_to_excel() 排序并写出 Excel。
10. 无论成功、异常还是取消，恢复原始当前目录，停止/清理服务端进程并恢复按钮状态。

点击“停止”只会设置取消标志并异步尝试 RCON stop；当前批次的阻塞操作结束前，UI 不能立即保证服务端已经退出。开发时必须保留这种有序关闭路径，避免 Java 仍在写 region 文件时开始扫描。

## 5. 模块职责和修改边界

### app/constants.py

这里集中维护 UI 和扫描器共享的配置：

- ALL_ORES 是完整候选列表；每一项是 (Minecraft block ID, Excel 显示名)。
- OVERWORLD_ORES、NETHER_ORES、END_ORES 是按维度筛选后的列表。
- DIMENSION_DEFAULT_ORES 控制 GUI 初始勾选项。
- DIMENSIONS 控制维度选择项。
- MANIFEST_URL、RCON_PASSWORD、RCON_PORT 控制服务端安装和连接。

匹配必须使用原始 block ID，例如 minecraft:diamond_ore；中文名称只用于 UI/Excel 展示。添加矿物时必须同时考虑目标 Minecraft 版本、所在维度和默认勾选行为，不要只修改显示文本。

### app/installer.py

负责网络请求和服务端配置：

- fetch_versions(version_type) 下载 Mojang manifest，并按 release 或 snapshot 过滤版本。
- download_server() 解析版本详情中的 server 下载 URL，通过 urllib.request.urlretrieve() 写入 server.jar，随后写入 EULA 和默认属性。
- update_server_properties() 读取现有 key=value，丢弃注释/空行格式，覆盖本工具要求的属性后整体重写文件。
- find_installed_servers() 只通过子目录中是否存在 server.jar 判断“已安装”。

当前下载流程没有对下载的 JAR 执行 SHA-1 校验。若修改安装流程，应优先使用 Mojang manifest 中的 hash/size 元数据增加校验，并保留失败时不启动损坏服务端的行为。

### app/rcon.py

RconClient 实现 Source RCON 的最小客户端：小端序 packet header、认证、命令收发、完整读取 socket、超时/断连重连。command(cmd, retries=2) 会在失败后重新连接并重试。

注意事项：

- 当前密码是代码中的固定常量 ore_scan_local，只适合作为本机临时生成任务的默认值，不是安全凭据。
- 不要把 RCON 端口暴露到公网，也不要在日志中打印密码。
- 如果修改 packet 逻辑，必须保留完整 recv 语义，不能假设一次 recv() 就返回完整数据包。
- 与 Tkinter 控件交互无关；RCON 网络调用必须放在后台线程，避免冻结 GUI。

### app/world.py

这是核心模块，包含三类逻辑：

1. 服务端进程管理：start_server() 固定使用 Java、2 GB 最大堆和 nogui。
2. 区块预生成：pregenerate_chunks() 以区块坐标分批发送带维度前缀的 forceload 命令，并通过磁盘阈值和 Anvil location header 检查进度。
3. 只读扫描：解析 region 文件、压缩区块 payload、NBT sections 和 packed block states。

维度目录必须保持以下映射：

    minecraft:overworld  -> world/region/
    minecraft:the_nether -> world/DIM-1/region/
    minecraft:the_end    -> world/DIM1/region/

不要把服务端的 world/ 根目录误当成所有维度共用的 region/ 目录。下界和末地的 RCON 命令还必须加上 execute in <dimension> run 前缀。

### app/excel.py

export_to_excel() 接受 (x, y, z, block_id) 记录，计算距离平方，按以下键排序：

    (distance_squared, y, x, z)

输出列顺序固定为：

    X | Y | Z | Mineral | DistanceTo_(originX,originY,originZ)

使用 openpyxl.Workbook(write_only=True)，每个 worksheet 写入一行表头和最多 1,048,575 行数据，超过限制时创建 Minerals_2、Minerals_3 等。每个矿物方块占一行，不合并矿脉。

当前一个边界行为是：当 positions 为空时，文件仍会创建带表头的 Minerals_1，但函数返回的 sheets_count 为 0，GUI 日志可能显示“0 个工作表”。修改导出器时要明确决定是否修正这个返回值，并同步验证空结果场景。

### app/gui.py

GUI 负责状态、参数采集、线程调度和用户提示，不应重复实现服务端、NBT 或 Excel 算法。当前约定是：

- 任何网络、Java、RCON、预生成、region 扫描和 Excel 大量写入都放在后台线程。
- 工作线程不能直接操作 Tk 控件；用 root.after(0, callback) 更新控件或弹窗。
- self.running 是取消和收尾逻辑共享的状态。新增长耗时循环时必须定期检查它。
- 异常在工作线程边界统一记录 traceback，并通过 root.after() 给用户提示。
- 页面切换由 _clear_container() 统一清理当前容器中的控件。

### legacy/

legacy/actual-run/ 保存固定范围的主世界/下界预生成、钻石/远古残骸扫描和 OOXML 文本替换脚本；legacy/generic/ 保存带 argparse 的独立 CLI 脚本。它们有自己的默认值和部分重复实现，例如旧版预生成批次默认 25×10，而 GUI 核心使用 20×8。

修改 legacy 脚本时不要默认同步修改 app/；只有当用户明确要求兼容旧 CLI 或修复共同算法时才跨目录变更。历史文档中的旧路径、固定范围和固定输出名不应被当作 GUI 当前行为。

## 6. Anvil/NBT 必须保持的不变量

这些规则是扫描正确性的核心，修改 world.py 或 legacy 扫描器时必须针对它们验证。

### 6.1 region 坐标和 location header

每个 .mca 最多包含 32×32 个区块，sector 大小为 4096 字节。文件开头第一个 4096 字节是 location table。目标区块必须使用 Python 的 divmod() 计算 region 和局部坐标：

    region_x, local_x = divmod(chunk_x, 32)
    region_z, local_z = divmod(chunk_z, 32)
    entry = 4 * (local_x + local_z * 32)
    sector_offset = (header[entry] << 16) | (header[entry + 1] << 8) | header[entry + 2]

负坐标不能使用向零截断：chunk=-1 必须映射到 region=-1, local=31。sector_offset == 0 表示没有已保存区块。

### 6.2 区块 payload 和 NBT

区块记录是大端序的 4 字节 payload 长度、1 字节压缩类型和压缩内容。当前支持：

    1 = gzip
    2 = zlib
    3 = 未压缩

应先确保服务端执行 save-all flush 并已停止，再扫描 region 文件。扫描器只读，不应把 NBT 写回 .mca。

### 6.3 palette 和 packed block states

扫描每个 chunk 的 sections[]，读取 block_states.palette 和可选的 block_states.data。先在 palette 中找目标 block ID；当前 section 不包含目标 ID 时可以直接跳过 4096 个方块的解码。

当没有 data 时，按 palette index 0 处理全部 4096 个位置。存在 data 时，必须使用固定 long 槽位规则：

    bits = max(4, (palette_size - 1).bit_length())
    mask = (1 << bits) - 1
    values_per_long = 64 // bits
    long_index, slot = divmod(index, values_per_long)
    offset = slot * bits
    value = (data[long_index] & ((1 << 64) - 1)) >> offset
    palette_index = value & mask

不能把所有 long 拼成跨 long 的连续 bit stream。Minecraft 的每个 long 只存放 64 // bits 个完整槽位，余下 bit 不属于下一个 long 的值。NBT LongArray 可能以有符号整数表示，取无符号位模式后再移位。

### 6.4 section index 到世界坐标

对于 section 内的 index，坐标还原必须保持：

    local_x = index & 15
    local_z = (index >> 4) & 15
    local_y = (index >> 8) & 15

    world_x = chunk_x * 16 + local_x
    world_y = section_y * 16 + local_y
    world_z = chunk_z * 16 + local_z

扫描结果表示实际保存的方块状态，会包含地下、不可见和未暴露于空气的矿物；不要把它解释为“玩家可见矿物”或矿脉数量。

## 7. 性能、资源和安全约束

- radius=500 会请求 1000×1000 个区块，可能消耗很长时间、较多磁盘和内存；不要在没有明确授权时运行大范围真实服务端生成。
- /forceload 单批矩形不能超过 256 个区块。当前 GUI 的 20×8 批次和 legacy generic 的 25×10 批次都保持在限制内。
- 预生成进度日志不能代替最终完整性检查。需要通过每个目标区块的 location entry 重新统计缺失数。
- 必须在服务端停止并完成保存后扫描，避免读取正在写入的压缩 payload。
- 生成世界会产生 world_backup_<timestamp>；删除或清理备份前必须得到明确授权。
- 当前服务端默认设置 online-mode=false、开启 RCON，并使用固定密码和端口。这只适合本机临时扫描；不要将该服务端暴露到公网。
- 下载、服务端启动和输出文件写入都可能产生部分文件。失败恢复时先确认目标路径和进程状态，不要盲目删除整个 Minecraft/ 或仓库目录。
- 任何新的临时文件、报告或 Excel 输出都应保持在 .gitignore 覆盖范围内，除非它是明确要提交的测试 fixture 或文档示例。

## 8. 开发约定

### 8.1 一般约定

- 源码、中文文档和命令行文本使用 UTF-8。仓库当前包含中文 UI 文本；终端显示乱码时先检查读取编码，不要把中文替换成问号。
- Python 使用 4 空格缩进；遵循现有的模块化方式，优先复用 app 中已有函数，不要为单一调用点引入大型抽象。
- 新增运行依赖必须同步修改 requirements.txt，并说明它为什么不能使用标准库或已有依赖。
- 资源密集型任务要提供日志和取消检查；不要在 Tk 主线程中执行网络、Java、RCON、NBT 扫描或 Excel 写入。
- 保持路径操作使用 pathlib.Path。区分仓库根目录、程序目录、服务端目录、世界目录和维度 region 目录。
- 不要把生成的服务端、世界、Excel 或日志提交到 Git。

### 8.2 修改扫描算法时

1. 先确认 Minecraft 目标版本的 Anvil/NBT 结构和 block ID。
2. 维持负区块坐标的 divmod() 语义。
3. 分别验证 palette 单值、普通 packed data、5/6/7 bit palette 和负坐标。
4. 验证 gzip、zlib 和未压缩 payload，验证缺失 region/区块和空结果。
5. 验证坐标恢复、三维距离和相同距离下的稳定排序。
6. 确认服务器写入已经结束后再读取文件。

### 8.3 修改 GUI 或线程流程时

- 网络请求和 Java 进程启动都要放后台线程，并给出失败提示。
- 所有 Tk 控件访问，包括 messagebox、Text.insert、按钮状态和进度条，都应在 GUI 线程执行。
- 保持服务器停止、RCON 关闭、进程回收和 os.chdir() 恢复的 finally 路径。
- 不要在日志中输出 RCON 密码、用户本地隐私路径之外不必要的敏感内容。
- 若增加新的控件字段，要同步考虑空值、非法整数、取消、已有世界和安装失败。

## 9. 验证方式

仓库当前没有 pytest/unittest 测试套件、formatter、linter 或 CI 配置。每次修改至少执行以下检查：

    python -m compileall -q .
    python -c "import tkinter, nbtlib, openpyxl; print('imports: OK')"
    git diff --check
    git status --short

针对不同改动增加相应检查：

- 修改 constants.py：确认每个维度的矿物 ID 与显示名，末地空列表行为不变。
- 修改 installer.py/rcon.py：做网络失败、认证失败、超时和断线重连的人工或 mock 测试；不要以真实 Mojang 下载作为唯一快速测试。
- 修改 world.py：使用小型临时 world fixture，验证 .mca header、NBT 解压、palette、packed long、负坐标和扫描范围；不要提交真实大型世界。
- 修改 excel.py：验证零结果、单行、跨 worksheet 边界、排序和输出文件能否被 openpyxl.load_workbook() 重新打开。
- 修改 gui.py：先做 import/compile 检查，再在具备 Java 的 Windows 环境手动验证安装、切换维度、取消和正常完成流程。没有 Java 或服务端时只能做静态检查，不能宣称端到端通过。
- 必要时可进行小范围手动验收：安装一个已知 Minecraft release，使用很小的 radius，确认服务端停止后才开始扫描，并检查输出 Excel 的首行、总行数、sheet 数和坐标范围。

## 10. 现有已知行为和注意点

以下是当前源码的事实，不要在修复前把它们误写成已经实现的能力：

- download_server() 使用 Mojang 提供的下载地址和大小，但当前不校验 JAR SHA-1。
- scan_all_regions() 为覆盖边界会检查 min_chunk // 32 - 1 到 max_chunk // 32 + 1 的 region 文件，不过 scan_region() 仍会过滤到目标区块范围；这会带来额外文件检查但不会按设计把范围外区块加入结果。
- scan_region() 可以捕获单个 region 的解析异常并返回已经收集的部分结果。GUI 当前调用 scan_all_regions() 时没有传入错误回调，因此某些损坏 region 的错误可能只表现为结果偏少。
- 空矿物结果会产生一个只有表头的 Minerals_1，但 export_to_excel() 返回的 worksheet 数量为 0；涉及导出统计的修改必须覆盖此边界。
- GUI 对 origin 的长度没有单独的友好校验；格式不正确会在后台线程中以异常结束并显示错误。改进输入校验时不要改变合法 X,Y,Z 的含义。
- GUI 输出名来自用户输入，当前没有专门的文件名白名单或冲突确认。修改时要避免意外覆盖已有 Excel 或源码文件。
- docs/ 和 legacy/ 文档包含历史路径、固定范围和早期脚本示例；当前 GUI 行为应以 app/ 源码和 README 为准。

## 11. Git 和远端协作

当前仓库已配置：

    remote: origin
    url: https://github.com/snake-aabb-wtf/minecraft-ore-scan
    branch: master

提交前执行：

    git status --short --branch
    git diff --check
    git diff --stat
    git diff

只提交与当前任务相关的文件。若任务要求把文档或代码上传到远端，确认工作树中的其他修改属于用户后，再创建清晰的单一提交并推送：

    git add AGENTS.md
    git commit -m "docs: add project agent instructions"
    git push origin master

推送后检查：

    git status --short --branch
    git log -1 --oneline --decorate
    git ls-remote --heads origin master

不要使用 git reset --hard、git checkout -- 或清理命令覆盖用户已有改动。遇到认证失败、保护分支、远端领先或网络错误时，保留本地提交并报告具体错误，不要改写历史或强制推送。

## 12. 代理工作清单

开始任务时：

1. 确认当前目录是仓库根目录，读取 git status --short --branch。
2. 先读本文件、README.md 和任务涉及模块，再决定修改范围。
3. 检查是否已有未提交改动；不覆盖、不回滚与任务无关的用户修改。
4. 识别任务属于 GUI 主流程、共享扫描算法、legacy 兼容还是仅文档变更。

完成任务前：

1. 运行与风险匹配的静态、单元或人工验证。
2. 执行 git diff --check，确认没有生成物、密码、服务端 JAR 或世界文件进入差异。
3. 检查文档中的路径、命令和默认值是否与当前源码一致。
4. 汇报实际修改、实际运行过的验证，以及没有运行的端到端检查。
