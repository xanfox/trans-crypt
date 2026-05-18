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

## ⚙️ Como Funciona

1. **Exportação:** Você exporta o chat do WhatsApp (com mídias) e insere na pasta `clientes/`.
2. **Step 1 & 2:** O menu de terminal processa e unifica os dados, transcrevendo horas de áudios em poucos minutos.
3. **Dashboard (Step 3 / Opção 5):** O sistema abre seu navegador num ambiente local simulado. 
4. **Revisão:** Você lê o texto, corrige as transcrições geradas se necessário, marca pontos chave com a Âncora e deleta saudações/vendas (limpeza de dados).
5. **Resultado Final:** Todo o processamento gera um arquivo `historico_consolidado.txt` cirurgicamente limpo e pronto para virar base para geração de relatórios de clientes ou alimentação de novos IAs de contexto.

---
**Nota de Privacidade:** Todos os arquivos de clientes (áudios, transcrições e `.txt` crus) são ignorados via `.gitignore` por razões de sigilo e não estão incluídos neste repositório.
