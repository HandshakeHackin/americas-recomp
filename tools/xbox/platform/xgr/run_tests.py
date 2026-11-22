"""Build xgameruntime.dll with the runtime and every test_*.cpp next to this script with MSVC, run the tests, and exit non-zero if any fails.

usage: python tools/xbox/platform/xgr/run_tests.py <dir with the Xodus *.idl> [--out build-xgr] [--only name ...]

Windows only. Finds Visual Studio with vswhere (as build_msvc.py does); run it from a normal Windows shell.
The IDLs are read to make table.json (idl_table.py) and the stub source (gen_stub.py) in the output directory; neither is committed.
Each test runs in the output directory with table.json next to it; test_save also runs a second time with `reopen`.
In GitHub Actions each FAIL line becomes an error annotation and a summary table is written to the job summary.
"""
import argparse, glob, locale, os, pathlib, shutil, subprocess, sys, time, traceback

HERE = pathlib.Path(__file__).resolve().parent
RUNTIME = HERE / "runtime"
sys.path.insert(0, str(HERE.parents[1]))
from build_msvc import vc_env

DLL_LIBS = ["shell32.lib", "ole32.lib", "user32.lib"]
TEST_LIBS = ["advapi32.lib", "user32.lib", "ole32.lib", "shell32.lib", "runtimeobject.lib"]
TIMEOUT = 300


def annotate(name, line, level="error"):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::%s title=xgr %s::%s" % (level, name, line.replace("%", "%25").replace("\r", "").replace("\n", " ")), flush=True)


def run(cmd, env, cwd, name):
    print(">", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, errors="replace")
    print(p.stdout + p.stderr, flush=True)
    if p.returncode:
        errors = [l.strip() for l in (p.stdout + p.stderr).splitlines() if ": error" in l or ": fatal error" in l]
        for l in errors[:20] or ["exit code %d" % p.returncode]:
            annotate(name, l)
    return p.returncode


def fail(name, message):
    annotate(name, message)
    sys.exit(message)


def run_test(exe, args, env, cwd):
    started = time.time()
    try:
        p = subprocess.run([str(exe)] + args, env=env, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
        out, code = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        captured = []
        for value in (e.stdout, e.stderr):
            if isinstance(value, bytes):
                value = value.decode(locale.getpreferredencoding(False), errors="replace")
            captured.append(value or "")
        out, code = "".join(captured) + "\nFAIL timed out after %d s" % TIMEOUT, None
    return out, code, time.time() - started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("idl_dir")
    ap.add_argument("--out", default="build-xgr")
    ap.add_argument("--only", nargs="*", help="test names to run (e.g. test_system); default all")
    a = ap.parse_args()
    if os.name != "nt":
        sys.exit("run_tests.py builds with MSVC and runs Windows executables; run it on Windows.")
    idl_dir = str(pathlib.Path(a.idl_dir).resolve())
    out = pathlib.Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    annotate("run_tests", "building into %s from the IDLs in %s" % (out, idl_dir), "notice")
    try:
        env = vc_env()
    except Exception as e:
        fail("setup", "no MSVC environment: %s" % e)
    cl = shutil.which("cl", path=env.get("Path") or env.get("PATH"))
    if not cl:
        fail("setup", "cl.exe is not on the MSVC environment's PATH")

    py = [sys.executable, "-I"]
    if run(py + [str(HERE / "idl_table.py"), idl_dir, str(out / "table.json")], None, out, "idl_table.py"):
        fail("idl_table.py", "making table.json failed")
    if run(py + [str(HERE / "gen_stub.py"), str(out / "table.json"), str(out / "gen")], None, out, "gen_stub.py"):
        fail("gen_stub.py", "generating the stub failed")

    sources = [str(out / "gen" / "xgr_stub.cpp")] + sorted(glob.glob(str(RUNTIME / "*.cpp"))) + sorted(glob.glob(str(RUNTIME / "gtx" / "*.cpp")))
    dll = [cl, "/nologo", "/LD", "/O2", "/EHsc", "/std:c++20", "/DXGR_WITH_RUNTIME", "/I", str(RUNTIME), "/Fo:" + str(out) + "\\"] + sources
    dll += ["/Fe:" + str(out / "xgameruntime.dll"), "/link", "/DEF:" + str(out / "gen" / "xgameruntime.def")] + DLL_LIBS
    if run(dll, env, out, "xgameruntime.dll"):
        fail("xgameruntime.dll", "building xgameruntime.dll failed")

    tests = sorted(pathlib.Path(p) for p in glob.glob(str(HERE / "test_*.cpp")))
    if a.only:
        tests = [t for t in tests if t.stem in a.only]
    results = []
    for src in tests:
        name = src.stem
        objdir = out / "obj" / name
        objdir.mkdir(parents=True, exist_ok=True)
        cmd = [cl, "/nologo", "/EHsc", "/std:c++20", "/Fo:" + str(objdir) + "\\", str(src), "/Fe:" + str(out / (name + ".exe")), "/link"] + TEST_LIBS
        if run(cmd, env, out, name):
            results.append((name, "build failed", 0, 0.0))
            continue
        runs = [[]] + ([["reopen"]] if name == "test_save" else [])
        for args in runs:
            label = " ".join([name] + args)
            text, code, seconds = run_test(out / (name + ".exe"), args, env, out)
            print("=" * 20, label, "exit", code, "%.1fs" % seconds)
            print(text, flush=True)
            fails = [l for l in text.splitlines() if l.startswith("FAIL")]
            for l in fails:
                annotate(label, l)
            if code != 0 and not fails:
                annotate(label, "exit code %s" % code)
            results.append((label, "pass" if code == 0 else "FAIL", len(fails), seconds))

    rows = ["| test | result | FAIL lines | seconds |", "| --- | --- | --- | --- |"]
    rows += ["| %s | %s | %d | %.1f |" % r for r in results]
    print("\n".join(rows))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### xgameruntime stand-in tests (MSVC, Windows)\n\n" + "\n".join(rows) + "\n")
    if not results:
        fail("run_tests", "no test_*.cpp found next to run_tests.py")
    annotate("run_tests", "; ".join("%s %s" % (r[0], r[1]) for r in results), "notice")
    failed = [r[0] for r in results if r[1] != "pass"]
    if failed:
        sys.exit("failed: " + ", ".join(failed))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        main()
    except Exception:
        annotate("run_tests", traceback.format_exc().strip().splitlines()[-1])
        raise
