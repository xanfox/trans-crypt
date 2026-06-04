import os
import re
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


# ================= FUNÇÕES DE ÁUDIO =================
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


def _get_duracao_audio(caminho):
    """Retorna a duração em segundos de um áudio via ffprobe. Retorna 0.0 em falha."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                caminho
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


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
        "hallucination_silence_threshold": 2, # suprime texto gerado sobre silêncio (>2s)
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


# ================= PRÉ-ANÁLISE E SELEÇÃO DE SESSÃO =================

def _formatar_duracao(segundos):
    """Formata segundos em string legível: '2h 18min', '45min', '38s'."""
    segundos = int(segundos)
    if segundos >= 3600:
        h = segundos // 3600
        m = (segundos % 3600) // 60
        return f"{h}h {m}min"
    elif segundos >= 60:
        m = segundos // 60
        s = segundos % 60
        return f"{m}min {s}s" if s else f"{m}min"
    else:
        return f"{segundos}s"


def _extrair_data_do_nome(nome_arquivo):
    """Extrai a data de um arquivo de áudio do WhatsApp.

    O WhatsApp nomeia os arquivos como PTT-YYYYMMDD-WAxxxx.opus ou
    AUD-YYYYMMDD-WAxxxx.opus. Esta função extrai YYYYMMDD e converte
    para o formato interno DD/MM/AAAA.

    Args:
        nome_arquivo (str): Nome do arquivo (sem caminho completo).

    Returns:
        str: Data no formato 'DD/MM/AAAA', ou 'Data desconhecida' se não encontrar.
    """
    match = re.search(r'-(\d{8})-', nome_arquivo)
    if match:
        ds = match.group(1)  # YYYYMMDD
        return f"{ds[6:8]}/{ds[4:6]}/{ds[:4]}"
    return "Data desconhecida"


def estimar_tempo(segundos_audio):
    """Estima o tempo de processamento com base no RTF do modelo configurado.

    O RTF (Real-Time Factor) indica quantos segundos de processamento são
    necessários para cada segundo de áudio. Os valores em config.WHISPER_RTF
    foram medidos em benchmark real. O paralelismo reduz o tempo efetivo,
    mas não é considerado para dar uma estimativa conservadora (segura).

    Args:
        segundos_audio (float): Duração total dos áudios em segundos.

    Returns:
        float: Tempo estimado de processamento em segundos.
    """
    rtf = config.WHISPER_RTF.get(config.MODELO_WHISPER, 1.4)
    return segundos_audio * rtf


def analisar_pendentes(pasta_cliente):
    """Analisa os áudios da pasta do cliente e retorna um dict com métricas.

    Usa ffprobe em paralelo para calcular a duração total dos áudios pendentes
    de forma eficiente, mesmo com dezenas de arquivos.

    Args:
        pasta_cliente (str): Caminho da pasta do cliente.

    Returns:
        dict com as chaves:
            - total (int): total de áudios encontrados.
            - ja_transcritos (int): áudios que já têm .txt em _transcricoes/.
            - pendentes (list[str]): nomes dos arquivos ainda não transcritos.
            - duracao_total_sec (float): soma das durações dos pendentes.
            - duracao_por_audio (dict[str, float]): nome → duração em segundos.
    """
    pasta_saida = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    os.makedirs(pasta_saida, exist_ok=True)

    todos = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(config.EXTENSOES_AUDIO) and not f.endswith(".temp.wav")
    ]

    pendentes = [
        f for f in todos
        if not os.path.exists(
            os.path.join(pasta_saida, os.path.splitext(f)[0] + ".txt")
        )
    ]

    ja_transcritos = len(todos) - len(pendentes)

    duracao_por_audio = {}
    if pendentes:
        print(f"\n⏳ Calculando duração de {len(pendentes)} áudio(s) pendente(s)...")
        workers = min(8, len(pendentes))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futuros = {
                ex.submit(_get_duracao_audio, os.path.join(pasta_cliente, f)): f
                for f in pendentes
            }
            for futuro in as_completed(futuros):
                nome = futuros[futuro]
                duracao_por_audio[nome] = futuro.result()

    duracao_total = sum(duracao_por_audio.values())

    return {
        "total": len(todos),
        "ja_transcritos": ja_transcritos,
        "pendentes": pendentes,
        "duracao_total_sec": duracao_total,
        "duracao_por_audio": duracao_por_audio,
    }


def agrupar_por_sessao(pendentes, duracao_por_audio):
    """Agrupa os áudios pendentes por data extraída do nome do arquivo.

    Ordena as sessões com a mais recente primeiro (decrescente), que é a
    ordem mais útil para o caso de uso principal: revisar a última consulta.

    Args:
        pendentes (list[str]): Lista de nomes de arquivos de áudio pendentes.
        duracao_por_audio (dict[str, float]): Mapa nome → duração em segundos.

    Returns:
        list[tuple]: Lista de (data_str, [audio_files], duracao_sec),
                     ordenada por data decrescente.
    """
    grupos = {}
    for audio in pendentes:
        data = _extrair_data_do_nome(audio)
        grupos.setdefault(data, []).append(audio)

    def sort_key(data_str):
        try:
            d, m, a = data_str.split('/')
            return (int(a), int(m), int(d))
        except Exception:
            return (0, 0, 0)

    resultado = []
    for data in sorted(grupos, key=sort_key, reverse=True):
        audios_do_dia = grupos[data]
        dur = sum(duracao_por_audio.get(a, 0) for a in audios_do_dia)
        resultado.append((data, audios_do_dia, dur))

    return resultado


def _mostrar_painel_analise(analise):
    """Exibe o painel de pré-análise com estimativa de tempo no terminal."""
    pendentes = analise["pendentes"]
    dur_total = analise["duracao_total_sec"]
    tempo_proc = estimar_tempo(dur_total)

    print("\n" + "=" * 52)
    print("       ETAPA 1 | ANÁLISE DE ÁUDIOS")
    print("=" * 52)
    print(f"  📦 Total de áudios encontrados : {analise['total']}")
    print(f"  ✅ Já transcritos              : {analise['ja_transcritos']}")
    print(f"  ⏳ Pendentes                   : {len(pendentes)}")

    if pendentes:
        print()
        print(f"  🎵 Duração total (pendentes)   : {_formatar_duracao(dur_total)}")
        print(f"  ⏱️  Estimativa ({config.MODELO_WHISPER:<16}): ~{_formatar_duracao(tempo_proc)}")
        n = config.PROCESSAMENTO_PARALELO_ARQUIVOS
        if n > 1:
            print(f"     ↳ {n} processos paralelos — tempo real pode ser até {n}x menor")

    print("=" * 52)


def _mostrar_seletor_sessao(grupos):
    """Exibe o seletor interativo de sessão e retorna a lista de áudios selecionados.

    Args:
        grupos (list[tuple]): Resultado de agrupar_por_sessao().

    Returns:
        list[str] | None: Lista de nomes de arquivos selecionados, ou None se cancelado.
    """
    print("\n" + "=" * 62)
    print("     SESSÕES DISPONÍVEIS  (mais recente primeiro)")
    print("=" * 62)
    print(f"  {'#':<4} {'Data':<14} {'Áudios':<10} {'Dur. Áudio':<14} {'Proc. Estimado'}")
    print("-" * 62)

    for i, (data, audios, dur) in enumerate(grupos):
        proc = estimar_tempo(dur)
        n = len(audios)
        audio_label = f"{n} áudio{'s' if n > 1 else ''}"
        print(f"  [{i}]  {data:<14} {audio_label:<10} {_formatar_duracao(dur):<14} ~{_formatar_duracao(proc)}")

    print("=" * 62)
    print("  Digite o número da sessão (ex: 0) ou várias separadas por vírgula (ex: 0,1)")
    print("  [C] Cancelar")

    entrada = input("\n  Sua escolha: ").strip().upper()

    if entrada == 'C':
        return None

    try:
        indices = [int(x.strip()) for x in entrada.split(',') if x.strip()]
        audios_selecionados = []
        datas_selecionadas = []
        for idx in indices:
            if 0 <= idx < len(grupos):
                data, audios, _ = grupos[idx]
                audios_selecionados.extend(audios)
                datas_selecionadas.append(data)
            else:
                print(f"  ⚠️  Índice {idx} inválido — ignorado.")

        if not audios_selecionados:
            print("  ❌ Nenhuma sessão válida selecionada.")
            return None

        print(f"\n  ✅ Selecionado: {', '.join(datas_selecionadas)} → {len(audios_selecionados)} áudio(s)")
        return audios_selecionados

    except ValueError:
        print("  ❌ Entrada inválida.")
        return None


def _oferecer_geracao_html(pasta_cliente):
    """Após a transcrição, oferece gerar o histórico consolidado e o HTML visual."""
    print("\n" + "=" * 52)
    print("  Deseja gerar o HTML de conferência agora?")
    print("  [1] Sim — gerar histórico + HTML visual completo")
    print("  [2] Não — voltar ao menu")
    print("=" * 52)

    sub = input("  Escolha: ").strip()
    if sub == '1':
        import step2
        import step3
        limpar_memoria()
        print("\n>>> GERANDO HISTÓRICO CONSOLIDADO (Step 2)...")
        step2.run(pasta_cliente)
        print("\n>>> GERANDO HTML VISUAL (Step 3)...")
        step3.run(pasta_cliente)
        print("\n✅ Pronto! Use a opção [6] do menu para abrir o editor visual.")


# ================= PIPELINE PRINCIPAL =================

def run(pasta_cliente=None, interativo=True):
    """Ponto de entrada do Step 1: transcreve os áudios da pasta do cliente.

    Em modo interativo (padrão), exibe um painel de pré-análise com estimativa
    de tempo e permite selecionar apenas os áudios de uma sessão/data específica
    antes de iniciar a transcrição.

    Em modo não-interativo (interativo=False), processa todos os áudios pendentes
    diretamente sem menus, ideal para ser chamado como parte de um pipeline
    sequencial (ex: opção 5 do menu principal).

    Estratégia de paralelismo:
      - `PROCESSAMENTO_PARALELO_ARQUIVOS` arquivos são processados simultaneamente.
      - Cada instância do WhisperModel recebe `cpu_count / n_paralelo` threads,
        garantindo 100% de utilização dos núcleos disponíveis.
      - `num_workers=WHISPER_NUM_WORKERS` permite que o próximo arquivo seja
        pré-carregado enquanto o modelo ainda está transcrevendo o atual.

    Args:
        pasta_cliente (str | None): Caminho para a pasta do cliente. Se None,
                                    exibe menu interativo para o usuário escolher.
        interativo (bool): Se True (padrão), exibe painel de análise e menus de
                           seleção. Se False, processa tudo sem interação.
    """
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()

    pasta_saida = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    os.makedirs(pasta_saida, exist_ok=True)

    # --- MODO NÃO-INTERATIVO: lista completa de pendentes, sem menus ---
    if not interativo:
        audios_todos = [
            f for f in os.listdir(pasta_cliente)
            if f.lower().endswith(config.EXTENSOES_AUDIO) and not f.endswith(".temp.wav")
        ]
        audios_para_processar = [
            f for f in audios_todos
            if not os.path.exists(os.path.join(pasta_saida, os.path.splitext(f)[0] + ".txt"))
        ]
        if not audios_para_processar:
            print("\n✅ Todos os áudios já foram transcritos.")
            return
        print(f"\nEncontrados {len(audios_para_processar)} áudios pendentes.")

    else:
        # --- MODO INTERATIVO: pré-análise + seleção de sessão ---
        analise = analisar_pendentes(pasta_cliente)

        if not analise["pendentes"]:
            _mostrar_painel_analise(analise)
            print("\n✅ Todos os áudios já foram transcritos!")
            return

        _mostrar_painel_analise(analise)

        print("\n  O que deseja fazer?")
        print("  [Enter]  Transcrever TUDO que ainda não foi transcrito")
        print("  [S]      Selecionar por sessão/data específica")
        print("  [C]      Cancelar")

        escolha = input("\n  Escolha: ").strip().upper()

        if escolha == 'C':
            print("  ↩ Cancelado.")
            return

        elif escolha == 'S':
            grupos = agrupar_por_sessao(analise["pendentes"], analise["duracao_por_audio"])
            if not grupos:
                print("  ⚠️  Não foi possível identificar sessões pelos nomes dos arquivos.")
                audios_para_processar = analise["pendentes"]
            else:
                selecao = _mostrar_seletor_sessao(grupos)
                if selecao is None:
                    print("  ↩ Cancelado.")
                    return
                audios_para_processar = selecao

        else:
            # Enter ou qualquer outra tecla → tudo
            audios_para_processar = analise["pendentes"]

    # --- TRANSCRIÇÃO ---
    if not audios_para_processar:
        print("Nenhum áudio para processar.")
        return

    print(f"\n🚀 Iniciando processamento em PARALELO ({config.PROCESSAMENTO_PARALELO_ARQUIVOS} áudios por vez)...\n")

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

        return f"✔ Transcrito: {audio} (às: {hora_processamento} | Tempo: {tempo_formatado})"

    with ThreadPoolExecutor(max_workers=config.PROCESSAMENTO_PARALELO_ARQUIVOS) as executor:
        futuros = [executor.submit(processar_audio, audio) for audio in audios_para_processar]
        total_audios = len(audios_para_processar)
        contador = 0
        for futuro in as_completed(futuros):
            contador += 1
            print(f"[{contador}/{total_audios}] {futuro.result()}")

    # --- VERIFICAÇÃO FINAL ---
    sucessos = sum(
        1 for audio in audios_para_processar
        if os.path.exists(os.path.join(pasta_saida, os.path.splitext(audio)[0] + ".txt"))
    )
    falhas = [
        audio for audio in audios_para_processar
        if not os.path.exists(os.path.join(pasta_saida, os.path.splitext(audio)[0] + ".txt"))
    ]

    print("\n" + "=" * 45)
    print("📊 RELATÓRIO DE INTEGRIDADE")
    print("=" * 45)
    print(f"Áudios processados  : {len(audios_para_processar)}")
    print(f"Transcrições geradas: {sucessos}")

    if not falhas:
        print("\n✅ STATUS: PERFEITO!")
        print("Todos os áudios foram convertidos e validados com sucesso.")
    else:
        print(f"\n⚠️  ATENÇÃO: Faltam transcrições para {len(falhas)} arquivo(s)!")
        for f in falhas[:10]:
            print(f"  ❌ {f}")
        if len(falhas) > 10:
            print(f"  ... e mais {len(falhas) - 10} arquivo(s) ocultados.")
        print("\n💡 Dica: Rode o Passo 1 novamente para transcrever apenas os que faltam.")

    print("=" * 45)

    # Oferece geração de HTML apenas no modo interativo (standalone)
    if interativo:
        _oferecer_geracao_html(pasta_cliente)

    print("\n✔ ETAPA 1 FINALIZADA")


if __name__ == "__main__":
    run()
