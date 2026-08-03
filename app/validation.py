"""GUI 输入校验纯函数（无 Tk/网络依赖，便于单元测试）。

本模块的每个函数只做解析和校验，不触碰任何 Tk 控件或全局状态。
GUI 在变更运行状态（self.running、按钮禁用、进度条启动）之前调用这些
函数，确保非法输入以友好提示结束而不是让后台状态永远停留在"运行中"。
"""

import ntpath

GUI_RADIUS_MIN = 1
GUI_RADIUS_MAX = 500
MAX_SEED_LENGTH = 128

# Windows 文件名保留字符（跨平台检查，因为输出 Excel 主要面向 Windows 用户）
_INVALID_FILENAME_CHARS = '<>:"|?*'


def parse_origin(text):
    """解析逗号分隔的三整数原点坐标。

    返回 (x, y, z) 元组；格式非法（不是三个整数）时返回 None。
    合法输入示例："0,64,0"、" -1, 5, 300"。三个值必须是整数这一语义
    保持不变（AGENTS.md：不要改变合法 X,Y,Z 的含义）。
    """
    if not isinstance(text, str):
        return None
    parts = text.strip().split(",")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(part.strip()) for part in parts)
    except ValueError:
        return None


def parse_radius(text):
    """解析区块半径并检查 GUI 允许范围（1 到 500）。

    返回 int；非法文本或越界时返回 None。text 可以来自 IntVar 的字符串
    值或任意可转为整数的对象。
    """
    try:
        radius = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    if radius < GUI_RADIUS_MIN or radius > GUI_RADIUS_MAX:
        return None
    return radius


def validate_seed(text):
    """校验 seed 文本。

    空字符串合法（表示不指定新 seed，复用已有世界）。拒绝会破坏
    server.properties 格式的字符（换行、回车、等号）和超长输入，返回
    清洗后的 seed；非法时返回 None。
    """
    if not isinstance(text, str):
        return None
    seed = text.strip()
    if not seed:
        return ""
    if len(seed) > MAX_SEED_LENGTH:
        return None
    if any(ch in seed for ch in "\r\n="):
        return None
    return seed


def validate_output_name(text):
    """校验输出文件名/相对路径。

    返回清洗后的名字；非法（空、绝对路径、目录逃逸、Windows 非法字符）
    时返回 None。只允许相对程序输出目录的文件名，防止用户输入覆盖源码
    或仓库外文件。
    """
    if not isinstance(text, str):
        return None
    name = text.strip()
    if not name:
        return None
    # 拒绝绝对路径或任何带盘符的名字：ntpath.isabs 按 Windows 语义识别
    # "C:\..."、"C:/..."、"/..."；splitdrive 额外拒绝 "C:foo" 这类
    # 驱动器相对路径（Windows 上会丢弃程序目录前缀，导致输出逃逸）。
    if ntpath.isabs(name) or ntpath.splitdrive(name)[0]:
        return None
    # 拒绝目录逃逸：统一用 / 解析路径段，".." 段一律拒绝
    normalized = name.replace("\\", "/")
    if ".." in normalized.split("/"):
        return None
    # 拒绝 Windows 文件名保留字符和控制字符（0x00-0x1F）
    if any(ch in name for ch in _INVALID_FILENAME_CHARS) or any(ord(ch) < 32 for ch in name):
        return None
    return name
