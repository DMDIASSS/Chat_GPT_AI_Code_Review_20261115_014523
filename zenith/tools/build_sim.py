"""Build script for zenith_sim native pybind11 extension using CMake and Ninja."""
import hashlib, json, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def ensure_build_tools():
    cmake = shutil.which("cmake")
    ninja = shutil.which("ninja")
    gf_tools = ROOT.parent / "gigaforge" / "tools" / "runtime"
    if gf_tools.exists():
        direct_cmake = gf_tools / "cmake" / "data" / "bin" / "cmake.exe"
        if direct_cmake.exists():
            cmake = str(direct_cmake)
        for cand in [gf_tools / "ninja" / "data" / "bin" / "ninja.exe", gf_tools / "bin" / "ninja.exe", gf_tools / "Scripts" / "ninja.exe"]:
            if cand.exists():
                ninja = str(cand)
                break
    if not cmake or not ninja:
        raise FileNotFoundError(f"CMake or Ninja not found. cmake: {cmake}, ninja: {ninja}")
    return cmake, ninja

def get_msvc_env():
    env = dict(os.environ)
    if os.name == "nt" and not shutil.which("cl"):
        vswhere = pathlib.Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
        if not vswhere.exists():
            raise RuntimeError("Visual Studio 2022 C++ Build Tools required.")
        install_path = subprocess.check_output(
            [str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
            text=True
        ).strip()
        vcvars = pathlib.Path(install_path) / "VC/Auxiliary/Build/vcvars64.bat"
        output = subprocess.check_output(f'cmd.exe /d /s /c ""{vcvars}" >nul && set"', text=True)
        for line in output.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env

def build():
    cmake, ninja = ensure_build_tools()
    env = get_msvc_env()
    build_dir = ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    cmd_configure = [
        str(cmake), "-S", str(ROOT), "-B", str(build_dir), "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        f"-DPython_EXECUTABLE={sys.executable}",
        "-DPYBIND11_FINDPYTHON=ON"
    ]
    print(f"[Zenith Build] Configuring CMake with {cmake} and {ninja}...", flush=True)
    subprocess.run(cmd_configure, env=env, check=True)

    print("[Zenith Build] Compiling zenith_sim...", flush=True)
    subprocess.run([str(cmake), "--build", str(build_dir), "--parallel", "2"], env=env, check=True)

    pyd_files = list(build_dir.glob("zenith_sim*.pyd"))
    if not pyd_files:
        raise FileNotFoundError("Could not find compiled zenith_sim.pyd in build directory")
    
    pyd = pyd_files[0]
    out_dir = ROOT / "zenith"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / pyd.name
    shutil.copy2(pyd, target)
    print(f"[Zenith Build] SUCCESS! zenith_sim installed to: {target}", flush=True)
    print(f"[Zenith Build] SHA256: {sha256(target)}", flush=True)
    return target

if __name__ == "__main__":
    build()
