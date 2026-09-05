# Producing a release

Written 2026-08-05, from the 0.3.0-alpha build. Run every command from the project
root in **PowerShell**.

> **Use PowerShell, not Git Bash.** Git Bash mangles Windows-style installer flags
> and paths, which once cost an afternoon chasing a false "the installer has hung"
> lead.

## 1. Decide the version, and change it in three places

All three must move together, or the About box, the installer and the download link
will disagree about which build is which.

| Where | What |
|---|---|
| `models/app_version.py` | `APP_VERSION = "0.3.0-alpha"` (and the example in `version_string()`'s docstring, which is cosmetic) |
| `installer/LatexIndexingEditor.iss` | `#define MyAppVersion "0.3.0-alpha"` |
| `README.md` | four occurrences — the download link, the filename, and the release-tag URL |

A test pins the first two against each other:

```
pytest tests/controllers/test_about_dialog.py
```

**`README.md` is not covered by any test.** A find-and-replace on the old version
string is the reliable way to catch all four occurrences.

## 2. Turn the changelog's Unreleased section into the release

In `CHANGELOG.md`, change `## Unreleased` to `## 0.3.0-alpha — 5 August 2026`, then
add at the end of that section, before the `---` that separates it from the previous
release:

- a short **Under the hood** list;
- an **Upgrading from &lt;previous version&gt;** list, saying plainly anything that
  will behave differently on a project the user already has.

Then add a fresh `## Unreleased` heading above it for the next cycle.

**Write the release notes as you go during the cycle, not here at the end.**
Reconstructing them from `git log` afterwards does not work on this project — the
commit messages are too terse ("changes for db commit on save" appears five times in
one release).

## 3. Regenerate the documentation PDFs, if the docs changed

Only these three ship, and only as PDFs:

```
documentation/User Guide - Alpha.pdf
documentation/Design Overview.pdf
documentation/Name Cache SQL Queries.pdf
```

Export them from their `.docx`/`.rtf` sources in Word. The sources and
`documentation/images/` deliberately do **not** ship — they are several times the
size of what they produce and a tester has no use for them. `.gitignore` and the
PyInstaller spec both encode that same split.

If you edited the User Guide, press **Ctrl+A** then **F9** in Word before exporting,
so figure numbers and the List of Figures are up to date.

## 4. Run the whole test suite

```
pytest
```

Fully green before you build. Takes about a minute.

## 5. Clear out the previous build

```
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
```

**Do not skip this.** The installer copies `dist\LatexIndexingEditor\*` recursively,
so anything left in there from a previous build — or from launching the app for a
quick test — gets bundled into the installer.

## 6. Build the frozen application

```
.venv\Scripts\python.exe -m PyInstaller LatexIndexingEditor.spec --noconfirm --clean
```

About a minute. Expect roughly 111 MB in `dist\LatexIndexingEditor` and a 5.3 MB exe.

## 7. Check what actually got bundled

```
Get-ChildItem dist\LatexIndexingEditor\documentation
Get-ChildItem dist\LatexIndexingEditor -Directory | Select-Object Name
```

The first should list exactly the three PDFs. The second must **not** contain
`session_logs`, `.session_logs` or `.session_backups` — if it does, the app was
launched from `dist` at some point and step 5 was skipped.

**And check that the shared package came with it.** This step could not see
`bookindexcore` at all until 5 September 2026, and the check is not the
obvious one: the package is pure Python, so PyInstaller puts it in the archive
embedded in the exe and ***there is no `bookindexcore` folder to look for***.
Ask the binary:

```
Select-String -Path dist\LatexIndexingEditor\LatexIndexingEditor.exe -Pattern bookindexcore -Encoding Byte -AllMatches | Measure-Object
```

**157 matches, measured 5 September 2026.** Then start the application, which
is the check the count only approximates:

```
dist\LatexIndexingEditor\LatexIndexingEditor.exe
```

It must open its window and stay open. A missing shared package fails on the
first import, so that failure is immediate and total rather than subtle.

### Why `pathex` is empty, and why that is not a bug

***It was believed to be one.*** After Phase 6a put the extraction branch on
`main`, this spec still read `pathex=[]` and had never named `bookindexcore`,
which looked like a build recipe that could not find the package the
application now depends on. The Word editor's spec names both trees and says
PyInstaller *"walks imports rather than following a `.pth`"*, which made the
conclusion look settled.

**A control build refuted it.** The spec as it stands, and the same spec with
the package named in `pathex`, produce **157 matches each**, and the frozen
application starts either way. The reason is the shape of the editable
install: both venvs carry `_editable_impl_bookindexcore.pth` holding **one
bare path**, which Python adds to `sys.path` at interpreter startup.
PyInstaller runs inside that interpreter and seeds its search from `sys.path`,
so it finds the package with no help from the spec.

Naming it would matter only for the *other* kind of editable install, the
import-hook shape that ships a `__editable___*_finder.py`, which neither venv
here has. So nothing is added: on this project's own rule, a line earns its
place by being **measured wrong** without it, and this one was not.

**If that shim shape ever changes, the count above goes to nothing and the
application stops on its first import** — which is exactly what this step now
catches.

## 8. Build the installer

```
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\LatexIndexingEditor.iss
```

Output lands in `dist_installer` as `LatexIndexingEditor-Setup-<version>.exe`,
roughly 33 MB. That folder keeps every previous release's installer too, so **pick
the file by version** rather than assuming there is only one.

## 9. Verify the round trip before publishing anything

Install to a temporary folder rather than over your own working copy:

```
$v = "0.3.0-alpha"
$target = "$env:TEMP\LIE_$v"
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
$p = Start-Process -FilePath "dist_installer\LatexIndexingEditor-Setup-$v.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/DIR=$target" -Wait -PassThru
Write-Output "exit code: $($p.ExitCode)"
Get-ChildItem "$target\documentation"
```

Then check each of these:

- the exit code is `0`;
- the three PDFs are in `$target\documentation`;
- the registry reports the right version:

```
Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" | Where-Object { $_.DisplayName -like "*LaTeX Indexing*" } | Select-Object DisplayName, DisplayVersion, InstallLocation
```

- all three Start Menu shortcuts exist — the app, the documentation folder, and the
  uninstaller:

```
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Filter "*LaTeX Indexing*"
```

- the app launches from the installed location and stays running:

```
$proc = Start-Process "$target\LatexIndexingEditor.exe" -PassThru
Start-Sleep -Seconds 14
Write-Output "still running: $(-not $proc.HasExited)"
Stop-Process -Id $proc.Id -Force
```

Then uninstall and confirm it left nothing behind:

```
Start-Process "$target\unins000.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART"
$w = 0
while ((Test-Path $target) -and $w -lt 60) { Start-Sleep 2; $w += 2 }
Write-Output "install dir gone: $(-not (Test-Path $target))"
```

**The uninstaller's exit code means nothing.** It copies itself to `%TEMP%` and
relaunches from there, so it returns immediately whether or not it worked — poll for
the directory to disappear, as above. Finally confirm the registry entry, the Start
Menu shortcuts and any `LatexIndexingEditor` process are all gone.

## 10. Publish on GitHub

Through the web UI. The `gh` CLI is not installed on the build machine, and `git
fetch` there fails with an SSL certificate error, so the tag and release cannot be
created or confirmed from the command line.

1. Commit and push everything, **including the three PDFs**. They are tracked
   (`.gitignore` has `documentation/*` plus `!documentation/*.pdf`), so check
   `git status` actually lists them.
2. **Releases → Draft a new release.**
3. Tag: `v<version>`, e.g. `v0.3.0-alpha`. Create it on publish.
4. Title: the same version.
5. Body: paste that version's section from `CHANGELOG.md`.
6. Attach `dist_installer\LatexIndexingEditor-Setup-<version>.exe`.
7. Tick **Set as a pre-release**. Easy to miss — it was missed on 0.3.0-alpha and had
   to be fixed afterwards. Alpha builds are pre-releases, which is also why
   `README.md` links to the specific tag and not to `/latest/`: the
   `/releases/latest/` shortcut skips pre-releases entirely.
8. Publish, then check both of these on the
   [releases list](https://github.com/DWHowes/LaTeX_Indexing_Editor/releases):
   - the new release carries a **Pre-release** badge, not **Latest**;
   - the download link in `README.md` downloads the file rather than 404ing.

If the pre-release flag was missed, it can be fixed at any time: open the release,
click the pencil icon, tick the box, **Update release**. Editing a release leaves the
tag, the attached assets and their download URLs untouched, so nothing has to be
re-uploaded and no link breaks.

---

## Things that have gone wrong before

**Runtime state ending up inside the installer.** The app writes `session_logs` and
`data\name_cache.db` next to itself. Launch it from `dist` even once and those get
bundled. Step 5 prevents it; step 7 catches it.

**Session logs not appearing where you expect.** `SessionLogger` builds its path from
the *current working directory*, not from the application folder, so the log follows
whatever launched the process — a test launch from a prompt sitting in the project
root writes its log into the project root. This is not a broken build.

**`PySide6-Essentials` vs the full metapackage.** `requirements.txt` uses
Essentials. Never "downgrade" a venv that already has the full `PySide6` metapackage
by uninstalling the Addons — the two share files on disk, pip's uninstall orphans
them, and `QtCore` then fails to import with an unhelpful *DLL load failed*. Build a
fresh venv instead.

**The frozen build cannot find `help/`, `icons/` or `data/`.** Check that
`contents_directory='.'` is still on `EXE(...)` in the spec file and not on
`COLLECT(...)`. PyInstaller 6.x nests everything under `_internal/` otherwise, and
`models/app_paths.py`'s `get_app_root()` resolves bundled resources relative to the
exe's own folder.

**Any new code that needs a bundled file** must go through `get_app_root()`. Bare
`__file__` arithmetic and relative path strings both work in development and both
break once frozen.
