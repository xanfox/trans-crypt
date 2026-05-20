# TransCrypt 🎙️💬

TransCrypt é uma suíte automatizada e interativa para **transcrição, consolidação e auditoria de conversas do WhatsApp**.

O sistema foi projetado para o fluxo real de trabalho de um profissional que atende clientes via WhatsApp: receber backups exportados diretamente do aplicativo, organizá-los em pastas de clientes, transcrever os áudios automaticamente e gerar uma **interface visual de auditoria** completa — tudo localmente, sem enviar nada para a nuvem.

---

## 🚀 Funcionalidades Principais

### 📦 Step 0 — Extração e Organização Inteligente de Backups

- Detecta e extrai automaticamente arquivos `.zip` exportados do WhatsApp depositados na pasta `clientes/`.
- Remove tags de qualificação do nome do arquivo (`Lead`, `Consulente`, `FR`, `Conversa do WhatsApp com`, etc.) para criar nomes de pasta limpos e padronizados.
- Agrupa múltiplos backups do mesmo cliente (incluindo cópias como `arquivo (1).zip`) e os processa em conjunto.
- **Mesclagem cronológica inteligente:** quando há dois backups do mesmo cliente (um parcial e um mais completo), o sistema combina ambos, elimina mensagens duplicadas e reconstrói o histórico em ordem cronológica correta.
- Arquiva os `.zip` originais em `_zips_processados/` após processamento para evitar reprocessamento acidental.

### 🎙️ Step 1 — Transcrição de Áudio de Alta Precisão

- Converte automaticamente os áudios exportados (`.opus`, `.ogg`, `.m4a`, `.mp4`, `.wav`, `.mp3`) para texto usando o modelo **Whisper large-v3**.
- **Paralelismo otimizado:** `N` arquivos são transcritos simultaneamente, cada instância do modelo recebe `cpu_count / N` threads — garantindo **100% de utilização** dos núcleos disponíveis.
- **I/O em paralelo com inferência:** `num_workers=2` pré-carrega e decodifica o próximo áudio enquanto o modelo ainda está processando o atual.
- Retomável: arquivos já transcritos são pulados automaticamente, protegendo o trabalho feito.
- Configurável via `config.py`: modelo, `beam_size`, `initial_prompt` e nível de paralelismo.

#### Estratégia Anti-Alucinação (4 camadas)

O Whisper pode gerar texto onde não há fala: "Obrigado." em silêncio, loops de repetição, continuações inventadas entre segmentos. O TransCrypt combina 4 defesas simultâneas:

| Parâmetro | Valor | Proteção |
|---|---|---|
| `condition_on_previous_text` | `False` | Elimina continuações inventadas — o modelo não "completa" frases inexistentes entre mensagens curtas |
| `hallucination_silence_threshold` | `2 s` | Suprime qualquer texto gerado sobre segmentos com mais de 2 s de silêncio |
| `compression_ratio_threshold` | `2.4` | Detecta e descarta loops de repetição (padrão característico de alucinação) |
| `vad_filter` | `True` | Remove regiões de silêncio antes de processar, reduzindo janelas onde alucinações ocorrem |

#### `initial_prompt` — Ancoragem de Vocabulário

O parâmetro `WHISPER_INITIAL_PROMPT` em `config.py` permite orientar o modelo com o vocabulário do seu domínio antes de cada transcrição. O Whisper trata esse texto como "transcrição prévia" — termos mencionados no prompt são favorecidos durante a decodificação, reduzindo erros em palavras técnicas ou específicas do negócio.

> **Formato correto:** texto conversacional natural, não lista de palavras-chave. O modelo foi treinado em transcrições reais; texto em formato de fala ancora melhor o vocabulário do que um glossário.


### 📄 Step 2 — Consolidação de Histórico

- Lê o `_chat.txt` unificado e intercala mensagens de texto com as transcrições geradas.
- Gera o arquivo `historico_consolidado.txt` com toda a linha do tempo em ordem cronológica.
- Respeita edições e deleções feitas no editor visual (não-destrutivo).

### 🖥️ Step 3 + Editor — Dashboard Visual de Auditoria

Gera uma página HTML com tema dark profissional e abre um servidor Flask local para permitir edições persistentes.

#### Cabeçalho do Documento
Ao abrir a conferência, o header exibe automaticamente:
- **Nome do cliente** extraído da pasta
- **Contagem de palavras** (textos + transcrições, separador PT-BR: `1.234`)
- **Tempo estimado de leitura** (200 palavras/min — ritmo de revisão)
- **Duração total dos áudios** calculada via `ffprobe`
- **Tempo estimado de revisão** (leitura + escuta somados)

> As estatísticas são calculadas apenas na primeira abertura e ficam em cache — status toggles não relentizam o sistema.

#### Painel de Controle Flutuante (canto inferior direito)
| Elemento | Descrição |
|---|---|
| Velocidade 1x / 1.5x / 2x / 2.5x | Controla a velocidade de todos os players de áudio da página |
| Mensagens conferidas `X/N` | Contador ao vivo de mensagens com status OK ou Âncora |
| ⭐ MSG Importantes `X/N` ↑↓ | Navegação indexada entre âncoras, com contador de posição |
| ⚠️ Revisar `X/N` ↑↓ | Navegação indexada entre revisões, com contador de posição |

Todos os contadores atualizam **em tempo real** sem necessidade de F5.

#### Sistema de Status de Auditoria (clique no balão)
Cada mensagem tem um ciclo de 4 estados ativado por clique simples no balão:

```
[sem status] → ✅ OK → ✅⭐ Âncora (Importante) → ⚠️ Revisar → [sem status]
```

| Status | Visual | Uso |
|---|---|---|
| *(sem status)* | Normal | Mensagem ainda não avaliada |
| ✅ **OK** | Borda verde | Conferida e aprovada |
| ✅⭐ **Âncora** | Borda roxa | Trecho importante para referência rápida |
| ⚠️ **Revisar** | Borda amarela | Precisa de atenção antes de finalizar |

#### Edição Não-Destrutiva
- **Editar transcrição:** clique em `#id ⚙️` → Editar → altera o `.txt` na pasta `_transcricoes/`
- **Editar texto de mensagem:** mesmo caminho, persiste em `conferencia_edits.json`
- **Apagar mensagem:** remove do histórico visual (e arquivo de mídia opcional)
- Todas as alterações rebuildam automaticamente o HTML e o `historico_consolidado.txt`

#### Botões de Ação em Massa
| Botão | Comportamento |
|---|---|
| **Marcar Pendentes Como Conferido ✅** | Marca apenas mensagens *sem nenhum status* como OK — preserva Âncoras e Revisões existentes |
| **🔄 Zerar Todos os Status** | Apaga *todos* os status com confirmação dupla — útil para rever uma conversa do zero |

#### Rastreio de Auditoria
O rodapé exibe **data/hora da primeira abertura** e da **última revisão**, persistidos automaticamente em `conferencia_edits.json`.

---

## 🗂️ Estrutura de Arquivos

```
trans-crypt/
├── main.py              # Ponto de entrada: menu interativo no terminal
├── step0.py             # Extração e mesclagem de zips de backup
├── step1.py             # Transcrição de áudios via Whisper
├── step2.py             # Consolidação do histórico em .txt
├── step3.py             # Geração do painel visual HTML + helpers de stats
├── editor_server.py     # Servidor Flask para persistir edições da UI
├── whatsapp_parser.py   # Parser do formato de chat exportado pelo WhatsApp
├── config.py            # Configurações globais (modelo, extensões, remetentes)
├── utils.py             # Utilitários compartilhados (menus, busca de transcrição)
├── requirements.txt     # Dependências Python
└── clientes/            # Dados dos clientes (bloqueado pelo .gitignore)
    ├── _zips_processados/        # Zips arquivados após extração pelo Step 0
    └── Nome do Cliente/          # Uma pasta por cliente
        ├── _chat.txt                     # Histórico unificado (gerado pelo Step 0)
        ├── PTT-*.opus / *.m4a / ...      # Áudios exportados do WhatsApp
        ├── _transcricoes/                # Transcrições .txt (geradas pelo Step 1)
        ├── historico_consolidado.txt     # Histórico completo com transcrições (Step 2)
        ├── conferencia_visual.html       # Dashboard de auditoria (Step 3)
        └── conferencia_edits.json        # Edições, status e cache de stats (persistência)
```

### Estrutura do `conferencia_edits.json`

```json
{
    "deleted_ids": [12, 47],
    "edited_texts": { "23": "texto corrigido manualmente" },
    "status": {
        "5": "ok",
        "18": "anchor",
        "31": "review"
    },
    "_stats": {
        "total_palavras": 2316,
        "duracao_audios_sec": 739.4
    },
    "last_opened": "19/05/2026 14:30",
    "last_revised": "19/05/2026 18:45"
}
```

---

## 🏷️ Sistema de Tags de Clientes (Step 0)

O Step 0 reconhece e remove automaticamente tags de qualificação do nome dos arquivos `.zip`:

| Tag no arquivo | Significado |
|---|---|
| `Conversa do WhatsApp com` | Prefixo padrão do Android |
| `WhatsApp Chat with` | Prefixo padrão do iOS |
| `Lead` | Contato em prospecção |
| `Consulente` | Cliente com atendimento realizado |
| `FR` | Lead qualificado via Free Read |

**Exemplo de renomeação:**

```
Conversa do WhatsApp com Lead FR Marcelo Rubem Paiva 15_03_1985.zip
→ pasta: Marcelo Rubem Paiva - 15_03_1985
```

---

## 🔄 Fluxo de Trabalho Recomendado

```
[WhatsApp] → Exportar chat com mídia → arquivo .zip
     ↓
Deposite o .zip em clientes/
     ↓
[main.py] → Opção 0: Extrai, organiza e mescla backups
     ↓
[main.py] → Opção 1: Transcreve os áudios (Whisper large-v3)
     ↓
[main.py] → Opção 2: Consolida histórico com transcrições
     ↓
[main.py] → Opção 3: Gera o painel visual HTML
     ↓
[main.py] → Opção 5: Abre o Editor Visual no navegador
     ↓
Confira áudios ▶ edite transcrições ✏️ marque status ✅⭐⚠️
     ↓
"Marcar Pendentes Como Conferido" quando a revisão estiver completa
```

---

## ⚙️ Instalação

### Pré-requisitos

O **FFmpeg** é necessário tanto para o Whisper processar áudios quanto para calcular a duração dos arquivos de mídia:

```bash
# Linux (Ubuntu/Debian)
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
winget install ffmpeg
```

### Instalação do TransCrypt

```bash
# 1. Clone o repositório
git clone https://github.com/xanfox/trans-crypt.git
cd trans-crypt

# 2. (Recomendado) Crie um ambiente virtual
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt
```

### Rodando

```bash
python3 main.py
```

No primeiro uso, a pasta `clientes/` é criada automaticamente. Basta depositar os `.zip` dentro dela e usar o menu interativo.

---

## ⚙️ Configuração (`config.py`)

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `MODELO_WHISPER` | `large-v3` | Modelo Whisper (`tiny`, `small`, `medium`, `large-v3`, `large-v3-turbo`) |
| `WHISPER_BEAM_SIZE` | `5` | Qualidade de busca (1=rápido, 5=padrão ouro, 7+=ganho mínimo) |
| `WHISPER_INITIAL_PROMPT` | `""` | Prompt de domínio em linguagem natural para ancorar vocabulário específico |
| `WHISPER_NUM_WORKERS` | `2` | Workers de pré-processamento de áudio (I/O em paralelo com a inferência) |
| `PROCESSAMENTO_PARALELO_ARQUIVOS` | `cpu_count // 2` | Instâncias simultâneas do modelo (cada uma recebe `cpu_count / N` threads) |
| `REMETENTES_DIREITA` | `("Alex", "VIP", "Xan", ...)` | Nomes que aparecem alinhados à direita no chat visual |
| `EXTENSOES_AUDIO` | `.opus .ogg .m4a .mp4 .wav .mp3` | Formatos suportados para transcrição |

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Uso |
|---|---|
| **Python 3** | Lógica central, manipulação de arquivos e servidor |
| **faster-whisper (large-v3)** | Motor de transcrição de áudio com IA — 100% local |
| **FFmpeg / ffprobe** | Conversão de áudio para Whisper e cálculo de durações |
| **Flask** | Servidor backend leve para persistir edições da UI |
| **HTML / CSS / Vanilla JS** | Dashboard de auditoria sem dependências Node/NPM |
| **JSON** | Camada de persistência leve para edições, status e cache de stats |

---

> **Nota de Privacidade:** O TransCrypt não possui chaves de API, telemetria ou conexões externas. A transcrição roda **100% localmente** via Whisper. Todos os dados de clientes (áudios, transcrições e históricos) são bloqueados via `.gitignore`.
