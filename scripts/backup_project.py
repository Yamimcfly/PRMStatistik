"""
Erstellt ein vollständiges Backup des PRMStatistik-Projekts
inkl. Datenbank, Konfiguration und allen wichtigen Dateien.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
import zipfile

def create_backup():
    # Basis-Verzeichnis
    base_dir = Path(__file__).parent.parent
    
    # Backup-Name mit Zeitstempel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"PRMStatistik_Backup_{timestamp}"
    backup_dir = base_dir / "backups" / backup_name
    
    # Backup-Verzeichnis erstellen
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Erstelle Backup: {backup_name}")
    print(f"Ziel: {backup_dir}")
    print()
    
    # Liste der zu kopierenden Dateien und Verzeichnisse
    items_to_backup = [
        # Hauptverzeichnis Dateien
        ("config.json", "config.json"),
        ("config.example.json", "config.example.json"),
        ("requirements.txt", "requirements.txt"),
        ("pyproject.toml", "pyproject.toml"),
        ("README.md", "README.md"),
        
        # App-Verzeichnis (komplett)
        ("app", "app"),
        
        # Data-Verzeichnis
        ("data/prm_stats.db", "data/prm_stats.db"),
        ("data/WCH_Typ_reinform.xlsx", "data/WCH_Typ_reinform.xlsx"),
        
        # Scripts-Verzeichnis
        ("scripts", "scripts"),
    ]
    
    copied_files = 0
    skipped_files = 0
    
    for source_rel, dest_rel in items_to_backup:
        source = base_dir / source_rel
        dest = backup_dir / dest_rel
        
        if not source.exists():
            print(f"⚠ Überspringe (nicht vorhanden): {source_rel}")
            skipped_files += 1
            continue
        
        try:
            if source.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                size_mb = source.stat().st_size / (1024 * 1024)
                print(f"✓ Kopiert: {source_rel} ({size_mb:.2f} MB)")
                copied_files += 1
            elif source.is_dir():
                # Verzeichnis kopieren, aber __pycache__ ausschließen
                shutil.copytree(
                    source, 
                    dest, 
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', '.venv*')
                )
                file_count = sum(1 for _ in dest.rglob('*') if _.is_file())
                print(f"✓ Kopiert: {source_rel}/ ({file_count} Dateien)")
                copied_files += 1
        except Exception as e:
            print(f"✗ Fehler bei {source_rel}: {e}")
            skipped_files += 1
    
    print()
    print(f"Backup abgeschlossen!")
    print(f"  Kopiert: {copied_files} Elemente")
    print(f"  Übersprungen: {skipped_files} Elemente")
    
    # ZIP-Archiv erstellen
    print()
    print("Erstelle ZIP-Archiv...")
    zip_path = backup_dir.parent / f"{backup_name}.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in backup_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(backup_dir.parent)
                zipf.write(file_path, arcname)
    
    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"✓ ZIP erstellt: {zip_path.name} ({zip_size_mb:.2f} MB)")
    
    # Backup-Ordner löschen (nur ZIP behalten)
    shutil.rmtree(backup_dir)
    print(f"✓ Temporärer Ordner gelöscht")
    
    print()
    print("=" * 70)
    print("BACKUP ERFOLGREICH!")
    print("=" * 70)
    print(f"Backup-Datei: {zip_path}")
    print()
    print("WIEDERHERSTELLUNG auf anderem Computer:")
    print("1. Python 3.13+ installieren")
    print("2. ZIP-Datei entpacken")
    print("3. In PowerShell:")
    print("   cd PRMStatistik_Backup_XXXXXXXX_XXXXXX")
    print("   python -m venv .venv")
    print("   .venv\\Scripts\\Activate.ps1")
    print("   pip install -r requirements.txt")
    print("   python -m app")
    print()
    
    return zip_path

if __name__ == "__main__":
    create_backup()
