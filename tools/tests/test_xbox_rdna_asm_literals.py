import importlib.util
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "xbox" / "rdna_asm.py"


class ScalarLiteralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("rdna_asm_literals", SCRIPT)
        cls.asm = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"XBOX_RDNA2": "recomp"}):
            spec.loader.exec_module(cls.asm)

    def emit(self, program, kind, first, second):
        if kind == "sop2":
            program.sop2("s_add_u32", 0, first, second)
        else:
            program.sopc("s_cmp_eq_u32", first, second)

    def test_identical_literals_share_one_encoded_word(self):
        for kind, opcode in (("sop2", 0x8000FFFF), ("sopc", 0xBF06FFFF)):
            for value in (0, 0x12345678, 0xFFFFFFFF):
                with self.subTest(kind=kind, value=value):
                    program = self.asm.Program()
                    self.emit(program, kind, ("lit", value), ("lit", value))
                    self.assertEqual(program.bytes(), struct.pack("<II", opcode, value))

    def test_implicit_and_explicit_literal_sources_share_one_word(self):
        for kind, opcode in (("sop2", 0x8000FFFF), ("sopc", 0xBF06FFFF)):
            with self.subTest(kind=kind):
                program = self.asm.Program()
                self.emit(program, kind, -17, ("lit", 0xFFFFFFEF))
                self.assertEqual(program.bytes(), struct.pack("<II", opcode, 0xFFFFFFEF))

    def test_one_literal_in_either_source(self):
        for kind, opcode in (("sop2", 0x80000000), ("sopc", 0xBF060000)):
            for first, second, sources in ((0x12345678, "s3", 0x03FF), ("s3", 0x12345678, 0xFF03)):
                with self.subTest(kind=kind, sources=sources):
                    program = self.asm.Program()
                    self.emit(program, kind, first, second)
                    self.assertEqual(program.bytes(), struct.pack("<II", opcode | sources, 0x12345678))

    def test_inline_sources_need_no_literal_word(self):
        for kind, opcode in (("sop2", 0x80000000), ("sopc", 0xBF060000)):
            with self.subTest(kind=kind):
                program = self.asm.Program()
                self.emit(program, kind, 0, 64)
                self.assertEqual(program.bytes(), struct.pack("<I", opcode | 0xC080))

    def test_different_literals_are_rejected_without_changing_the_program(self):
        for kind in ("sop2", "sopc"):
            with self.subTest(kind=kind):
                program = self.asm.Program()
                program.sopp("s_nop")
                before = program.bytes()
                with self.assertRaisesRegex(ValueError, "literal"):
                    self.emit(program, kind, 0x12345678, 0x87654321)
                self.assertEqual(program.bytes(), before)

    def test_the_next_instruction_starts_after_the_shared_literal(self):
        for kind, name in (("sop2", "s_add_u32"), ("sopc", "s_cmp_eq_u32")):
            with self.subTest(kind=kind):
                program = self.asm.Program()
                self.emit(program, kind, 0x12345678, 0x12345678)
                program.sopp("s_endpgm")
                instructions, bad = self.asm.rdna2.sweep(program.bytes(), 0, len(program.bytes()))
                self.assertEqual(bad, [])
                self.assertEqual([(i.name, i.off, i.size) for i in instructions], [(name, 0, 8), ("s_endpgm", 8, 4)])


if __name__ == "__main__":
    unittest.main()
