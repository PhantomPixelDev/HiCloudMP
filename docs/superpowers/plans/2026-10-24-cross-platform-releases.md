# Cross-Platform Releases (Linux x86_64 + macOS Apple Silicon) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every tagged release of HiCloudMP ships Windows (existing), Linux x86_64, and macOS Apple Silicon artifacts from the same pipeline — AppImage + tarball on Linux, `.app` in a DMG on macOS — with stable download URLs and README guidance for all three.

**Architecture:** One expanded workflow (renamed `windows-build.yml` → `build.yml`): the current Nuitka+Inno Windows job stays as-is; two new sibling jobs (ubuntu-latest, macos-15) run the same Nuitka+PySide6 build with per-OS bundling steps, then a single `release` job (all three `needs`) publishes the artifact set on `v*` tags — all-or-nothing. `tests/test_release_packaging.py` (content-assertion suite) is extended in a test-first cycle per task so the pipeline contract is testable on any machine without running CI.

**Tech Stack:** GitHub Actions, Nuitka 4.3.1, PySide6 6.10.3, Python 3.12, appimagetool, hdiutil, ad-hoc codesign, imageio-ffmpeg (pinned static ffmpeg for Linux/macOS), pytest.

**Spec:** Approved in chat (2026-10-24 brainstorming session with PhantomPixelDev); the decided scope and constraints live in **Global Constraints** below.

## Global Constraints

- Build pins identical on all three jobs: `PySide6==6.10.3`, `nuitka==4.3.1`, Python `3.12` (same toolchain as the existing Windows job).
- ffmpeg on Linux/macOS comes from a pinned PyPI package (`imageio-ffmpeg==<exact version pinned during Task 2>`), copied next to the compiled app binary — this feeds the existing `cover_extractor.find_ffmpeg()` exe-dir lookup. No download aliases allowed anywhere (`ffmpeg-release-essentials.zip` precedent).
- No floating/`continuous`/`latest` URLs for any downloaded tool; when a tool must be downloaded by URL (e.g. appimagetool), pin a tagged release and record its sha256 in a workflow comment (same discipline as the Windows ffmpeg pin).
- Existing stable Windows aliases are untouched: `HiCloudMP-Setup.exe`, `HiCloudMP-portable.zip`. New stable aliases: `HiCloudMP-macOS.dmg`, `HiCloudMP-linux-x86_64.AppImage` (linked from README via `releases/latest/download/...`).
- macOS target: **Apple Silicon (arm64) only** (macos-15 runner; Intel runner images are retired). README says so explicitly. Builds are ad-hoc signed (`codesign --force --deep --sign -`), NOT notarized; README documents the Gatekeeper first-launch steps and the optional `$99/yr` notarization path.
- App code is not touched: non-Windows keeps plaintext credential storage (documented `secure_store.py` policy); `APP_VERSION` in `updates_check.py` is not bumped by this work.
- Release is all-or-nothing: the `release` job requires `build-windows`, `build-linux`, `build-macos`, so a broken platform never half-publishes a release.
- Prerelease marking: tags containing `rc` publish as prerelease (`prerelease: ${{ contains(github.ref_name, 'rc') }}`).

## Review Focus

1. **Ubuntu user without libfuse2** — double-clicking the AppImage does nothing. Expected: README names the AppImage FUSE2 requirement (`sudo apt install libfuse2`) and offers the tarball as fallback. → pinned by `test_readme_documents_linux_platform_notes` (Task 4).
2. **macOS user (unsigned app)** — Gatekeeper blocks first launch. Expected: README gives both routes (Right-click → Open once; or `xattr -dr com.apple.quarantine`) and states Apple-Silicon-only. → pinned by `test_readme_documents_macos_platform_notes` (Task 4).
3. **Windows user regression** — the established `releases/latest/download/HiCloudMP-Setup.exe` / `-portable.zip` links must keep resolving after the release step moves to a central job. → pinned by `test_release_publishes_all_platform_assets` (Task 4).
4. **Update-check mismatch** — an rc validation tag must not trigger update prompts (compare_versions refuses rc). → existing `tests/test_update_check.py` covers this; Task 5 re-runs the suite to confirm no behavior broke.
5. **Qt multimedia backend missing per OS** — same regression class as the documented v1.0.0 Windows failure ("packaged app played nothing") now applies to the new platforms; each platform job must copy the multimedia dir AND the av/sw libs with OS-correct extensions. → pinned by `test_workflow_bundles_qt_multimedia_backend_on_all_platforms` (Task 3, after Linux lands in Task 2).

---

### Task 1: Rename the workflow to `build.yml` (contract moves with it)

**Files:**
- Rename: `.github/workflows/windows-build.yml` → `.github/workflows/build.yml` (contents unchanged in this task)
- Modify: `tests/test_release_packaging.py` (`_wf()` path, line 9)
- Modify: `README.md` (CI badge line ~128, packaging line ~116)

**Interfaces:**
- Consumes: existing tests in `tests/test_release_packaging.py` (all Windows assertions must keep passing after the rename)
- Produces: `.github/workflows/build.yml` — the file every later task extends; `_wf()` still returns its full text

- [ ] **Step 1: Write the failing test**

In `tests/test_release_packaging.py`, replace `_wf()`'s target with `build.yml` and add:

```python
def test_build_workflow_replaces_windows_only_workflow():
    wf_path = ROOT / ".github" / "workflows" / "build.yml"
    assert wf_path.exists(), ".github/workflows/build.yml missing"
    assert not (ROOT / ".github" / "workflows" / "windows-build.yml").exists(), \
        "windows-build.yml must be renamed, not duplicated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: FAIL on `test_build_workflow_replaces_windows_only_workflow` (build.yml missing)

- [ ] **Step 3: Rename the workflow file**

`git mv .github/workflows/windows-build.yml .github/workflows/build.yml`, then update `README.md`: badge URL path `windows-build.yml` → `build.yml` (line ~128) and the packaging paragraph filename (line ~116) → `build.yml`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: PASS (all existing Windows assertions — `main.dist\\ffmpeg.exe`, `essentials_build.zip`, Inno/ISCC checks — still valid against the renamed file)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "build: rename windows-build.yml to build.yml ahead of multi-platform jobs"
```

### Task 2: Linux x86_64 job (Nuitka + AppImage + tarball + bundled ffmpeg)

**Files:**
- Modify: `.github/workflows/build.yml` (add `build-linux` job)
- Modify: `tests/test_release_packaging.py` (new Linux contract tests)
- Create: `packaging/linux/HiCloudMP.desktop`

**Interfaces:**
- Consumes: `requirements.txt`, `requirements-linux.txt` (MPRIS: PyGObject/dbus-python), existing Nuitka flag set from the Windows job
- Produces: artifacts `HiCloudMP-linux` (containing versioned + stable-alias AppImage and tar.gz); artifact names consumed by the Task 4 `release` job; `find_ffmpeg()` finds bundled `ffmpeg` next to the binary (no app code change)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_release_packaging.py`:

```python
def test_workflow_has_linux_job():
    wf = _wf()
    assert "build-linux:" in wf
    assert "runs-on: ubuntu-latest" in wf
    assert "--enable-plugin=pyside6" in wf
    assert "requirements-linux.txt" in wf, "MPRIS deps must ride along"
    assert "imageio-ffmpeg==" in wf, "linux ffmpeg must come from a pinned PyPI build"
    assert "get_ffmpeg_exe" in wf
    assert "chmod +x" in wf

def test_workflow_bundles_linux_qt_multimedia():
    wf = _wf()
    assert "plugins/multimedia" in wf
    assert "libavcodec" in wf and "libswresample" in wf

def test_workflow_builds_appimage():
    wf = _wf()
    assert "appimagetool" in wf
    assert "--appimage-extract-and-run" in wf
    assert "appimagetool/releases/download/" in wf  # versioned release, not continuous
    assert "HiCloudMP.desktop" in wf

def test_linux_artifacts_and_stable_alias():
    wf = _wf()
    assert "HiCloudMP-linux-x86_64.AppImage" in wf  # stable alias name
    assert "linux-x86_64.tar.gz" in wf
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: the four new `linux` tests FAIL, existing tests PASS

- [ ] **Step 3: Create `packaging/linux/HiCloudMP.desktop`**

```ini
[Desktop Entry]
Type=Application
Name=HiCloud MP
Comment=Your music, local and cloud, in one quiet player
Exec=HiCloudMP
Icon=HiCloudMP
Categories=Audio;AudioVideo;
Terminal=false
```

- [ ] **Step 4: Add the `build-linux` job to `build.yml`**

Trigger conditions: `pull_request`, `push` (branches + `v*` tags) — same node as the existing jobs. Steps, each one action:

1. checkout, `setup-python@v5` 3.12
2. apt prereqs: `sudo apt-get update && sudo apt-get install -y ccache python3-dev libglib2.0-dev libdbus-1-dev libdbus-glib-1-dev` (build deps for `requirements-linux.txt`, per its own header comment)
3. pip install: `PySide6==6.10.3`, `nuitka==4.3.1`, `-r requirements.txt`, `-r requirements-linux.txt`, then `imageio-ffmpeg==<pin>` — **the exact pin is decided here**: `pip index versions imageio-ffmpeg` in a throwaway step or locally; record the newest stable version and write it with a comment ("shipped ffmpeg version X"). If the executor cannot pin during authoring, default `imageio-ffmpeg==0.6.0` and verify it resolves on all runners in Task 5.
4. Ruff-style sanity is already covered by the `lint` job — skip.
5. Run the test suite before burning Nuitka minutes: `QT_QPA_PLATFORM=offscreen pytest -x -q` (conftest already defaults offscreen; any failure is triaged in Task 5's validation cycle, not suppressed)
6. Nuitka: `python -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=pyside6 --output-dir=build --output-filename=HiCloudMP --include-data-file=web_panel.html=web_panel.html --include-data-file=icon.png=icon.png main.py`
7. Bundle Qt multimedia (mirrors the Windows step with `*.so`): after locating `PySide6.__file__` ($ps), copy `$ps/plugins/multimedia/*.so` → `build/main.dist/PySide6/qt-plugins/multimedia/`; if that source path doesn't exist on the Linux wheel, fall back to `$ps/Qt/plugins/multimedia/*.so` (both are checked by the same shell snippet, `set -e` on neither found)
8. Copy the ffmpeg backend libs the plugin links (`$ps/libavcodec*.so* $ps/libavformat*.so* $ps/libavutil*.so* $ps/libswresample*.so* $ps/libswscale*.so*`) → `build/main.dist/`
9. Bundle ffmpeg: `ffmpeg_bin=$(python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")`; copy → `build/main.dist/ffmpeg`; `chmod +x`
10. AppDir assembly (inline bash block, deterministic layout):
    ```
    mkdir -p AppDir/usr/bin
    cp -r build/main.dist/* AppDir/usr/bin/
    mv -f AppDir/usr/bin/main.bin AppDir/usr/bin/HiCloudMP 2>/dev/null || true
    cp packaging/linux/HiCloudMP.desktop AppDir/
    cp build/main.dist/icon.png AppDir/HiCloudMP.png
    ln -sf HiCloudMP.png AppDir/.DirIcon
    cp AppDir/usr/bin/HiCloudMP AppDir/AppRun
    chmod +x AppDir/AppRun AppDir/usr/bin/HiCloudMP
    ```
    (Nuitka names the linux output binary `main.bin`; the step renames it `<AppDir>/usr/bin/HiCloudMP` so `Exec=HiCloudMP` matches and `find_ffmpeg()` sits beside it.)
11. appimagetool: download a **versioned** release URL (pinned tag + sha256 recorded in a comment; if only `continuous` exists for the tool, pin to the exact continuous asset URL generated at a recorded date and note it) → `chmod +x appimagetool-x86_64.AppImage` → `./appimagetool-x86_64.AppImage --appimage-extract-and-run AppDir "HiCloudMP-$ver-linux-x86_64.AppImage"` (`$ver` from tag, `.TrimStart('v')` equivalent in bash: `${GITHUB_REF_NAME#v}` — on non-tag builds use the run number)
12. tarball: `tar -czf "HiCloudMP-$ver-linux-x86_64.tar.gz" -C build main.dist`
13. Stable alias: `cp "HiCloudMP-$ver-linux-x86_64.AppImage" HiCloudMP-linux-x86_64.AppImage` (versioned name = canonical alias for `releases/latest/download/...`)
14. `upload-artifact@v4`, name `HiCloudMP-linux`, path: the AppImage (.AppImage), alias copy, tar.gz

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "build(ci): linux x86_64 job — Nuitka standalone, AppImage, tarball, pinned imageio-ffmpeg"
```

### Task 3: macOS Apple Silicon job (`.app` bundle + ad-hoc codesign + DMG)

**Files:**
- Modify: `.github/workflows/build.yml` (add `build-macos` job)
- Modify: `tests/test_release_packaging.py` (new macOS contract tests)
- Create: `packaging/macos/make-icns.sh`

**Interfaces:**
- Consumes: `icon.png` (icns input), Nuitka `--macos-create-app-bundle`
- Produces: artifacts `HiCloudMP-macos` (versioned DMG + stable alias `HiCloudMP-macOS.dmg`) consumed by the Task 4 `release` job

- [ ] **Step 1: Write the failing tests**

```python
def test_workflow_has_macos_job():
    wf = _wf()
    assert "build-macos:" in wf
    assert "runs-on: macos-15" in wf
    assert "--macos-create-app-bundle" in wf
    assert "--macos-app-name=\"HiCloudMP\"" in wf
    assert "make-icns.sh" in wf

def test_workflow_adhoc_signs_app_bundle():
    wf = _wf()
    assert "codesign --force --deep --sign -" in wf

def test_workflow_bundles_macos_qt_multimedia():
    wf = _wf()
    assert "*.dylib" in wf
    assert "Contents/MacOS" in wf

def test_macos_dmg_and_stable_alias():
    wf = _wf()
    assert "hdiutil create" in wf and "UDZO" in wf
    assert "HiCloudMP-macOS.dmg" in wf
    assert "macos-arm64.dmg" in wf
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: four new macOS tests FAIL, rest PASS

- [ ] **Step 3: Create `packaging/macos/make-icns.sh`**

Bash script, exact behavior: builds `build/icon.icns` from `icon.png` via a plain Bourne snippet using `sips`+`arm64`-native `iconutil`: mkdir `icon.iconset`, `sips -s format png -z {16..512@2x}` for the standard sizes, `iconutil -c icns`. Keep under ~20 lines, `set -e`, `chmod +x` on itself in repo.

- [ ] **Step 4: Add the `build-macos` job to `build.yml`**

Steps (same trigger node as siblings):

1. checkout, `setup-python@v5` 3.12
2. pip install: `PySide6==6.10.3`, `nuitka==4.3.1`, `-r requirements.txt` (same pin comments), `imageio-ffmpeg==<pin>`
3. `QT_QPA_PLATFORM=offscreen pytest -x -q` (mac runners provide GUI session; offscreen is still fastest and matches conftest defaults)
4. `packaging/macos/make-icns.sh`
5. Nuitka: `python -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=pyside6 --macos-create-app-bundle --macos-app-name="HiCloudMP" --macos-app-icon=build/icon.icns --output-dir=build --output-filename=HiCloudMP --include-data-file=web_panel.html=web_panel.html --include-data-file=icon.png=icon.png main.py`
6. Locate the multimedia plugins + av/sw `*.dylib` (same discovery pattern as the Linux step 7 — check `$ps/plugins/multimedia`, fallback `$ps/Qt/plugins/multimedia`) and copy them into `build/main.dist/HiCloudMP.app/Contents/MacOS/` (plugins subfolder `PySide6/qt-plugins/multimedia/`; dylibs next to the executable). CI prints the resulting `Contents` tree so Task 5 can catch layout drift from Nuitka's macOS bundler.
7. Copy the imageio ffmpeg binary as `Contents/MacOS/ffmpeg`, `chmod +x`
8. `codesign --force --deep --sign - build/main.dist/HiCloudMP.app` (ad-hoc, mandatory for arm64 launch)
9. DMG: `hdiutil create -volname HiCloudMP -srcfolder build/main.dist/HiCloudMP.app -ov -format UDZO "HiCloudMP-$ver-macos-arm64.dmg"`
10. Stable alias: `cp "HiCloudMP-$ver-macos-arm64.dmg" HiCloudMP-macOS.dmg`
11. `upload-artifact@v4`, name `HiCloudMP-macos`, paths: both DMGs

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "build(ci): macos arm64 job — .app bundle, ad-hoc codesign, DMG"
```

### Task 4: Central `release` job + README downloads/notes for all platforms

**Files:**
- Modify: `.github/workflows/build.yml` (add `release` job; strip the old release steps from `build-windows`)
- Modify: `tests/test_release_packaging.py` (release-aggregation tests; also update `test_iss_*`-adjacent expectations that reference the old in-job publish)
- Modify: `README.md` (download table rows, platform notes, badge already done in Task 1)
- Modify: `packaging/HiCloudMP.iss`: none (Windows flow unchanged)

**Interfaces:**
- Consumes: artifacts `HiCloudMP-portable`/windows installer, `HiCloudMP-linux`, `HiCloudMP-macos`
- Produces: on `v*` tags, one GitHub release with all 6 files; stable aliases resolvable at `releases/latest/download/<file>`

- [ ] **Step 1: Write the failing tests**

```python
def test_release_publishes_all_platform_assets():
    wf = _wf()
    # all-or-nothing: every platform must pass before anything publishes
    assert "release:" in wf
    for need in ("build-windows", "build-linux", "build-macos"):
        assert need in wf
    assert "download-artifact" in wf
    assert "softprops/action-gh-release" in wf
    for asset in ("HiCloudMP-portable.zip", "HiCloudMP-Setup", "HiCloudMP-Setup.exe",
                  "HiCloudMP-linux-x86_64.AppImage", "linux-x86_64.tar.gz",
                  "HiCloudMP-macOS.dmg", "macos-arm64.dmg"):
        assert asset in wf, asset
    assert "prerelease: ${{ contains(github.ref_name, 'rc') }}" in wf

def test_readme_documents_all_platform_downloads():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "releases/latest/download/HiCloudMP-macOS.dmg" in src
    assert "releases/latest/download/HiCloudMP-linux-x86_64.AppImage" in src

def test_readme_documents_linux_platform_notes():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "libfuse2" in src.lower()

def test_readme_documents_macos_platform_notes():
    src = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Apple Silicon" in src
    assert "xattr -dr com.apple.quarantine" in src
    assert ("Right-click" in src or "right-click" in src)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_release_packaging.py -q`
Expected: new tests FAIL, rest PASS

- [ ] **Step 3: Add the `release` job; move publish out of `build-windows`**

- `release:` job, `needs: [build-windows, build-linux, build-macos]`, `if: startsWith(github.ref, 'refs/tags/v')`, `permissions: contents: write`
- `download-artifact@v4` with `merge-multiple: true` into one dir (keeps all three platforms' files), then `softprops/action-gh-release@v2` with the full 6-file list from the test, `generate_release_notes: true`, `prerelease: ${{ contains(github.ref_name, 'rc') }}`
- Inside `build-linux`/`build-macos`, the stable-alias copies stay step-local; remove the old publish + alias-copy steps from `build-windows` (its artifact upload now carries the Setup.exe pair for the central release); keep the `HiCloudMP-Setup.exe` alias creation inside `build-windows` exactly as today

- [ ] **Step 4: Update README downloads + platform notes**

- Add two rows to the download table: **macOS (Apple Silicon)** → `HiCloudMP-macOS.dmg` (size note "~150 MB"), **Linux** → `HiCloudMP-linux-x86_64.AppImage`
- Extend the "First launch" blockage section: macOS → right-click → Open (once), or `xattr -dr com.apple.quarantine HiCloudMP.app`; note unsigned/notarization TODO path; **Linux** → `chmod +x`, `libfuse2` for AppImage (`sudo apt install libfuse2`), tarball fallback
- Add badges: same style as Windows buttons (macOS logo, Linux logo)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_release_packaging.py tests/test_update_check.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "build(ci): central all-or-nothing release job, README downloads + platform notes"
```

### Task 5: Branch validation run (workflow_dispatch + RC tag dry-run)

**Files:**
- Modify: `.github/workflows/build.yml` (add `workflow_dispatch:` trigger)
- Modify: (none else)

**Interfaces:**
- Consumes: feature branch `feature/cross-platform-releases`, local authenticated `gh`
- Produces: green dispatch run for all three platforms; any discovered CI-only breakage fixed here before merge

- [ ] **Step 1: Add `workflow_dispatch:` to the `on:` block of `build.yml`**

- [ ] **Step 2: Push the branch and dispatch**

```bash
git push -u origin feature/cross-platform-releases
gh workflow run build.yml --ref feature/cross-platform-releases
gh run watch   # until completion
```

Expected: lint + three build jobs green. Failures here are expected content: Nuitka subprocess quirks, Qt plugin path drift, imageio pin resolution — fix the job script, re-dispatch until green (iterate: `gh run watch -i 10`, next attempt after each fix commit).

- [ ] **Step 3: Smoke each artifact in CI conditions (within the dispatch run)**

- Linux job: `appimagetool` step leaves `--appimage-extract-and-run` output logged; add a light post-build check step: `unzip -p "HiCloudMP-$ver-linux-x86_64.AppImage" .appimage_version 2>/dev/null; ls -lh` (proves the image assembled; full GUI launch is out of CI scope)
- macOS job: `hdiutil imageinfo` on the DMG (format + size), `codesign -dv` prints ad-hoc signature

- [ ] **Step 4: Fix-and-rerun cycle ends green, then commit**

```bash
git add -A && git commit -m "fix(ci): cross-platform job corrections from first dispatch run"
```

### Task 6: Merge, tag `v1.0.6-rc.1`, verify the real release

**Files:**
- Modify: `progress.md` (ledger entry at the end)

**Interfaces:**
- Consumes: green dispatch branch; open PR
- Produces: prerelease `v1.0.6-rc.1` on GitHub with 6 assets; recorded in the project ledger

- [ ] **Step 1: Open/merge PR to `main`**

`gh pr create --fill && gh pr merge --merge` (or via repo UI). `main` push triggers `build.yml`; watch it once more (`gh run watch`).

- [ ] **Step 2: Tag and watch the release build**

```bash
git tag v1.0.6-rc.1 && git push origin v1.0.6-rc.1
gh run watch
gh release view v1.0.6-rc.1 --json assets -q '.assets[].name'
```

Expected: exactly `HiCloudMP-Setup-1.0.6.exe` (versioned per current Inno naming), `HiCloudMP-Setup.exe`, `HiCloudMP-portable.zip`, `HiCloudMP-1.0.6-linux-x86_64.AppImage`, `HiCloudMP-linux-x86_64.AppImage`, `HiCloudMP-1.0.6-linux-x86_64.tar.gz`, `HiCloudMP-1.0.6-macos-arm64.dmg`, `HiCloudMP-macOS.dmg`, marked prerelease.

- [ ] **Step 3: Verify stable aliases resolve**

```bash
for f in HiCloudMP-portable.zip HiCloudMP-Setup.exe HiCloudMP-macOS.dmg HiCloudMP-linux-x86_64.AppImage; do
  curl -sI -o /dev/null -w "%{http_code} $f\n" "https://github.com/PhantomPixelDev/HiCloudMP/releases/latest/download/$(bash -c 'echo $f')" || true
done
```
(bash quoting per-file loop; expected: 200 for windows aliases — prereleases do not perturb `releases/latest` — and 404 for the two new aliases until the real `v1.0.6` release; this is documented behavior, the README links go live at first stable tag. The macOS AppImage download check is re-run at the first stable release.)

- [ ] **Step 4: no-silence check on app behavior**

Run the local test suite once more on the branch tip: `python -m pytest -q` (Windows, full suite). Expected: green — no test was licensed to fail/skip silently.

- [ ] **Step 5: Ledger + close**

Append to `progress.md`: date, feature cross-platform releases, commit range, artifacts emitted, and the open item: "notarization path ($99/yr Apple Developer) optional upgrade; Intel macOS unsupported (runner retirement); ARM64 Linux builds possible with ubuntu-24.04-arm runners".

```bash
git add progress.md && git commit -m "docs(progress): ledger cross-platform release pipeline"
```

---

**Executor's local environment note:** everything except Task 5/6's live-CI verification runs as `pytest tests/test_release_packaging.py` on the author's Windows host (fast, file-based). The `printf`-style bash steps inside the workflow only execute in CI; their authoring format above (one action per numbered step) is the review unit.
