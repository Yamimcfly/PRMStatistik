"""
Stellt ein Backup des PRMStatistik-Projekts wieder her.
"""
import os
import shutil
import zipfile
from pathlib import Path
import sys

def restore_backup(zip_path: str, target_dir: str = None):
    zip_file = Path(zip_path)
    
    if not zip_file.exists():
        print(f"✗ Fehler: Backup-Datei nicht gefunden: {zip_path}")
        return False
    
    # Zielverzeichnis bestimmen
    if target_dir:
        restore_dir = Path(target_dir)
    else:
        # Standard: Neben der ZIP-Datei
        restore_dir = zip_file.parent / zip_file.stem
    
    if restore_dir.exists():
        response = input(f"Verzeichnis {restore_dir} existiert bereits. Überschreiben? (j/n): ")
        if response.lower() != 'j':
            print("Abgebrochen.")
            return False
        shutil.rmtree(restore_dir)
    
    restore_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Entpacke Backup...")
    print(f"Quelle: {zip_file}")
    print(f"Ziel: {restore_dir}")
    print()
    
    # ZIP entpacken
    with zipfile.ZipFile(zip_file, 'r') as zipf:
        zipf.extractall(restore_dir.parent)
    
    print("✓ Backup wiederhergestellt!")
    print()
    print("=" * 70)
    print("NÄCHSTE SCHRITTE:")
    print("=" * 70)
    print()
    print("1. Wechsel in das Projektverzeichnis:")
    print(f"   cd {restore_dir}")
    print()
    print("2. Erstelle virtuelle Umgebung:")
    print("   python -m venv .venv")
    print()
    print("3. Aktiviere virtuelle Umgebung:")
    print("   Windows:  .venv\\Scripts\\Activate.ps1")
    print("   Linux:    source .venv/bin/activate")
    print()
    print("4. Installiere Abhängigkeiten:")
    print("   pip install -r requirements.txt")
    print()
    print("5. Starte die Anwendung:")
    print("   python -m app")
    print()
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Verwendung: python restore_backup.py <backup.zip> [zielverzeichnis]")
        print()
        print("Beispiel:")
        print("  python restore_backup.py PRMStatistik_Backup_20260209_143000.zip")
        print("  python restore_backup.py backup.zip C:\\Projekte\\PRMStatistik")
        sys.exit(1)
    
    zip_path = sys.argv[1]
    target_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    restore_backup(zip_path, target_dir)
