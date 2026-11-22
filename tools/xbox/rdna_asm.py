"""Tiny RDNA2 assembler for execution-harness test programs (inputs, not a general assembler).
Opcode numbers come from the decoder tables in rdna2.py (out_disasm, set XBOX_RDNA2_DIR). When rdna2.py is not found they come from LLVM
(rdna2_llvm.py) if an llvm-mc with the AMDGPU target is available, otherwise from the recompiler's decoder (rdna2_recomp.py). An llvm-mc
found on PATH that cannot decode AMDGPU (the official Windows LLVM builds have no such target) is passed over; XBOX_LLVM_MC or
XBOX_RDNA2=llvm insist on LLVM, XBOX_RDNA2=recomp picks the recompiler's tables. Every program is checked by decoding it back."""
import os, shutil, struct, sys
sys.path.insert(0, os.environ.get("XBOX_RDNA2_DIR", r"E:/Programming/rpf9shaders/out_disasm"))
_CHOICE = os.environ.get("XBOX_RDNA2")
try:
    if _CHOICE in ("llvm", "recomp"):
        raise ImportError
    import rdna2
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    rdna2 = None
    if _CHOICE == "llvm" or (_CHOICE != "recomp" and os.environ.get("XBOX_LLVM_MC")):
        import rdna2_llvm as rdna2
    elif _CHOICE != "recomp" and shutil.which("llvm-mc"):
        try:
            import rdna2_llvm as rdna2
        except (OSError, RuntimeError):
            rdna2 = None
        if rdna2 is not None and not rdna2.SOPP:
            rdna2 = None
    if rdna2 is None:
        import rdna2_recomp as rdna2

def _inv(t):
    return {v: k for k, v in t.items()}

SOPP, SMEM, VOP2, VOP1, MUBUF = (_inv(rdna2.SOPP), _inv(rdna2.SMEM), _inv(rdna2.VOP2), _inv(rdna2.VOP1), _inv(rdna2.MUBUF))
SOP1, VOPC, SOP2, SOPC, MIMG = _inv(rdna2.SOP1), _inv(rdna2.VOPC), _inv(rdna2.SOP2), _inv(rdna2.SOPC), _inv(rdna2.MIMG)
MTBUF = _inv(getattr(rdna2, "MTBUF", {}))
# rdna2.py's VOPC table is unreliable for the non-cmpx compares; RDNA2 u32 compares are 0xC0 + {f,lt,eq,le,gt,ne,ge,t}, cmpx adds 0x10.
for _i, _c in enumerate(['f', 'lt', 'eq', 'le', 'gt', 'lg', 'ge', 'tru']):
    VOPC['v_cmp_%s_u32' % _c] = 0xC0 + _i
    VOPC['v_cmpx_%s_u32' % _c] = 0xD0 + _i
EXEC_LO, VCC_LO = ('r', 126), ('r', 106)

def src(x):
    """operand: 'sN', 'vN', integer inline constant (-16..64) or ('lit', value)"""
    if isinstance(x, tuple):
        return (x[1], None) if x[0] == 'r' else (255, x[1])
    if isinstance(x, int):
        if 0 <= x <= 64:
            return 128 + x, None
        if -16 <= x < 0:
            return 192 - x, None
        return 255, x & 0xffffffff
    if x[0] == 's':
        return int(x[1:]), None
    if x[0] == 'v':
        return 256 + int(x[1:]), None
    raise ValueError(x)

class Program:
    def __init__(self):
        self.words = []
    def sopp(self, name, imm=0):
        self.words.append(0xBF800000 | (SOPP[name] << 16) | (imm & 0xffff))
    def smem(self, name, sdata, sbase, offset=0, soffset=None):
        self.words.append(0xF4000000 | (SMEM[name] << 18) | (sdata << 6) | (sbase >> 1))
        self.words.append(((0x7D if soffset is None else int(soffset[1:])) << 25) | offset)
    def vop2(self, name, vdst, s0, vsrc1):
        code, lit = src(s0)
        self.words.append((VOP2[name] << 25) | (vdst << 17) | (int(vsrc1[1:]) << 9) | code)
        if lit is not None:
            self.words.append(lit)
    def vop1(self, name, vdst, s0):
        code, lit = src(s0)
        self.words.append(0x7E000000 | (vdst << 17) | (VOP1[name] << 9) | code)
        if lit is not None:
            self.words.append(lit)
    def sop1(self, name, sdst, s0):
        sdst = sdst[1] if isinstance(sdst, tuple) else sdst
        code, lit = src(s0)
        self.words.append(0xBE800000 | (sdst << 16) | (SOP1[name] << 8) | code)
        if lit is not None:
            self.words.append(lit)
    def sop2(self, name, sdst, s0, s1):
        sdst = sdst[1] if isinstance(sdst, tuple) else sdst
        c0, l0 = src(s0)
        c1, l1 = src(s1)
        if l0 is not None and l1 is not None and l0 != l1:
            raise ValueError("SOP2 can only encode one unique literal value")
        self.words.append(0x80000000 | (SOP2[name] << 23) | (sdst << 16) | (c1 << 8) | c0)
        lit = l0 if l0 is not None else l1
        if lit is not None:
            self.words.append(lit)
    def sopc(self, name, s0, s1):
        c0, l0 = src(s0)
        c1, l1 = src(s1)
        if l0 is not None and l1 is not None and l0 != l1:
            raise ValueError("SOPC can only encode one unique literal value")
        self.words.append(0xBF000000 | (SOPC[name] << 16) | (c1 << 8) | c0)
        lit = l0 if l0 is not None else l1
        if lit is not None:
            self.words.append(lit)
    def mimg(self, name, vdata, vaddr, srsrc, dmask=0xf, dim=1, ssamp=0, a16=False):
        op = MIMG[name]
        self.words.append(0xF0000000 | ((op & 0x7f) << 18) | ((op >> 7) & 1) | (dim << 3) | (dmask << 8))
        self.words.append((int(a16) << 30) | (ssamp // 4 << 21) | ((srsrc // 4) << 16) | (vdata << 8) | vaddr)
    def branch_fwd(self, name):
        self.words.append(0xBF800000 | (SOPP[name] << 16))
        return len(self.words) - 1
    def patch_to_here(self, index):
        self.words[index] = (self.words[index] & 0xffff0000) | ((len(self.words) - (index + 1)) & 0xffff)
    def ds(self, name, vdst, addr, data0=0, data1=0, offset=0):
        op = _inv(rdna2.DS)[name]
        self.words.append(0xD8000000 | (op << 18) | (offset & 0xffff))
        self.words.append((vdst << 24) | (data1 << 16) | (data0 << 8) | addr)
    def label(self):
        return len(self.words)
    def branch_to(self, name, target):
        # simm16 is relative to the instruction after the branch, in dwords
        self.words.append(0xBF800000 | (SOPP[name] << 16) | ((target - (len(self.words) + 1)) & 0xffff))
    def vopc(self, name, s0, vsrc1):
        code, lit = src(s0)
        self.words.append(0x7C000000 | (VOPC[name] << 17) | (int(vsrc1[1:]) << 9) | code)
        if lit is not None:
            self.words.append(lit)
    def mubuf(self, name, vdata, vaddr, srsrc, soffset=128, offset=0, offen=True, idxen=False):
        self.words.append(0xE0000000 | (MUBUF[name] << 18) | (int(idxen) << 13) | (int(offen) << 12) | offset)
        self.words.append((soffset << 24) | ((srsrc // 4) << 16) | (vdata << 8) | vaddr)
    def mtbuf(self, name, vdata, vaddr, srsrc, fmt, soffset=128, offset=0, offen=False, idxen=True):
        op = MTBUF[name]
        self.words.append(0xE8000000 | ((fmt & 0x7f) << 19) | ((op & 7) << 16) | (int(idxen) << 13) | (int(offen) << 12) | offset)
        self.words.append((soffset << 24) | (((op >> 3) & 1) << 21) | ((srsrc // 4) << 16) | (vdata << 8) | vaddr)
    def bytes(self):
        return struct.pack('<%dI' % len(self.words), *self.words)
    def disasm(self):
        ins, _ = rdna2.sweep(self.bytes(), 0, len(self.words) * 4)
        return [str(i.text) for i in ins]
