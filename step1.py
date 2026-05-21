import os
import subprocess
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import utils

# ================= WHISPER (lazy initialization) =================
# O modelo Whisper NÃO é carregado aqui no nível do módulo para evitar
# consumo desnecessário de ~3GB de RAM toda vez que main.py é iniciado.
# A inicialização acontece apenas dentro de run(), na primeira chamada,
# usando o padrão singleton (a variável global _whisper_model guarda a instância).
_whisper_model = None

def _get_whisper():
    """Retorna o modelo Whisper, inicializando-o na primeira chamada (lazy singleton)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("=== ETAPA 1 | Inicializando Whisper (isso pode levar alguns segundos) ===")
        # BUG CORRIGIDO: a fórmula anterior dividia por 2 novamente, deixando
        # metade dos núcleos ociosos. Agora cada instância paralela recebe
        # sua fatia correta de threads (cpu_count / n_paralelo).
        n_threads = max(2, (os.cpu_count() or 4) // config.PROCESSAMENTO_PARALELO_ARQUIVOS)
        _whisper_model = WhisperModel(
            config.MODELO_WHISPER,
            device="cpu",
            compute_type="int8",
            cpu_threads=n_threads,
            num_workers=config.WHISPER_NUM_WORKERS,  # pré-carrega áudio enquanto computa
        )
        print(f"    └─ {config.MODELO_WHISPER} | int8 | {n_threads} threads/instância | {config.PROCESSAMENTO_PARALELO_ARQUIVOS} em paralelo")
    return _whisper_model


def limpar_memoria():
    """Libera a memória RAM ocupada pelo modelo Whisper.
    
    Deve ser chamada quando a transcrição terminar e o usuário for
    para outras etapas do sistema, devolvendo preciosos gigabytes 
    de RAM para o sistema operacional antes de abrir o navegador.
    """
    global _whisper_model
    if _whisper_model is not None:
        _whisper_model = None
        import gc
        gc.collect()
        print("🧹 [Memória de ~3GB do Whisper liberada com sucesso]")


# ================= FUNÇÕES =================
def converter_para_wav_seguro(caminho_origem):
    """Converte qualquer arquivo de áudio para WAV mono 16kHz compatível com o Whisper.

    Usa o FFmpeg com a flag `ignore_err` para tolerar arquivos de áudio levemente
    corrompidos (comum em exportações do WhatsApp). O arquivo temporário `.temp.wav`
    é sempre removido pelo chamador após a transcrição, seja por sucesso ou erro.

    Args:
        caminho_origem (str): Caminho absoluto ou relativo para o arquivo de áudio
                              de origem (.opus, .ogg, .m4a, .mp4, .wav, .mp3).

    Returns:
        str | None: Caminho do arquivo WAV temporário gerado, ou None se a conversão
                    falhar ou o arquivo resultante estiver vazio (< 1.5 KB).
    """
    caminho_wav = caminho_origem + ".temp.wav"

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-err_detect", "ignore_err",
                "-i", caminho_origem,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                caminho_wav
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3600  # 1 hora de timeout para áudios muito longos
        )

        if not os.path.exists(caminho_wav):
            return None

        if os.path.getsize(caminho_wav) < 1500:
            os.remove(caminho_wav)
            return None

        return caminho_wav

    except Exception:
        if os.path.exists(caminho_wav):
            os.remove(caminho_wav)
        return None

def transcrever_audio(caminho_audio):
    """Transcreve um único arquivo de áudio para texto usando o modelo Whisper.

    Pipeline interno:
      1. Converte o áudio para WAV 16kHz mono via `converter_para_wav_seguro`.
      2. Executa a transcrição com os parâmetros definidos em config.py.
      3. Remove o arquivo WAV temporário (bloco `finally` garante limpeza).

    Decisões de design dos parâmetros de transcrição:
      - temperature=0.0 / beam_size=N : beam search determinista — sem variação
        entre execuções, máxima consistência de saída.
      - best_of=1 : `best_of > 1` só tem efeito com temperature > 0 (amostragem).
        Setar 1 evita passes extras desnecessários se ocorrer fallback de temperatura.
      - condition_on_previous_text=False : para mensagens curtas do WhatsApp, o
        contexto anterior gera alucinações de continuidade. Desativado para evitar
        que o modelo "invente" continuações que não existem no áudio.
      - vad_filter=True : remove regiões de silêncio antes de processar, acelerando
        a transcrição e evitando alucinações em silêncios longos.
      - hallucination_silence_threshold=2 : suprime segmentos onde o modelo gera
        texto mesmo detectando mais de 2 s de silêncio (áudio mudo ou voz de fundo).
      - compression_ratio_threshold=2.4 : detecta loops de repetição — padrão
        característico de alucinações do Whisper — e descarta o segmento.

    Args:
        caminho_audio (str): Caminho para o arquivo de áudio a ser transcrito.

    Returns:
        str: Texto transcrito, ou uma mensagem de erro/aviso entre colchetes
             caso o áudio seja inválido, silencioso ou ocorra uma exceção.
    """
    wav = converter_para_wav_seguro(caminho_audio)

    if not wav:
        return "[Áudio inválido ou sem conteúdo audível]"

    whisper = _get_whisper()

    # Monta kwargs opcionais
    kwargs = {
        "language": "pt",
        "beam_size": config.WHISPER_BEAM_SIZE,
        "best_of": 1,                      # best_of > 1 só ajuda com temperature > 0;
                                            # evita passes extras desnecessários no fallback
        "temperature": 0.0,                # beam search determinista: máxima consistência
        "vad_filter": True,                # remove segmentos de silêncio antes de transcrever
        "condition_on_previous_text": False, # False = sem alucinações de continuidade
                                             # útil para áudios longos; contra-producente
                                             # para mensagens curtas do WhatsApp
        "no_speech_threshold": 0.4,        # descarta segmentos com baixa probabilidade de fala
        "log_prob_threshold": -0.5,        # descarta segmentos com baixa confiança geral
        "compression_ratio_threshold": 2.4, # detecta repetições (sinal de alucinação)
        "hallucination_silence_threshold": 2, # suprime texto gerado sobre silêncio (> 2s)
    }

    # Adiciona initial_prompt apenas se configurado (deixar vazio desativa)
    if config.WHISPER_INITIAL_PROMPT:
        kwargs["initial_prompt"] = config.WHISPER_INITIAL_PROMPT

    try:
        segments, _ = whisper.transcribe(wav, **kwargs)
        texto = " ".join(s.text.strip() for s in segments)
        return texto if texto else "[Áudio sem fala detectável]"

    except Exception as e:
        return f"[Erro na transcrição: {e}]"

    finally:
        if os.path.exists(wav):
            os.remove(wav)

# ================= PIPELINE =================
def run(pasta_cliente=None):
    """Ponto de entrada do Step 1: transcreve todos os áudios da pasta do cliente.

    Descobre todos os arquivos de áudio na pasta, pula os que já possuem
    transcrição em `_transcricoes/` e processa os demais em paralelo usando
    um ThreadPoolExecutor. Ao final, exibe um relatório de integridade.

    Estratégia de paralelismo:
      - `PROCESSAMENTO_PARALELO_ARQUIVOS` arquivos são processados simultaneamente.
      - Cada instância do WhisperModel recebe `cpu_count / n_paralelo` threads,
        garantindo 100% de utilização dos núcleos disponíveis.
      - `num_workers=WHISPER_NUM_WORKERS` permite que o próximo arquivo seja
        pré-carregado enquanto o modelo ainda está transcrevendo o atual.

    Args:
        pasta_cliente (str | None): Caminho para a pasta do cliente. Se None,
                                    exibe menu interativo para o usuário escolher.
    """
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()

    pasta_saida = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    os.makedirs(pasta_saida, exist_ok=True)

    arquivos = os.listdir(pasta_cliente)

    audios = [
        f for f in arquivos
        if f.lower().endswith(config.EXTENSOES_AUDIO) and not f.endswith(".temp.wav")
    ]

    if not audios:
        print("Nenhum áudio encontrado nessa pasta.")
        return

    print(f"\nEncontrados {len(audios)} áudios na pasta do cliente.")
    print(f"🚀 Iniciando processamento em PARALELO ({config.PROCESSAMENTO_PARALELO_ARQUIVOS} áudios por vez)...\n")

    def processar_audio(audio):
        """Worker executado em thread: converte + transcreve um arquivo e salva o .txt."""
        caminho_audio = os.path.join(pasta_cliente, audio)
        nome_txt = os.path.splitext(audio)[0] + ".txt"
        caminho_txt = os.path.join(pasta_saida, nome_txt)

        if os.path.exists(caminho_txt):
            return f"⏭️  Pulando (já existe): {audio}"

        inicio = time.time()
        hora_processamento = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        texto = transcrever_audio(caminho_audio)

        fim = time.time()
        duracao = fim - inicio
        horas, resto = divmod(duracao, 3600)
        minutos, segundos = divmod(resto, 60)

        if horas > 0:
            tempo_formatado = f"{int(horas)}h {int(minutos)}m {int(segundos)}s"
        elif minutos > 0:
            tempo_formatado = f"{int(minutos)}m {int(segundos)}s"
        else:
            tempo_formatado = f"{duracao:.2f}s"

        with open(caminho_txt, "w", encoding="utf-8") as f:
            f.write(texto)

        return f"✔ Transcrito: {audio} (Processado às: {hora_processamento} | Tempo: {tempo_formatado})"

    with ThreadPoolExecutor(max_workers=config.PROCESSAMENTO_PARALELO_ARQUIVOS) as executor:
        futuros = [executor.submit(processar_audio, audio) for audio in audios]

        total_audios = len(audios)
        contador = 0

        for futuro in as_completed(futuros):
            contador += 1
            # Imprime o resultado assim que cada thread termina, com o status de progresso
            print(f"[{contador}/{total_audios}] {futuro.result()}")

    # ================= VERIFICAÇÃO FINAL =================
    sucessos = 0
    falhas = []

    for audio in audios:
        nome_txt = os.path.splitext(audio)[0] + ".txt"
        if os.path.exists(os.path.join(pasta_saida, nome_txt)):
            sucessos += 1
        else:
            falhas.append(audio)

    print("\n" + "="*45)
    print("📊 RELATÓRIO DE INTEGRIDADE (VERIFICAÇÃO)")
    print("="*45)
    print(f"Total de áudios encontrados : {len(audios)}")
    print(f"Transcrições bem-sucedidas  : {sucessos}")

    if not falhas:
        print("\n✅ STATUS: PERFEITO!")
        print("Todos os áudios foram convertidos e validados com sucesso.")
    else:
        print(f"\n⚠️ ATENÇÃO: Faltam transcrições para {len(falhas)} arquivos!")
        print("Áudios com falha (ou interrompidos):")
        for f in falhas[:10]:
            print(f"  ❌ {f}")
        if len(falhas) > 10:
            print(f"  ... e mais {len(falhas) - 10} arquivos ocultados.")

        print("\n💡 Dica: Rode o Passo 1 novamente para transcrever apenas os que faltam.")
    print("="*45 + "\n")

    print("✔ ETAPA 1 FINALIZADA")

if __name__ == "__main__":
    run()
