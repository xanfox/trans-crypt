import os
import json
import datetime
from flask import Flask, request, jsonify

import step2
import step3

app = None

def get_edits_file():
    return os.path.join(app.config['CLIENT_FOLDER'], "conferencia_edits.json")

def load_edits():
    path = get_edits_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "status" not in data:
                    data["status"] = {}
                return data
        except Exception as e:
            print(f"\\n⚠️ AVISO: O arquivo de edições está corrompido: {e}")
            print(f"Fazendo backup para .corrupted e iniciando um estado vazio para não travar.")
            try:
                import shutil
                shutil.copy(path, path + ".corrupted")
            except:
                pass
    return {"deleted_ids": [], "edited_texts": {}, "status": {}}

def save_edits(data):
    path = get_edits_file()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    # Escrita atômica: previne corrupção de arquivo em caso de queda de energia
    os.replace(tmp_path, path)

def rebuild_files():
    step2.run(app.config['CLIENT_FOLDER'], auto=True)
    step3.run(app.config['CLIENT_FOLDER'], auto=True)

def setup_routes():
    @app.route('/')
    def index():
        html_path = os.path.join(app.config['CLIENT_FOLDER'], "conferencia_visual.html")
        if not os.path.exists(html_path):
            return "Conferência não encontrada. Rode os passos 1, 2 e 3 primeiro.", 404
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()

    @app.route('/api/edit_transcription', methods=['POST'])
    def edit_transcription():
        data = request.json
        arquivo_midia = data.get('arquivo_midia')
        novo_texto = data.get('novo_texto')
        
        if not arquivo_midia or not novo_texto:
            return jsonify({"error": "Faltam parâmetros"}), 400
            
        import config
        pasta_trans = os.path.join(app.config['CLIENT_FOLDER'], config.PASTA_TRANSCRICOES)
        base = os.path.splitext(arquivo_midia)[0]
        caminho = os.path.join(pasta_trans, base + ".txt")
        
        if os.path.exists(caminho):
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(novo_texto)
            edits = load_edits()
            edits.pop('_stats', None)  # Invalida cache de stats (conteúdo mudou)
            edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            save_edits(edits)
            rebuild_files()
            return jsonify({"success": True})
        return jsonify({"error": "Transcrição não encontrada"}), 404

    @app.route('/api/edit_text', methods=['POST'])
    def edit_text():
        data = request.json
        msg_id = str(data.get('id'))
        novo_texto = data.get('novo_texto')
        
        if not msg_id or not novo_texto:
            return jsonify({"error": "Faltam parâmetros"}), 400
            
        edits = load_edits()
        edits['edited_texts'][msg_id] = novo_texto
        edits.pop('_stats', None)  # Invalida cache de stats (conteúdo mudou)
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        rebuild_files()
        
        return jsonify({"success": True})

    @app.route('/api/delete', methods=['POST'])
    def delete_message():
        data = request.json
        msg_id = data.get('id')
        arquivo_midia = data.get('arquivo_midia')
        
        if not msg_id:
            return jsonify({"error": "Faltam parâmetros"}), 400
            
        edits = load_edits()
        edits.pop('_stats', None)  # Invalida cache de stats (mensagem removida)
        # Normaliza: sempre armazena IDs como int para consistência entre Python e JSON
        deleted_int = int(msg_id)
        if deleted_int not in edits['deleted_ids']:
            edits['deleted_ids'].append(deleted_int)
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        
        if arquivo_midia:
            caminho_midia = os.path.join(app.config['CLIENT_FOLDER'], arquivo_midia)
            if os.path.exists(caminho_midia):
                os.remove(caminho_midia)
                
            import config
            pasta_trans = os.path.join(app.config['CLIENT_FOLDER'], config.PASTA_TRANSCRICOES)
            base = os.path.splitext(arquivo_midia)[0]
            caminho_txt = os.path.join(pasta_trans, base + ".txt")
            if os.path.exists(caminho_txt):
                os.remove(caminho_txt)
                
        rebuild_files()
        return jsonify({"success": True})

    @app.route('/api/toggle_status', methods=['POST'])
    def toggle_status():
        data = request.json
        msg_id = str(data.get('id'))
        status = data.get('status')
        
        VALID_STATUS = {'ok', 'anchor', 'review', 'none'}
        if not msg_id or not status or status not in VALID_STATUS:
            return jsonify({"error": "Parâmetros inválidos"}), 400
            
        edits = load_edits()
        if status == 'none':
            if msg_id in edits['status']:
                del edits['status'][msg_id]
        else:
            edits['status'][msg_id] = status
            
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        # Recriamos silenciosamente apenas o html para persistir
        step3.run(app.config['CLIENT_FOLDER'], auto=True)
        return jsonify({"success": True})

    @app.route('/api/mark_all_ok', methods=['POST'])
    def mark_all_ok():
        data = request.json
        ids = data.get('ids', [])
        edits = load_edits()
        for msg_id in ids:
            edits['status'][str(msg_id)] = 'ok'
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        step3.run(app.config['CLIENT_FOLDER'], auto=True)
        return jsonify({"success": True})

    @app.route('/api/reset_all_status', methods=['POST'])
    def reset_all_status():
        edits = load_edits()
        edits['status'] = {}
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        step3.run(app.config['CLIENT_FOLDER'], auto=True)
        return jsonify({"success": True})

    @app.route('/api/track_open', methods=['POST'])
    def track_open():
        edits = load_edits()
        edits['last_opened'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        return jsonify({"success": True})

def start_server(pasta_cliente):
    import webbrowser
    global app
    app = Flask(__name__, static_folder=pasta_cliente, static_url_path='')
    app.config['CLIENT_FOLDER'] = pasta_cliente
    setup_routes()
    
    import socket
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    port = None
    for candidate in range(5000, 5011):
        if not is_port_in_use(candidate):
            port = candidate
            break

    if port is None:
        print("❌ ERRO: Nenhuma porta disponível entre 5000 e 5010. Feche outros servidores e tente novamente.")
        return

    print(f"\n===========================================")
    print(f"🚀 EDITOR VISUAL INICIADO")
    print(f"👉 ACESSE NO NAVEGADOR: http://127.0.0.1:{port}")
    print(f"===========================================\n")
    print(f"Para encerrar o editor, pressione CTRL+C")
    
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    import threading
    import time

    def open_browser():
        time.sleep(1.5) # Dá tempo do servidor Flask subir completamente
        webbrowser.open(f'http://127.0.0.1:{port}')

    threading.Thread(target=open_browser, daemon=True).start()
    
    app.run(host='127.0.0.1', port=port, debug=False)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        start_server(sys.argv[1])
    else:
        print("Uso: python editor_server.py /caminho/pasta/cliente")
