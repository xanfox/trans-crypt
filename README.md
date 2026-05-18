# TransCrypt 🎙️💬

TransCrypt é uma suíte automatizada e interativa para **transcrição, consolidação e auditoria de conversas do WhatsApp**. 

O sistema foi projetado para lidar com o fluxo real de trabalho de um profissional que atende clientes via WhatsApp: receber backups exportados diretamente do aplicativo, organizá-los em pastas de clientes, transcrever os áudios automaticamente e gerar uma **interface visual de auditoria** completa — tudo localmente, sem enviar nada para a nuvem.

---

## 🚀 Funcionalidades Principais

### 📦 Extração e Organização Inteligente de Backups (Step 0)
- Detecta e extrai automaticamente os arquivos `.zip` exportados do WhatsApp.
- Reconhece e remove tags de qualificação do nome do arquivo (`Lead`, `Consulente`, `FR`, `Conversa do WhatsApp com`, etc.) para criar nomes de pasta limpos.
- Agrupa múltiplos backups do mesmo cliente (incluindo cópias como `arquivo (1).zip`) e os processa em conjunto.
- **Mesclagem cronológica inteligente:** quando existem dois backups do mesmo cliente (um parcial e um mais completo), o sistema combina os dois, elimina mensagens duplicadas e reconstrói o histórico em ordem cronológica correta.
- Arquiva os `.zip` originais em `_zips_processados/` após o processamento para evitar reprocessamento acidental.

### 🎙️ Transcrição de Áudio de Alta Precisão (Step 1)
- Converte automaticamente os áudios exportados (`.opus`, `.ogg`, `.m4a`, etc.) para texto usando o modelo **Whisper large-v3**.
- Processamento paralelo com multi-threading para processar múltiplos áudios simultaneamente.
- Retomável: arquivos já transcritos são pulados automaticamente.

### 📄 Consolidação de Histórico (Step 2)
- Lê o `_chat.txt` unificado e intercala mensagens de texto com as transcrições geradas.
- Gera o arquivo `historico_consolidado.txt` com toda a linha do tempo em ordem cronológica.
- Respeita edições e deleções feitas via editor visual.

### 🖥️ Dashboard Visual Interativa (Step 3 + Editor)
- Gera uma página HTML com tema dark profissional para conferência visual da conversa.
- Reprodução de áudios e vídeos diretamente no navegador com controle de velocidade (1x, 1.5x, 2x, 2.5x).
- **Edição não-destrutiva:** edite transcrições e textos de mensagens sem alterar os arquivos originais.
- **Sistema de auditoria em 3 estados** (clique no balão para alternar):
  - ✅ Conferido (OK)
  - ✅⭐ Âncora / Favorito (para marcar trechos importantes)
  - ⚠️ Para Revisão
- Navegação rápida entre âncoras com botões direcionais.
- Marcação em massa com "Conferir Tudo" de um clique.
- Rastreio de auditoria: registra data/hora da primeira abertura e da última revisão.

---

## 🗂️ Estrutura de Arquivos do Projeto

```
trans-crypt/
├── main.py              # Ponto de entrada: menu interativo no terminal
├── step0.py             # Extração e mesclagem de zips de backup
├── step1.py             # Transcrição de áudios via Whisper
├── step2.py             # Consolidação do histórico em .txt
├── step3.py             # Geração do painel visual HTML
├── editor_server.py     # Servidor Flask para persistir edições da UI
├── whatsapp_parser.py   # Parser/serializador do formato de chat do WhatsApp
├── config.py            # Configurações globais (modelo, extensões, remetentes)
├── utils.py             # Funções auxiliares (menus, limpeza de texto)
├── requirements.txt     # Dependências Python
└── clientes/            # Pasta de dados dos clientes (ignorada pelo git)
    ├── _zips_processados/  # Zips arquivados após extração
    ├── Nome do Cliente/    # Uma pasta por cliente
    │   ├── _chat.txt            # Histórico unificado de mensagens
    │   ├── PTT-*.opus           # Áudios exportados do WhatsApp
    │   ├── _transcricoes/       # Transcrições geradas pelo Step 1
    │   ├── historico_consolidado.txt  # Gerado pelo Step 2
    │   ├── conferencia_visual.html    # Gerado pelo Step 3
    │   └── conferencia_edits.json     # Edições não-destrutivas persistidas
```

---

## 🏷️ Sistema de Tags de Clientes

O nome dos arquivos `.zip` exportados do WhatsApp pode conter tags de qualificação. O Step 0 as reconhece e remove automaticamente ao criar a pasta do cliente:

| Tag no nome do arquivo | Significado |
|---|---|
| `Conversa do WhatsApp com` | Prefixo padrão do Android |
| `WhatsApp Chat with` | Prefixo padrão do iOS |
| `Lead` | Contato que ainda não é cliente |
| `Consulente` | Cliente com pelo menos 1 atendimento realizado |
| `FR` | Lead qualificado via Free Read (leitura gratuita) |

**Exemplo de renomeação:**

`Conversa do WhatsApp com Lead FR Marcelo Rubem Paiva 15_03_1985.zip`

→ pasta criada: `Marcelo Rubem Paiva - 15_03_1985`

---

## 🔄 Fluxo de Trabalho Recomendado

```
[WhatsApp] → Exportar chat com mídia → arquivo .zip
     ↓
Jogou o .zip na pasta clientes/
     ↓
[main.py] → Opção 0: Extrai, organiza e mescla
     ↓
[main.py] → Opção 1 ao 3: Selecione o cliente e processe
     ↓
[main.py] → Opção 5: Abra o editor visual no navegador
     ↓
Confira, edite e marque como auditado ✅
```

---

## ⚙️ Como Instalar e Rodar

### Pré-requisitos

O **FFmpeg** é necessário para o Whisper processar os áudios:

```bash
# Linux (Ubuntu/Debian)
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
winget install ffmpeg
```

### Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/trans-crypt.git
cd trans-crypt

# 2. (Recomendado) Crie um ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt
```

### Rodando

```bash
python3 main.py
```

No primeiro uso, a pasta `clientes/` será criada automaticamente. Basta jogar seus arquivos `.zip` dentro dela e usar o menu.

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Uso |
|---|---|
| **Python 3** | Lógica central e manipulação de arquivos |
| **faster-whisper (large-v3)** | Motor de transcrição de áudio com IA |
| **FFmpeg** | Conversão de formatos de áudio antes da transcrição |
| **Flask** | Servidor backend leve para persistir edições da UI |
| **HTML / CSS / Vanilla JS** | Interface visual sem dependências Node/NPM |
| **JSON** | Camada de persistência leve para edições e status de auditoria |

---

> **Nota de Privacidade:** O TransCrypt não possui chaves de API, telemetria ou conexões externas. A transcrição roda **100% localmente** via Whisper. Todos os dados de clientes (áudios, transcrições e históricos) são bloqueados via `.gitignore`.
