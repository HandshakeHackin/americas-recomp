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
            struct.pack_into("<H", data, 0x44, 0x14C)
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

    def consumer(self, plus=True):
        path = self.root / "consumer.exe"
        build_pe(path, with_symbols=False)
        data = bytearray(path.read_bytes())
        if not plus:
            struct.pack_into("<H", data, 0x44, 0x14C)
            struct.pack_into("<H", data, 0x58, 0x10B)
            data[0x58 + 96:0x58 + 240] = bytes(144)
            struct.pack_into("<I", data, 0x58 + 92, 16)
        struct.pack_into("<II", data, 0x58 + (120 if plus else 104), 0x2100, 40)
        struct.pack_into("<IIIII", data, 0x700, 0x2140, 0, 0, 0x2170, 0x2140)
        ordinal = 1 << (63 if plus else 31)
        struct.pack_into("<QQQQQ" if plus else "<IIIII", data, 0x740,
                         ordinal | 7, ordinal | 8, ordinal | 9, 0x2190, 0)
        data[0x770:0x77D] = b"provider.dll\0"
        data[0x790:0x79D] = b"\0\0first_func\0"
        path.write_bytes(data)
        return path

    def test_exports_can_mix_headers_and_sections(self):
        for plus in (False, True):
            for placement in range(8):
                with self.subTest(plus=plus, placement=placement):
                    path = self.provider(plus=plus)
                    data = bytearray(path.read_bytes())
                    struct.pack_into("<I", data, 0x58 + 60, 0x400)
                    data[0x200:0x400] = data[0x600:0x800]
                    directory_rva, directory_offset = (0x200, 0x200) if placement & 1 else (0x2000, 0x600)
                    arrays_rva, arrays_offset = (0x240, 0x240) if placement & 2 else (0x2040, 0x640)
                    name_rva = 0x260 if placement & 4 else 0x2060
                    struct.pack_into("<II", data, 0x58 + (112 if plus else 96), directory_rva, 0x100)
                    struct.pack_into("<III", data, directory_offset + 28, arrays_rva, arrays_rva + 16, arrays_rva + 24)
                    struct.pack_into("<I", data, arrays_offset + 16, name_rva)
                    path.write_bytes(data)
                    self.assertEqual(pe_imports.parse(path)["exports"], ["first_func", "#7", "#9"])

    def mixed_imports(self, plus, placement, delayed):
        path = self.consumer(plus=plus)
        data = bytearray(path.read_bytes())
        dd = 0x58 + (112 if plus else 96)
        struct.pack_into("<I", data, 0x58 + 60, 0x400)
        if delayed:
            struct.pack_into("<II", data, dd + 8, 0, 0)
            data[0x700:0x740] = bytes(64)
        data[0x200:0x300] = data[0x700:0x800]
        directory_rva, directory_offset = (0x200, 0x200) if placement & 1 else (0x2100, 0x700)
        thunks_rva, thunks_offset = (0x240, 0x240) if placement & 2 else (0x2140, 0x740)
        dll_rva, name_rva = (0x270, 0x290) if placement & 4 else (0x2170, 0x2190)
        struct.pack_into("<II", data, dd + (13 if delayed else 1) * 8, directory_rva, 64 if delayed else 40)
        if delayed:
            struct.pack_into("<IIIIIIII", data, directory_offset, 1, dll_rva, 0, thunks_rva, thunks_rva, 0, 0, 0)
        else:
            struct.pack_into("<IIIII", data, directory_offset, thunks_rva, 0, 0, dll_rva, thunks_rva)
        ordinal = 1 << (63 if plus else 31)
        struct.pack_into("<QQQQQ" if plus else "<IIIII", data, thunks_offset,
                         ordinal | 7, ordinal | 8, ordinal | 9, name_rva, 0)
        path.write_bytes(data)
        return path

    def test_imports_can_mix_headers_and_sections(self):
        for plus in (False, True):
            for placement in range(8):
                with self.subTest(plus=plus, placement=placement):
                    path = self.mixed_imports(plus, placement, delayed=False)
                    self.assertEqual(pe_imports.parse(path)["imports"], {
                        "provider.dll": ["#7", "#8", "#9", "first_func"],
                    })

    def test_delay_imports_can_mix_headers_and_sections(self):
        for plus in (False, True):
            for placement in range(8):
                with self.subTest(plus=plus, placement=placement):
                    path = self.mixed_imports(plus, placement, delayed=True)
                    self.assertEqual(pe_imports.parse(path)["delay"], {
                        "provider.dll": ["#7", "#8", "#9", "first_func"],
                    })

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
