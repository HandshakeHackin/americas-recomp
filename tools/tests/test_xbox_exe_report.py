import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


PLATFORM = Path(__file__).resolve().parents[1] / "xbox" / "platform"
spec = importlib.util.spec_from_file_location("xbox_exe_report", PLATFORM / "exe_report.py")
exe_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe_report)


class XboxExeHeaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "synthetic.exe"

    def image(self, pe_offset=0x80, plus=True, sections=(".text", ".rdata")):
        optional_size = 240 if plus else 224
        optional = pe_offset + 24
        table = optional + optional_size
        header_size = (table + 40 * len(sections) + 0x1FF) & ~0x1FF
        first_section = (header_size + 0xFFF) & ~0xFFF
        data = bytearray(header_size)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, pe_offset)
        data[pe_offset:pe_offset + 4] = b"PE\0\0"
        struct.pack_into("<HHIIIHH", data, pe_offset + 4,
                         0x8664 if plus else 0x14C, len(sections), 0, 0, 0, optional_size, 0x22)
        struct.pack_into("<H", data, optional, 0x20B if plus else 0x10B)
        struct.pack_into("<I", data, optional + 16, first_section + 0x34)
        struct.pack_into("<Q" if plus else "<I", data, optional + (24 if plus else 28),
                         0x140000000 if plus else 0x400000)
        struct.pack_into("<IIII", data, optional + 32, 0x1000, 0x200, 0, 0)
        struct.pack_into("<II", data, optional + 56, first_section + len(sections) * 0x1000, header_size)
        struct.pack_into("<HH", data, optional + 68, 3, 0x160)
        struct.pack_into("<I", data, optional + (108 if plus else 92), 16)
        for i, name in enumerate(sections):
            struct.pack_into("<8sIIII", data, table + 40 * i,
                             name.encode("ascii"), 0x100, first_section + i * 0x1000, 0, 0)
        self.path.write_bytes(data)

    def expected(self, plus=True, sections=(".text", ".rdata"), entry_rva="0x1034"):
        return {
            "machine": "0x8664" if plus else "0x14c",
            "timestamp": "1970-01-01",
            "entry_rva": entry_rva,
            "image_base": "0x140000000" if plus else "0x400000",
            "subsystem": "windows console",
            "dll_characteristics": "0x160",
            "sections": list(sections),
        }

    def test_normal_pe32_and_pe32_plus(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.image(plus=plus)
                self.assertEqual(exe_report.header(self.path), self.expected(plus))

    def test_pe_header_beyond_first_page(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.image(pe_offset=0x2000, plus=plus)
                self.assertEqual(exe_report.header(self.path), self.expected(plus, entry_rva="0x3034"))

    def test_optional_header_crosses_first_page(self):
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.image(pe_offset=0xFC0, plus=plus)
                self.assertEqual(exe_report.header(self.path), self.expected(plus, entry_rva="0x2034"))

    def test_section_table_crosses_first_page(self):
        names = tuple("s%03d" % i for i in range(96))
        for plus in (False, True):
            with self.subTest(plus=plus):
                self.image(plus=plus, sections=names)
                self.assertEqual(exe_report.header(self.path), self.expected(plus, names, entry_rva="0x2034"))

    def test_truncated_section_table_does_not_report_partial_names(self):
        self.image()
        self.path.write_bytes(self.path.read_bytes()[:0x80 + 24 + 240 + 2 * 40 - 1])
        with self.assertRaisesRegex(ValueError, "truncated PE optional header or section table"):
            exe_report.header(self.path)

    def test_truncated_optional_header_is_rejected(self):
        self.image()
        self.path.write_bytes(self.path.read_bytes()[:0x80 + 24 + 70])
        with self.assertRaisesRegex(ValueError, "truncated PE optional header or section table"):
            exe_report.header(self.path)


if __name__ == "__main__":
    unittest.main()
