import os
import re
import json
import config
import utils
import step2
import step3
from whatsapp_parser import parse_chat_whatsapp

# ================= DICIONÁRIO DE TERMOS CLÍNICOS =================
TERMOS_CLINICOS = [
    "depressão", "depressao", "ansiedade", "síndrome do pânico", "sindrome do panico",
    "pânico", "panico", "bipolar", "transtorno", "borderline", "esquizofrenia",
    "tdah", "toc", "burnout", "estresse pós-traumático", "ptsd", "fobia",
    "anorexia", "bulimia", "compulsão", "compulsao",
    "diabetes", "hipertensão", "hipertensao", "câncer", "cancer", "tumor",
    "fibromialgia", "endometriose", "tireoide", "hipotireoidismo",
    "hipertireoidismo", "artrite", "artrose", "lúpus", "lupus", "anemia",
    "asma", "bronquite", "pneumonia", "covid", "hiv", "aids", "hepatite",
    "epilepsia", "parkinson", "alzheimer", "esclerose", "mioma", "cisto",
    "hérnia", "hernia", "gastrite", "úlcera", "ulcera", "insônia", "insonia",
    "apneia", "enxaqueca", "labirintite", "sinusite", "rinite", "dermatite",
    "psoríase", "psoriase", "vitiligo", "trombose", "avc", "infarto",
    "arritmia", "taquicardia", "bradicardia",
    "rivotril", "fluoxetina", "sertralina", "escitalopram", "venlafaxina",
    "clonazepam", "diazepam", "alprazolam", "lorazepam", "amitriptilina",
    "paroxetina", "citalopram", "duloxetina", "ritalina", "metilfenidato",
    "lítio", "litio", "quetiapina", "risperidona", "olanzapina", "haloperidol",
    "carbamazepina", "valproato", "lexapro", "prozac", "zoloft", "frontal",
    "omeprazol", "losartana", "metformina", "insulina",
]

# ================= MOTOR NER (spaCy) =================
_nlp = None  # Cache global

def _carregar_spacy():
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
    except ImportError:
        print("❌ spaCy não instalado. Rode: pip3 install spacy")
        return None
    for modelo in ("pt_core_news_lg", "pt_core_news_md", "pt_core_news_sm"):
        try:
            _nlp = spacy.load(modelo)
            print(f"   ✔ Modelo NER carregado: {modelo}")
            return _nlp
        except OSError:
            continue
    print("❌ Nenhum modelo spaCy pt encontrado.")
    return None

# ================= EXTRAÇÃO DE IDENTIDADE =================
def _extrair_identidade_cliente(pasta_cliente, mensagens_chat):
    nomes = set()
    nome_display = utils.formatar_nome_display(pasta_cliente)
    partes_display = nome_display.split(" - ")
    nome_limpo = partes_display[0].strip()
    nomes.add(nome_limpo)
    for parte in nome_limpo.split():
        if len(parte) > 2:
            nomes.add(parte)

    data_nascimento = None
    if len(partes_display) > 1:
        possivel_data = partes_display[-1].strip()
        if re.match(r'\d{2}/\d{2}/\d{4}', possivel_data):
            data_nascimento = possivel_data

    autores_vistos = set()
    for m in mensagens_chat:
        autor = m.get("autor", "")
        if autor in autores_vistos:
            continue
        autores_vistos.add(autor)

        if any(r in autor for r in config.REMETENTES_DIREITA):
            continue

        autor_limpo = re.sub(r'[^\w\s]', '', autor).strip()
        for prefixo in ("Lead", "FR", "lead", "fr", "Consulente", "consulente"):
            if autor_limpo.lower().startswith(prefixo.lower()):
                autor_limpo = autor_limpo[len(prefixo):].strip()

        if autor_limpo:
            nomes.add(autor_limpo)
            for parte in autor_limpo.split():
                if len(parte) > 2:
                    nomes.add(parte)

    nomes.discard("")
    return nomes, data_nascimento

# ================= EXTRAÇÃO DE ENTIDADES (PRÉVIA) =================
def extrair_entidades(pasta_cliente):
    chat = utils.escolher_chat_txt(pasta_cliente, auto=True)
    if not chat:
        return []
        
    mensagens_chat = parse_chat_whatsapp(chat)
    nlp = _carregar_spacy()
    if not nlp:
        return []
        
    # Precisamos varrer textos e transcricoes
    from step4_menu import load_stoplist
    stoplist = load_stoplist()
    
    pasta_trans_orig = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    arquivos_midia = [f for f in os.listdir(pasta_cliente) if f.lower().endswith(config.EXTENSOES_MIDIA_HTML)]
    
    nomes_encontrados = set()
    
    # Adicionar identidades do cliente
    nomes_cliente, _ = _extrair_identidade_cliente(pasta_cliente, mensagens_chat)
    nomes_encontrados.update(nomes_cliente)
    
    for m in mensagens_chat:
        conteudo = m["conteudo"]
        arquivo_encontrado = next((arq for arq in arquivos_midia if arq in conteudo), None)
        textos_para_analisar = []
        
        if arquivo_encontrado:
            trans_orig = utils.buscar_transcricao(pasta_trans_orig, arquivo_encontrado)
            if trans_orig:
                textos_para_analisar.append(trans_orig)
        else:
            textos_para_analisar.append(conteudo)
            
        for texto in textos_para_analisar:
            if not texto.strip():
                continue
            doc = nlp(texto)
            for ent in doc.ents:
                if ent.label_ == "PER":
                    ent_lower = ent.text.strip().lower()
                    if ent_lower in stoplist or any(w in stoplist for w in ent_lower.split()):
                        continue
                    nomes_encontrados.add(ent.text.strip())
                    
    return list(nomes_encontrados)

# ================= MOTOR DE ANONIMIZAÇÃO =================
def _anonimizar_texto(texto, nomes_cliente, nlp, data_nascimento, flags, personas, stoplist):
    if not texto.strip():
        return texto, []

    substituicoes = []

    # Helper para descobrir a tag do nome
    def get_tag_nome(nome_str):
        nome_lower = nome_str.lower()
        for p_nome, p_tag in personas.items():
            if p_nome.lower() == nome_lower or p_nome.lower() in nome_lower.split():
                return f"[{p_tag}]"
        return "[PERSONA]"

    # 1. Nomes do cliente
    if flags.get("nomes", True):
        for nome in sorted(nomes_cliente, key=len, reverse=True):
            padrao = re.compile(re.escape(nome), re.IGNORECASE)
            for match in padrao.finditer(texto):
                substituicoes.append((match.start(), match.end(), get_tag_nome(nome), "dict"))

        # 2. NER com spaCy
        if nlp:
            doc = nlp(texto)
            for ent in doc.ents:
                ent_lower = ent.text.strip().lower()
                if ent_lower in stoplist or any(w in stoplist for w in ent_lower.split()):
                    continue
                if ent.label_ == "PER":
                    substituicoes.append((ent.start_char, ent.end_char, get_tag_nome(ent.text), "ner"))
                elif ent.label_ in ("LOC", "GPE") and flags.get("locais", True):
                    substituicoes.append((ent.start_char, ent.end_char, "[LOCAL]", "ner"))

    # 3. Datas
    if flags.get("datas", True):
        if data_nascimento:
            for sep in ("/", "-", "."):
                variacao = data_nascimento.replace("/", sep)
                for match in re.finditer(re.escape(variacao), texto):
                    substituicoes.append((match.start(), match.end(), "[DATA NASCIMENTO]", "regex"))

        for match in re.finditer(r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b', texto):
            substituicoes.append((match.start(), match.end(), "[DATA]", "regex"))

    # 4. Termos clínicos
    if flags.get("clinicas", True):
        for termo in TERMOS_CLINICOS:
            padrao = re.compile(r'\b' + re.escape(termo) + r'\b', re.IGNORECASE)
            for match in padrao.finditer(texto):
                substituicoes.append((match.start(), match.end(), "[TRAIT]", "dict"))

    # ── Resolver sobreposições e aplicar ──
    substituicoes.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    filtradas = []
    ultimo_fim = -1
    for inicio, fim, tag, tipo in substituicoes:
        if inicio >= ultimo_fim:
            filtradas.append((inicio, fim, tag, tipo))
            ultimo_fim = fim

    anon_map = []
    for inicio, fim, tag, tipo in filtradas:
        anon_map.append({
            "original": texto[inicio:fim],
            "tag": tag,
            "type": tipo
        })

    resultado = texto
    for inicio, fim, tag, tipo in reversed(filtradas):
        resultado = resultado[:inicio] + tag + resultado[fim:]

    return resultado, anon_map

# ================= EXECUÇÃO =================
def executar_processo(pasta_cliente, flags_anon, personas, stoplist):
    client_name = utils.formatar_nome_display(pasta_cliente)
    chat = utils.escolher_chat_txt(pasta_cliente, auto=True)

    print(f"\n📖 Carregando mensagens de {client_name}...")
    mensagens_chat = parse_chat_whatsapp(chat)

    print("🔍 Carregando motor de reconhecimento de entidades (spaCy)...")
    nlp = _carregar_spacy() if flags_anon.get("nomes", True) or flags_anon.get("locais", True) else None

    nomes_cliente, data_nascimento = _extrair_identidade_cliente(pasta_cliente, mensagens_chat)
    if flags_anon.get("nomes", True):
        print(f"   📋 Nomes/variações detectados: {sorted(nomes_cliente, key=len, reverse=True)}")
    if data_nascimento and flags_anon.get("datas", True):
        print(f"   📅 Data de nascimento detectada: {data_nascimento}")

    caminho_edits = os.path.join(pasta_cliente, "conferencia_edits.json")
    edits = {"deleted_ids": [], "edited_texts": {}}
    if os.path.exists(caminho_edits):
        try:
            with open(caminho_edits, "r", encoding="utf-8") as f:
                edits = json.load(f)
        except Exception as e:
            print(f"\n⚠️ AVISO: conferencia_edits.json corrompido ({e}).")

    caminho_edits_anon = os.path.join(pasta_cliente, "conferencia_edits_anonimizada.json")
    edits_anon = {
        "deleted_ids": edits.get("deleted_ids", []),
        "edited_texts": {},
        "status": edits.get("status", {})
    }

    pasta_trans_orig = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    pasta_trans_anon = os.path.join(pasta_cliente, "_transcricoes_anonimizadas")
    os.makedirs(pasta_trans_anon, exist_ok=True)

    arquivos_midia = [f for f in os.listdir(pasta_cliente) if f.lower().endswith(config.EXTENSOES_MIDIA_HTML)]
    deleted_ids = {int(x) for x in edits_anon.get("deleted_ids", [])}
    mensagens_validas = [m for m in mensagens_chat if m["id"] not in deleted_ids]
    total = len(mensagens_validas)

    print(f"\n🤖 Anonimizando {total} mensagens...\n")

    contadores = {"nomes": 0, "locais": 0, "datas": 0, "clinicos": 0, "inalteradas": 0}

    for idx, m in enumerate(mensagens_validas, 1):
        msg_id_str = str(m["id"])
        conteudo_base = edits.get("edited_texts", {}).get(msg_id_str, m["conteudo"])
        arquivo_encontrado = next((arq for arq in arquivos_midia if arq in conteudo_base), None)

        texto_msg = "" if arquivo_encontrado else conteudo_base
        texto_anon = ""
        msg_anon_map = []
        
        if texto_msg.strip():
            texto_anon, msg_anon_map = _anonimizar_texto(texto_msg, nomes_cliente, nlp, data_nascimento, flags_anon, personas, stoplist)

        trans_anon_texto = None
        if arquivo_encontrado:
            trans_orig = utils.buscar_transcricao(pasta_trans_orig, arquivo_encontrado)
            if trans_orig:
                trans_anon_texto, trans_map = _anonimizar_texto(trans_orig, nomes_cliente, nlp, data_nascimento, flags_anon, personas, stoplist)
                msg_anon_map.extend(trans_map)
                base_nome = os.path.splitext(arquivo_encontrado)[0]
                with open(os.path.join(pasta_trans_anon, base_nome + ".txt"), "w", encoding="utf-8") as f:
                    f.write(trans_anon_texto)

        if arquivo_encontrado:
            edits_anon["edited_texts"][msg_id_str] = conteudo_base
        else:
            edits_anon["edited_texts"][msg_id_str] = texto_anon if texto_anon else conteudo_base

        if msg_anon_map:
            edits_anon.setdefault("anon_map", {})[msg_id_str] = msg_anon_map

        texto_comparar = (texto_anon or "") + (trans_anon_texto or "")
        
        # Check logic based on tags
        for p in personas.values():
            if f"[{p}]" in texto_comparar:
                contadores["nomes"] += 1
                break
        else:
            if "[PERSONA]" in texto_comparar: contadores["nomes"] += 1
            
        if "[LOCAL]" in texto_comparar: contadores["locais"] += 1
        if "[DATA" in texto_comparar: contadores["datas"] += 1
        if "[TRAIT]" in texto_comparar: contadores["clinicos"] += 1
        
        orig_comparar = (texto_msg or "") + ((utils.buscar_transcricao(pasta_trans_orig, arquivo_encontrado) or "") if arquivo_encontrado else "")
        if texto_comparar == orig_comparar:
            contadores["inalteradas"] += 1

        if idx % 50 == 0 or idx == total:
            pct = int(idx / total * 100)
            print(f"   [{idx}/{total}] {pct}% concluído — "
                  f"Nomes/Personas:{contadores['nomes']} | Locais:{contadores['locais']} | "
                  f"Datas:{contadores['datas']} | Clínicos:{contadores['clinicos']}")

    tmp_anon = caminho_edits_anon + f".{__import__('uuid').uuid4().hex}.tmp"
    with open(tmp_anon, "w", encoding="utf-8") as f:
        json.dump(edits_anon, f, indent=4, ensure_ascii=False)
    os.replace(tmp_anon, caminho_edits_anon)

    print(f"\n✅ Anonimização concluída!")
    
    print("\n📄 Gerando exportações...")
    step2.gerar_historico(
        pasta_cliente, mensagens_chat,
        arquivo_saida="historico_anonimizado.txt",
        arquivo_edits="conferencia_edits_anonimizada.json",
        pasta_transcricoes="_transcricoes_anonimizadas"
    )

    step3.gerar_html(
        mensagens_chat, pasta_cliente,
        nome_saida="conferencia_anonimizada.html",
        arquivo_edits="conferencia_edits_anonimizada.json",
        pasta_transcricoes="_transcricoes_anonimizadas"
    )

def run(pasta_cliente=None):
    from step4_menu import load_stoplist, load_personas
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()
    flags_anon = {"nomes": True, "datas": True, "locais": True, "clinicas": True}
    personas = load_personas(pasta_cliente)
    stoplist = load_stoplist()
    executar_processo(pasta_cliente, flags_anon, personas, stoplist)

if __name__ == '__main__':
    run()
