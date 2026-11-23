import os
import sys
from pathlib import Path

# Detecta se está rodando como executável congelado (PyInstaller) ou script Python
if getattr(sys, 'frozen', False):
    # Pasta onde o executável .exe está rodando
    BASE_DIR = Path(sys.executable).parent
else:
    # Pasta raiz do projeto durante o desenvolvimento
    BASE_DIR = Path(__file__).resolve().parent

# Diretório de persistência e caminhos de arquivo
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "notebook.db"