"""app.validation 纯函数与 _start_scan 校验路径的单元测试。

validation 测试不依赖 Tk；_start_scan 测试用 __new__ + mock 属性隔离 GUI。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.gui import OreScanGUI
from app.validation import parse_origin, parse_radius, validate_output_name, validate_seed


class ParseOriginTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_origin("0,64,0"), (0, 64, 0))
        self.assertEqual(parse_origin(" -1, 5, 300"), (-1, 5, 300))

    def test_invalid(self):
        for bad in ("", "a,b,c", "1,2", "1,2,3,4", "1,2,x", None, 123):
            self.assertIsNone(parse_origin(bad))


class ParseRadiusTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_radius("50"), 50)
        self.assertEqual(parse_radius("1"), 1)
        self.assertEqual(parse_radius("500"), 500)
        self.assertEqual(parse_radius(50), 50)

    def test_invalid(self):
        for bad in ("", "abc", "0", "501", "-1", None):
            self.assertIsNone(parse_radius(bad))


class ValidateSeedTest(unittest.TestCase):
    def test_blank_seed_is_allowed(self):
        self.assertEqual(validate_seed("  "), "")

    def test_valid_seeds(self):
        self.assertEqual(validate_seed("123456789"), "123456789")
        self.assertEqual(validate_seed("Hello World"), "Hello World")

    def test_rejects_properties_breaking_input(self):
        self.assertIsNone(validate_seed("a\nb"))
        self.assertIsNone(validate_seed("a\rb"))
        self.assertIsNone(validate_seed("a=b"))
        self.assertIsNone(validate_seed("x" * 129))
        self.assertIsNone(validate_seed(None))
        self.assertIsNone(validate_seed(42))


class ValidateOutputNameTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_output_name("minerals.xlsx"), "minerals.xlsx")
        self.assertEqual(validate_output_name("  result 1.xlsx "), "result 1.xlsx")
        self.assertEqual(validate_output_name("sub/result.xlsx"), "sub/result.xlsx")
        self.assertEqual(validate_output_name("a\\b\\c.xlsx"), "a\\b\\c.xlsx")

    def test_invalid(self):
        for bad in (
            "",
            "   ",
            "C:\\evil.xlsx",
            "C:/evil.xlsx",
            "C:foo.xlsx",
            "C:",
            "/abs/path.xlsx",
            "..\\escape.xlsx",
            "../escape.xlsx",
            "a/../escape.xlsx",
            "a\\..\\escape.xlsx",
            "bad:name.xlsx",
            "bad?name.xlsx",
            "bad*name.xlsx",
            "bad\x01name.xlsx",
            "bad\x1fname.xlsx",
            None,
            123,
        ):
            self.assertIsNone(validate_output_name(bad))


class ValidateCustomBlockIdTest(unittest.TestCase):
    """validate_custom_block_id 纯函数测试（类内惰性导入，保证函数未实现时
    本模块其余测试仍可收集）。"""

    @staticmethod
    def _validate(text):
        from app.validation import validate_custom_block_id

        return validate_custom_block_id(text)

    def test_valid_block_ids(self):
        self.assertEqual(self._validate("minecraft:bedrock"), "minecraft:bedrock")
        self.assertEqual(self._validate("thermal:tin_ore"), "thermal:tin_ore")
        self.assertEqual(self._validate("betterend.forest:ore"), "betterend.forest:ore")
        self.assertEqual(self._validate("my-mod:block"), "my-mod:block")
        self.assertEqual(self._validate("modded:path/with_slash"), "modded:path/with_slash")
        self.assertEqual(self._validate("minecraft:deepslate_diamond_ore"), "minecraft:deepslate_diamond_ore")

    def test_whitespace_is_stripped(self):
        self.assertEqual(self._validate("  minecraft:bedrock  "), "minecraft:bedrock")

    def test_blank_is_allowed_as_empty(self):
        self.assertEqual(self._validate(""), "")
        self.assertEqual(self._validate("   "), "")

    def test_invalid_block_ids(self):
        for bad in (
            "bedrock",          # 缺少命名空间
            ":stone",           # 空命名空间
            "minecraft:",       # 空路径
            "Bedrock",          # 大写（NBT 名称恒为小写）
            "Minecraft:stone",  # 大写命名空间
            "mine craft:stone", # 内部空格
            "minecraft:bad space",
            "minecraft:\nstone",  # 内部换行（strip 只去首尾）
            "a\rb",
            "x=y",
            "x" * 129,          # 超长
            None,
            123,
        ):
            self.assertIsNone(self._validate(bad))


class StartScanValidationTest(unittest.TestCase):
    def _make_gui(self, custom=""):
        gui = OreScanGUI.__new__(OreScanGUI)
        gui.running = False
        gui.worker = None
        gui.server_process = None
        gui.app_dir = Path(tempfile.gettempdir())
        gui.current_server_dir = Path("server")
        gui.ore_vars = {}
        gui._get_selected_config = lambda: (["minecraft:diamond_ore"], "minecraft:overworld")
        gui.custom_ore_var = Mock()
        gui.custom_ore_var.get = lambda: custom
        gui.origin_var = Mock()
        gui.radius_var = Mock()
        gui.seed_var = Mock()
        gui.output_var = Mock()
        gui.disk_free_var = Mock()
        gui.start_btn = Mock()
        gui.stop_btn = Mock()
        gui.scan_progress = Mock()
        gui._run_pipeline = Mock()
        return gui

    def _start(self, gui, origin="0,64,0", radius=50, seed="123", output="minerals.xlsx", disk=""):
        gui.origin_var.get = lambda: origin
        gui.radius_var.get = lambda: radius
        gui.seed_var.get = lambda: seed
        gui.output_var.get = lambda: output
        gui.disk_free_var.get = lambda: disk
        with patch("app.gui.messagebox.showwarning") as warn:
            gui._start_scan()
        return warn

    def test_valid_input_starts_pipeline(self):
        gui = self._make_gui()
        warn = self._start(gui)
        warn.assert_not_called()
        self.assertTrue(gui.running)
        gui._run_pipeline.assert_called_once()
        config = gui._run_pipeline.call_args.args[0]
        self.assertEqual(config["ox"], 0)
        self.assertEqual(config["radius"], 50)
        self.assertEqual(config["seed"], "123")

    def test_valid_disk_threshold_passes_through(self):
        gui = self._make_gui()
        warn = self._start(gui, disk="8")
        warn.assert_not_called()
        self.assertTrue(gui.running)
        config = gui._run_pipeline.call_args.args[0]
        self.assertEqual(config["min_free_gb"], 8.0)

    def test_non_finite_disk_threshold_treated_as_unlimited(self):
        # nan/inf 不应报错，也不应传入 world.py（int(nan) 会 ValueError）
        for disk_value in ("nan", "inf", "-inf"):
            gui = self._make_gui()
            warn = self._start(gui, disk=disk_value)
            warn.assert_not_called()
            self.assertTrue(gui.running)
            config = gui._run_pipeline.call_args.args[0]
            self.assertIsNone(config["min_free_gb"])

    def test_invalid_origin_does_not_start(self):
        gui = self._make_gui()
        warn = self._start(gui, origin="a,b,c")
        warn.assert_called_once()
        self.assertFalse(gui.running)
        gui._run_pipeline.assert_not_called()

    def test_origin_with_wrong_count_does_not_start(self):
        gui = self._make_gui()
        warn = self._start(gui, origin="1,2")
        warn.assert_called_once()
        self.assertFalse(gui.running)

    def test_radius_tcl_error_does_not_start(self):
        # IntVar 绑定非法文本时 get() 抛 TclError
        import tkinter as tk

        gui = self._make_gui()
        gui.origin_var.get = lambda: "0,64,0"

        def bad_radius():
            raise tk.TclError("bad value")

        gui.radius_var.get = bad_radius
        gui.seed_var.get = lambda: "123"
        gui.output_var.get = lambda: "minerals.xlsx"
        gui.disk_free_var.get = lambda: ""
        with patch("app.gui.messagebox.showwarning") as warn:
            gui._start_scan()
        warn.assert_called_once()
        self.assertFalse(gui.running)

    def test_radius_out_of_range_does_not_start(self):
        gui = self._make_gui()
        warn = self._start(gui, radius=501)
        warn.assert_called_once()
        self.assertFalse(gui.running)

    def test_invalid_seed_does_not_start(self):
        gui = self._make_gui()
        warn = self._start(gui, seed="a\nb")
        warn.assert_called_once()
        self.assertFalse(gui.running)

    def test_invalid_output_name_does_not_start(self):
        gui = self._make_gui()
        warn = self._start(gui, output="C:\\evil.xlsx")
        warn.assert_called_once()
        self.assertFalse(gui.running)

    def test_invalid_disk_threshold_does_not_start(self):
        gui = self._make_gui()
        warn = self._start(gui, disk="not-a-number")
        warn.assert_called_once()
        self.assertFalse(gui.running)

    def test_existing_output_file_asks_confirmation(self):
        gui = self._make_gui()
        existing = Path(tempfile.gettempdir()) / "minerals.xlsx"
        try:
            existing.write_bytes(b"old")
            gui.origin_var.get = lambda: "0,64,0"
            gui.radius_var.get = lambda: 50
            gui.seed_var.get = lambda: "123"
            gui.output_var.get = lambda: "minerals.xlsx"
            gui.disk_free_var.get = lambda: ""
            with (
                patch("app.gui.messagebox.showwarning") as warn,
                patch("app.gui.messagebox.askyesno", return_value=False) as ask,
            ):
                gui._start_scan()
            ask.assert_called_once()
            self.assertFalse(gui.running)
            warn.assert_not_called()
        finally:
            existing.unlink(missing_ok=True)

    def test_custom_block_id_appended_to_ores(self):
        gui = self._make_gui(custom="minecraft:bedrock")
        warn = self._start(gui)
        warn.assert_not_called()
        self.assertTrue(gui.running)
        config = gui._run_pipeline.call_args.args[0]
        self.assertIn("minecraft:bedrock", config["ores"])
        self.assertEqual(config["ores"], ["minecraft:diamond_ore", "minecraft:bedrock"])

    def test_custom_block_id_only_starts(self):
        gui = self._make_gui(custom="minecraft:bedrock")
        gui._get_selected_config = lambda: ([], "minecraft:overworld")
        warn = self._start(gui)
        warn.assert_not_called()
        self.assertTrue(gui.running)
        config = gui._run_pipeline.call_args.args[0]
        self.assertEqual(config["ores"], ["minecraft:bedrock"])

    def test_custom_block_id_only_works_for_end(self):
        # 末地没有内置矿物选项，自定义 ID 是唯一扫描途径
        gui = self._make_gui(custom="modid:end_block")
        gui._get_selected_config = lambda: ([], "minecraft:the_end")
        warn = self._start(gui)
        warn.assert_not_called()
        self.assertTrue(gui.running)
        config = gui._run_pipeline.call_args.args[0]
        self.assertEqual(config["dimension"], "minecraft:the_end")
        self.assertEqual(config["ores"], ["modid:end_block"])

    def test_invalid_custom_block_id_warns_and_does_not_start(self):
        gui = self._make_gui(custom="Bedrock")
        warn = self._start(gui)
        warn.assert_called_once()
        self.assertFalse(gui.running)
        gui._run_pipeline.assert_not_called()

    def test_blank_custom_block_id_is_ignored(self):
        gui = self._make_gui(custom="")
        warn = self._start(gui)
        warn.assert_not_called()
        self.assertTrue(gui.running)
        config = gui._run_pipeline.call_args.args[0]
        self.assertEqual(config["ores"], ["minecraft:diamond_ore"])


class StopScanCapturesOldProcessTest(unittest.TestCase):
    def test_shutdown_thread_captures_old_process_reference(self):
        # 停止线程必须捕获调用时刻的旧进程引用：即使停止后立即重新扫描
        # （server_process 被新进程覆盖），也不会误杀新进程
        import threading

        gui = OreScanGUI.__new__(OreScanGUI)
        gui._proc_lock = threading.Lock()
        gui.running = True
        old_proc = Mock()
        gui.server_process = old_proc
        gui._log = Mock()
        gui.stop_btn = Mock()
        with (
            patch("app.gui.threading.Thread") as mock_thread,
            patch("app.gui.time.sleep"),
            patch("app.gui.RconClient", side_effect=Exception("no rcon")),
        ):
            gui._stop_scan()
        kwargs = mock_thread.call_args.kwargs
        self.assertEqual(kwargs["args"], (old_proc,))
        self.assertTrue(kwargs["daemon"])
        # 若重新扫描，server_process 更新为新进程，但停止线程仍持有旧引用
        new_proc = Mock()
        with gui._proc_lock:
            gui.server_process = new_proc
        self.assertNotEqual(kwargs["args"][0], new_proc)


if __name__ == "__main__":
    unittest.main()
