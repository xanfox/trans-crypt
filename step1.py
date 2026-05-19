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
        _whisper_model = WhisperModel(
            config.MODELO_WHISPER,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, (os.cpu_count() or 4) // config.PROCESSAMENTO_PARALELO_ARQUIVOS)
        )
    return _whisper_model


# ================= FUNÇÕES =================
def converter_para_wav_seguro(caminho_origem):
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
    wav = converter_para_wav_seguro(caminho_audio)

    if not wav:
        return "[Áudio inválido ou sem conteúdo audível]"

    whisper = _get_whisper()

    try:
        segments, _ = whisper.transcribe(
            wav,
            language="pt",
            beam_size=config.WHISPER_BEAM_SIZE,
            best_of=5,
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=True,
            no_speech_threshold=0.4,
            log_prob_threshold=-0.5,
            compression_ratio_threshold=2.4
        )

        texto = " ".join(s.text.strip() for s in segments)
        return texto if texto else "[Áudio sem fala detectável]"

    except Exception as e:
        return f"[Erro na transcrição: {e}]"

    finally:
        if os.path.exists(wav):
            os.remove(wav)

# ================= PIPELINE =================
def run(pasta_cliente=None):
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
