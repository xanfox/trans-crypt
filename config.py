import os

import os

# ================= CONFIG =================
PASTA_BASE = "./clientes"
PASTA_TRANSCRICOES = "_transcricoes"
ARQUIVO_HISTORICO = "historico_consolidado.txt"

# Extensões de áudio suportadas para transcrição
EXTENSOES_AUDIO = (".opus", ".ogg", ".m4a", ".mp4", ".wav", ".mp3")

# Extensões de mídia suportadas no HTML
EXTENSOES_MIDIA_HTML = EXTENSOES_AUDIO + (".jpg", ".jpeg", ".png")

# Configuração do modelo do Whisper
# Modelos: 'tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3'
# Para a maior acurácia possível, recomendamos 'large-v3' (exige mais processamento)
MODELO_WHISPER = "large-v3"

# O 'beam_size' dita o quanto a IA "pensa" nas palavras. 
# 1 é rápido e burro, 5 é o padrão ouro de qualidade, valores maiores (ex: 7) aumentam muito o tempo para pouco ganho.
WHISPER_BEAM_SIZE = 5

# Nomes ou identificadores para as mensagens que ficarão alinhadas à direita no HTML
REMETENTES_DIREITA = ("Alex", "VIP", "Xan", "7caballa")

# ================= PERFORMANCE =================
# Número de arquivos de áudio processados SIMULTANEAMENTE.
# Usa metade dos núcleos do seu processador para não travar o computador inteiro.
PROCESSAMENTO_PARALELO_ARQUIVOS = max(1, (os.cpu_count() or 4) // 2)

# Lixo unicode para limpar nas leituras
UNICODE_LIXO = ["\u200e", "\u202a", "\u202c", "\ufeff"]
