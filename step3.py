import os
import config
import utils
from whatsapp_parser import parse_chat_whatsapp

# ================= TRANSCRIÇÃO =================
def buscar_transcricao(pasta, arquivo):
    base = os.path.splitext(arquivo)[0]
    caminho = os.path.join(pasta, base + ".txt")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    return None

# ================= HTML =================
def gerar_html(mensagens, pasta_cliente):
    import json
    pasta_trans = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    saida = os.path.join(pasta_cliente, "conferencia_visual.html")
    
    caminho_edits = os.path.join(pasta_cliente, "conferencia_edits.json")
    edits = {"deleted_ids": [], "edited_texts": {}}
    if os.path.exists(caminho_edits):
        with open(caminho_edits, "r", encoding="utf-8") as f:
            edits = json.load(f)

    arquivos_midia = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(config.EXTENSOES_MIDIA_HTML)
    ]

    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Conferência Visual</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
    :root {
        --bg-color: #0f172a;
        --chat-bg: #1e293b;
        --text-main: #cbd5e1;
        --text-muted: #94a3b8;
        --accent: #10b981;
        --msg-esq-bg: #334155;
        --msg-dir-bg: #047857;
    }
    body {
        background-color: var(--bg-color);
        color: var(--text-main);
        font-family: 'Inter', sans-serif;
        line-height: 1.45;
        font-weight: 500;
        margin: 0;
        padding: 40px 20px;
    }
    .chat {
        max-width: 900px;
        margin: 0 auto;
        background: var(--chat-bg);
        border-radius: 16px;
        padding: 30px 40px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    h2 {
        text-align: center;
        font-weight: 600;
        color: #fff;
        font-size: 24px;
        border-bottom: 1px solid #334155;
        padding-bottom: 20px;
        margin-top: 0;
        margin-bottom: 30px;
    }
    .msg {
        padding: 16px 20px;
        margin: 20px 0;
        border-radius: 16px;
        max-width: 80%;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
    }
    .msg:hover {
        transform: translateY(-2px);
    }
    .esq {
        background: var(--msg-esq-bg);
        margin-right: auto;
        border-bottom-left-radius: 4px;
        border: 1px solid #475569;
    }
    .dir {
        background: var(--msg-dir-bg);
        margin-left: auto;
        border-bottom-right-radius: 4px;
        border: 1px solid #059669;
    }
    .apagada {
        background: transparent;
        border: 1px dashed #475569;
        margin: 10px auto;
        padding: 10px;
        opacity: 0.6;
        text-align: center;
        max-width: 50%;
    }
    .status-ok {
        border-left: 6px solid #10b981 !important;
    }
    .status-review {
        border-left: 6px solid #f59e0b !important;
        background-color: rgba(245, 158, 11, 0.05);
    }
    .status-anchor {
        border-left: 6px solid #8b5cf6 !important;
        background-color: rgba(139, 92, 246, 0.05);
    }
    .status-indicator {
        font-size: 14px;
        margin-left: 8px;
    }
    .meta-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .meta {
        font-size: 13px;
        color: var(--text-muted);
        font-weight: 600;
    }
    .id {
        font-size: 12px;
        color: var(--accent);
        opacity: 0.9;
        font-weight: 600;
        cursor: pointer;
        padding: 2px 6px;
        border-radius: 4px;
        transition: background 0.2s;
    }
    .id:hover {
        background: rgba(16, 185, 129, 0.2);
    }
    .media {
        background: rgba(0, 0, 0, 0.25);
        padding: 15px;
        margin-top: 12px;
        border-radius: 12px;
    }
    audio, video, img {
        width: 100%;
        margin-top: 5px;
        border-radius: 8px;
    }
    .transc {
        background: rgba(0, 0, 0, 0.4);
        padding: 15px 18px;
        margin-top: 15px;
        border-left: 4px solid var(--accent);
        border-radius: 0 8px 8px 0;
        font-size: 18px; 
        font-weight: 500;
        line-height: 1.5;
        color: #cbd5e1;
    }
    .transc b {
        color: var(--accent);
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 1px;
        display: block;
        margin-bottom: 8px;
        font-weight: 700;
    }
    .msg-content {
        font-size: 18px;
        font-weight: 500;
        line-height: 1.45;
        margin-top: 5px;
        word-wrap: break-word;
    }
    .speed-control {
        position: fixed;
        bottom: 30px;
        right: 30px;
        background: rgba(30, 41, 59, 0.85);
        backdrop-filter: blur(12px);
        padding: 12px 20px;
        border-radius: 30px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        display: flex;
        gap: 12px;
        align-items: center;
        border: 1px solid #475569;
        z-index: 1000;
    }
    .speed-control span {
        font-size: 14px;
        font-weight: 600;
        color: #cbd5e1;
        margin-right: 5px;
    }
    .speed-btn {
        background: #334155;
        color: #fff;
        border: none;
        padding: 8px 14px;
        border-radius: 20px;
        cursor: pointer;
        font-weight: 600;
        font-size: 14px;
        transition: all 0.2s ease;
    }
    .speed-btn:hover {
        background: var(--accent);
        transform: translateY(-2px);
    }
    .speed-btn.active {
        background: var(--accent);
        color: #fff;
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.4);
    }
    .context-menu {
        position: absolute;
        background: #1e293b;
        border: 1px solid #475569;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        z-index: 2000;
        display: flex;
        flex-direction: column;
        padding: 5px;
        min-width: 120px;
    }
    .context-menu button {
        background: transparent;
        color: #cbd5e1;
        border: none;
        padding: 10px 16px;
        text-align: left;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
    }
    .context-menu button:hover {
        background: #334155;
        border-radius: 4px;
    }
    .editor-textarea {
        width: 100%;
        min-height: 100px;
        background: #0f172a;
        color: #fff;
        border: 1px solid #10b981;
        padding: 10px;
        border-radius: 8px;
        margin-top: 10px;
        font-family: inherit;
        font-size: inherit;
        resize: vertical;
    }
    .editor-btn {
        background: #10b981;
        color: #fff;
        border: none;
        padding: 8px 16px;
        border-radius: 8px;
        margin-top: 10px;
        cursor: pointer;
        font-weight: 600;
    }
</style>
</head>
<body>
<div id="contextMenu" class="context-menu" style="display:none;">
    <button onclick="editarSelecionado()">✏️ Editar</button>
    <button onclick="apagarSelecionado()" style="color: #ef4444;">🗑️ Apagar</button>
</div>
"""

    total_validas = 0
    total_ok = 0
    total_anchors = 0
    for m in mensagens:
        msg_id_str = str(m["id"])
        msg_id_int = m["id"]
        if msg_id_int in edits.get("deleted_ids", []) or msg_id_str in edits.get("deleted_ids", []):
            continue
        total_validas += 1
        status = edits.get("status", {}).get(msg_id_str)
        if status in ["ok", "anchor"]:
            total_ok += 1
        if status == "anchor":
            total_anchors += 1

    html += f"""
<div class="speed-control">
    <div style="display: flex; flex-direction: column; gap: 8px;">
        <div style="display: flex; align-items: center; justify-content: center;">
            <span>Velocidade:</span>
            <button class="speed-btn active" onclick="setSpeed(1)">1x</button>
            <button class="speed-btn" onclick="setSpeed(1.5)">1.5x</button>
            <button class="speed-btn" onclick="setSpeed(2)">2x</button>
            <button class="speed-btn" onclick="setSpeed(2.5)">2.5x</button>
        </div>
        <div style="text-align: center; font-size: 13px; color: #94a3b8; font-weight: 600; border-top: 1px solid #475569; padding-top: 6px;">
            Mensagens conferidas: <span id="msg-ok-count" style="color: #10b981;">{total_ok}</span>/<span id="msg-total-count">{total_validas}</span>
        </div>
        <div style="text-align: center; font-size: 13px; color: #94a3b8; font-weight: 600; border-top: 1px solid #475569; padding-top: 6px; display: flex; align-items: center; justify-content: center; gap: 8px;">
            Navegar Âncoras (<span id="msg-anchor-count">{total_anchors}</span>):
            <button class="speed-btn" style="padding: 2px 8px; font-size: 14px;" onclick="navigateAnchor('prev')" title="Mensagem favorita anterior">↑</button>
            <button class="speed-btn" style="padding: 2px 8px; font-size: 14px;" onclick="navigateAnchor('next')" title="Próxima mensagem favorita">↓</button>
        </div>
    </div>
</div>
<div class="chat">
<h2>Conferência Visual da Conversa</h2>
"""

    for m in mensagens:
        msg_id_str = str(m["id"])
        msg_id_int = m["id"]
        
        if msg_id_int in edits.get("deleted_ids", []) or msg_id_str in edits.get("deleted_ids", []):
            html += f'<div class="msg apagada">'
            html += f'<div class="meta-container" style="justify-content: center; margin:0;"><div class="meta">[Mensagem #id:{m["id"]} Apagada]</div></div>'
            html += '</div>'
            continue
            
        if msg_id_str in edits.get("edited_texts", {}):
            m["conteudo"] = edits["edited_texts"][msg_id_str]

        lado = "dir" if any(x in m["autor"] for x in config.REMETENTES_DIREITA) else "esq"
        
        status_msg = edits.get("status", {}).get(msg_id_str, "none")
        class_status = ""
        icon_status = ""
        if status_msg == "ok":
            class_status = " status-ok"
            icon_status = " ✅"
        elif status_msg == "anchor":
            class_status = " status-anchor"
            icon_status = " ✅⭐"
        elif status_msg == "review":
            class_status = " status-review"
            icon_status = " ⚠️ Revisar"

        html += f'<div class="msg {lado}{class_status}" data-id="{m["id"]}" onclick="toggleMsgStatus(event, {m["id"]})" style="cursor: pointer;" title="Clique no balão para marcar como OK/Revisar">'
        
        conteudo = m["conteudo"]
        arquivo_encontrado = None

        for arq in arquivos_midia:
            if arq in conteudo:
                arquivo_encontrado = arq
                break
                
        tipo_edicao = 'transcricao' if arquivo_encontrado else 'texto'
        arq_midia_js = arquivo_encontrado if arquivo_encontrado else ''

        html += '<div class="meta-container">'
        html += f'<div class="meta">{m["data"]} {m["hora"]} — {m["autor"]}<span class="status-indicator" id="status-icon-{m["id"]}">{icon_status}</span></div>'
        html += f'<div class="id" onclick="showMenu(event, {m["id"]}, \'{arq_midia_js}\', \'{tipo_edicao}\')" title="Clique para editar/apagar">#id:{m["id"]} ⚙️</div>'
        html += '</div>'

        if arquivo_encontrado:
            trans = buscar_transcricao(pasta_trans, arquivo_encontrado)
            html += '<div class="media">'

            arq = arquivo_encontrado.lower()
            if arq.endswith((".opus", ".ogg", ".mp3", ".wav", ".m4a")):
                html += f'<audio controls src="{arquivo_encontrado}"></audio>'
            elif arq.endswith(".mp4"):
                html += f'<video controls src="{arquivo_encontrado}"></video>'
            elif arq.endswith((".jpg", ".jpeg", ".png", ".webp")):
                html += f'<img src="{arquivo_encontrado}">'

            if trans:
                trans_html = trans.replace('\\n', '<br>')
                html += f'<div class="transc"><b>Transcrição</b><span id="text-{m["id"]}">{trans_html}</span></div>'

            html += '</div>'
        else:
            conteudo_html = conteudo.replace('\\n', '<br>')
            html += f'<div class="msg-content" id="content-{m["id"]}">{conteudo_html}</div>'

        html += '</div>'

    last_opened = edits.get("last_opened", "Nunca")
    last_revised = edits.get("last_revised", "Nunca")

    html += f"""
<div style="text-align: center; margin: 40px 0; padding: 20px; background: rgba(30, 41, 59, 0.5); border-radius: 12px; border: 1px solid #475569;">
    <button onclick="markAllAsChecked()" style="background: #10b981; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">Marcar Tudo Como Conferido ✅</button>
    <div style="margin-top: 15px; color: #94a3b8; font-size: 14px;">
        Última abertura: {last_opened} &nbsp;|&nbsp; Última revisão: {last_revised}
    </div>
</div>
"""

    html += """
<script>
    let currentMsgId = null;
    let currentMidia = null;
    let currentTipo = null;

    function setSpeed(speed) {
        document.querySelectorAll('audio').forEach(audio => {
            audio.playbackRate = speed;
        });
        document.querySelectorAll('.speed-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.innerText === speed + 'x' || (speed === 1 && btn.innerText === '1x')) {
                btn.classList.add('active');
            }
        });
    }

    function toggleMsgStatus(e, id) {
        if (['AUDIO', 'VIDEO', 'BUTTON', 'TEXTAREA', 'IMG', 'A'].includes(e.target.tagName)) return;
        if (e.target.closest('.id') || e.target.closest('.context-menu')) return;
        
        const msgDiv = e.currentTarget;
        const iconSpan = document.getElementById('status-icon-' + id);
        
        let currentStatus = 'none';
        if (msgDiv.classList.contains('status-ok')) currentStatus = 'ok';
        else if (msgDiv.classList.contains('status-anchor')) currentStatus = 'anchor';
        else if (msgDiv.classList.contains('status-review')) currentStatus = 'review';
        
        const countSpan = document.getElementById('msg-ok-count');
        const anchorSpan = document.getElementById('msg-anchor-count');
        let count = parseInt(countSpan.innerText);
        let anchorCount = parseInt(anchorSpan.innerText);
        
        let newStatus = 'none';
        if (currentStatus === 'none') {
            newStatus = 'ok';
            msgDiv.classList.remove('status-review', 'status-anchor');
            msgDiv.classList.add('status-ok');
            iconSpan.innerText = ' ✅';
            count++;
        } else if (currentStatus === 'ok') {
            newStatus = 'anchor';
            msgDiv.classList.remove('status-ok');
            msgDiv.classList.add('status-anchor');
            iconSpan.innerText = ' ✅⭐';
            anchorCount++;
        } else if (currentStatus === 'anchor') {
            newStatus = 'review';
            msgDiv.classList.remove('status-anchor');
            msgDiv.classList.add('status-review');
            iconSpan.innerText = ' ⚠️ Revisar';
            count--;
            anchorCount--;
        } else {
            newStatus = 'none';
            msgDiv.classList.remove('status-ok', 'status-review', 'status-anchor');
            iconSpan.innerText = '';
        }
        
        countSpan.innerText = count;
        anchorSpan.innerText = anchorCount;
        
        fetch(getApiUrl() + '/api/toggle_status', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: id, status: newStatus})
        }).catch(e => console.error('Erro ao salvar status', e));
    }

    function showMenu(e, id, midia, tipo) {
        e.preventDefault();
        currentMsgId = id;
        currentMidia = midia;
        currentTipo = tipo;
        
        const menu = document.getElementById('contextMenu');
        menu.style.display = 'flex';
        menu.style.left = e.pageX + 'px';
        menu.style.top = e.pageY + 'px';
    }

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.context-menu') && !e.target.closest('.id')) {
            document.getElementById('contextMenu').style.display = 'none';
        }
    });

    function getApiUrl() {
        if (window.location.protocol === 'http:') {
            return window.location.origin;
        }
        return 'http://127.0.0.1:5000';
    }

    function apagarSelecionado() {
        if(!confirm('Tem certeza que deseja apagar esta mensagem (e sua mídia, se houver)?\\n\\nIsso removerá a mensagem do histórico final.')) return;
        
        fetch(getApiUrl() + '/api/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: currentMsgId, arquivo_midia: currentMidia})
        }).then(res => res.json()).then(data => {
            if(data.success) location.reload();
            else alert('Erro ao apagar. Verifique se o Servidor de Edição está rodando em outro terminal.');
        }).catch(e => alert('Erro de conexão. Você iniciou o Servidor de Edição via main.py?'));
    }

    function editarSelecionado() {
        document.getElementById('contextMenu').style.display = 'none';
        const containerId = currentTipo === 'transcricao' ? 'text-' + currentMsgId : 'content-' + currentMsgId;
        const container = document.getElementById(containerId);
        if(!container) return;
        
        let originalText = container.innerHTML.replace(/<br\\s*[\\/]?>/gi, '\\n');
        
        const textarea = document.createElement('textarea');
        textarea.className = 'editor-textarea';
        textarea.value = originalText;
        
        const btn = document.createElement('button');
        btn.className = 'editor-btn';
        btn.innerText = '💾 Salvar Alterações';
        
        btn.onclick = function() {
            const url = currentTipo === 'transcricao' ? '/api/edit_transcription' : '/api/edit_text';
            const payload = currentTipo === 'transcricao' 
                ? { arquivo_midia: currentMidia, novo_texto: textarea.value }
                : { id: currentMsgId, novo_texto: textarea.value };
                
            fetch(getApiUrl() + url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            }).then(res => res.json()).then(data => {
                if(data.success) location.reload();
                else alert('Erro ao salvar. Verifique se o Servidor de Edição está rodando.');
            }).catch(e => alert('Erro de conexão. Você iniciou o Servidor de Edição via main.py?'));
        };
        
        container.innerHTML = '';
        container.appendChild(textarea);
        container.appendChild(btn);
    }
    
    function navigateAnchor(direction) {
        const anchors = Array.from(document.querySelectorAll('.status-anchor'));
        if (anchors.length === 0) {
            alert('Nenhuma mensagem favoritada (âncora) encontrada.');
            return;
        }
        
        let target = null;
        const threshold = window.innerHeight / 2;
        
        if (direction === 'next') {
            target = anchors.find(el => el.getBoundingClientRect().top > threshold + 50);
            if (!target) target = anchors[0]; // Dá a volta para o começo
        } else {
            const reversed = [...anchors].reverse();
            target = reversed.find(el => el.getBoundingClientRect().top < threshold - 50);
            if (!target) target = anchors[0]; // Se não houver nada pra cima, vai para a primeira
        }
        
        if (target) {
            target.scrollIntoView({behavior: 'smooth', block: 'center'});
            target.style.transition = 'box-shadow 0.3s ease';
            target.style.boxShadow = '0 0 15px 5px rgba(139, 92, 246, 0.5)';
            setTimeout(() => { target.style.boxShadow = 'none'; }, 1500);
        }
    }
    
    function markAllAsChecked() {
        if (!confirm("Tem certeza que deseja marcar TODAS as mensagens pendentes como Conferidas (OK)?")) return;
        
        // Coleta todos os IDs que ainda não estão conferidos nem são âncoras
        const msgs = document.querySelectorAll('.msg:not(.apagada):not(.status-ok):not(.status-anchor)');
        const ids = Array.from(msgs).map(el => parseInt(el.getAttribute('data-id')));
        
        if (ids.length === 0) {
            alert('Todas as mensagens já estão conferidas!');
            return;
        }
        
        fetch(getApiUrl() + '/api/mark_all_ok', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ids: ids})
        }).then(res => res.json()).then(data => {
            if(data.success) location.reload();
        }).catch(e => alert('Erro. Servidor não está rodando.'));
    }
    
    // Registra abertura do arquivo
    window.addEventListener('DOMContentLoaded', () => {
        fetch(getApiUrl() + '/api/track_open', { method: 'POST' }).catch(e => {});
    });
</script>
</div></body></html>"""

    with open(saida, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\\n✔ Conferência criada com sucesso: {saida}")

# ================= MAIN =================
def run(pasta_cliente=None, auto=False):
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()
    
    chat = utils.escolher_chat_txt(pasta_cliente, auto=auto)
    msgs = parse_chat_whatsapp(chat)
    gerar_html(msgs, pasta_cliente)

if __name__ == "__main__":
    run()
