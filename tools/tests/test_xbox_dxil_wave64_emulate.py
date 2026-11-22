import contextlib
import io
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLATFORM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xbox", "platform")
sys.path.insert(0, PLATFORM)
import wave64_emulate as w64

HEAD = """target datalayout = "e-m:e-p:32:32-i1:32-i8:8-i16:16-i32:32-i64:64-f16:16-f32:32-f64:64-n8:16:32:64"
target triple = "dxil-ms-dx"

%dx.types.Handle = type { i8* }
%dx.types.fouri32 = type { i32, i32, i32, i32 }

"""
TAIL = """
declare %dx.types.Handle @dx.op.createHandle(i32, i8, i32, i32, i1) #2
attributes #0 = { nounwind readnone }
attributes #1 = { nounwind }
attributes #2 = { nounwind readonly }
!dx.version = !{!1}
!dx.shaderModel = !{!2}
!dx.entryPoints = !{!3}
!1 = !{i32 1, i32 5}
!2 = !{!"cs", i32 6, i32 5}
!3 = !{void ()* @main, !"main", null, null, !4}
!4 = !{i32 0, i64 524304, i32 4, !5}
!5 = !{i32 64, i32 1, i32 1}
"""


def module(body, decls=""):
    return HEAD + "define void @main() {\n" + body + "  ret void\n}\n" + decls + TAIL


def lower_of(name):
    path = os.path.join(PLATFORM, name)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    from xbox_dxil_lower import lower
    return lower(text)[0]


class TestWave64Emulate(unittest.TestCase):
    KERNELS = {"01": "wave64_emulate_kernel.ll", "02": "wave64_prefix_kernel.ll"}
    DECLARED = 524304
    ACTUAL = {"01": 1048592, "02": 16}

    def lower_all(self, validate, inputs_name="inputs"):
        run = subprocess.run
        attempts = []

        def fake_run(args, **kwargs):
            if args[0] != "dxasm.exe":
                return run(args, **kwargs)
            shader = Path(args[1])
            text = shader.read_text(encoding="utf-8")
            number = shader.stem[1:]
            self.assertIn("@__wave64.i32", text)
            self.assertNotIn("@dx.op.wave", text)
            metadata = re.search(r"!\d+ = !\{i32 0, i64 (\d+), i32 4,", text)
            self.assertIsNotNone(metadata, f"shader {number} has no flag metadata")
            flags = int(metadata[1])
            attempts.append((number, flags))
            code, message = validate(number, flags)
            return subprocess.CompletedProcess(args, code, message, "")

        script = os.path.join(PLATFORM, "lower_all.py")
        with tempfile.TemporaryDirectory() as directory:
            inputs = Path(directory, inputs_name)
            inputs.mkdir()
            for number, name in self.KERNELS.items():
                Path(inputs, f"shader_{number}.ll").write_bytes(Path(PLATFORM, name).read_bytes())
            output = io.StringIO()
            args = [script, str(inputs), str(Path(directory, "out")), "64", "dxasm.exe", "--emulate"]
            with (
                mock.patch.object(sys, "argv", args),
                mock.patch.object(sys, "path", sys.path.copy()),
                mock.patch.object(subprocess, "run", side_effect=fake_run),
                contextlib.redirect_stdout(output),
            ):
                runpy.run_path(script, run_name="__main__")
        return attempts, output.getvalue().splitlines()

    @staticmethod
    def flags_mismatch(declared, actual):
        return 1, f"validation failed: error: Flags must match usage.\nnote: Flags declared={declared}, actual={actual}\n"

    def test_lower_all_repairs_declared_flags_and_retries_once(self):
        def validate(number, flags):
            if flags != self.ACTUAL[number]:
                return self.flags_mismatch(flags, self.ACTUAL[number])
            return 0, ""

        attempts, lines = self.lower_all(validate)
        self.assertEqual(attempts, [
            ("01", self.DECLARED), ("01", self.ACTUAL["01"]),
            ("02", self.DECLARED), ("02", self.ACTUAL["02"]),
        ])
        self.assertEqual(lines, ["01 emulated; ok", "02 emulated; ok", "2 of 2 assembled and signed"])

    def test_lower_all_does_not_retry_a_second_flags_mismatch(self):
        attempts, lines = self.lower_all(lambda number, flags: self.flags_mismatch(flags, flags + 1))
        self.assertEqual(attempts, [
            ("01", self.DECLARED), ("01", self.DECLARED + 1),
            ("02", self.DECLARED), ("02", self.DECLARED + 1),
        ])
        self.assertEqual(lines, [
            "01 emulated; validation: validation failed: error: Flags must match usage.",
            "02 emulated; validation: validation failed: error: Flags must match usage.",
            "0 of 2 assembled and signed",
        ])

    def test_lower_all_does_not_retry_other_validation_errors(self):
        message = "validation failed: error: Instructions must be of an allowed type.\n"
        attempts, lines = self.lower_all(lambda number, flags: (1, message))
        self.assertEqual(attempts, [("01", self.DECLARED), ("02", self.DECLARED)])
        self.assertEqual(lines, [
            "01 emulated; validation: validation failed: error: Instructions must be of an allowed type.",
            "02 emulated; validation: validation failed: error: Instructions must be of an allowed type.",
            "0 of 2 assembled and signed",
        ])

    def test_lower_all_uses_the_filename_id_when_a_parent_contains_shader_digits(self):
        attempts, lines = self.lower_all(lambda number, flags: (0, ""), "shader_900-inputs")
        self.assertEqual(attempts, [("01", self.DECLARED), ("02", self.DECLARED)])
        self.assertEqual(lines, ["01 emulated; ok", "02 emulated; ok", "2 of 2 assembled and signed"])

    def test_bundled_kernels_emulate_to_no_wave_operations(self):
        for name in ("wavelower_kernel.ll",):
            text, count, left = w64.emulate(lower_of(name))
            self.assertGreater(count, 0, name)
            self.assertEqual(left, set(), name)
            self.assertNotIn("@dx.op.wave", text)
            self.assertNotIn("dxil-ms-xb", text)
            self.assertIn("call void @dx.op.barrier(i32 80, i32 3)", text)
            self.assertIn("@__wave64.i32 = internal addrspace(3) global [64 x i32] undef, align 4", text)
            self.assertIn("declare void @dx.op.barrier(i32, i32) #1", text)

    def test_synthetic_kernel_emulates(self):
        text, count, left = w64.emulate(lower_of("wave64_emulate_kernel.ll"))
        self.assertGreaterEqual(count, 9)
        self.assertEqual(left, set())
        self.assertNotIn("@dx.op.wave", text)
        self.assertIn("@__wave64.f32", text)
        self.assertIn("@__wave64.i64", text)

    def test_read_lane_first_writes_reads_and_syncs(self):
        body = "  %1 = call i32 @dx.op.waveReadLaneFirst.i32(i32 118, i32 7)\n"
        text, count, left = w64.emulate(module(body))
        self.assertEqual((count, left), (1, set()))
        self.assertIn("call i32 @dx.op.flattenedThreadIdInGroup.i32(i32 96)", text)
        self.assertIn("store i32 7, i32 addrspace(3)*", text)
        self.assertEqual(text.count("call void @dx.op.barrier(i32 80, i32 3)"), 2)
        self.assertRegex(text, r"%\d+ = load i32, i32 addrspace\(3\)\*")

    def test_read_lane_at_masks_the_index(self):
        body = "  %1 = call float @dx.op.waveReadLaneAt.f32(i32 117, float 1.0, i32 %p)\n"
        text, _, left = w64.emulate(module("  %p = call i32 @dx.op.groupId.i32(i32 94, i32 0)\n" + body))
        self.assertEqual(left, set())
        self.assertRegex(text, r"and i32 %[\w.]+, 63")

    def test_ballot_becomes_two_mask_halves(self):
        body = ("  %1 = call %dx.types.fouri32 @dx.op.waveActiveBallot(i32 116, i1 true)\n"
                "  %2 = extractvalue %dx.types.fouri32 %1, 0\n"
                "  %3 = extractvalue %dx.types.fouri32 %1, 1\n")
        text, count, left = w64.emulate(module(body))
        self.assertEqual((count, left), (1, set()))
        self.assertNotIn("fouri32", text.split("define void @main")[1].split("}")[0])
        self.assertIn("shl i64", text)
        self.assertIn("lshr i64", text)
        self.assertIn("trunc i64", text)

    def test_active_op_kinds(self):
        cases = {"i8 0, i8 0": "add i32", "i8 1, i8 0": "mul i32",
                 "i8 2, i8 1": "icmp slt i32", "i8 3, i8 0": "icmp ugt i32",
                 "i8 2, i8 0": "icmp ult i32", "i8 3, i8 1": "icmp sgt i32"}
        for flags, expected in cases.items():
            body = "  %%1 = call i32 @dx.op.waveActiveOp.i32(i32 119, i32 5, %s)\n" % flags
            text, _, left = w64.emulate(module(body))
            self.assertEqual(left, set())
            self.assertIn(expected, text, flags)

    def test_active_op_on_floats_and_bit_operations(self):
        body = ("  %1 = call float @dx.op.waveActiveOp.f32(i32 119, float 1.0, i8 2, i8 0)\n"
                "  %2 = call i32 @dx.op.waveActiveBit.i32(i32 120, i32 5, i8 2)\n")
        text, _, left = w64.emulate(module(body))
        self.assertEqual(left, set())
        self.assertIn("fcmp olt float", text)
        self.assertIn("xor i32", text)

    def test_wave_operation_outside_the_entry_block_is_refused(self):
        body = "  br label %next\nnext:\n  %1 = call i32 @dx.op.waveReadLaneFirst.i32(i32 118, i32 1)\n"
        with self.assertRaises(ValueError):
            w64.emulate(module(body))

    def test_a_group_that_is_not_64_threads_is_refused(self):
        body = "  %1 = call i32 @dx.op.waveReadLaneFirst.i32(i32 118, i32 1)\n"
        text = module(body).replace("!5 = !{i32 64, i32 1, i32 1}", "!5 = !{i32 32, i32 1, i32 1}")
        with self.assertRaises(ValueError):
            w64.emulate(text)
        missing = module(body).replace("!4 = !{i32 0, i64 524304, i32 4, !5}", "!4 = !{i32 0, i64 524304, i32 4}")
        with self.assertRaises(ValueError):
            w64.emulate(missing)
        self.assertEqual(w64.group_threads(module(body)), 64)

    def test_uncovered_intrinsic_is_reported_and_kept(self):
        body = "  %1 = call i32 @dx.op.waveActiveBit.i32(i32 120, i32 5, i8 9)\n"
        text, count, left = w64.emulate(module(body))
        self.assertEqual(count, 0)
        self.assertEqual(left, {"@dx.op.waveActiveBit("})
        self.assertIn("@dx.op.waveActiveBit", text)

    def test_unused_wave_declarations_are_dropped(self):
        decls = "declare i32 @dx.op.waveGetLaneIndex(i32) #0\n"
        body = "  %1 = call i32 @dx.op.waveGetLaneIndex(i32 111)\n"
        text, _, left = w64.emulate(module(body, decls))
        self.assertEqual(left, set())
        self.assertNotIn("declare i32 @dx.op.waveGetLaneIndex", text)
        self.assertIn("declare i32 @dx.op.flattenedThreadIdInGroup.i32(i32) #0", text)

    def test_lane_count_is_first_lane_and_boolean_reductions(self):
        body = ("  %1 = call i32 @dx.op.waveGetLaneCount(i32 112)\n"
                "  %2 = call i1 @dx.op.waveIsFirstLane(i32 110)\n"
                "  %3 = call i1 @dx.op.waveAnyTrue(i32 113, i1 true)\n"
                "  %4 = call i1 @dx.op.waveAllTrue(i32 114, i1 true)\n"
                "  %5 = call i1 @dx.op.waveActiveAllEqual.i32(i32 115, i32 3)\n")
        text, count, left = w64.emulate(module(body))
        self.assertEqual((count, left), (5, set()))
        self.assertIn("add i32 0, 64", text)
        self.assertIn("icmp eq i32", text)
        self.assertIn("or i32", text)
        self.assertIn("and i32", text)
        self.assertRegex(text, r"icmp ne i32 %[\w.]+, 0")

    def test_prefix_operation_is_exclusive_and_starts_from_the_identity(self):
        body = ("  %1 = call i32 @dx.op.wavePrefixOp.i32(i32 121, i32 %x, i8 0, i8 0)\n"
                "  %2 = call i32 @dx.op.wavePrefixOp.i32(i32 121, i32 %x, i8 2, i8 1)\n"
                "  %3 = call float @dx.op.wavePrefixOp.f32(i32 121, float 1.5, i8 2, i8 0)\n")
        text, count, left = w64.emulate(module("  %x = call i32 @dx.op.groupId.i32(i32 94, i32 0)\n" + body))
        self.assertEqual((count, left), (3, set()))
        self.assertIn("icmp slt i32 0,", text)
        self.assertIn("select i1", text)
        self.assertIn("2147483647", text)
        self.assertIn("0x7FF0000000000000", text)
        self.assertIn("fcmp olt float", text)

    def test_quad_operations_read_inside_the_group_of_four(self):
        body = ("  %1 = call i32 @dx.op.quadReadLaneAt.i32(i32 122, i32 1, i32 2)\n"
                "  %2 = call i32 @dx.op.quadOp.i32(i32 123, i32 1, i8 0)\n"
                "  %3 = call i32 @dx.op.quadOp.i32(i32 123, i32 1, i8 2)\n")
        text, count, left = w64.emulate(module(body))
        self.assertEqual((count, left), (3, set()))
        self.assertIn(", -4", text)
        self.assertIn("xor i32", text)
        self.assertRegex(text, r"xor i32 %[\w.]+, 3")

    def test_an_unsupported_quad_operation_is_reported(self):
        body = "  %1 = call i32 @dx.op.quadOp.i32(i32 123, i32 1, i8 5)\n"
        text, count, left = w64.emulate(module(body))
        self.assertEqual(count, 0)
        self.assertEqual(left, {"@dx.op.quadOp("})
        self.assertIn("@dx.op.quadOp", text)

    def test_command_line_exit_status(self):
        script = os.path.join(PLATFORM, "wave64_emulate.py")
        for body, expected in (("  %1 = call i32 @dx.op.waveGetLaneIndex(i32 111)\n", 0),
                               ("  %1 = call i32 @dx.op.quadOp.i32(i32 123, i32 1, i8 5)\n", 1)):
            with open(os.path.join(PLATFORM, "_w64_test.ll"), "w", encoding="utf-8") as f:
                f.write(module(body))
            try:
                r = subprocess.run([sys.executable, "-I", script, os.path.join(PLATFORM, "_w64_test.ll"),
                                    os.path.join(PLATFORM, "_w64_test_out.ll")], capture_output=True, text=True)
            finally:
                for leftover in ("_w64_test.ll", "_w64_test_out.ll"):
                    path = os.path.join(PLATFORM, leftover)
                    if os.path.exists(path):
                        os.remove(path)
            self.assertEqual(r.returncode, expected, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
