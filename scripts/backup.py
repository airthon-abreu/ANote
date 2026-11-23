import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

# Garante que o script enxergue o config.py na raiz
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR, DATA_DIR, DB_PATH

def create_backup():
    backups_dir = BASE_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backups_dir / f"notebook_backup_{timestamp}.db"
    
    if not DB_PATH.exists():
        print(f"[!] Banco de dados não encontrado em: {DB_PATH}")
        return

    print(f"[*] Iniciando backup seguro de: {DB_PATH.name}...")
    
    # Usa a API nativa do SQLite para backup atômico (evita lock ou corrupção)
    src_conn = sqlite3.connect(DB_PATH)
    dst_conn = sqlite3.connect(backup_file)
    
    with dst_conn:
        src_conn.backup(dst_conn)
        
    dst_conn.close()
    src_conn.close()

    print(f"[OK] Backup gerado com sucesso em:")
    print(f"     -> {backup_file}")

if __name__ == "__main__":
    create_backup()