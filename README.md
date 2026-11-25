# ANote - Caderno Interativo Offline

Aplicação desktop leve, rápida e 100% offline para estudo técnico, leitura estruturada e anotações contextuais, construída em Python com interface **PySide6 (Qt)** e persistência em banco relacional **SQLite**.

---

## Funcionalidades Principais

### Leitura, Edição e Organização
- **Organização por Pastas e Busca Instantânea:** Classifique cadernos por categorias/pastas e localize qualquer material em tempo real (`Ctrl+F`).
- **Modo Leitura e Modo Edição (`Ctrl+E`):** Alterne entre leitura limpa em folha centralizada e edição completa com barra de formatação contextual (negrito, itálico, sublinhado, cor da fonte, família tipográfica e limpeza de destaques).
- **Modo Foco / Sem Distrações (`F11` / `Esc`):** Oculta barras e painéis em tela cheia para leitura imersiva, restaurando o layout anterior ao sair.
- **Painéis Retráteis (`Ctrl+1` / `Ctrl+2`):** Recolha ou expanda facilmente a lista de cadernos e o painel de anotações.
- **Indicador de Alterações Pendentes:** Aviso visual de conteúdo não salvo e confirmação segura antes de fechar ou trocar de caderno.

### Marcação Contextual e Estudo Ativo
- **Marcação Dinâmica de Termos (`Ctrl+M`):** Destaque palavras ou trechos sem risco de quebra de referências por edição (*offset drift* prevenido via âncoras imutáveis).
- **Painel Lateral Contextual e Índice de Termos:** Clique em qualquer termo grifado no texto — ou no índice lateral do caderno — para navegar até o trecho e editar sua nota correspondente.
- **Salvamento Automático das Notas:** Alterações feitas nas anotações laterais são salvas automaticamente ao trocar de termo, mudar de caderno ou sair do campo.
- **Cores de Marca-Texto:** Paleta predefinida e seletor de cor personalizada para cada termo, com opção de trocar a cor ou desmarcar posteriormente.
- **Modo Flashcards (`Ctrl+P`):** Pratique revisão ativa com cartões gerados automaticamente a partir dos termos marcados no caderno aberto.

### Personalização Visual (Estilo Google Keep) e Produtividade
- **Cores de Card Adaptativas:** Escolha entre uma paleta inspirada no Google Keep (Coral, Pêssego, Areia, Menta, Sálvia, Névoa, Tempestade, Crepúsculo, Flor, Argila, Padrão do Tema ou cor personalizada), com adaptação automática para os modos Claro e Escuro na folha e na lista lateral.
- **Modo Escuro e Modo Claro:** Alternância em tempo real com suporte à barra de título nativa do Windows e ajuste dinâmico de tamanho de fonte.
- **Desfazer e Refazer Global (`Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y`):** Histórico unificado que funciona tanto no **Modo Edição** quanto no **Modo Leitura**, cobrindo alterações no texto, marcação/remoção de termos, cor de marca-texto, notas laterais, cor do card, título e categoria.
- **Atalhos Personalizáveis:** Configure todos os atalhos de teclado pela janela de configurações (`⚙️ Atalhos`).

### Resiliência, Histórico e Portabilidade
- **Histórico de Versões:** Snapshots automáticos (até 20 versões por caderno) com pré-visualização e restauração de versões anteriores.
- **Backup e Restauração Atômica (`.db`):** Gere e restaure cópias de segurança online do banco SQLite diretamente pelo menu **Arquivo** ou via linha de comando.
- **Exportação e Importação:**
  - **PDF (`.pdf`):** Documento formatado pronto para impressão, incluindo glossário final com todas as anotações.
  - **Markdown (`.md`):** Texto estruturado acompanhado do glossário de termos.
  - **Pacote ANote (`.json`):** Exportação e importação completa de cadernos com termos, cores e notas preservadas.

---

## Arquitetura do Software

O projeto segue arquitetura desacoplada entre regras de negócio, persistência e camada visual:

```text
caderno_interativo/
├── data/                       # Banco de dados local portátil (notebook.db)
├── backups/                    # Snapshots de backup do SQLite
├── scripts/                    # Automação (backup, build .exe, ícones e handoff)
├── src/
│   ├── core/                   # Regras de negócio e persistência
│   │   ├── models.py           # Dataclasses Document e Term
│   │   ├── storage.py          # Conexão SQLite (WAL) e migrações
│   │   ├── parser.py           # Sanitização de HTML, contraste e tokens
│   │   └── services.py         # Serviços de cadernos, termos, histórico e exportação
│   └── ui/                     # Camada visual em PySide6
│       ├── assets/             # Temas (dark.qss, light.qss) e ícones
│       ├── components/         # Diálogos e utilitários visuais modulares
│       └── app.py              # Janela principal e gerenciador global de Undo/Redo
├── config.py                   # Resolução dinâmica de caminhos (dev vs executável)
└── main.py                     # Ponto de entrada da aplicação
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

O arquivo **`ANote.exe`** será gerado dentro da pasta `dist/`. Ele pode ser copiado para um pendrive ou qualquer computador com Windows sem necessidade de instalar Python (mantendo os dados na pasta `data/` ao lado do executável).

---

## Utilitários de Resiliência e Automação

- **Backup Seguro do Banco:**
  ```bash
  python scripts/backup.py
  ```
  *Gera uma cópia snapshot atômica do banco SQLite na pasta `backups/` com carimbo de data/hora.*

- **Conversão de Ícones (`.png` / `.ico` e ícone da pasta no Windows):**
  ```bash
  python scripts/converter_icone.py
  ```

- **Gerador de Handoff (Contexto para IA / Auditoria):**
  ```bash
  python scripts/gerar_handoff.py
  ```
  *Consolida a árvore do projeto e todo o código-fonte em um único arquivo (`handoff_projeto.txt`).*git status