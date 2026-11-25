import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def clean_previous_builds():
    """Remove pastas e specs de compilação antigos para evitar arquivos zumbis."""
    print("[*] Limpando diretórios temporários antigos...")
    for folder in ["build", "dist"]:
        path = ROOT_DIR / folder
        if path.exists():
            shutil.rmtree(path)

    for spec_name in ["CadernoInterativo.spec", "ANote.spec"]:
        spec_file = ROOT_DIR / spec_name
        if spec_file.exists():
            spec_file.unlink()


def run_build():
    clean_previous_builds()

    entry_point = ROOT_DIR / "main.py"
    app_name = "ANote"

    assets_src = ROOT_DIR / "src" / "ui" / "assets"
    add_data_flag = f"{assets_src}{os.pathsep}src/ui/assets"
    icon_file = assets_src / "icon.ico"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        f"--name={app_name}",
        "--clean",
        f"--add-data={add_data_flag}",
        f"--icon={icon_file}",
        str(entry_point)
    ]

    print("[*] Compilando executável com PyInstaller...")
    print(f"    Comando: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=ROOT_DIR)

    if result.returncode == 0:
        exe_path = ROOT_DIR / "dist" / f"{app_name}.exe"
        print("\n" + "=" * 60)
        print("[SUCESSO] Build concluído com êxito!")
        print("Arquivo executável com temas embutidos gerado em:")
        print(f"-> {exe_path}")
        print("=" * 60)
    else:
        print("\n[ERRO] Falha durante o processo de build.", file=sys.stderr)


if __name__ == "__main__":
    run_build()