# PyInstaller spec for question-tracker MCP server.
# Bundles fastmcp + transitive deps (pydantic, httpx, anyio, ...) into a single binary.
# Run: pyinstaller mcp_server.spec --distpath ../../dist --noconfirm

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for pkg in ("fastmcp", "mcp", "pydantic", "pydantic_core", "httpx", "anyio", "certifi", "sniffio", "h11"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["mcp_server.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="question-tracker-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
