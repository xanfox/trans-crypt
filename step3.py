import html as html_module
import json
import os
import re
import subprocess
import config
import utils
from whatsapp_parser import parse_chat_whatsapp

def _get_audio_duration_sec(filepath):
    """Retorna duração em segundos de um arquivo de áudio usando ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def _fmt_duracao(sec):
    """Formata segundos como Xh YYmin ZZs."""
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m:02d}min"
    elif m > 0:
        return f"{m}min {s:02d}s"
    else:
        return f"{s}s"

# ================= MODO REVISÃO ANONIMIZAÇÃO =================
# Mapeia cada tag de anonimização para sua classe CSS correspondente.
_TAG_CSS_MAP = {
    "[NOME]": "tag-nome",
    "[LOCAL]": "tag-local",
    "[DATA NASCIMENTO]": "tag-data",
    "[DATA]": "tag-data",
    "[DADO CLÍNICO]": "tag-clinico",
}

def _render_anon_tags(html_text, anon_map, msg_id_str, arq_midia=''):
    """Substitui tags de anonimização em texto HTML por spans interativos.
    
    Cada tag renderizada:
    - Mostra tooltip com texto original ao hover
    - Clique 1: reverte ao texto original (chama API /api/revert_tag)
    - Clique no texto revertido: popup para re-taggear com outra categoria
    
    Usa abordagem de 2 passes com placeholders para evitar que a substituição
    de uma tag sobrescreva o HTML já injetado de uma tag anterior.
    """
    msg_subs = anon_map.get(msg_id_str, [])
    if not msg_subs:
        return html_text
    
    # Passo 1: Substitui cada tag por um placeholder único
    placeholders = {}
    for i, sub in enumerate(msg_subs):
        tag = sub["tag"]
        original = html_module.escape(sub["original"])
        
        css_class = "tag-nome"
        if "LOCAL" in tag:
            css_class = "tag-local"
        elif "DATA" in tag:
            css_class = "tag-data"
        elif "TRAIT" in tag:
            css_class = "tag-clinico"
        
        placeholder = f"\x00ANON_{i}\x00"
        span = (f'<span class="anon-tag {css_class}" '
                f'title="← {original}" '
                f'data-msg-id="{msg_id_str}" '
                f'data-sub-index="{i}" '
                f'data-original="{original}" '
                f'data-tag="{html_module.escape(tag)}" '
                f'data-midia="{arq_midia}" '
                f'onclick="onAnonTagClick(this)">'
                f'{html_module.escape(tag)}'
                f'<span class="anon-original">← {original}</span>'
                f'</span>')
        placeholders[placeholder] = span
        
        escaped_tag = html_module.escape(tag)
        html_text = html_text.replace(escaped_tag, placeholder, 1)
    
    # Passo 2: Substitui placeholders pelos spans HTML finais
    for placeholder, span in placeholders.items():
        html_text = html_text.replace(placeholder, span)
    
    return html_text

# ================= HTML =================
def gerar_html(mensagens, pasta_cliente, nome_saida="conferencia_visual.html", 
               arquivo_edits="conferencia_edits.json", pasta_transcricoes=config.PASTA_TRANSCRICOES):
    pasta_trans = os.path.join(pasta_cliente, pasta_transcricoes)
    saida = os.path.join(pasta_cliente, nome_saida)
    
    caminho_edits = os.path.join(pasta_cliente, arquivo_edits)
    edits = {"deleted_ids": [], "edited_texts": {}}
    if os.path.exists(caminho_edits):
        try:
            with open(caminho_edits, "r", encoding="utf-8") as f:
                edits = json.load(f)
        except Exception as e:
            print(f"\\n⚠️ AVISO: {caminho_edits} corrompido ({e}).")
            print("Gerando interface visual sem o estado anterior salvo para evitar queda.")

    # Normaliza deleted_ids para sempre trabalhar com int, independente de como foram salvos.
    deleted_ids = {int(x) for x in edits.get("deleted_ids", [])}

    # Detecta modo de revisão de anonimização pelo nome do arquivo de edições
    # (não pelo conteúdo de anon_map, que pode ficar vazio após todas as tags serem revertidas)
    anon_map = edits.get("anon_map", {})
    is_anon_mode = "anonimizada" in arquivo_edits

    arquivos_midia = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(config.EXTENSOES_MIDIA_HTML)
    ]

    # ── Calcula estatísticas do documento (com cache para evitar ffprobe em cada toggle) ──
    nome_cliente = utils.formatar_nome_display(pasta_cliente)
    stats_cache = edits.get('_stats', {})
    if stats_cache and 'total_palavras' in stats_cache:
        total_palavras = stats_cache['total_palavras']
        duracao_audios_sec = stats_cache['duracao_audios_sec']
    else:
        total_palavras = 0
        duracao_audios_sec = 0.0
        _midia_set = set(arquivos_midia)
        for m in mensagens:
            if m['id'] in deleted_ids:
                continue
            conteudo = m['conteudo']
            mid_str = str(m['id'])
            if mid_str in edits.get('edited_texts', {}):
                conteudo = edits['edited_texts'][mid_str]
            arq_encontrado = next((a for a in _midia_set if a in conteudo), None)
            if arq_encontrado:
                trans = utils.buscar_transcricao(pasta_trans, arq_encontrado)
                if trans:
                    total_palavras += len(trans.split())
                if arq_encontrado.lower().endswith(config.EXTENSOES_AUDIO):
                    fp = os.path.join(pasta_cliente, arq_encontrado)
                    if os.path.exists(fp):
                        duracao_audios_sec += _get_audio_duration_sec(fp)
            else:
                total_palavras += len(conteudo.split())
        # Persiste cache para evitar recálculo em regenerações automáticas de forma atômica
        edits['_stats'] = {'total_palavras': total_palavras, 'duracao_audios_sec': duracao_audios_sec}
        import uuid as _uuid
        tmp_path = caminho_edits + f".{_uuid.uuid4().hex}.tmp"
        with open(tmp_path, 'w', encoding='utf-8') as _f:
            json.dump(edits, _f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, caminho_edits)
        
    total_palavras_fmt = f'{total_palavras:,}'.replace(',', '.')  # Separador PT-BR: 1.234
    tempo_leitura_min = max(1, round(total_palavras / 200))
    duracao_audios_fmt = _fmt_duracao(duracao_audios_sec)
    duracao_audios_min = duracao_audios_sec / 60
    tempo_total_min = max(1, round(tempo_leitura_min + duracao_audios_min))

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
        cursor: pointer;
        transition: opacity 0.2s;
    }
    .meta:hover {
        opacity: 0.7;
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
    /* ── Tags de anonimização (modo revisão) ── */
    .anon-tag {
        padding: 1px 6px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 13px;
        cursor: pointer;
        position: relative;
        transition: all 0.25s ease;
        user-select: none;
    }
    .anon-tag:hover {
        filter: brightness(1.3);
    }
    .anon-tag .anon-original {
        display: none;
        position: absolute;
        bottom: 120%;
        left: 50%;
        transform: translateX(-50%);
        background: #0f172a;
        color: #f1f5f9;
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid #475569;
        font-size: 13px;
        font-weight: 500;
        white-space: nowrap;
        z-index: 100;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        pointer-events: none;
    }
    .anon-tag .anon-original::after {
        content: '';
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: #475569;
    }
    .anon-tag:hover .anon-original {
        display: block;
    }
    .tag-nome {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
    }
    .tag-local {
        background: rgba(59, 130, 246, 0.2);
        color: #60a5fa;
    }
    .tag-data {
        background: rgba(168, 85, 247, 0.2);
        color: #c084fc;
    }
    .tag-clinico {
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
    }
    .anon-legend {
        display: flex;
        justify-content: center;
        gap: 12px;
        flex-wrap: wrap;
        margin-top: 12px;
        padding-top: 10px;
        border-top: 1px solid #334155;
    }
    .anon-legend span {
        padding: 3px 10px;
        border-radius: 10px;
        font-size: 12px;
        font-weight: 600;
    }
    /* ── Tag revertida (texto original exposto) ── */
    .anon-reverted {
        padding: 1px 6px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 13px;
        cursor: pointer;
        position: relative;
        border: 2px dashed #94a3b8;
        background: rgba(148, 163, 184, 0.1);
        color: #e2e8f0;
        transition: all 0.25s ease;
        user-select: none;
    }
    .anon-reverted:hover {
        border-color: #60a5fa;
        background: rgba(96, 165, 250, 0.1);
    }
    /* ── Popup de re-tag ── */
    #retagPopup {
        display: none;
        position: fixed;
        z-index: 9999;
        background: #1e293b;
        border: 1px solid #475569;
        border-radius: 12px;
        padding: 10px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.6);
        gap: 10px;
        flex-direction: column;
    }
    #retagPopup.show {
        display: flex;
    }
    .retag-option {
        padding: 8px 16px;
        border: none;
        border-radius: 8px;
        font-weight: 700;
        font-size: 13px;
        cursor: pointer;
        transition: filter 0.2s, transform 0.15s;
        text-align: left;
    }
    .retag-option:hover {
        filter: brightness(1.4);
        transform: scale(1.04);
    }
    .retag-opt-nome { background: rgba(239,68,68,0.25); color: #f87171; }
    .retag-opt-local { background: rgba(59,130,246,0.25); color: #60a5fa; }
    .retag-opt-data { background: rgba(168,85,247,0.25); color: #c084fc; }
    .retag-opt-clinico { background: rgba(245,158,11,0.25); color: #fbbf24; }
    .retag-cancel { background: rgba(148,163,184,0.15); color: #94a3b8; }
    /* ── Popup de seleção de texto manual ── */
    #textSelectMenu {
        display: none;
        position: absolute;
        z-index: 9999;
        background: #1e293b;
        border: 1px solid #475569;
        border-radius: 12px;
        padding: 8px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.6);
        gap: 6px;
        flex-direction: row;
    }
    #textSelectMenu.show {
        display: flex;
    }
    #textSelectMenu .retag-option {
        padding: 6px 12px;
        font-size: 12px;
    }
    .menu-item {
        position: relative;
        display: inline-block;
    }
    .submenu {
        display: none;
        position: absolute;
        background: #1e293b;
        border: 1px solid #475569;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        flex-direction: column;
        min-width: 160px;
        z-index: 10000;
        padding: 4px;
        gap: 4px;
        white-space: nowrap;
    }
    /* Submenus do painel de seleção de texto (horizontal) abrem para baixo */
    #textSelectMenu .submenu {
        top: 100%;
        left: 0;
    }
    /* Submenus do painel de retag (vertical) abrem para a direita */
    #retagPopup .submenu {
        top: 0;
        left: 100%;
    }
    .menu-item:hover > .submenu {
        display: flex;
    }
</style>
</head>
<body>
<div id="contextMenu" class="context-menu" style="display:none;">
    <button onclick="editarSelecionado()">✏️ Editar</button>
    <button onclick="apagarSelecionado()" style="color: #ef4444;">🗑️ Apagar</button>
</div>
<div id="retagPopup">
    <div class="menu-item">
        <button class="retag-option retag-opt-nome" style="width:100%;">[PERSONA] ▼</button>
        <div class="submenu" id="retag-persona-submenu"></div>
    </div>
    <div class="menu-item" id="retag-unify-wrapper" style="display:none;">
        <button class="retag-option retag-opt-nome" style="width:100%;">[UNIFICAR] ▼</button>
        <div class="submenu" id="retag-unify-submenu"></div>
    </div>
    <button class="retag-option retag-opt-local" onclick="applyRetag('[LOCAL]')">[LOCAL]</button>
    <div class="menu-item">
        <button class="retag-option retag-opt-data" style="width:100%;">[DATA / IDADE] ▼</button>
        <div class="submenu">
            <button class="retag-option retag-opt-data" onclick="applyRetag('[DATA]')">[DATA COMUM]</button>
            <button class="retag-option retag-opt-data" onclick="applyRetag('[DATA NASCIMENTO]')">[DATA NASCIMENTO]</button>
        </div>
    </div>
    <div class="menu-item">
        <button class="retag-option retag-opt-clinico" style="width:100%;">[TRAIT] ▼</button>
        <div class="submenu" id="retag-trait-submenu">
        </div>
    </div>
    <button class="retag-option" onclick="removeTagCompletely()" style="background: rgba(239,68,68,0.15); color: #ef4444;">🗑️ Remover Tag</button>
    <button class="retag-option retag-cancel" onclick="closeRetagPopup()">✕ Cancelar</button>
</div>
<div id="textSelectMenu">
    <div class="menu-item">
        <button class="retag-option retag-opt-nome">PERSONA ▼</button>
        <div class="submenu" id="text-persona-submenu"></div>
    </div>
    <div class="menu-item" id="text-unify-wrapper" style="display:none;">
        <button class="retag-option retag-opt-nome">UNIFICAR ▼</button>
        <div class="submenu" id="text-unify-submenu"></div>
    </div>
    <button class="retag-option retag-opt-local" onclick="applyManualTag('[LOCAL]')">LOCAL</button>
    <div class="menu-item">
        <button class="retag-option retag-opt-data">DATA/IDADE ▼</button>
        <div class="submenu">
            <button class="retag-option retag-opt-data" onclick="applyManualTag('[DATA]')">DATA COMUM</button>
            <button class="retag-option retag-opt-data" onclick="applyManualTag('[DATA NASCIMENTO]')">DATA NASCIMENTO</button>
        </div>
    </div>
    <div class="menu-item">
        <button class="retag-option retag-opt-clinico">TRAIT ▼</button>
        <div class="submenu" id="text-trait-submenu">
        </div>
    </div>
</div>
"""

    total_validas = 0
    total_ok = 0
    total_anchors = 0
    total_review = 0
    for m in mensagens:
        msg_id_str = str(m["id"])
        if m["id"] in deleted_ids:
            continue
        total_validas += 1
        status = edits.get("status", {}).get(msg_id_str)
        if status in ["ok", "anchor"]:
            total_ok += 1
        if status == "anchor":
            total_anchors += 1
        if status == "review":
            total_review += 1

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
        <div style="text-align: center; font-size: 13px; color: #a78bfa; font-weight: 600; border-top: 1px solid #475569; padding-top: 6px; display: flex; align-items: center; justify-content: center; gap: 8px;">
            ⭐ MSG Importantes <span id="anchor-nav-counter" style="background: rgba(139,92,246,0.15); padding: 1px 7px; border-radius: 10px;">0/<span id="msg-anchor-count">{total_anchors}</span></span>:
            <button class="speed-btn" style="padding: 2px 8px; font-size: 14px; border: 1px solid #a78bfa;" onclick="navigateAnchor('prev')" title="Mensagem importante anterior">↑</button>
            <button class="speed-btn" style="padding: 2px 8px; font-size: 14px; border: 1px solid #a78bfa;" onclick="navigateAnchor('next')" title="Próxima mensagem importante">↓</button>
        </div>
        <div style="text-align: center; font-size: 13px; color: #f59e0b; font-weight: 600; border-top: 1px solid #475569; padding-top: 6px; display: flex; align-items: center; justify-content: center; gap: 8px;">
            ⚠️ Revisar <span id="review-nav-counter" style="background: rgba(245,158,11,0.15); padding: 1px 7px; border-radius: 10px;">0/<span id="msg-review-count">{total_review}</span></span>:
            <button class="speed-btn" style="padding: 2px 8px; font-size: 14px; border: 1px solid #f59e0b;" onclick="navigateReview('prev')" title="Revisão anterior">↑</button>
            <button class="speed-btn" style="padding: 2px 8px; font-size: 14px; border: 1px solid #f59e0b;" onclick="navigateReview('next')" title="Próxima revisão">↓</button>
        </div>
    </div>
</div>
<div class="chat">
<div style="text-align: center; border-bottom: 1px solid #334155; padding-bottom: 20px; margin-bottom: 24px;">
    <h2 style="margin: 0 0 14px 0; font-size: 22px; color: #fff;">📋 Conferência{' [ANONIMIZADA]' if is_anon_mode else ''}: {nome_cliente}</h2>
    <div style="display: flex; justify-content: center; gap: 14px; flex-wrap: wrap;">
        <span style="background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.3); padding: 5px 14px; border-radius: 20px; font-size: 13px; color: #10b981; font-weight: 600;">📝 {total_palavras_fmt} palavras</span>
        <span style="background: rgba(99,102,241,0.12); border: 1px solid rgba(99,102,241,0.3); padding: 5px 14px; border-radius: 20px; font-size: 13px; color: #818cf8; font-weight: 600;">📖 ~{tempo_leitura_min} min leitura</span>
        <span style="background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); padding: 5px 14px; border-radius: 20px; font-size: 13px; color: #fbbf24; font-weight: 600;">🎵 {duracao_audios_fmt} em áudios</span>
        <span style="background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3); padding: 5px 14px; border-radius: 20px; font-size: 13px; color: #f87171; font-weight: 600;">⏱️ ~{tempo_total_min} min de revisão</span>
    </div>
</div>
"""

    if is_anon_mode:
        html += """
    <div class="anon-legend">
        <span class="anon-tag tag-nome">[PERSONA]</span>
        <span class="anon-tag tag-local">[LOCAL]</span>
        <span class="anon-tag tag-data">[DATA]</span>
        <span class="anon-tag tag-clinico">[TRAIT]</span>
        <span style="font-size: 12px; color: #94a3b8; align-self: center;">← passe o mouse para ver o original</span>
    </div>
"""

    for m in mensagens:
        msg_id_str = str(m["id"])

        if m["id"] in deleted_ids:
            html += f'<div class="msg apagada">'
            html += f'<div class="meta-container" style="justify-content: center; margin:0;"><div class="meta">[Mensagem #id:{m["id"]} Apagada]</div></div>'
            html += '</div>'
            continue

        if msg_id_str in edits.get("edited_texts", {}):
            m = dict(m)  # Cópia rasa para não mutar a lista original
            m["conteudo"] = edits["edited_texts"][msg_id_str]

        autor_seguro = html_module.escape(m["autor"])
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

        html += f'<div class="msg {lado}{class_status}" data-id="{m["id"]}">'
        
        conteudo = m["conteudo"]
        arquivo_encontrado = None

        for arq in arquivos_midia:
            if arq in conteudo:
                arquivo_encontrado = arq
                break
                
        tipo_edicao = 'transcricao' if arquivo_encontrado else 'texto'
        # Escapa aspas simples no nome do arquivo para não quebrar o atributo onclick JS
        arq_midia_js = arquivo_encontrado.replace("'", "\\'") if arquivo_encontrado else ''

        html += '<div class="meta-container">'
        html += f'<div class="meta" onclick="toggleMsgStatus(event, {m["id"]})" title="Clique no cabeçalho para marcar como OK/Revisar/Ancora">{m["data"]} {m["hora"]} — {autor_seguro}<span class="status-indicator" id="status-icon-{m["id"]}">{icon_status}</span></div>'
        html += f'<div class="id" onclick="showMenu(event, {m["id"]}, \'{arq_midia_js}\', \'{tipo_edicao}\')" title="Clique para editar/apagar">#id:{m["id"]} ⚙️</div>'
        html += '</div>'

        if arquivo_encontrado:
            trans = utils.buscar_transcricao(pasta_trans, arquivo_encontrado)
            html += '<div class="media">'

            arq = arquivo_encontrado.lower()
            if arq.endswith((".opus", ".ogg", ".mp3", ".wav", ".m4a")):
                html += f'<audio controls src="{arquivo_encontrado}"></audio>'
            elif arq.endswith(".mp4"):
                html += f'<video controls src="{arquivo_encontrado}"></video>'
            elif arq.endswith((".jpg", ".jpeg", ".png", ".webp")):
                html += f'<img src="{arquivo_encontrado}">'

            if trans:
                # Usa '\n' (newline real) e escapa o conteúdo antes de inserir no HTML
                trans_html = html_module.escape(trans).replace('\n', '<br>')
                if is_anon_mode:
                    trans_html = _render_anon_tags(trans_html, anon_map, msg_id_str, arq_midia_js)
                html += f'<div class="transc"><b>Transcrição</b><span id="text-{m["id"]}">{trans_html}</span></div>'

            html += '</div>'
        else:
            conteudo_html = html_module.escape(conteudo).replace('\n', '<br>')
            if is_anon_mode:
                conteudo_html = _render_anon_tags(conteudo_html, anon_map, msg_id_str, "")
            html += f'<div class="msg-content" id="content-{m["id"]}">{conteudo_html}</div>'

        html += '</div>'

    last_opened = edits.get("last_opened", "Nunca")
    last_revised = edits.get("last_revised", "Nunca")

    html += f"""
<div style="text-align: center; margin: 40px 0; padding: 20px; background: rgba(30, 41, 59, 0.5); border-radius: 12px; border: 1px solid #475569; display: flex; flex-direction: column; align-items: center; gap: 14px;">
    <div style="display: flex; gap: 16px; flex-wrap: wrap; justify-content: center;">
        <button onclick="markAllAsChecked()" style="background: #10b981; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">Marcar Pendentes Como Conferido ✅</button>
        <button onclick="resetAllStatus()" style="background: #334155; color: #f87171; border: 1px solid #f87171; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">🔄 Zerar Todos os Status</button>
    </div>
    <div style="color: #94a3b8; font-size: 14px;">
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
        
        // O handler está no .meta, mas o estado de status está no .msg pai
        const msgDiv = e.currentTarget.closest('.msg');
        if (!msgDiv) return;
        const iconSpan = document.getElementById('status-icon-' + id);
        
        let currentStatus = 'none';
        if (msgDiv.classList.contains('status-ok')) currentStatus = 'ok';
        else if (msgDiv.classList.contains('status-anchor')) currentStatus = 'anchor';
        else if (msgDiv.classList.contains('status-review')) currentStatus = 'review';
        
        const countSpan = document.getElementById('msg-ok-count');
        const anchorSpan = document.getElementById('msg-anchor-count');
        const reviewCountSpan = document.getElementById('msg-review-count');
        let count = parseInt(countSpan.innerText);
        let anchorCount = parseInt(anchorSpan.innerText);
        let reviewCount = reviewCountSpan ? parseInt(reviewCountSpan.innerText) : 0;
        
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
            count = Math.max(0, count - 1);
            anchorCount = Math.max(0, anchorCount - 1);
            reviewCount++;
            _reviewIndex = -1;
        } else {
            newStatus = 'none';
            msgDiv.classList.remove('status-ok', 'status-review', 'status-anchor');
            iconSpan.innerText = '';
            reviewCount = Math.max(0, reviewCount - 1);
            _reviewIndex = -1;
        }
        
        countSpan.innerText = count;
        anchorSpan.innerText = anchorCount;
        if (reviewCountSpan) {
            reviewCountSpan.innerText = reviewCount;
            const reviewWrap = document.getElementById('review-nav-counter');
            if (reviewWrap) reviewWrap.innerHTML = '0/<span id="msg-review-count">' + reviewCount + '</span>';
        }
        // Atualiza painel de âncoras em tempo real
        const anchorWrap = document.getElementById('anchor-nav-counter');
        const anchorTotal = document.getElementById('msg-anchor-count');
        if (anchorWrap && anchorTotal) {
            anchorWrap.innerHTML = '0/<span id="msg-anchor-count">' + anchorCount + '</span>';
            _anchorIndex = -1;
        }
        
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
        // Sempre usa a origem da janela atual (porta correta, mesmo que Flask suba em 5001, 5002, etc.)
        return window.location.origin;
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
        
        // Captura apenas o texto visível (innerText evita capturar HTML de spans de anonimização)
        let originalText = container.innerText;
        
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
    
    let _anchorIndex = -1;
    function navigateAnchor(direction) {
        const anchors = Array.from(document.querySelectorAll('.status-anchor'));
        const total = anchors.length;
        if (total === 0) {
            alert('Nenhuma mensagem importante (âncora) encontrada.');
            return;
        }

        if (direction === 'next') {
            _anchorIndex = (_anchorIndex + 1) % total;
        } else {
            _anchorIndex = (_anchorIndex - 1 + total) % total;
        }

        const target = anchors[_anchorIndex];
        target.scrollIntoView({behavior: 'smooth', block: 'center'});
        target.style.transition = 'box-shadow 0.3s ease';
        target.style.boxShadow = '0 0 15px 5px rgba(139, 92, 246, 0.6)';
        setTimeout(() => { target.style.boxShadow = 'none'; }, 1500);

        // Atualiza contador X/N
        const counterWrap = document.getElementById('anchor-nav-counter');
        const totalSpan = document.getElementById('msg-anchor-count');
        if (counterWrap && totalSpan) {
            counterWrap.innerHTML = (_anchorIndex + 1) + '/<span id="msg-anchor-count">' + total + '</span>';
        }
    }

    let _reviewIndex = -1;
    function navigateReview(direction) {
        const reviews = Array.from(document.querySelectorAll('.status-review'));
        const total = reviews.length;
        if (total === 0) {
            alert('Nenhuma mensagem marcada para revisão.');
            return;
        }

        if (direction === 'next') {
            _reviewIndex = (_reviewIndex + 1) % total;
        } else {
            _reviewIndex = (_reviewIndex - 1 + total) % total;
        }

        const target = reviews[_reviewIndex];
        target.scrollIntoView({behavior: 'smooth', block: 'center'});
        target.style.transition = 'box-shadow 0.3s ease';
        target.style.boxShadow = '0 0 15px 5px rgba(245, 158, 11, 0.6)';
        setTimeout(() => { target.style.boxShadow = 'none'; }, 1500);

        // Atualiza contador X/N
        const counterSpan = document.getElementById('review-nav-counter');
        const totalSpan = document.getElementById('msg-review-count');
        if (counterSpan && totalSpan) {
            counterSpan.innerHTML = `${_reviewIndex + 1}/<span id="msg-review-count">${total}</span>`;
        }
    }
    
    function resetAllStatus() {
        if (!confirm("Isso vai apagar TODOS os status (OK, Ancoras e Revisar) de todas as mensagens. Tem certeza?")) return;
        if (!confirm("Segunda confirmacao: todos os status serao perdidos e a conferencia voltara ao zero. Continuar?")) return;

        fetch(getApiUrl() + '/api/reset_all_status', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({})
        }).then(function(res) {
            if (!res.ok) { alert('Erro: reinicie o Servidor de Edicao (CTRL+C e rode novamente).'); return; }
            return res.json();
        }).then(function(data) {
            if (data && data.success) location.reload();
        }).catch(function(e) { alert('Erro de conexao. O Servidor de Edicao esta rodando?'); });
    }
    
    function markAllAsChecked() {
        if (!confirm("Tem certeza que deseja marcar TODAS as mensagens pendentes como Conferidas (OK)?")) return;
        
        // Coleta apenas IDs sem nenhum status atribuído (não ok, não âncora, não revisar)
        const msgs = document.querySelectorAll('.msg:not(.apagada):not(.status-ok):not(.status-anchor):not(.status-review)');
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
        loadPersonas();
    });

    // ================= PERSONAS DINÂMICAS =================
    function loadPersonas() {
        fetch(getApiUrl() + '/api/get_personas').then(r => r.json()).then(data => {
            const tree = data.tree;
            const ativas = data.ativas;
            
            // Build Personas tree HTML
            let treeHtml = '';
            for (let grupo in tree) {
                treeHtml += `
                <div class="menu-item" style="width:100%; display:block;">
                    <div style="display:flex;">
                        <button class="retag-option retag-opt-nome" style="flex-grow:1; border-radius:0; background:rgba(239,68,68,0.1); text-align:left;">${grupo} ►</button>
                        <button class="retag-option" style="background:rgba(239,68,68,0.2); padding: 0 8px; color: #f87171;" onclick="removeCategoria(event, null, '${grupo}')" title="Remover Categoria">-</button>
                    </div>
                    <div class="submenu" style="left:100%; top:0; min-width: 140px;">
                `;
                for (let p of tree[grupo]) {
                    treeHtml += `
                    <div style="display:flex;">
                        <button class="retag-option retag-opt-nome" style="flex-grow:1; border-radius:0;" onclick="applyPersona('${p}')">${p}</button>
                        <button class="retag-option" style="background:rgba(239,68,68,0.2); padding: 0 8px; color: #f87171;" onclick="removeCategoria(event, '${grupo}', '${p}')" title="Remover Persona">-</button>
                    </div>`;
                }
                treeHtml += `
                        <button class="retag-option" style="border-radius:0; background:rgba(255,255,255,0.1); color:#fff;" onclick="addPersona('${grupo}')">+ Nova Persona</button>
                    </div>
                </div>`;
            }
            treeHtml += `<button class="retag-option" style="background:rgba(255,255,255,0.1); color:#fff;" onclick="addCategoria()">+ Nova Categoria</button>`;
            
            document.getElementById('retag-persona-submenu').innerHTML = treeHtml;
            document.getElementById('text-persona-submenu').innerHTML = treeHtml.replace(/applyPersona/g, 'applyManualPersona');

            // Build Traits tree HTML
            const treeTraits = data.tree_traits;
            let traitsHtml = '';
            for (let grupo in treeTraits) {
                traitsHtml += `
                <div class="menu-item" style="width:100%; display:block;">
                    <div style="display:flex;">
                        <button class="retag-option retag-opt-clinico" style="flex-grow:1; border-radius:0; background:rgba(245,158,11,0.1); text-align:left;">${grupo} ►</button>
                        <button class="retag-option" style="background:rgba(245,158,11,0.2); padding: 0 8px; color: #fbbf24;" onclick="removeTraitCategoria(event, null, '${grupo}')" title="Remover Categoria">-</button>
                    </div>
                    <div class="submenu" style="left:100%; top:0; min-width: 140px;">
                `;
                for (let p of treeTraits[grupo]) {
                    traitsHtml += `
                    <div style="display:flex;">
                        <button class="retag-option retag-opt-clinico" style="flex-grow:1; border-radius:0;" onclick="applyTrait('${grupo}', '${p}')">${p}</button>
                        <button class="retag-option" style="background:rgba(245,158,11,0.2); padding: 0 8px; color: #fbbf24;" onclick="removeTraitCategoria(event, '${grupo}', '${p}')" title="Remover Traço">-</button>
                    </div>`;
                }
                traitsHtml += `
                        <button class="retag-option" style="border-radius:0; background:rgba(255,255,255,0.1); color:#fff;" onclick="addTrait('${grupo}')">+ Novo Traço</button>
                    </div>
                </div>`;
            }
            traitsHtml += `<button class="retag-option" style="background:rgba(255,255,255,0.1); color:#fff;" onclick="addTraitCategoria()">+ Nova Categoria</button>`;
            
            document.getElementById('retag-trait-submenu').innerHTML = traitsHtml;
            document.getElementById('text-trait-submenu').innerHTML = traitsHtml.replace(/applyTrait/g, 'applyManualTrait');

            // Build Unificar HTML
            const ativasKeys = Object.keys(ativas);
            if (ativasKeys.length > 0) {
                document.getElementById('retag-unify-wrapper').style.display = 'inline-block';
                document.getElementById('text-unify-wrapper').style.display = 'inline-block';
                
                let unifyHtml = '';
                let unicos = {};
                for (let k of ativasKeys) {
                    let val = ativas[k];
                    if(!unicos[val]) unicos[val] = [];
                    unicos[val].push(k);
                }
                
                for (let u in unicos) {
                    let desc = u + " (" + unicos[u].join(', ') + ")";
                    unifyHtml += `<button class="retag-option retag-opt-nome" onclick="unifyPersona('${u}')">${desc}</button>`;
                }
                
                document.getElementById('retag-unify-submenu').innerHTML = unifyHtml;
                document.getElementById('text-unify-submenu').innerHTML = unifyHtml.replace(/unifyPersona/g, 'unifyManualPersona');
            }
        });
    }
    
    function removeCategoria(e, pai, item) {
        e.stopPropagation();
        if(!confirm(`Remover '${item}'?`)) return;
        fetch(getApiUrl() + '/api/remove_categoria', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({pai: pai, item: item})
        }).then(r=>r.json()).then(d=> { if(d.success) loadPersonas(); });
    }

    function removeTraitCategoria(e, pai, item) {
        e.stopPropagation();
        if(!confirm(`Remover '${item}'?`)) return;
        fetch(getApiUrl() + '/api/remove_trait_categoria', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({pai: pai, item: item})
        }).then(r=>r.json()).then(d=> { if(d.success) loadPersonas(); });
    }

    function addCategoria() {
        const cat = prompt("Digite o nome da nova CATEGORIA (ex: Profissional, Amigos):");
        if(cat) {
            fetch(getApiUrl() + '/api/add_categoria', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({nova: cat})
            }).then(r=>r.json()).then(d=> { if(d.success) loadPersonas(); });
        }
    }
    
    function addPersona(pai) {
        const p = prompt(`Digite o nome da nova PERSONA para a categoria ${pai}:`);
        if(p) {
            fetch(getApiUrl() + '/api/add_categoria', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({pai: pai, nova: p})
            }).then(r=>r.json()).then(d=> { if(d.success) loadPersonas(); });
        }
    }

    function addTraitCategoria() {
        const cat = prompt("Digite o nome da nova CATEGORIA de Traço (ex: Transtorno, Vício):");
        if(cat) {
            fetch(getApiUrl() + '/api/add_trait_categoria', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({nova: cat})
            }).then(r=>r.json()).then(d=> { if(d.success) loadPersonas(); });
        }
    }
    
    function addTrait(pai) {
        const p = prompt(`Digite o nome do novo TRAÇO para a categoria ${pai}:`);
        if(p) {
            fetch(getApiUrl() + '/api/add_trait_categoria', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({pai: pai, nova: p})
            }).then(r=>r.json()).then(d=> { if(d.success) loadPersonas(); });
        }
    }

    function applyPersona(tag) { applyRetag('[' + tag + ']'); }
    function applyManualPersona(tag) { applyManualTag('[' + tag + ']'); }

    function applyTrait(grupo, tag) { applyRetag('[TRAIT - ' + grupo + ' ' + tag + ']'); }
    function applyManualTrait(grupo, tag) { applyManualTag('[TRAIT - ' + grupo + ' ' + tag + ']'); }
    
    function unifyPersona(target) {
        if (!retagTarget) return;
        const msgId = retagTarget.dataset.msgId;
        const original = retagTarget.dataset.original;
        const midia = retagTarget.dataset.midia;
        
        fetch(getApiUrl() + '/api/unify_persona', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ msg_id: msgId, original: original, target_persona: target, arquivo_midia: midia })
        }).then(r=>r.json()).then(d=> { if(d.success) location.reload(); });
    }
    
    function unifyManualPersona(target) {
        if (!manualSelection.msgId) return;
        const original = manualSelection.text;
        if (!original) return;
        
        let fullText = manualSelection.container.innerText;
        if (manualSelection.container.classList.contains('transc')) {
            const span = manualSelection.container.querySelector('span[id^="text-"]');
            if (span) fullText = span.innerText;
        }
        
        fetch(getApiUrl() + '/api/unify_persona', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                msg_id: manualSelection.msgId, 
                original: original, 
                target_persona: target, 
                arquivo_midia: manualSelection.midia,
                full_text: fullText
            })
        }).then(r=>r.json()).then(d=> { if(d.success) location.reload(); });
    }

    // ================= ANONIMIZAÇÃO INTERATIVA =================
    let retagTarget = null; // span atualmente sendo re-taggeado

    function onAnonTagClick(el) {
        // Estado 1: tag ativa → reverter para texto original (imediato, sem popup)
        const msgId = el.dataset.msgId;
        const subIndex = parseInt(el.dataset.subIndex);
        const original = el.dataset.original;
        const midia = el.dataset.midia;

        revertTag(el, msgId, subIndex, original, midia);
    }

    function revertTag(el, msgId, subIndex, original, midia) {
        fetch(getApiUrl() + '/api/revert_tag', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({msg_id: msgId, original: original, tag: el.dataset.tag, arquivo_midia: midia})
        }).then(r => r.json()).then(data => {
            if (data.success) {
                // Transforma o span de tag ativa em span revertido
                el.className = 'anon-reverted';
                el.removeAttribute('title');
                el.textContent = original; // textContent evita injeção de HTML
                el.dataset.original = original;
                if (midia) el.dataset.midia = midia;
                el.onclick = function() { showRetagPopup(this); };
            } else {
                alert('Erro ao reverter: ' + (data.error || 'desconhecido'));
            }
        }).catch(e => alert('Erro. Servidor não está rodando.'));
    }

    function showRetagPopup(el) {
        retagTarget = el;
        const popup = document.getElementById('retagPopup');
        const rect = el.getBoundingClientRect();
        popup.style.left = Math.min(rect.left, window.innerWidth - 200) + 'px';
        popup.style.top = (rect.bottom + 8) + 'px';
        popup.classList.add('show');

        // Fecha ao clicar fora
        setTimeout(() => {
            document.addEventListener('click', closeRetagOnOutside, {once: true});
        }, 50);
    }

    function closeRetagOnOutside(e) {
        const popup = document.getElementById('retagPopup');
        if (!popup.contains(e.target)) {
            closeRetagPopup();
        }
    }

    function closeRetagPopup() {
        document.getElementById('retagPopup').classList.remove('show');
        retagTarget = null;
    }

    function removeTagCompletely() {
        if (!retagTarget) return;
        
        // Remove também da base de personas caso exista para não poluir o menu
        fetch(getApiUrl() + '/api/remove_persona', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ original: retagTarget.dataset.original })
        });

        // A tag já foi revertida no backend. Só precisamos tirar a caixa tracejada visual.
        const textNode = document.createTextNode(retagTarget.dataset.original);
        retagTarget.parentNode.replaceChild(textNode, retagTarget);
        closeRetagPopup();
    }

    function applyRetag(newTag) {
        if (!retagTarget) return;
        const el = retagTarget;
        const msgId = el.dataset.msgId;
        const original = el.dataset.original;
        const midia = el.dataset.midia;

        fetch(getApiUrl() + '/api/retag', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({msg_id: msgId, original: original, new_tag: newTag, arquivo_midia: midia})
        }).then(r => r.json()).then(data => {
            if (data.success) {
                closeRetagPopup();
                location.reload();
            } else {
                alert('Erro ao re-taggear: ' + (data.error || 'desconhecido'));
            }
        }).catch(e => alert('Erro. Servidor não está rodando.'));
    }

    // ================= SELEÇÃO MANUAL DE TEXTO =================
    let manualSelection = { text: '', msgId: '', midia: '', container: null };

    document.addEventListener('selectionchange', () => {
        const selection = window.getSelection();
        const menu = document.getElementById('textSelectMenu');
        
        if (selection.isCollapsed || !selection.toString().trim()) {
            menu.classList.remove('show');
            return;
        }
        
        // Verifica se estamos dentro de uma mensagem ou transcrição
        let node = selection.anchorNode;
        let container = null;
        while (node && node !== document.body) {
            if (node.classList && (node.classList.contains('msg-content') || node.classList.contains('transc'))) {
                container = node;
                break;
            }
            node = node.parentNode;
        }
        
        if (!container) {
            menu.classList.remove('show');
            return;
        }

        const msgDiv = container.closest('.msg');
        if (!msgDiv) return;
        
        manualSelection.msgId = msgDiv.getAttribute('data-id');
        manualSelection.text = selection.toString().trim();
        manualSelection.container = container;
        
        // Pega mídia se for transcrição
        const mediaTag = msgDiv.querySelector('audio, video, img');
        manualSelection.midia = mediaTag ? mediaTag.getAttribute('src') : '';
    });

    document.addEventListener('mouseup', (e) => {
        const selection = window.getSelection();
        const menu = document.getElementById('textSelectMenu');
        
        // Se soltou o clique dentro do próprio menu, ignora (para não fechar na hora de clicar)
        if (e.target.closest('#textSelectMenu')) return;

        if (selection.isCollapsed || !selection.toString().trim()) {
            menu.classList.remove('show');
            return;
        }
        
        if (!manualSelection.container) return;

        // Posiciona o menu
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        
        menu.style.left = Math.min(rect.left + window.scrollX, window.innerWidth - 300) + 'px';
        menu.style.top = Math.max(0, rect.top + window.scrollY - 45) + 'px'; // Acima da seleção
        menu.classList.add('show');
    });
    
    function applyManualTag(tag) {
        if (!manualSelection.text || !manualSelection.msgId) return;
        
        const menu = document.getElementById('textSelectMenu');
        menu.classList.remove('show');
        
        // Pega o texto completo visível no container para o caso de não estar no backend ainda
        let fullText = manualSelection.container.innerText;
        // Se for transcricao, a palavra "Transcrição" aparece no início do innerText por causa da tag <b>
        if (manualSelection.container.classList.contains('transc')) {
            const span = manualSelection.container.querySelector('span[id^="text-"]');
            if (span) fullText = span.innerText;
        }

        fetch(getApiUrl() + '/api/manual_tag', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                msg_id: manualSelection.msgId,
                original: manualSelection.text,
                tag: tag,
                full_text: fullText,
                arquivo_midia: manualSelection.midia
            })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert('Erro ao aplicar tag: ' + (data.error || 'desconhecido'));
            }
        }).catch(e => alert('Erro. Servidor não está rodando.'));
        
        // Limpa seleção do navegador para evitar bugs visuais após recarregar
        window.getSelection().removeAllRanges();
    }

    // Fecha popup com ESC
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            closeRetagPopup();
            document.getElementById('textSelectMenu').classList.remove('show');
            window.getSelection().removeAllRanges();
        }
    });
</script>
</div></body></html>"""

    with open(saida, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✔ Conferência criada com sucesso: {saida}")

# ================= MAIN =================
def run(pasta_cliente=None, auto=False, **kwargs):
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()
    
    chat = utils.escolher_chat_txt(pasta_cliente, auto=auto)
    msgs = parse_chat_whatsapp(chat)
    gerar_html(msgs, pasta_cliente, **kwargs)

if __name__ == "__main__":
    run()
