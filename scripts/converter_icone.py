import subprocess
import sys
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "src" / "ui" / "assets"


def convert_icon():
    source_img = None
    for candidate in ["icon_original.png", "icon_original.jpg", "icon.png"]:
        path = ASSETS_DIR / candidate
        if path.exists():
            source_img = path
            break

    if not source_img:
        print("[!] Erro: Coloque a imagem gerada em 'src/ui/assets/icon_original.png'")
        return

    print(f"[*] Processando imagem: {source_img.name}...")
    img = Image.open(source_img)

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    png_path = ASSETS_DIR / "icon.png"
    img.resize((512, 512), Image.Resampling.LANCZOS).save(png_path, format="PNG")
    print(f"[OK] Gerado: {png_path.name}")

    ico_path = ASSETS_DIR / "icon.ico"
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"[OK] Gerado: {ico_path.name} com {len(icon_sizes)} resoluções embutidas")

    apply_folder_icon(ico_path)


def apply_folder_icon(ico_path: Path):
    """Configura o desktop.ini do Windows para a pasta ter o ícone próprio."""
    if sys.platform != "win32":
        return

    desktop_ini = ROOT_DIR / "desktop.ini"
    rel_ico = ico_path.relative_to(ROOT_DIR)

    content = f"[.ShellClassInfo]\nIconResource={rel_ico},0\n[ViewState]\nMode=\nVid=\nFolderType=Generic\n"

    try:
        if desktop_ini.exists():
            subprocess.run(f'attrib -h -s "{desktop_ini}"', shell=True)

        desktop_ini.write_text(content, encoding="mbcs")

        subprocess.run(f'attrib +h +s "{desktop_ini}"', shell=True)
        subprocess.run(f'attrib +r "{ROOT_DIR}"', shell=True)
        print("[OK] Ícone aplicado na pasta do projeto no Windows Explorer!")
    except Exception as e:
        print(f"[!] Não foi possível definir o ícone da pasta: {e}")


if __name__ == "__main__":
    convert_icon()