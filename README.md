# TransCrypt 🎙️💬

TransCrypt é uma suíte automatizada e interativa desenhada para **transcrição, consolidação e auditoria de conversas do WhatsApp**. 

O sistema foi construído para lidar com longos históricos de mensagens mistas (texto e áudios), convertendo automaticamente arquivos de mídia de voz em texto (utilizando inteligência artificial) e unificando toda a linha do tempo da conversa em um formato legível. Mais do que apenas processamento de dados, o TransCrypt oferece uma **Dashboard Visual Interativa** de última geração para auditar e editar o histórico de forma ágil e não-destrutiva.

## 🚀 Funcionalidades Principais

* **Transcrição de Áudio de Alta Precisão (Whisper):** Extrai automaticamente mídias exportadas pelo WhatsApp (áudios `.opus`, `.ogg`, etc.) e realiza transcrição assíncrona utilizando o modelo Whisper.
* **Processamento Paralelo (Multi-threading):** Otimiza o tempo de execução dividindo tarefas de transcrição entre os núcleos do processador (processando 10+ áudios simultaneamente).
* **Consolidação de Histórico:** Intercala perfeitamente as mensagens de texto originais com as transcrições geradas na exata ordem cronológica do chat.
* **Dashboard Visual Interativa (Flask Backend):**
  * **Tema Dark Profissional:** Interface de conferência gerada em HTML/CSS nativo, focado em leitura de longos textos.
  * **Edição Não-Destrutiva:** Edite textos e apague mensagens irrelevantes com um clique. Os dados originais do chat são preservados e as edições persistem via `JSON`.
  * **Controle de Reprodução:** Ouça os áudios originais diretamente no navegador com velocidades variáveis (1x até 2.5x).
  * **Sistema de Auditoria (3 Estados):** Navegue rapidamente clicando nos balões para marcar como Conferido (✅), Favorito/Âncora (✅⭐), ou Para Revisão (⚠️).
  * **Navegação Rápida (Anchor Jump):** Pule instantaneamente entre as mensagens marcadas como Favoritas através dos botões direcionais.
  * **Ações em Massa e Rastreio de Tempo:** Marque todo o histórico como auditado com um clique, com rastreamento integrado da data e hora da última revisão.

## 🛠️ Tecnologias Utilizadas

* **Python 3** (Lógica central, manipulação de arquivos)
* **OpenAI Whisper** (Motor de Transcrição Inteligente via FFMPEG)
* **Flask** (Servidor Backend em segundo plano para estado de UI)
* **Vanilla JS + CSS3** (Interface Visual Leve, sem dependências Node/NPM)
* **JSON** (Camada de persistência leve)

## 📁 Estrutura do Projeto

* `main.py`: Ponto de entrada do sistema. Oferece o menu interativo no terminal.
* `step1.py`: Faz o parse dos arquivos e invoca a transcrição de mídias usando Whisper.
* `step2.py`: Processa o arquivo `_chat.txt` original e cria a linha do tempo consolidada.
* `step3.py`: Gera o motor visual (HTML/JS) da Dashboard baseado no estado atual.
* `editor_server.py`: Roda a API Flask em segundo plano para persistir cliques e edições visuais da Dashboard.
* `config.py`: Variáveis globais e configurações de caminhos/extensões do projeto.

## ⚙️ Como Instalar e Rodar

### Pré-requisitos
Para que a transcrição de áudios funcione, você precisará ter o **FFmpeg** instalado na sua máquina (necessário para o Whisper processar os áudios):
- **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install ffmpeg`
- **Windows:** Instale via `winget install ffmpeg` ou baixe do site oficial e adicione ao PATH.
- **Mac:** `brew install ffmpeg`

### Instalação
1. Clone este repositório:
   ```bash
   git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
   cd trans-crypt
   ```
2. (Opcional, mas recomendado) Crie um ambiente virtual Python:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # no Windows use: venv\Scripts\activate
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

### Primeiro Uso
1. Rode o arquivo principal:
   ```bash
   python3 main.py
   ```
2. O sistema detectará que não existe uma pasta base e criará a pasta `clientes/` automaticamente.
3. Exportar dados: Pegue a exportação de um chat do WhatsApp (o arquivo `_chat.txt` + as mídias `.opus` etc) e coloque dentro de uma subpasta em `clientes/` (ex: `clientes/Maria_Silva`).
4. Rode `python3 main.py` novamente e use o menu para iniciar o processamento!

---
**Nota de Privacidade:** O código não possui nenhuma chave de API, senha ou telemetria embutida. A transcrição do Whisper roda 100% localmente na sua máquina. Todos os arquivos de clientes (áudios, transcrições e `.txt` crus) são bloqueados via `.gitignore` por razões de sigilo absoluto.
