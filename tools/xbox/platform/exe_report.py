"""First look at a game executable (or any PE files): header facts, and what its imports need from the platform.

usage: exe_report.py <exe-or-dll-or-directory> [more ...] [--out report_dir] [--stubs]
  report_dir/report.md     header facts + the import breakdown
  report_dir/needs.json    {"dll": [names]} for everything nothing on this PC provides (input of stubgen.py)
  --stubs                  also generate logging stub DLLs for those (report_dir/stubs, see stubgen.py)

Classification of every imported function:
  standard   resolves on this PC (LoadLibrary + GetProcAddress)
  package    the DLL sits next to the file being examined and exports the name
  shim       one of the stand-ins in this directory (xmem.cpp, d3d12_xs.cpp) implements it
  needs      none of the above: it needs a real implementation, or at least a logging stub
Static imports only. Delay-load imports are included; imports resolved at run time (GetProcAddress, COM, vtables) are not visible.
Run on the 16 DLLs of the package it reproduces docs/xbox/PLATFORM_SURFACE.md (605 standard/package, 6 shim, 0 needs).
Windows only (it loads system DLLs to test them)."""
import collections, ctypes, json, os, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_imports

SHIMMED = {
    "xmem.dll": {"XMemAlloc", "XMemFree", "XMemGetWorkingSetStatistics", "XMemVirtualQuery"},
    "d3d12_xs.dll": {"D3D12SerializeVersionedRootSignature", "D3D12CreateRootSignatureDeserializer"},
}
SUBSYSTEMS = {1: "native", 2: "windows GUI", 3: "windows console", 14: "xbox", 16: "windows boot application"}


def header(path):
    with open(path, "rb") as f:
        f.seek(0x3C)
        pe = struct.unpack("<I", f.read(4))[0]
        f.seek(pe)
        d = f.read(24)
        machine, nsec, stamp = struct.unpack_from("<HHI", d, 4)
        osz = struct.unpack_from("<H", d, 20)[0]
        size = osz + 40 * nsec
        rest = f.read(size)
        if len(rest) != size:
            raise ValueError("truncated PE optional header or section table")
        d += rest
    opt = 24
    magic = struct.unpack_from("<H", d, opt)[0]
    entry = struct.unpack_from("<I", d, opt + 16)[0]
    base = struct.unpack_from("<Q", d, opt + 24)[0] if magic == 0x20B else struct.unpack_from("<I", d, opt + 28)[0]
    subsystem = struct.unpack_from("<H", d, opt + 68)[0]
    dllchar = struct.unpack_from("<H", d, opt + 70)[0]
    sections = [d[opt + osz + 40 * i:opt + osz + 40 * i + 8].rstrip(b"\0").decode("latin1") for i in range(nsec)]
    return {"machine": hex(machine), "timestamp": time.strftime("%Y-%m-%d", time.gmtime(stamp)), "entry_rva": hex(entry), "image_base": hex(base),
            "subsystem": SUBSYSTEMS.get(subsystem, str(subsystem)), "dll_characteristics": hex(dllchar), "sections": sections}


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                files += [os.path.join(root, n) for n in names if n.lower().endswith((".dll", ".exe"))]
        else:
            files.append(p)
    return files


def main():
    argv = sys.argv[1:]
    out = argv[argv.index("--out") + 1] if "--out" in argv else "exe_report"
    paths = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--out")]
    files = collect(paths)
    parsed = {f: pe_imports.parse(f) for f in files}
    parsed = {f: p for f, p in parsed.items() if p}
    # DLLs shipped next to the files examined count as "package"
    package = {os.path.basename(f).lower(): set(p["exports"]) for f, p in parsed.items()}
    gp = ctypes.windll.kernel32.GetProcAddress
    gp.restype = ctypes.c_void_p
    gp.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    sysdll = {}
    union = collections.defaultdict(lambda: collections.defaultdict(set))
    for f, p in parsed.items():
        for table in ("imports", "delay"):
            for dll, fns in p[table].items():
                for fn in fns:
                    union[dll][fn].add(os.path.basename(f))
    status, needs = {}, collections.defaultdict(list)
    for dll, fns in sorted(union.items()):
        for fn in sorted(fns):
            if dll in SHIMMED and fn in SHIMMED[dll] and not os.environ.get("EXE_REPORT_NO_SHIMS"):   # the variable is for testing stubgen
                st = "shim"
            elif dll in package:
                st = "package" if fn in package[dll] else "needs"
            else:
                if dll not in sysdll:
                    try:
                        sysdll[dll] = ctypes.WinDLL(dll)._handle
                    except OSError:
                        sysdll[dll] = None
                h = sysdll[dll]
                ok = h and gp(h, ctypes.cast(ctypes.c_void_p(int(fn[1:])), ctypes.c_char_p) if fn.startswith("#") else fn.encode())
                st = "standard" if ok else "needs"
            status[dll + "!" + fn] = st
            if st == "needs":
                needs[dll].append(fn)
    os.makedirs(out, exist_ok=True)
    count = collections.Counter(status.values())
    lines = ["# Platform report", "", "Files: " + ", ".join(os.path.basename(f) for f in parsed), ""]
    for f in parsed:
        if f.lower().endswith(".exe") or len(parsed) == 1:
            lines.append("`%s`: %s" % (os.path.basename(f), json.dumps(header(f))))
    lines += ["", "| class | functions |", "|---|---|"] + ["| %s | %d |" % (k, count[k]) for k in ("standard", "package", "shim", "needs")]
    if needs:
        lines += ["", "## needs an implementation (or a logging stub)"]
        for dll, fns in sorted(needs.items()):
            who = sorted({x for fn in fns for x in union[dll][fn]})
            lines.append("- **%s** (%d, imported by %s): %s" % (dll, len(fns), ", ".join(who), ", ".join(sorted(fns)[:25]) + (" ..." if len(fns) > 25 else "")))
    open(os.path.join(out, "report.md"), "w").write("\n".join(lines) + "\n")
    json.dump(needs, open(os.path.join(out, "needs.json"), "w"), indent=1)
    print("\n".join(lines))
    if "--stubs" in argv and needs:
        import stubgen
        print("stubs:", stubgen.generate(needs, os.path.join(out, "stubs")))


if __name__ == "__main__":
    main()
