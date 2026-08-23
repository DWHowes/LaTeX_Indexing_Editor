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
        # The PDFs only, deliberately -- documentation/ also holds the
        # .docx/.rtf authoring sources and their screenshot folder, none
        # of which a tester has any use for and all of which are several
        # times the size of what they produce. The same split is in
        # .gitignore, and for the same reason.
        ('documentation/*.pdf', 'documentation'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # rapidfuzz has an optional numpy-array integration (process.pyi/
    # process_cpp.py) that PyInstaller's static analyzer pulls in
    # defensively even though this app only uses rapidfuzz.fuzz on plain
    # strings (models/search_worker.py).
    #
    # This list used to also name torch, transformers, docling and the rest
    # of an ML stack left in the venv by an abandoned LLM-based
    # name-inversion experiment. Those packages have since been uninstalled
    # -- the venv now holds requirements-dev.txt and nothing else -- so the
    # excludes are gone with them. Only numpy stays, because it is a
    # *transitive* risk rather than a stray install: anything that pulls
    # numpy back in would reach the frozen build through rapidfuzz.
    excludes=['numpy'],
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
    # Embedded in the .exe, which is what Explorer and the taskbar read
    # before the app is running. The same file is set on the QApplication
    # at startup (main.py) for window and dialog icons.
    icon='icons/lix.ico',
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
