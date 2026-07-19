# -*- mode: python ; coding: utf-8 -*-
# Build with:  .venv\Scripts\python.exe -m PyInstaller LatexIndexingEditor.spec --noconfirm
#
# --onedir build, contents kept flat next to the exe (contents_directory='.')
# rather than PyInstaller 6.x's default nested "_internal/" folder -- this
# matches models/app_paths.py's get_app_root(), which resolves bundled
# resources (data/, help/, icons/) relative to the executable's own folder.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data', 'data'),
        ('help', 'help'),
        ('icons', 'icons'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # rapidfuzz has an optional numpy-array integration (process.pyi/
    # process_cpp.py) that PyInstaller's static analyzer pulls in
    # defensively even though this app only uses rapidfuzz.fuzz on plain
    # strings (models/search_worker.py). numpy itself is leftover in this
    # venv from an abandoned LLM-based name-inversion experiment, not an
    # actual app dependency -- excluded here, along with the rest of that
    # ML stack, so none of it balloons the frozen build.
    excludes=[
        'numpy', 'torch', 'torchvision', 'pandas', 'scipy', 'opencv',
        'cv2', 'transformers', 'accelerate', 'docling_ibm_models', 'rapidocr', 'shapely',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LatexIndexingEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LatexIndexingEditor',
)
