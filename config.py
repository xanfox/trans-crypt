import os

# ================= CONFIG =================
PASTA_BASE = "./clientes"
PASTA_TRANSCRICOES = "_transcricoes"
ARQUIVO_HISTORICO = "historico_consolidado.txt"

# Nome canônico do arquivo de chat gerado pelo Step 0 e consumido pelos Steps 2 e 3.
ARQUIVO_CHAT = "_chat.txt"

# Nomes das pastas de trabalho internas usadas pelo Step 0 (evita hardcoding espalhado).
PASTA_ZIPS_PROCESSADOS = "_zips_processados"
PASTA_TEMP_ZIPS = "_temp_zips"

# Extensões de áudio suportadas para transcrição
EXTENSOES_AUDIO = (".opus", ".ogg", ".m4a", ".mp4", ".wav", ".mp3")

# Extensões de mídia suportadas no HTML
EXTENSOES_MIDIA_HTML = EXTENSOES_AUDIO + (".jpg", ".jpeg", ".png")

# Configuração do modelo do Whisper
# Modelos disponíveis (do mais lento/preciso ao mais rápido):
#   'large-v3'       → máxima acurácia, mais lento
#   'large-v3-turbo' → ~6-8x mais rápido que large-v3, perda mínima de qualidade
#   'medium'         → boa acurácia, moderado
#   'small'          → rápido, aceitável para áudios limpos
MODELO_WHISPER = "large-v3"

# O 'beam_size' dita o quanto a IA "pensa" nas palavras.
# 1 = rápido e simples | 5 = padrão ouro de qualidade | 7+ = ganho mínimo, custo alto
WHISPER_BEAM_SIZE = 5

# Prompt inicial para orientar o vocabulário antes de cada transcrição.
# O Whisper trata este texto como "transcrição prévia" — escreva em linguagem
# natural e conversacional, não como lista de palavras-chave. Isso ancora o
# vocabulário do domínio sem confundir o modelo com estrutura de glossário.
# Deixe "" para desativar.
WHISPER_INITIAL_PROMPT = (
    "Essa é uma conversa de atendimento espiritual e desenvolvimento pessoal. "
    "Os temas abordados incluem tarô, chakras, espiritualidade e autoconhecimento. "
    "Também falamos sobre coaching, metas, planejamento e finanças pessoais. "
    "Outros temas recorrentes são psicologia, filosofia e aperfeiçoamento pessoal."
)

# Número de workers para pré-processamento paralelo de áudio.
# Permite que o próximo arquivo seja carregado/decodificado enquanto o atual é transcrito.
WHISPER_NUM_WORKERS = 2

# Nomes ou identificadores para as mensagens que ficarão alinhadas à direita no HTML
REMETENTES_DIREITA = ("Alex", "VIP", "Xan", "7caballa")

# ================= PERFORMANCE =================
# Número de arquivos de áudio processados SIMULTANEAMENTE.
# Usa metade dos núcleos do seu processador para não travar o computador inteiro.
# Cada instância paralela recebe (cpu_count / paralelo) threads — 100% de aproveitamento.
PROCESSAMENTO_PARALELO_ARQUIVOS = max(1, (os.cpu_count() or 4) // 2)

# Lixo unicode para limpar nas leituras
UNICODE_LIXO = ["\u200e", "\u202a", "\u202c", "\ufeff"]
