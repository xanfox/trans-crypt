import os
import json
import re
import datetime
import uuid
from flask import Flask, request, jsonify

import step2
import step3
import step4_menu

app = None

# ================= CONFIGURAÇÃO POR MODO =================
# Mapeia o modo ("normal" ou "anon") para os arquivos/parâmetros corretos.
MODE_CONFIG = {
    "normal": {
        "html_file": "conferencia_visual.html",
        "edits_file": "conferencia_edits.json",
        "pasta_transcricoes": "_transcricoes",
        "historico_saida": "historico_consolidado.txt",
    },
    "anon": {
        "html_file": "conferencia_anonimizada.html",
        "edits_file": "conferencia_edits_anonimizada.json",
        "pasta_transcricoes": "_transcricoes_anonimizadas",
        "historico_saida": "historico_anonimizado.txt",
    },
}

def _cfg(key):
    """Retorna a configuração correta para o modo atual do servidor."""
    modo = app.config.get('MODE', 'normal')
    return MODE_CONFIG[modo][key]

def get_edits_file():
    return os.path.join(app.config['CLIENT_FOLDER'], _cfg("edits_file"))

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
    tmp_path = path + f".{uuid.uuid4().hex}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    # Escrita atômica: previne corrupção de arquivo em caso de queda de energia
    os.replace(tmp_path, path)

def rebuild_files():
    pasta = app.config['CLIENT_FOLDER']
    modo = app.config.get('MODE', 'normal')
    cfg = MODE_CONFIG[modo]

    if modo == "anon":
        step2.run(pasta, auto=True,
                  arquivo_saida=cfg["historico_saida"],
                  arquivo_edits=cfg["edits_file"],
                  pasta_transcricoes=cfg["pasta_transcricoes"])
        step3.run(pasta, auto=True,
                  nome_saida=cfg["html_file"],
                  arquivo_edits=cfg["edits_file"],
                  pasta_transcricoes=cfg["pasta_transcricoes"])
    else:
        step2.run(pasta, auto=True)
        step3.run(pasta, auto=True)

def _rebuild_html_only():
    """Regenera apenas o HTML sem reprocessar o histórico texto (mais rápido)."""
    pasta = app.config['CLIENT_FOLDER']
    modo = app.config.get('MODE', 'normal')
    cfg = MODE_CONFIG[modo]
    if modo == "anon":
        step3.run(pasta, auto=True,
                  nome_saida=cfg["html_file"],
                  arquivo_edits=cfg["edits_file"],
                  pasta_transcricoes=cfg["pasta_transcricoes"])
    else:
        step3.run(pasta, auto=True)

def setup_routes():
    @app.route('/')
    def index():
        html_path = os.path.join(app.config['CLIENT_FOLDER'], _cfg("html_file"))
        if not os.path.exists(html_path):
            modo = app.config.get('MODE', 'normal')
            if modo == "anon":
                return "Conferência Anonimizada não encontrada. Rode o Passo 4 (Anonimizar) para este cliente primeiro.", 404
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
        pasta_trans = os.path.join(app.config['CLIENT_FOLDER'], _cfg("pasta_transcricoes"))
        base = os.path.splitext(arquivo_midia)[0]
        caminho = os.path.join(pasta_trans, base + ".txt")
        
        if os.path.exists(caminho):
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(novo_texto)
            edits = load_edits()
            edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            save_edits(edits)
            _rebuild_html_only()
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
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        _rebuild_html_only()
        
        return jsonify({"success": True})

    @app.route('/api/delete', methods=['POST'])
    def delete_message():
        data = request.json
        msg_id = data.get('id')
        arquivo_midia = data.get('arquivo_midia')
        
        if not msg_id:
            return jsonify({"error": "Faltam parâmetros"}), 400
            
        edits = load_edits()
        # Normaliza: sempre armazena IDs como int para consistência entre Python e JSON
        deleted_int = int(msg_id)
        if deleted_int not in edits['deleted_ids']:
            edits['deleted_ids'].append(deleted_int)
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        
        if arquivo_midia:
            # Em modo ANONIMIZADO, NÃO apaga o arquivo de mídia original
            # (o áudio está na pasta do cliente e pode ser necessário para re-transcrição futura)
            if app.config.get('MODE') != 'anon':
                caminho_midia = os.path.join(app.config['CLIENT_FOLDER'], arquivo_midia)
                if os.path.exists(caminho_midia):
                    os.remove(caminho_midia)
                
            pasta_trans = os.path.join(app.config['CLIENT_FOLDER'], _cfg("pasta_transcricoes"))
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
        _rebuild_html_only()
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
        _rebuild_html_only()
        return jsonify({"success": True})

    @app.route('/api/reset_all_status', methods=['POST'])
    def reset_all_status():
        edits = load_edits()
        edits['status'] = {}
        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        _rebuild_html_only()
        return jsonify({"success": True})

    @app.route('/api/track_open', methods=['POST'])
    def track_open():
        edits = load_edits()
        edits['last_opened'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        return jsonify({"success": True})

    # ================= ROTAS DE ANONIMIZAÇÃO INTERATIVA =================

    @app.route('/api/revert_tag', methods=['POST'])
    def revert_tag():
        """Reverte uma tag de anonimização ao texto original.

        Recebe: {"msg_id": "16", "original": "Bianca", "tag": "[NOME]"}
        Resultado: Remove a substituição do anon_map, atualiza edited_texts
        para repor o texto original, e regenera o HTML.
        """
        data = request.json
        msg_id = str(data.get('msg_id'))
        original_text = data.get('original')
        tag = data.get('tag')

        if not msg_id or not original_text or not tag:
            return jsonify({"error": "Faltam parâmetros"}), 400

        edits = load_edits()
        anon_map = edits.get('anon_map', {})
        subs = anon_map.get(msg_id, [])

        removed_idx = -1
        for i, sub in enumerate(subs):
            if sub['original'] == original_text and sub['tag'] == tag:
                removed_idx = i
                break

        if removed_idx == -1:
            return jsonify({"error": "Substituição não encontrada no mapa"}), 404

        arquivo_midia = data.get('arquivo_midia')

        # Remove do anon_map
        subs.pop(removed_idx)
        if not subs:
            del anon_map[msg_id]

        # Reverte no arquivo de transcrição (se for mídia) ou no edited_texts (se for texto)
        if arquivo_midia and app.config.get('MODE') == 'anon':
            caminho_trans = os.path.join(app.config['CLIENT_FOLDER'], _cfg("pasta_transcricoes"))
            base = os.path.splitext(arquivo_midia)[0]
            caminho_txt = os.path.join(caminho_trans, base + ".txt")
            if os.path.exists(caminho_txt):
                with open(caminho_txt, "r", encoding="utf-8") as f:
                    texto_atual = f.read()
                if tag in texto_atual:
                    texto_atual = texto_atual.replace(tag, original_text, 1)
                    with open(caminho_txt, "w", encoding="utf-8") as f:
                        f.write(texto_atual)
        else:
            texto_atual = edits.get('edited_texts', {}).get(msg_id, '')
            if tag in texto_atual:
                texto_atual = texto_atual.replace(tag, original_text, 1)
                edits['edited_texts'][msg_id] = texto_atual

        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        _rebuild_html_only()

        return jsonify({"success": True, "original": original_text})

    @app.route('/api/retag', methods=['POST'])
    def retag():
        """Aplica uma nova tag de anonimização a um texto previamente revertido.

        Recebe: {"msg_id": "16", "original": "Bianca", "new_tag": "[LOCAL]"}
        Resultado: Insere no anon_map, substitui no edited_texts, regenera HTML.
        """
        data = request.json
        msg_id = str(data.get('msg_id'))
        original = data.get('original', '').strip()
        new_tag = data.get('new_tag')
        # Validação flexível: aceita qualquer tag entre colchetes
        if not msg_id or not original or not new_tag or not (new_tag.startswith('[') and new_tag.endswith(']')):
            return jsonify({"error": "Parâmetros inválidos"}), 400

        tag_inner = new_tag[1:-1]

        # Calcula idade se for data de nascimento
        if new_tag == '[DATA NASCIMENTO]':
            match = re.search(r'\b(19\d\d|20\d\d)\b', original)
            if match:
                ano = int(match.group(1))
                idade = datetime.datetime.now().year - ano
                new_tag = f"[DATA NASCIMENTO (~{idade} anos)]"
        elif tag_inner not in ['DATA', 'DATA NASCIMENTO', 'LOCAL', 'NOME'] and not tag_inner.startswith('TRAIT'):
            # É uma Persona!
            pasta_cliente = app.config['CLIENT_FOLDER']
            personas_ativas = step4_menu.load_personas(pasta_cliente)
            tag_final = step4_menu.formatar_tag_persona(personas_ativas, original, tag_inner)
            step4_menu.save_personas(pasta_cliente, personas_ativas)
            new_tag = f"[{tag_final}]"

        edits = load_edits()
        anon_map = edits.setdefault('anon_map', {})
        subs = anon_map.setdefault(msg_id, [])

        arquivo_midia = data.get('arquivo_midia')

        # Adiciona a nova substituição
        subs.append({
            "original": original,
            "tag": new_tag,
            "type": "manual"
        })

        # Substitui no arquivo de transcrição ou no edited_texts
        if arquivo_midia and app.config.get('MODE') == 'anon':
            caminho_trans = os.path.join(app.config['CLIENT_FOLDER'], _cfg("pasta_transcricoes"))
            base = os.path.splitext(arquivo_midia)[0]
            caminho_txt = os.path.join(caminho_trans, base + ".txt")
            if os.path.exists(caminho_txt):
                with open(caminho_txt, "r", encoding="utf-8") as f:
                    texto_atual = f.read()
                if original in texto_atual:
                    texto_atual = texto_atual.replace(original, new_tag, 1)
                    with open(caminho_txt, "w", encoding="utf-8") as f:
                        f.write(texto_atual)
        else:
            texto_atual = edits.get('edited_texts', {}).get(msg_id, '')
            if original in texto_atual:
                texto_atual = texto_atual.replace(original, new_tag, 1)
                edits['edited_texts'][msg_id] = texto_atual

        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        _rebuild_html_only()

        return jsonify({"success": True})


    @app.route('/api/manual_tag', methods=['POST'])
    def manual_tag():
        """Aplica uma tag a um texto selecionado manualmente (com cálculo de idade).

        Recebe: {"msg_id": "16", "original": "21 de 10 de 1995", "tag": "[DATA]", "full_text": "...", "arquivo_midia": "..."}
        """
        data = request.json
        msg_id = str(data.get('msg_id'))
        original = data.get('original', '').strip()
        tag = data.get('tag')
        # Validação flexível
        if not msg_id or not original or not tag or not (tag.startswith('[') and tag.endswith(']')):
            return jsonify({"error": "Parâmetros inválidos"}), 400
            
        tag_inner = tag[1:-1]

        # Calcula idade se for data de nascimento
        if tag == '[DATA NASCIMENTO]':
            match = re.search(r'\b(19\d\d|20\d\d)\b', original)
            if match:
                ano = int(match.group(1))
                idade = datetime.datetime.now().year - ano
                tag = f"[DATA NASCIMENTO (~{idade} anos)]"
        elif tag_inner not in ['DATA', 'DATA NASCIMENTO', 'LOCAL', 'NOME'] and not tag_inner.startswith('TRAIT'):
            # É uma Persona!
            pasta_cliente = app.config['CLIENT_FOLDER']
            personas_ativas = step4_menu.load_personas(pasta_cliente)
            tag_final = step4_menu.formatar_tag_persona(personas_ativas, original, tag_inner)
            step4_menu.save_personas(pasta_cliente, personas_ativas)
            tag = f"[{tag_final}]"

        edits = load_edits()
        anon_map = edits.setdefault('anon_map', {})
        subs = anon_map.setdefault(msg_id, [])

        arquivo_midia = data.get('arquivo_midia')

        # Adiciona a nova substituição
        subs.append({
            "original": original,
            "tag": tag,
            "type": "manual"
        })

        # Substitui no arquivo de transcrição ou no edited_texts
        if arquivo_midia and app.config.get('MODE') == 'anon':
            caminho_trans = os.path.join(app.config['CLIENT_FOLDER'], _cfg("pasta_transcricoes"))
            base = os.path.splitext(arquivo_midia)[0]
            caminho_txt = os.path.join(caminho_trans, base + ".txt")
            if os.path.exists(caminho_txt):
                with open(caminho_txt, "r", encoding="utf-8") as f:
                    texto_atual = f.read()
                if original in texto_atual:
                    texto_atual = texto_atual.replace(original, tag, 1)
                    with open(caminho_txt, "w", encoding="utf-8") as f:
                        f.write(texto_atual)
        else:
            texto_atual = edits.get('edited_texts', {}).get(msg_id)
            if not texto_atual:
                texto_atual = full_text

            if original in texto_atual:
                texto_atual = texto_atual.replace(original, tag, 1)
                edits['edited_texts'][msg_id] = texto_atual

        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        _rebuild_html_only()

        return jsonify({"success": True})


    @app.route('/api/get_personas', methods=['GET'])
    def get_personas():
        tree = step4_menu.load_categorias_globais()
        tree_traits = step4_menu.load_categorias_traits()
        pasta_cliente = app.config['CLIENT_FOLDER']
        ativas = step4_menu.load_personas(pasta_cliente)
        return jsonify({"tree": tree, "tree_traits": tree_traits, "ativas": ativas})


    @app.route('/api/add_categoria', methods=['POST'])
    def add_categoria():
        data = request.json
        pai = data.get('pai')
        nova = data.get('nova', '').strip()
        if not nova:
            return jsonify({"error": "Nome inválido"}), 400
            
        tree = step4_menu.load_categorias_globais()
        if pai:
            if pai in tree:
                if nova not in tree[pai]:
                    tree[pai].append(nova)
            else:
                tree[pai] = [nova]
        else:
            if nova not in tree:
                tree[nova] = []
                
        step4_menu.save_categorias_globais(tree)
        # Recria HTML se precisar? Normalmente a gente só atualiza via JS, 
        # mas vamos recriar por segurança
        _rebuild_html_only()
        return jsonify({"success": True, "tree": tree})

    @app.route('/api/remove_categoria', methods=['POST'])
    def remove_categoria():
        data = request.json
        pai = data.get('pai')
        item = data.get('item', '').strip()
        tree = step4_menu.load_categorias_globais()
        if pai and pai in tree:
            if item in tree[pai]:
                tree[pai].remove(item)
        elif item and item in tree:
            del tree[item]
        step4_menu.save_categorias_globais(tree)
        _rebuild_html_only()
        return jsonify({"success": True, "tree": tree})

    @app.route('/api/add_trait_categoria', methods=['POST'])
    def add_trait_categoria():
        data = request.json
        pai = data.get('pai')
        nova = data.get('nova', '').strip()
        if not nova:
            return jsonify({"error": "Nome inválido"}), 400
            
        tree = step4_menu.load_categorias_traits()
        if pai:
            if pai in tree:
                if nova not in tree[pai]:
                    tree[pai].append(nova)
            else:
                tree[pai] = [nova]
        else:
            if nova not in tree:
                tree[nova] = []
                
        step4_menu.save_categorias_traits(tree)
        _rebuild_html_only()
        return jsonify({"success": True, "tree": tree})

    @app.route('/api/remove_trait_categoria', methods=['POST'])
    def remove_trait_categoria():
        data = request.json
        pai = data.get('pai')
        item = data.get('item', '').strip()
        tree = step4_menu.load_categorias_traits()
        if pai and pai in tree:
            if item in tree[pai]:
                tree[pai].remove(item)
        elif item and item in tree:
            del tree[item]
        step4_menu.save_categorias_traits(tree)
        _rebuild_html_only()
        return jsonify({"success": True, "tree": tree})


    @app.route('/api/unify_persona', methods=['POST'])
    def unify_persona():
        data = request.json
        msg_id = str(data.get('msg_id'))
        original = data.get('original', '').strip()
        target_persona = data.get('target_persona')
        arquivo_midia = data.get('arquivo_midia')
        
        if not all([msg_id, original, target_persona]):
            return jsonify({"error": "Parâmetros inválidos"}), 400
            
        pasta_cliente = app.config['CLIENT_FOLDER']
        personas_ativas = step4_menu.load_personas(pasta_cliente)
        
        # Unifica: diz que a palavra original agora mapeia para a tag pronta
        personas_ativas[original] = target_persona
        step4_menu.save_personas(pasta_cliente, personas_ativas)
        
        tag = f"[{target_persona}]"
        
        edits = load_edits()
        anon_map = edits.setdefault('anon_map', {})
        subs = anon_map.setdefault(msg_id, [])
        
        subs.append({
            "original": original,
            "tag": tag,
            "type": "manual"
        })
        
        if arquivo_midia and app.config.get('MODE') == 'anon':
            caminho_trans = os.path.join(app.config['CLIENT_FOLDER'], _cfg("pasta_transcricoes"))
            base = os.path.splitext(arquivo_midia)[0]
            caminho_txt = os.path.join(caminho_trans, base + ".txt")
            if os.path.exists(caminho_txt):
                with open(caminho_txt, "r", encoding="utf-8") as f:
                    texto_atual = f.read()
                if original in texto_atual:
                    texto_atual = texto_atual.replace(original, tag, 1)
                    with open(caminho_txt, "w", encoding="utf-8") as f:
                        f.write(texto_atual)
        else:
            texto_atual = edits.get('edited_texts', {}).get(msg_id)
            if not texto_atual:
                texto_atual = data.get('full_text', '')

            if original in texto_atual:
                texto_atual = texto_atual.replace(original, tag, 1)
                edits['edited_texts'][msg_id] = texto_atual

        edits['last_revised'] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        save_edits(edits)
        _rebuild_html_only()

        return jsonify({"success": True})

    @app.route('/api/remove_persona', methods=['POST'])
    def remove_persona():
        data = request.json
        original = data.get('original', '').strip()
        pasta_cliente = app.config['CLIENT_FOLDER']
        personas_ativas = step4_menu.load_personas(pasta_cliente)
        
        if original in personas_ativas:
            del personas_ativas[original]
            step4_menu.save_personas(pasta_cliente, personas_ativas)
            
        return jsonify({"success": True})

def start_server(pasta_cliente, modo="normal"):
    import webbrowser
    global app
    app = Flask(__name__, static_folder=pasta_cliente, static_url_path='')
    app.config['CLIENT_FOLDER'] = pasta_cliente
    app.config['MODE'] = modo
    setup_routes()
    
    modo_label = "ANONIMIZADA" if modo == "anon" else "ORIGINAL"
    
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
    print(f"🚀 EDITOR VISUAL INICIADO — Modo: {modo_label}")
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
        modo = sys.argv[2] if len(sys.argv) > 2 else "normal"
        start_server(sys.argv[1], modo=modo)
    else:
        print("Uso: python editor_server.py /caminho/pasta/cliente [normal|anon]")
