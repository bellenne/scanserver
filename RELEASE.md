# Release Process

## Asset name

Use this exact asset name in every GitHub Release:
`ScanServer-windows-x64.zip`

The updater is configured to download that exact file from `bellenne/scanserver`.

## Local build command

```powershell
./scripts/build_release.ps1
```

Output:
`build/ScanServer-windows-x64.zip`

## Versioning

1. Update `APP_VERSION` in `core/app_meta.py`
2. Commit changes
3. Create and push a tag in the form `vX.Y.Z`

Example:

```powershell
git tag v0.1.1
git push origin v0.1.1
```

## GitHub Actions release flow

The workflow in `.github/workflows/release.yml`:
- runs on tag push `v*`
- checks that the tag matches `APP_VERSION`
- builds the PyInstaller package
- uploads `build/ScanServer-windows-x64.zip` to the GitHub Release

## Archive contents

The zip archive contains:
- `ScanServer.exe`
- files from `dist/ScanServer/`
- `config.json`
- `README.md`

The updater preserves local runtime files during update:
- `config.json`
- `state.json`
- `users_cache.json`
- `.tts_cache`
