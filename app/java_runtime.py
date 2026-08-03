from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess


JAVA_VERSION_PATTERN = re.compile(
    r"(?:openjdk|java)(?:\s+version)?\s+\"?([0-9][0-9A-Za-z._+\-]*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JavaRuntime:
    executable: Path
    major_version: int
    version_text: str


def parse_java_version(output: str):
    """Return a Java major version and printable version string from java -version output."""
    if not isinstance(output, str):
        return None
    match = JAVA_VERSION_PATTERN.search(output)
    if not match:
        return None

    version_text = match.group(1)
    parts = re.match(r"(\d+)(?:\.(\d+))?", version_text)
    if not parts:
        return None

    first = int(parts.group(1))
    second = parts.group(2)
    major_version = int(second) if first == 1 and second else first
    return major_version, version_text


def _java_filename() -> str:
    return "java.exe" if os.name == "nt" else "java"


def _windows_registry_java_homes():
    if os.name != "nt":
        return []

    try:
        import winreg
    except ImportError:
        return []

    homes = []
    key_paths = (
        r"SOFTWARE\JavaSoft\JDK",
        r"SOFTWARE\JavaSoft\Java Development Kit",
        r"SOFTWARE\JavaSoft\JRE",
    )
    access_modes = [winreg.KEY_READ]
    for flag_name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
        flag = getattr(winreg, flag_name, None)
        if flag is not None:
            access_modes.append(winreg.KEY_READ | flag)

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in key_paths:
            for access in access_modes:
                try:
                    with winreg.OpenKey(hive, key_path, 0, access) as key:
                        subkey_count = winreg.QueryInfoKey(key)[0]
                        for index in range(subkey_count):
                            subkey_name = winreg.EnumKey(key, index)
                            try:
                                with winreg.OpenKey(key, subkey_name) as version_key:
                                    java_home, _ = winreg.QueryValueEx(version_key, "JavaHome")
                                    homes.append(Path(java_home))
                            except OSError:
                                continue
                except OSError:
                    continue
    return homes


def _common_java_executables():
    java_name = _java_filename()
    candidates = []

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / java_name)

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            candidates.append(Path(entry.strip('"')) / java_name)

    path_java = shutil.which("java")
    if path_java:
        candidates.append(Path(path_java))

    if os.name == "nt":
        for home in _windows_registry_java_homes():
            candidates.append(home / "bin" / java_name)

        roots = []
        for env_name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            value = os.environ.get(env_name)
            if value:
                roots.extend(
                    [
                        Path(value) / "Java",
                        Path(value) / "Eclipse Adoptium",
                        Path(value) / "Microsoft",
                        Path(value) / "Azul Systems",
                    ]
                )
        for root in roots:
            try:
                for child in root.iterdir():
                    candidates.append(child / "bin" / java_name)
            except OSError:
                continue
    else:
        alternatives = shutil.which("update-alternatives")
        if alternatives:
            try:
                result = subprocess.run(
                    [alternatives, "--list", "java"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    check=False,
                )
                candidates.extend(Path(line.strip()) for line in result.stdout.splitlines() if line.strip())
            except (OSError, subprocess.SubprocessError):
                pass

        jvm_root = Path("/usr/lib/jvm")
        try:
            for child in jvm_root.iterdir():
                candidates.append(child / "bin" / java_name)
        except OSError:
            pass

    return candidates


def probe_java_runtime(executable: Path):
    try:
        result = subprocess.run(
            [str(executable), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    parsed = parse_java_version(f"{result.stdout}\n{result.stderr}")
    if not parsed:
        return None

    major_version, version_text = parsed
    return JavaRuntime(executable=executable, major_version=major_version, version_text=version_text)


def find_java_runtimes():
    runtimes = []
    seen = set()
    for candidate in _common_java_executables():
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        key = str(resolved).casefold() if os.name == "nt" else str(resolved)
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)

        runtime = probe_java_runtime(resolved)
        if runtime:
            runtimes.append(runtime)

    return sorted(runtimes, key=lambda runtime: (runtime.major_version, str(runtime.executable).casefold()))


def select_java_runtime(required_major_version: int, runtimes=None):
    if runtimes is None:
        runtimes = find_java_runtimes()
    return next((runtime for runtime in runtimes if runtime.major_version == required_major_version), None)


def format_java_runtimes(runtimes) -> str:
    if not runtimes:
        return "未检测到可用的 Java 运行时"
    return "；".join(
        f"Java {runtime.version_text} ({runtime.executable})" for runtime in runtimes
    )
