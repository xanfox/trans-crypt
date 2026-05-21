import os
import time
import subprocess
import gc
import webbrowser
import config
import utils
import step1

def get_audio_duration(filepath):
    """Calcula a duração total do áudio em segundos usando ffprobe."""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def gerar_html_comparativo(pasta_cliente, modelos):
    """Gera uma página HTML estática comparando os resultados lado a lado, com anotações e status via localStorage."""
    print("\nGerando conferência visual lado a lado...")
    
    arquivos = os.listdir(pasta_cliente)
    audios = sorted([f for f in arquivos if f.lower().endswith(config.EXTENSOES_AUDIO) and not f.endswith(".temp.wav")])
    
    if not audios:
        print("Nenhum áudio encontrado para gerar o relatório.")
        return

    html_path = os.path.join(pasta_cliente, "conferencia_benchmark.html")
    
    # Inicia a string do HTML
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Benchmark Whisper: Comparativo</title>
    <style>
        body {{
            background-color: #121212;
            color: #e0e0e0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 20px;
        }}
        h1 {{ text-align: center; color: #fff; margin-bottom: 40px; }}
        .audio-row {{
            background: #1e1e1e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }}
        .audio-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
            border-bottom: 1px solid #333;
            padding-bottom: 15px;
        }}
        .audio-title {{ font-size: 1.2em; font-weight: bold; color: #8ab4f8; }}
        .controls-wrapper {{ display: flex; align-items: center; gap: 20px; width: 60%; }}
        audio {{ width: 100%; height: 40px; }}
        
        .anotacao-container {{ display: flex; flex-direction: column; gap: 5px; width: 40%; }}
        .anotacao-container label {{ font-size: 0.8em; color: #aaa; }}
        .anotacao-input {{
            background: #2a2a2a; border: 1px solid #444; color: #fff;
            padding: 8px; border-radius: 6px; font-family: inherit; resize: vertical; min-height: 40px;
        }}
        
        /* Status Tags (inspirado no sistema principal) */
        .status-btn {{
            cursor: pointer; padding: 6px 12px; border-radius: 20px; font-size: 0.9em;
            font-weight: bold; border: 2px solid transparent; user-select: none;
            transition: all 0.2s; background: #2a2a2a; color: #aaa;
        }}
        .status-btn[data-status="normal"] {{ border-color: #444; }}
        .status-btn[data-status="ok"] {{ border-color: #34a853; color: #34a853; }}
        .status-btn[data-status="anchor"] {{ border-color: #a142f4; color: #a142f4; }}
        .status-btn[data-status="review"] {{ border-color: #fbbc04; color: #fbbc04; }}

        .grid {{
            display: grid;
            grid-template-columns: repeat({len(modelos)}, 1fr);
            gap: 15px;
        }}
        .col {{
            background: #252525;
            padding: 15px;
            border-radius: 8px;
            border-top: 3px solid #444;
        }}
        .col h4 {{
            margin-top: 0; color: #aaa; font-size: 0.9em; text-align: center;
            border-bottom: 1px solid #333; padding-bottom: 8px;
        }}
        .texto-transcrito {{
            font-size: 1.15em; /* Fonte grande para não cansar a leitura */
            line-height: 1.5;
            color: #ddd;
        }}
    </style>
</head>
<body>
    <h1>🔎 Comparativo de Modelos: Lado a Lado</h1>
    
    <div style="text-align: center; margin-bottom: 20px; color: #aaa;">
        As anotações e status que você fizer aqui serão salvos localmente no seu navegador para esta pasta de cliente.
    </div>
"""

    for audio in audios:
        html += f"""
    <div class="audio-row" id="row_{audio}">
        <div class="audio-header">
            <div class="audio-title">🎙️ {audio}</div>
            
            <div class="controls-wrapper">
                <audio controls src="{audio}"></audio>
                
                <div class="status-btn" data-status="normal" onclick="toggleStatus('{audio}', this)">⚪ Normal</div>
            </div>
            
            <div class="anotacao-container">
                <label>Anotações (Sotaque, Ruído, Alcoolizado...)</label>
                <textarea class="anotacao-input" oninput="salvarNota('{audio}', this.value)" placeholder="Digite notas sobre a qualidade deste áudio..."></textarea>
            </div>
        </div>
        <div class="grid">"""
        
        for modelo in modelos:
            txt_file = os.path.join(pasta_cliente, "_benchmark", modelo, os.path.splitext(audio)[0] + ".txt")
            texto = "[Não transcrito]"
            if os.path.exists(txt_file):
                with open(txt_file, "r", encoding="utf-8") as f:
                    texto = f.read()
                    
            html += f"""
            <div class="col">
                <h4>{modelo.upper()}</h4>
                <div class="texto-transcrito">{texto}</div>
            </div>"""
            
        html += """
        </div>
    </div>"""

    # Add JavaScript for LocalStorage logic
    html += """
    <script>
        const statusCycle = ['normal', 'ok', 'anchor', 'review'];
        const statusLabels = {
            'normal': '⚪ Normal',
            'ok': '✅ OK',
            'anchor': '⭐ Âncora',
            'review': '⚠️ Revisar'
        };
        
        const storageKeyPrefix = 'benchmark_notas_';
        // Pega o nome da pasta do cliente pela URL para isolar as anotações
        const clientId = window.location.pathname.split('/').slice(-2, -1)[0]; 

        function salvarNota(audioFile, nota) {
            let dados = JSON.parse(localStorage.getItem(storageKeyPrefix + clientId) || '{}');
            if(!dados[audioFile]) dados[audioFile] = {};
            dados[audioFile].nota = nota;
            localStorage.setItem(storageKeyPrefix + clientId, JSON.stringify(dados));
        }
        
        function salvarStatus(audioFile, status) {
            let dados = JSON.parse(localStorage.getItem(storageKeyPrefix + clientId) || '{}');
            if(!dados[audioFile]) dados[audioFile] = {};
            dados[audioFile].status = status;
            localStorage.setItem(storageKeyPrefix + clientId, JSON.stringify(dados));
        }

        function toggleStatus(audioFile, element) {
            let currentStatus = element.getAttribute('data-status');
            let nextIndex = (statusCycle.indexOf(currentStatus) + 1) % statusCycle.length;
            let nextStatus = statusCycle[nextIndex];
            
            element.setAttribute('data-status', nextStatus);
            element.innerText = statusLabels[nextStatus];
            
            salvarStatus(audioFile, nextStatus);
        }

        // Carrega dados salvos ao iniciar a página
        window.onload = function() {
            let dados = JSON.parse(localStorage.getItem(storageKeyPrefix + clientId) || '{}');
            for(let audioFile in dados) {
                let row = document.getElementById('row_' + audioFile);
                if(row) {
                    if(dados[audioFile].nota) {
                        row.querySelector('.anotacao-input').value = dados[audioFile].nota;
                    }
                    if(dados[audioFile].status) {
                        let btn = row.querySelector('.status-btn');
                        btn.setAttribute('data-status', dados[audioFile].status);
                        btn.innerText = statusLabels[dados[audioFile].status];
                    }
                }
            }
        };
    </script>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
        
    print(f"✅ Arquivo gerado em: {html_path}")
    print("Tentando abrir no seu navegador...")
    try:
        webbrowser.open("file://" + os.path.abspath(html_path))
    except Exception as e:
        print(f"Não foi possível abrir o navegador automaticamente: {e}")

def run_benchmark():
    print("\n" + "="*50)
    print("🏎️  BENCHMARK DE PERFORMANCE DO WHISPER 🏎️")
    print("="*50)
    print("Escolha uma opção:")
    print(" [1] Rodar Benchmark Completo (Transcrever tudo de novo)")
    print(" [2] Apenas Gerar HTML Comparativo de um Benchmark Anterior")
    print(" [0] Sair")
    
    opcao = input("\nOpção: ").strip()
    
    if opcao == "0":
        return
        
    pasta_cliente = utils.escolher_pasta_cliente()
    if not pasta_cliente:
        return
        
    modelos = ["tiny", "small", "medium", "large-v3-turbo", "large-v3"]

    if opcao == "2":
        gerar_html_comparativo(pasta_cliente, modelos)
        return
        
    if opcao != "1":
        print("Opção inválida.")
        return

    arquivos = os.listdir(pasta_cliente)
    audios = [f for f in arquivos if f.lower().endswith(config.EXTENSOES_AUDIO) and not f.endswith(".temp.wav")]

    if not audios:
        print("Nenhum áudio válido encontrado para o benchmark.")
        return

    print("\nCalculando duração real da massa de teste...")
    duracao_total_audios = sum(get_audio_duration(os.path.join(pasta_cliente, a)) for a in audios)
    
    if duracao_total_audios == 0:
        print("Erro ao calcular a duração dos áudios. Verifique os arquivos.")
        return
        
    minutos = int(duracao_total_audios // 60)
    segundos = int(duracao_total_audios % 60)
    print(f"⏱️  Duração total de áudio: {duracao_total_audios:.2f} segundos ({minutos}m {segundos}s)")
    print(f"📁 Arquivos: {len(audios)}\n")

    resultados = []

    # Salva configurações originais para restaurar no final
    modelo_original = config.MODELO_WHISPER
    pasta_trans_original = config.PASTA_TRANSCRICOES

    try:
        for model in modelos:
            print("\n" + "━"*60)
            print(f"🏃 INICIANDO TESTE COM O MODELO: {model.upper()}")
            print("━"*60)

            # Injeção das configurações temporárias do benchmark
            config.MODELO_WHISPER = model
            config.PASTA_TRANSCRICOES = f"_benchmark/{model}"
            step1._whisper_model = None  # Força o singleton do modelo a resetar e carregar o novo

            inicio = time.time()
            # Chama o mesmo pipeline de produção para manter o paralelismo real
            step1.run(pasta_cliente=pasta_cliente)
            fim = time.time()

            tempo_processamento = fim - inicio
            rtf = tempo_processamento / duracao_total_audios 
            velocidade = duracao_total_audios / tempo_processamento 

            resultados.append({
                "modelo": model,
                "tempo": tempo_processamento,
                "rtf": rtf,
                "velocidade": velocidade
            })

            # Força o Garbage Collector a limpar o modelo anterior da memória RAM
            step1._whisper_model = None
            gc.collect()

    except KeyboardInterrupt:
        print("\n\n⚠️ Benchmark interrompido pelo usuário.")
        
    finally:
        # Restaura a sanidade do sistema original
        config.MODELO_WHISPER = modelo_original
        config.PASTA_TRANSCRICOES = pasta_trans_original
        step1._whisper_model = None
        gc.collect()

    if not resultados:
        return

    # Imprime a Tabela Visual de Resultados
    print("\n\n" + "🏆"*15)
    print(f"{'RESULTADOS DO BENCHMARK':^40}")
    print("🏆"*15)
    print(f"\n{'Modelo':<16} | {'Tempo Proc.':<12} | {'Velocidade':<12} | {'RTF (↓ melhor)'}")
    print("-" * 65)
    
    for r in resultados:
        tempo_str = f"{r['tempo']:>8.1f} s"
        vel_str = f"{r['velocidade']:>8.1f} x"
        rtf_str = f"{r['rtf']:>5.3f}"
        print(f"{r['modelo']:<16} | {tempo_str:<12} | {vel_str:<12} | {rtf_str}")
        
    print("-" * 65)
    
    # Gera o HTML no final automaticamente
    gerar_html_comparativo(pasta_cliente, modelos)

if __name__ == "__main__":
    try:
        run_benchmark()
    finally:
        # O Whisper (CTranslate2/OpenMP) costuma deixar threads C/C++ órfãs travando
        # o terminal após o término. O os._exit(0) força a morte imediata do processo
        # a nível de sistema operacional, garantindo a devolução limpa do terminal.
        os._exit(0)
