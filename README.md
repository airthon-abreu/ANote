# Caderno Interativo Offline

Aplicação desktop leve, rápida e 100% offline para estudo técnico, anotações e leitura estruturada, construída em Python com interface PySide6 (Qt) e persistência em banco relacional SQLite.

## Funcionalidades
- **Marcação Dinâmica de Termos:** Destaque termos no texto sem risco de quebra por deslocamento de caracteres (*offset drift* prevenido via tokens imutáveis).
- **Painel Lateral Contextual:** Clique em qualquer termo grifado para exibir e editar a nota/conceito correspondente em tempo real.
- **Customização Visual:** Alternador de temas nativo (Modo Escuro / Modo Claro), seletor de tamanho de fonte e paleta de cores para cada marcação.
- **Persistência Segura:** Configurações e anotações gravadas com transações atômicas no SQLite local (`data/notebook.db`).
- **Portabilidade Total:** Script de compilação em executável único (`.exe`) pronto para rodar a partir de pendrive.

## Arquitetura
O projeto segue separação estrita de responsabilidades:
- `src/core/`: Regra de negócio pura, modelos de dados (`models.py`), gerenciador SQLite (`storage.py`), parser de âncoras (`parser.py`) e casos de uso (`services.py`).
- `src/ui/`: Apresentação gráfica desacoplada em PySide6 e folhas de estilo QSS.
- `scripts/`: Utilitários automatizados de backup seguro (`backup.py`), compilação (`build.py`) e consolidação de código (`gerar_handoff.py`).

## Como Executar

### 1. Clonar o repositório e criar o ambiente virtual:
```bash
git clone https://github.com/SEU_USUARIO/caderno-interativo.git
cd caderno-interativo
python -m venv .venv