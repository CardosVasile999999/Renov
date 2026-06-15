"""Descărcare și aplicare update .exe (Windows)."""
from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from renov_config import (
    EXE_FILENAME,
    INSTALL_DIR,
    UPDATE_BACKUP_FILENAME,
    UPDATE_DIR,
    UPDATE_LOG_PATH,
    UPDATE_PS1_FILENAME,
    UPDATE_STAGING_FILENAME,
    USER_DATA_DIR,
)
from updater.dialog import show_error, show_info

_CHUNK_SIZE = 256 * 1024


def _log(msg: str) -> None:
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with UPDATE_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {msg}\n")


def _ps_single_quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def download_new_exe(url: str, dest: Path, timeout_s: float = 300.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "DanRenov-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            expected_raw = resp.headers.get("Content-Length")
            expected = int(expected_raw) if expected_raw else None
            tmp = dest.with_suffix(dest.suffix + ".part")
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            total = 0
            with tmp.open("wb") as fh:
                while True:
                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total += len(chunk)
            if expected is not None and total != expected:
                _log(f"download size mismatch expected={expected} got={total}")
                try:
                    tmp.unlink()
                except OSError:
                    pass
                return False
            if total <= 0:
                _log("download empty response")
                return False
            tmp.replace(dest)
            _log(f"download ok bytes={total} dest={dest}")
            return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _log(f"download failed: {exc}")
        return False


def _powershell_script(
    *,
    staging_path: Path,
    install_dir: Path,
    exe_name: str,
    backup_name: str,
    log_path: Path,
    ps1_path: Path,
) -> str:
    proc_name = Path(exe_name).stem
    return f"""$ErrorActionPreference = 'Continue'
$LogFile = {_ps_single_quoted(str(log_path))}
$Staging = {_ps_single_quoted(str(staging_path))}
$InstallDir = {_ps_single_quoted(str(install_dir))}
$ExeName = {_ps_single_quoted(exe_name)}
$BackupName = {_ps_single_quoted(backup_name)}
$ProcName = {_ps_single_quoted(proc_name)}
$Self = {_ps_single_quoted(str(ps1_path))}

function Write-Log([string]$Message) {{
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss UTC')
    Add-Content -LiteralPath $LogFile -Value "[$stamp] [ps1] $Message" -Encoding UTF8
}}

function Show-Err([string]$Message) {{
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        'Dan Renov - actualizare esuata',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}}

try {{
    Write-Log 'update script started'
    Start-Sleep -Seconds 2

    for ($i = 0; $i -lt 40; $i++) {{
        $running = Get-Process -Name $ProcName -ErrorAction SilentlyContinue
        if (-not $running) {{ break }}
        Start-Sleep -Milliseconds 500
    }}

    $running = Get-Process -Name $ProcName -ErrorAction SilentlyContinue
    if ($running) {{
        Write-Log 'process still running, force stop'
        Stop-Process -Name $ProcName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }}

    if (-not (Test-Path -LiteralPath $Staging)) {{
        Write-Log 'staging file missing'
        Show-Err "Fisierul descarcat lipseste.`n`nJurnal:`n$LogFile"
        exit 1
    }}

    $dest = Join-Path $InstallDir $ExeName
    $backup = Join-Path $InstallDir $BackupName

    if (Test-Path -LiteralPath $backup) {{
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }}

    $applied = $false
    for ($i = 0; $i -lt 120; $i++) {{
        try {{
            if (Test-Path -LiteralPath $dest) {{
                Move-Item -LiteralPath $dest -Destination $backup -Force
            }}
            Move-Item -LiteralPath $Staging -Destination $dest -Force
            $applied = $true
            Write-Log "replace ok attempt=$i dest=$dest"
            break
        }} catch {{
            Write-Log "replace retry $i: $($_.Exception.Message)"
            Start-Sleep -Milliseconds 500
        }}
    }}

    if (-not $applied) {{
        Write-Log 'replace failed after retries'
        Show-Err "Nu s-a putut inlocui Renov.exe.`n`nJurnal:`n$LogFile"
        exit 1
    }}

    if (-not (Test-Path -LiteralPath $dest)) {{
        Write-Log 'destination missing after replace'
        Show-Err "Actualizarea nu s-a finalizat.`n`nJurnal:`n$LogFile"
        exit 1
    }}

    $legacyBat = Join-Path $InstallDir '_renov_apply_update.bat'
    $legacyStaging = Join-Path $InstallDir 'Renov-new.exe'
    Remove-Item -LiteralPath $legacyBat -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $legacyStaging -Force -ErrorAction SilentlyContinue

    Start-Process -FilePath $dest -WorkingDirectory $InstallDir
    Write-Log 'new exe started'
}} catch {{
    Write-Log "fatal: $($_.Exception.Message)"
    Show-Err "Actualizarea a esuat.`n`nJurnal:`n$LogFile"
    exit 1
}} finally {{
    Remove-Item -LiteralPath $Self -Force -ErrorAction SilentlyContinue
}}
"""


def _launch_update_script(ps1_path: Path) -> bool:
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(ps1_path),
            ],
            cwd=str(USER_DATA_DIR),
            close_fds=True,
        )
        _log(f"powershell launched script={ps1_path}")
        return True
    except OSError as exc:
        _log(f"powershell launch failed: {exc}")
        return False


def apply_exe_update(download_url: str) -> bool:
    """
    Descarcă noul .exe în AppData și lansează scriptul care îl înlocuiește
    după închiderea aplicației. Returnează True dacă procesul curent trebuie să se oprească.
    """
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    staging = UPDATE_DIR / UPDATE_STAGING_FILENAME
    if staging.exists():
        try:
            staging.unlink()
        except OSError:
            pass

    _log(f"apply start install_dir={INSTALL_DIR} url={download_url}")

    show_info(
        "Dan Renov — actualizare",
        "Se descarcă versiunea nouă...\n"
        "Așteaptă — poate dura 1–2 minute.\n"
        "Aplicația se va reporni automat.",
    )

    if not download_new_exe(download_url, staging):
        show_error(
            "Dan Renov — actualizare eșuată",
            "Nu s-a putut descărca fișierul de actualizare.\n"
            "Verifică conexiunea la internet și încearcă din nou.\n\n"
            f"Jurnal: {UPDATE_LOG_PATH}",
        )
        return False

    exe_name = Path(sys.executable).name if getattr(sys, "frozen", False) else EXE_FILENAME
    ps1_path = UPDATE_DIR / UPDATE_PS1_FILENAME
    try:
        ps1_path.write_text(
            _powershell_script(
                staging_path=staging.resolve(),
                install_dir=INSTALL_DIR.resolve(),
                exe_name=exe_name,
                backup_name=UPDATE_BACKUP_FILENAME,
                log_path=UPDATE_LOG_PATH.resolve(),
                ps1_path=ps1_path.resolve(),
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        _log(f"ps1 write failed: {exc}")
        show_error(
            "Dan Renov — actualizare eșuată",
            f"Nu s-a putut pregăti actualizarea.\n\nJurnal: {UPDATE_LOG_PATH}",
        )
        return False

    if not _launch_update_script(ps1_path):
        show_error(
            "Dan Renov — actualizare eșuată",
            "Nu s-a putut lansa scriptul de actualizare.\n\n"
            f"Jurnal: {UPDATE_LOG_PATH}",
        )
        return False

    show_info(
        "Dan Renov — actualizare",
        "Descărcare terminată.\n"
        "Se instalează versiunea nouă și aplicația se repornește.",
    )
    return True
