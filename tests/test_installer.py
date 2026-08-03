"""app.installer 的单元测试：服务端属性更新、Java 需求解析、已安装发现、
卸载安全限制、下载 SHA-1 校验。网络访问全部 mock，不触碰真实 Mojang。
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import installer as installer_mod
from app.installer import (
    _java_requirement_from_data,
    ServerJavaRequirement,
    download_server,
    find_installed_servers,
    get_server_java_requirement,
    uninstall_server,
    update_server_properties,
    write_server_metadata,
)


class UpdateServerPropertiesTest(unittest.TestCase):
    def _write(self, path, text):
        path.write_text(text, encoding="utf-8")

    def test_empty_seed_removes_level_seed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            self._write(props, "level-seed=123\ngamemode=survival\n")
            update_server_properties(props, "")
            text = props.read_text(encoding="utf-8")
            self.assertNotIn("level-seed", text)
            self.assertIn("gamemode=survival", text)

    def test_non_empty_seed_writes_level_seed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            self._write(props, "gamemode=survival\n")
            update_server_properties(props, "987654")
            text = props.read_text(encoding="utf-8")
            self.assertIn("level-seed=987654", text)

    def test_required_properties_are_forced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            self._write(props, "enable-rcon=false\n")
            update_server_properties(props, "123")
            text = props.read_text(encoding="utf-8")
            self.assertIn("enable-rcon=true", text)
            self.assertIn("online-mode=false", text)
            self.assertIn("rcon.password=ore_scan_local", text)

    def test_server_binds_to_localhost(self):
        # 固定 RCON 密码不应暴露到局域网/公网：服务端只绑定 127.0.0.1
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            update_server_properties(props, "123")
            text = props.read_text(encoding="utf-8")
            self.assertIn("server-ip=127.0.0.1", text)

    def test_update_properties_rejects_properties_breaking_seed(self):
        # 纵深防御：即使绕过 GUI 校验，含换行/等号/超长的 seed 也会被拒绝
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            for bad in ("a\nb", "a\rb", "a=b", "x" * 129):
                with self.assertRaises(ValueError):
                    update_server_properties(props, bad)
            with self.assertRaises(ValueError):
                update_server_properties(props, None)

    def test_comments_and_blank_lines_are_dropped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            self._write(props, "# comment\n\ngamemode=survival\n")
            update_server_properties(props, "123")
            text = props.read_text(encoding="utf-8")
            self.assertNotIn("comment", text)
            self.assertIn("gamemode=survival", text)

    def test_missing_file_creates_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            props = Path(temp_dir) / "server.properties"
            update_server_properties(props, "123")
            text = props.read_text(encoding="utf-8")
            self.assertIn("level-seed=123", text)


class JavaRequirementFromDataTest(unittest.TestCase):
    def test_valid_requirement(self):
        req = _java_requirement_from_data("1.20.5", {"majorVersion": 21, "component": "java-runtime-linux"})
        self.assertIsInstance(req, ServerJavaRequirement)
        self.assertEqual((req.version_id, req.major_version, req.component), ("1.20.5", 21, "java-runtime-linux"))

    def test_missing_component_is_none(self):
        req = _java_requirement_from_data("1.20.5", {"majorVersion": 21})
        self.assertIsNotNone(req)
        self.assertIsNone(req.component)

    def test_non_dict_java_version(self):
        self.assertIsNone(_java_requirement_from_data("1.20.5", "21"))

    def test_invalid_major_version(self):
        self.assertIsNone(_java_requirement_from_data("1.20.5", {"majorVersion": "abc"}))
        self.assertIsNone(_java_requirement_from_data("1.20.5", {"majorVersion": 0}))
        self.assertIsNone(_java_requirement_from_data("1.20.5", {"majorVersion": None}))

    def test_major_version_string_is_parsed(self):
        req = _java_requirement_from_data("1.20.5", {"majorVersion": "21"})
        self.assertEqual(req.major_version, 21)


class ServerMetadataTest(unittest.TestCase):
    def test_write_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir)
            write_server_metadata(server_dir, "1.20.5", {"javaVersion": {"majorVersion": 21}})
            content = json.loads((server_dir / ".ore-scan-server.json").read_text(encoding="utf-8"))
            self.assertEqual(content["minecraftVersion"], "1.20.5")
            self.assertEqual(content["javaVersion"]["majorVersion"], 21)

    def test_get_requirement_uses_cache_without_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir)
            write_server_metadata(server_dir, "1.20.5", {"javaVersion": {"majorVersion": 21}})
            with patch.object(installer_mod, "fetch_version_data") as mock_fetch:
                req = get_server_java_requirement(server_dir, version_id="1.20.5")
                mock_fetch.assert_not_called()
            self.assertEqual(req.major_version, 21)

    def test_get_requirement_fetches_and_caches_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir)
            with patch.object(
                installer_mod, "fetch_version_data",
                return_value={"javaVersion": {"majorVersion": 17}},
            ) as mock_fetch:
                req = get_server_java_requirement(server_dir, version_id="1.18.2")
                mock_fetch.assert_called_once_with("1.18.2")
            self.assertEqual(req.major_version, 17)
            # 已写回缓存
            content = json.loads((server_dir / ".ore-scan-server.json").read_text(encoding="utf-8"))
            self.assertEqual(content["minecraftVersion"], "1.18.2")


class FindInstalledServersTest(unittest.TestCase):
    def test_only_dirs_with_server_jar_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            minecraft_dir = Path(temp_dir) / "Minecraft"
            (minecraft_dir / "1.20.5").mkdir(parents=True)
            (minecraft_dir / "1.20.5" / "server.jar").touch()
            (minecraft_dir / "empty").mkdir()
            (minecraft_dir / "not-a-dir.txt").write_text("x")
            found = find_installed_servers(minecraft_dir)
            self.assertEqual([d.name for d in found], ["1.20.5"])

    def test_missing_minecraft_dir_returns_empty(self):
        self.assertEqual(find_installed_servers(Path("nonexistent")), [])


class UninstallServerTest(unittest.TestCase):
    def test_refuses_path_outside_minecraft_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            minecraft_dir = base / "Minecraft"
            minecraft_dir.mkdir()
            outside = base / "other"
            outside.mkdir()
            with self.assertRaises(ValueError):
                uninstall_server(outside, minecraft_dir)

    def test_refuses_non_direct_child(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            minecraft_dir = Path(temp_dir) / "Minecraft"
            nested = minecraft_dir / "a" / "b"
            nested.mkdir(parents=True)
            with self.assertRaises(ValueError):
                uninstall_server(nested, minecraft_dir)

    def test_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            minecraft_dir = Path(temp_dir) / "Minecraft"
            target = Path(temp_dir) / "real"
            target.mkdir()
            minecraft_dir.mkdir()
            link = minecraft_dir / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                uninstall_server(link, minecraft_dir)

    def test_uninstalls_direct_child(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            minecraft_dir = Path(temp_dir) / "Minecraft"
            server_dir = minecraft_dir / "1.20.5"
            server_dir.mkdir(parents=True)
            (server_dir / "server.jar").touch()
            uninstall_server(server_dir, minecraft_dir)
            self.assertFalse(server_dir.exists())


class DownloadServerTest(unittest.TestCase):
    def test_reporthook_with_zero_total_does_not_divide_by_zero(self):
        version_data = {
            "downloads": {"server": {"url": "http://example.invalid/x.jar", "size": 10, "sha1": "abc"}}
        }
        captured = {}

        def fake_urlretrieve(url, filename, reporthook=None):
            Path(filename).write_bytes(b"abc")
            if reporthook:
                reporthook(0, 1024, 0)  # total_size=0：旧代码会 ZeroDivisionError
                reporthook(5, 1024, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve),
                patch.object(installer_mod, "fetch_version_data", return_value=version_data),
                patch.object(installer_mod, "_sha1_file", return_value="abc"),
                patch.object(installer_mod, "write_server_metadata"),
                patch.object(installer_mod, "write_eula"),
                patch.object(installer_mod, "write_default_properties"),
            ):
                download_server(
                    Path(temp_dir), "1.20.5", {},
                    progress_callback=lambda pct, d, t: captured.update(pct=pct),
                )
        self.assertEqual(captured.get("pct"), 0)

    def test_sha1_mismatch_removes_jar_and_retries(self):
        version_data = {
            "downloads": {"server": {"url": "http://example.invalid/x.jar", "size": 10, "sha1": "abc"}}
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir)

            def fake_urlretrieve(url, filename, reporthook=None):
                Path(filename).write_bytes(b"wrong-content")  # sha1 不匹配
                if reporthook:
                    reporthook(1, 10, 10)

            with (
                patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve),
                patch.object(installer_mod, "fetch_version_data", return_value=version_data),
                patch.object(installer_mod, "write_server_metadata"),
                patch.object(installer_mod, "write_eula"),
                patch.object(installer_mod, "write_default_properties"),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    download_server(server_dir, "1.20.5", {})
                self.assertIn("SHA-1", str(ctx.exception))
            # 校验失败后 server.jar 不得存在，.part 也被清理
            self.assertFalse((server_dir / "server.jar").exists())
            self.assertFalse((server_dir / "server.jar.part").exists())

    def test_successful_download_replaces_part(self):
        version_data = {
            "downloads": {"server": {"url": "http://example.invalid/x.jar", "size": 3, "sha1": "abc"}}
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = Path(temp_dir)

            def fake_urlretrieve(url, filename, reporthook=None):
                Path(filename).write_bytes(b"abc")
                if reporthook:
                    reporthook(1, 3, 3)

            with (
                patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve),
                patch.object(installer_mod, "fetch_version_data", return_value=version_data),
                patch.object(installer_mod, "_sha1_file", return_value="abc"),
                patch.object(installer_mod, "write_server_metadata") as mock_meta,
                patch.object(installer_mod, "write_eula"),
                patch.object(installer_mod, "write_default_properties"),
            ):
                size = download_server(server_dir, "1.20.5", {})
            self.assertEqual(size, 3)
            self.assertTrue((server_dir / "server.jar").exists())
            self.assertFalse((server_dir / "server.jar.part").exists())
            mock_meta.assert_called_once()


if __name__ == "__main__":
    unittest.main()
