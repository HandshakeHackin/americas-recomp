"""Lower, pin the wave size and assemble every shader_NN.ll of a directory; report which ones validate.
usage: python -I lower_all.py <dir with shader_NN.ll> <out_dir> [wave=64] [dxasm=dxasm.exe] [--emulate]
For each shader writes <out>/sNN.ll (lowered), <out>/wNN.ll (SM 6.6; the wave size is pinned only when wave operations are used and xbox_dxil_lower.needs_wave64 says the shader can tell the wave size) and <out>/repl_NN.dxil (signed; the file bvh_test's BVH_REPLACE_DIR reads).
--emulate tries wave64_emulate.py first on every shader that would be pinned, which replaces the 64-lane wave operations with group-shared memory and leaves the wave size unpinned, so the shader also creates on a 32-lane device; <out>/eNN.ll holds the emulated text. A shader the emulation refuses (a wave operation outside the entry block) or cannot finish (an intrinsic it does not cover) is pinned as before and says so.
A validator complaint "Flags must match usage" (declared=X, actual=Y) is repaired by rewriting the declared shader-flags word and retrying."""
import glob, os, re, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from xbox_dxil_lower import needs_wave64
from wave64_emulate import emulate

plain = [a for a in sys.argv[1:] if not a.startswith("--")]
do_emulate = "--emulate" in sys.argv
src, out = plain[0], plain[1]
wave = plain[2] if len(plain) > 2 else "64"
dxasm = plain[3] if len(plain) > 3 else os.path.join(out, "dxasm.exe")
os.makedirs(out, exist_ok=True)
res = {}
for f in sorted(glob.glob(os.path.join(src, "shader_*.ll"))):
    n = re.search(r"shader_(\d+)", os.path.basename(f)).group(1)
    s_ll, w_ll, dxil = (os.path.join(out, p % n) for p in ("s%s.ll", "w%s.ll", "repl_%s.dxil"))
    r = subprocess.run([sys.executable, "-I", os.path.join(here, "xbox_dxil_lower.py"), f, s_ll], capture_output=True, text=True)
    if r.returncode:
        res[n] = "intrinsics left: " + r.stdout.strip().split(": ", 1)[-1]
        continue
    lowered = open(s_ll, encoding="utf-8").read()
    source, note, pin = s_ll, "", "0"
    if "@dx.op.wave" in lowered or "@dx.op.createHandleFromHeap" in lowered:
        pin = wave if "@dx.op.wave" in lowered and needs_wave64(open(f, encoding="utf-8", errors="ignore").read()) else "0"
        if do_emulate and pin != "0":
            try:
                emulated, _, left = emulate(lowered)
            except ValueError as error:
                note = "pinned, not emulated: %s; " % error
            else:
                if left:
                    note = "pinned, not emulated: %s left; " % ", ".join(sorted(left))
                else:
                    source, pin, note = os.path.join(out, "e%s.ll" % n), "0", "emulated; "
                    open(source, "w", encoding="utf-8", newline="\n").write(emulated)
        r = subprocess.run([sys.executable, "-I", os.path.join(here, "dxil_sm66_wave.py"), source, w_ll, pin], capture_output=True, text=True)
        if r.returncode:
            res[n] = note + "sm66 rewrite failed: " + (r.stderr.strip().splitlines() or ["?"])[-1]
            continue
    else:
        open(w_ll, "w", encoding="utf-8", newline="\n").write(open(s_ll, encoding="utf-8").read())
    for attempt in range(2):
        r = subprocess.run([dxasm, w_ll, dxil], capture_output=True, text=True)
        m = re.search(r"Flags declared=(\d+), actual=(\d+)", r.stdout)
        if m and attempt == 0:
            t = open(w_ll, encoding="utf-8").read()
            t = re.sub(r"(!\d+ = !\{i32 0, i64 )\d+(, i32 4)", r"\g<1>%s\g<2>" % m.group(2), t)
            open(w_ll, "w", encoding="utf-8", newline="\n").write(t)
            continue
        break
    res[n] = note + ("ok" if r.returncode == 0 else "validation: " + " | ".join(l for l in r.stdout.splitlines() if "error" in l)[:300])
ok = sum(1 for v in res.values() if v.endswith("ok"))
for n, v in res.items():
    print(n, v)
print("%d of %d assembled and signed" % (ok, len(res)))
