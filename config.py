import sys
from pathlib import Path

# Detecta se está rodando como executável congelado (PyInstaller) ou script Python
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR

# Diretório de persistência e caminhos de arquivo
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKUPS_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "notebook.db"