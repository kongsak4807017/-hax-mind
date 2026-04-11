param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$BundlePath = ""
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
if ($BundlePath) {
    & "$ProjectRoot\.venv\Scripts\python.exe" -c "from pathlib import Path; from engine.production_ops import restore_backup_bundle, validate_restore_target; bundle=Path(r'''$BundlePath'''); manifest=restore_backup_bundle(bundle_path=bundle); result=validate_restore_target(Path(manifest['destination'])); print(manifest['destination']); print(result['success'])"
} else {
    & "$ProjectRoot\.venv\Scripts\python.exe" -c "from pathlib import Path; from engine.production_ops import restore_backup_bundle, validate_restore_target; manifest=restore_backup_bundle(); result=validate_restore_target(Path(manifest['destination'])); print(manifest['destination']); print(result['success'])"
}
