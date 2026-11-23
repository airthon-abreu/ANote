import os
import sys
from datetime import datetime
from pathlib import Path

# Localiza a raiz do projeto (uma pasta acima de scripts/)
ROOT_DIR = Path(__file__).resolve().parent.parent

# Pastas e arquivos que NUNCA devem entrar no texto (binários, caches, ambientes)
IGNORE_DIRS = {
    ".venv", "venv", "env", "__pycache__", ".git", 
    ".vscode", ".idea", "build", "dist", "backups", "data"
}

IGNORE_FILES = {
    "notebook.db", "*.exe", "*.spec", "*.pyc", 
    "handoff_projeto.txt", "gerar_handoff.py"
}

# Extensões válidas de código e configuração
VALID_EXTENSIONS = {".py", ".qss", ".txt", ".md", ".gitignore", ".json", ".sql"}

def should_ignore_file(file_path: Path) -> bool:
    if file_path.name in IGNORE_FILES:
        return True
    if any(file_path.name.endswith(ext.replace("*", "")) for ext in IGNORE_FILES if "*" in ext):
        return True
    return file_path.suffix not in VALID_EXTENSIONS and file_path.name != ".gitignore"

def generate_tree(dir_path: Path, prefix: str = "") -> list:
    """Gera a árvore visual do projeto."""
    lines = []
    items = sorted([p for p in dir_path.iterdir() if p.name not in IGNORE_DIRS], 
                   key=lambda s: (s.is_file(), s.name.lower()))
    
    total = len(items)
    for index, item in enumerate(items):
        is_last = (index == total - 1)
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{item.name}")
        
        if item.is_dir():
            sub_prefix = prefix + ("    " if is_last else "│   ")
            lines.extend(generate_tree(item, sub_prefix))
            
    return lines

def build_handoff():
    output_file = ROOT_DIR / "handoff_projeto.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[*] Escaneando arquivos do projeto em: {ROOT_DIR}")
    
    handoff_lines = []
    handoff_lines.append("=" * 80)
    handoff_lines.append(f"PROJETO: CADERNO INTERATIVO OFFLINE - HANDOFF DE CÓDIGO")
    handoff_lines.append(f"DATA DO SNAPSHOT: {timestamp}")
    handoff_lines.append("=" * 80)
    handoff_lines.append("\nESTRUTURA DE DIRETÓRIOS:")
    handoff_lines.append(ROOT_DIR.name + "/")
    handoff_lines.extend(generate_tree(ROOT_DIR))
    handoff_lines.append("\n" + "=" * 80 + "\n")

    files_processed = 0

    # Percorre os arquivos da raiz e subpastas de forma determinística
    for root, dirs, files in os.walk(ROOT_DIR):
        # Modifica dirs in-place para não descer em pastas ignoradas
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in sorted(files):
            file_path = Path(root) / file
            if should_ignore_file(file_path):
                continue

            rel_path = file_path.relative_to(ROOT_DIR).as_posix()
            
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                content = f"[Erro ao ler arquivo como UTF-8: {e}]"

            handoff_lines.append(f"#" + "=" * 78)
            handoff_lines.append(f"# ARQUIVO: {rel_path}")
            handoff_lines.append(f"#" + "=" * 78)
            handoff_lines.append(content)
            handoff_lines.append("\n")
            files_processed += 1

    output_file.write_text("\n".join(handoff_lines), encoding="utf-8")
    
    file_size_kb = output_file.stat().st_size / 1024
    print(f"[OK] Handoff gerado com sucesso!")
    print(f"     -> Arquivo: {output_file.name}")
    print(f"     -> Local: {output_file}")
    print(f"     -> Arquivos consolidados: {files_processed}")
    print(f"     -> Tamanho total: {file_size_kb:.2f} KB")

if __name__ == "__main__":
    build_handoff()