"""app.java_runtime 的单元测试：版本输出解析、运行时探测与精确选择。"""
import unittest
from pathlib import Path
from unittest.mock import patch

from app.java_runtime import (
    JavaRuntime,
    _java_filename,
    parse_java_version,
    probe_java_runtime,
    select_java_runtime,
)


class ParseJavaVersionTest(unittest.TestCase):
    def test_java_8(self):
        self.assertEqual(parse_java_version('openjdk version "1.8.0_392" 2023-11-23'), (8, "1.8.0_392"))

    def test_java_11(self):
        self.assertEqual(parse_java_version('openjdk version "11.0.21" 2023-10-17'), (11, "11.0.21"))

    def test_java_17(self):
        self.assertEqual(parse_java_version('openjdk version "17.0.9" 2023-10-17'), (17, "17.0.9"))

    def test_java_21(self):
        self.assertEqual(parse_java_version('openjdk version "21.0.1" 2023-10-17'), (21, "21.0.1"))

    def test_unquoted_version(self):
        self.assertEqual(parse_java_version("openjdk version 17.0.9 2023-10-17"), (17, "17.0.9"))

    def test_java_without_version_keyword(self):
        self.assertEqual(parse_java_version("openjdk 11.0.21 2023-10-17"), (11, "11.0.21"))

    def test_case_insensitive(self):
        self.assertEqual(parse_java_version('OpenJDK Version "17.0.9"'), (17, "17.0.9"))

    def test_garbage_output_returns_none(self):
        self.assertIsNone(parse_java_version("not java at all"))
        self.assertIsNone(parse_java_version(""))
        self.assertIsNone(parse_java_version(None))

    def test_java_9_single_digit_major(self):
        self.assertEqual(parse_java_version('openjdk version "9.0.4"'), (9, "9.0.4"))


class JavaFilenameTest(unittest.TestCase):
    def test_windows(self):
        with patch("app.java_runtime.os.name", "nt"):
            self.assertEqual(_java_filename(), "java.exe")

    def test_posix(self):
        with patch("app.java_runtime.os.name", "posix"):
            self.assertEqual(_java_filename(), "java")


class ProbeJavaRuntimeTest(unittest.TestCase):
    def test_successful_probe(self):
        result = unittest.mock.Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = 'openjdk version "21.0.1" 2023-10-17'
        with patch("app.java_runtime.subprocess.run", return_value=result):
            runtime = probe_java_runtime(Path("C:/java/bin/java.exe"))
        self.assertIsInstance(runtime, JavaRuntime)
        self.assertEqual(runtime.major_version, 21)

    def test_nonzero_exit_returns_none(self):
        result = unittest.mock.Mock()
        result.returncode = 1
        with patch("app.java_runtime.subprocess.run", return_value=result):
            self.assertIsNone(probe_java_runtime(Path("java")))

    def test_oserror_returns_none(self):
        with patch("app.java_runtime.subprocess.run", side_effect=OSError("no such file")):
            self.assertIsNone(probe_java_runtime(Path("missing/java")))

    def test_unparseable_output_returns_none(self):
        result = unittest.mock.Mock()
        result.returncode = 0
        result.stdout = "hello"
        result.stderr = "world"
        with patch("app.java_runtime.subprocess.run", return_value=result):
            self.assertIsNone(probe_java_runtime(Path("java")))


class SelectJavaRuntimeTest(unittest.TestCase):
    def _runtime(self, major, executable="C:/java/bin/java.exe"):
        return JavaRuntime(executable=Path(executable), major_version=major, version_text=str(major))

    def test_exact_match(self):
        runtimes = [self._runtime(8), self._runtime(17), self._runtime(21)]
        selected = select_java_runtime(17, runtimes)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.major_version, 17)

    def test_no_match_returns_none(self):
        runtimes = [self._runtime(8), self._runtime(21)]
        self.assertIsNone(select_java_runtime(17, runtimes))

    def test_empty_list(self):
        self.assertIsNone(select_java_runtime(21, []))


if __name__ == "__main__":
    unittest.main()
