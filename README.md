# ANote - Caderno Interativo Offline

Aplicação desktop leve, rápida e 100% offline para estudo técnico, leitura estruturada e anotações contextuais, construída em Python com interface PySide6 (Qt) e persistência em banco relacional SQLite.

---

## Funcionalidades Principais

- **Marcação Dinâmica de Termos:** Destaque termos e conceitos no texto sem risco de quebra de referências por edição (*offset drift* prevenido via tokens imutáveis).
- **Painel Lateral Contextual:** Clique em qualquer termo grifado para abrir e editar a nota/conceito correspondente em tempo real.
- **Customização Visual Completa:**
  - Alternador nativo entre **Modo Escuro** e **Modo Claro**.
  - Seletor de tamanho de fonte dinâmico (com redimensionamento em tempo real).
  - Paleta de cores para escolher a cor de destaque de cada termo marcado.
- **Persistência Atômica:** Textos, anotações e preferências do usuário gravados no SQLite local (`data/notebook.db`).
- **Portabilidade Total:** Executável único (`.exe`) que carrega seus dados e temas de forma autônoma para outro computador.

---

## Arquitetura do Software

O projeto segue arquitetura desacoplada (separação rígida entre regras de negócio e apresentação):

```text
caderno_interativo/
├── data/                  # Banco de dados local portátil (notebook.db)
├── scripts/               # Utilitários de backup atômico, build e handoff
├── src/
│   ├── core/              # Regra de negócio pura (models, storage, services, parser)
│   └── ui/                # Camada visual desacoplada (PySide6 e temas QSS)
├── config.py              # Resolução dinâmica de caminhos (dev vs executável)
└── main.py                # Ponto de entrada leve da aplicação
```

---

## Como Executar

### Opção 1: Executar a partir do Código-Fonte (Desenvolvedores)

#### 1. Clonar o repositório:
```bash
git clone https://github.com/airthon-abreu/caderno-interativo.git
cd caderno-interativo
```

#### 2. Criar e ativar o ambiente virtual:
- **No Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
*(Caso o PowerShell bloqueie a execução de scripts, rode: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

- **No Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. Instalar as dependências:
```bash
pip install -r requirements.txt
```

#### 4. Executar a aplicação:
```bash
python main.py
```

---

### Opção 2: Gerar o Executável Portátil (`.exe`)

Para gerar o executável autônomo com os temas e assets embutidos:

```bash
python scripts/build.py
```
O arquivo `CadernoInterativo.exe` será gerado dentro da pasta `dist/`. Ele pode ser copiado para um pendrive ou qualquer computador com Windows sem necessidade de instalar Python.

---

## Utilitários de Resiliência e Automação

- **Backup Seguro do Banco:**
  ```bash
  python scripts/backup.py
  ```
  *Gera uma cópia snapshot do banco SQLite na pasta `backups/` com carimbo de data/hora.*

- **Gerador de Handoff (Contexto para IA / Auditoria):**
  ```bash
  python scripts/gerar_handoff.py
  ```
  *Consolida a árvore do projeto e todo o código-fonte em um único arquivo de texto (`handoff_projeto.txt`).*