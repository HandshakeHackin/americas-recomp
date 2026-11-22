import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from test_symbolize_samples import build_pe


PLATFORM = Path(__file__).resolve().parents[1] / "xbox" / "platform"
spec = importlib.util.spec_from_file_location("xbox_pe_imports", PLATFORM / "pe_imports.py")
pe_imports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe_imports)


class XboxPeImportsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def provider(self, plus=True, named=True):
        path = self.root / "provider.dll"
        build_pe(path, with_symbols=False, with_exports=True)
        data = bytearray(path.read_bytes())
        if not plus:
            struct.pack_into("<H", data, 0x58, 0x10B)
            data[0x58 + 96:0x58 + 240] = bytes(144)
            struct.pack_into("<III", data, 0x58 + 92, 16, 0x2000, 0x100)
        struct.pack_into("<IIIIII", data, 0x610, 7, 3, int(named), 0x2040,
                         0x2050 if named else 0, 0x2058 if named else 0)
        struct.pack_into("<III", data, 0x640, 0x1020, 0, 0x20A0)
        struct.pack_into("<I", data, 0x650, 0x2060)
        struct.pack_into("<H", data, 0x658, 0)
        data[0x6A0:0x6AD] = b"other.Target\0"
        path.write_bytes(data)
        return path

    def consumer(self):
        path = self.root / "consumer.exe"
        build_pe(path, with_symbols=False)
        data = bytearray(path.read_bytes())
        struct.pack_into("<II", data, 0x58 + 120, 0x2100, 40)
        struct.pack_into("<IIIII", data, 0x700, 0x2140, 0, 0, 0x2170, 0x2140)
        struct.pack_into("<QQQQQ", data, 0x740,
                         0x8000000000000007, 0x8000000000000008, 0x8000000000000009, 0x2190, 0)
        data[0x770:0x77D] = b"provider.dll\0"
        data[0x790:0x79D] = b"\0\0first_func\0"
        path.write_bytes(data)
        return path

    def run_tool(self, script, *args):
        result = subprocess.run([sys.executable, str(PLATFORM / script), *map(str, args)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_named_export_retains_ordinal_alias_and_skips_hole(self):
        for plus in (True, False):
            with self.subTest(plus=plus):
                exports = pe_imports.parse(self.provider(plus))["exports"]
                self.assertEqual(exports, ["first_func", "#7", "#9"])

    def test_ordinal_only_exports_need_no_name_table(self):
        for plus in (True, False):
            with self.subTest(plus=plus):
                self.assertEqual(pe_imports.parse(self.provider(plus, named=False))["exports"], ["#7", "#9"])

    def test_existing_named_exports_keep_their_names(self):
        path = self.root / "named.dll"
        build_pe(path, with_symbols=False, with_exports=True)
        self.assertEqual(pe_imports.parse(path)["exports"], ["first_func", "second_func", "#1", "#2"])

    def test_no_export_directory(self):
        path = self.root / "plain.dll"
        build_pe(path, with_symbols=False)
        self.assertEqual(pe_imports.parse(path)["exports"], [])

    def test_empty_address_table(self):
        path = self.provider(named=False)
        data = bytearray(path.read_bytes())
        struct.pack_into("<I", data, 0x614, 0)
        struct.pack_into("<I", data, 0x61C, 0)
        path.write_bytes(data)
        self.assertEqual(pe_imports.parse(path)["exports"], [])

    def named_exports(self, names, plus=True):
        path = self.provider(plus=plus, named=False)
        data = bytearray(path.read_bytes())
        if not plus:
            struct.pack_into("<H", data, 0x44, 0x14C)
        struct.pack_into("<IIIIII", data, 0x610, 7, 3, len(names), 0x2040, 0x2050, 0x2060)
        struct.pack_into("<III", data, 0x640, 0x1020, 0, 0x1060)
        cursor = 0x680
        for i, (name, ordinal_index) in enumerate(names):
            text = name.encode("ascii") + b"\0"
            data[cursor:cursor + len(text)] = text
            struct.pack_into("<I", data, 0x650 + 4 * i, 0x2000 + cursor - 0x600)
            struct.pack_into("<H", data, 0x660 + 2 * i, ordinal_index)
            cursor += len(text)
        path.write_bytes(data)
        return pe_imports.parse(path)["exports"]

    def test_named_export_pointing_to_an_address_table_hole_is_not_provided(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.assertEqual(self.named_exports([("missing_func", 1)], plus), ["#7", "#9"])

    def test_named_export_with_an_out_of_range_ordinal_is_not_provided(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.assertEqual(self.named_exports([("missing_func", 3)], plus), ["#7", "#9"])

    def test_multiple_names_can_alias_one_filled_export_slot(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.assertEqual(self.named_exports([("alias_func", 0), ("first_func", 0)], plus),
                                 ["alias_func", "first_func", "#7", "#9"])

    def test_export_names_use_their_ordinal_mapping_instead_of_name_position(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.assertEqual(self.named_exports([("alpha", 2), ("beta", 0)], plus),
                                 ["alpha", "beta", "#7", "#9"])

    def test_inventory_matches_imports_by_ordinal(self):
        self.provider()
        consumer = self.consumer()
        inventory = self.root / "imports.json"
        self.run_tool("pe_imports.py", self.root, inventory)
        data = json.loads(inventory.read_text())
        self.assertEqual(data[consumer.name]["imports"]["provider.dll"], ["#7", "#8", "#9", "first_func"])
        missing = set(data[consumer.name]["imports"]["provider.dll"]) - set(data["provider.dll"]["exports"])
        self.assertEqual(missing, {"#8"})

    @unittest.skipUnless(os.name == "nt", "platform reports query Windows system DLLs")
    def test_platform_reports_do_not_request_stubs_for_exported_ordinals(self):
        self.provider()
        self.consumer()
        report = self.root / "report"
        self.run_tool("exe_report.py", self.root, "--out", report)
        self.assertEqual(json.loads((report / "needs.json").read_text()), {"provider.dll": ["#8"]})
        inventory = self.root / "imports.json"
        results = self.root / "results.json"
        self.run_tool("pe_imports.py", self.root, inventory)
        results.write_text("{}")
        self.run_tool("make_platform_results.py", inventory, results)
        self.assertEqual(json.loads(results.read_text())["platform"], {
            "provider.dll!#7": "package", "provider.dll!#8": "fail",
            "provider.dll!#9": "package", "provider.dll!first_func": "package",
        })


if __name__ == "__main__":
    unittest.main()
