import os
import json
import config

def run():
    print("\n" + "="*35)
    print("      MENU STATS (ESTATÍSTICAS)")
    print("="*35)
    print("[1] Geral")
    print("[0] Voltar")
    print("="*35)
    
    escolha = input("\nEscolha uma opção: ").strip()
    if escolha == '1':
        mostrar_geral()
    elif escolha == '0':
        return
    else:
        print("Opção inválida.")
        input("\nPressione Enter para continuar...")

def mostrar_geral():
    # ler pastas
    pastas = [
        d for d in os.listdir(config.PASTA_BASE)
        if os.path.isdir(os.path.join(config.PASTA_BASE, d))
        and d not in (config.PASTA_ZIPS_PROCESSADOS, config.PASTA_TEMP_ZIPS)
    ]
    
    clientes_dados = []
    total_mensagens_geral = 0
    total_audios_geral = 0
    
    for pasta in pastas:
        caminho_json = os.path.join(config.PASTA_BASE, pasta, "cliente_info.json")
        if os.path.exists(caminho_json):
            try:
                with open(caminho_json, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    
                    nome = dados.get("nome", pasta)
                    data_nascimento = dados.get("data_nascimento") or "N/A"
                    metricas = dados.get("metricas", {})
                    num_consultas = metricas.get("num_consultas", 0)
                    
                    mensagens_autor = metricas.get("mensagens_por_autor", {})
                    total_mensagens = sum(mensagens_autor.values())
                    total_mensagens_geral += total_mensagens
                    
                    audios_autor = metricas.get("audios_por_autor", {})
                    total_audios = sum(audios_autor.values())
                    total_audios_geral += total_audios
                    
                    tempo_audio = metricas.get("tempo_audio_minutos", 0)
                    
                    clientes_dados.append({
                        "nome": nome,
                        "data_nascimento": data_nascimento,
                        "num_consultas": num_consultas,
                        "total_mensagens": total_mensagens,
                        "total_audios": total_audios,
                        "tempo_audio": tempo_audio
                    })
            except Exception as e:
                pass
                
    print(f"\n✅ Total de Clientes Únicos: {len(clientes_dados)}")
    print(f"💬 Total de Mensagens (Global): {total_mensagens_geral}")
    
    if not clientes_dados:
        print("Nenhum cliente com cliente_info.json encontrado.")
        return
        
    print("\n" + "="*45)
    print("CATEGORIAS DE ORGANIZAÇÃO")
    print("="*45)
    print("[1] Nome")
    print("[2] Data de Nascimento")
    print("[3] Número de Consultas")
    print("[4] Total de Mensagens")
    print("[5] Total de Áudios")
    print("[6] Tempo de Áudio em Minutos")
    
    cat_escolha = input("\nEscolha a categoria de ordenação: ").strip()
    
    opcoes_sort = {
        '1': ('nome', 'Nome'),
        '2': ('data_nascimento', 'Data de Nascimento'),
        '3': ('num_consultas', 'Nº Consultas'),
        '4': ('total_mensagens', 'Mensagens'),
        '5': ('total_audios', 'Áudios'),
        '6': ('tempo_audio', 'Tempo (min)')
    }
    
    if cat_escolha not in opcoes_sort:
        print("Opção inválida. Usando Nome como padrão.")
        cat_escolha = '1'
        
    chave_sort, nome_coluna = opcoes_sort[cat_escolha]
    
    ordem_escolha = input("Ordem: [1] Crescente [2] Decrescente: ").strip()
    reverse = False
    if ordem_escolha == '2':
        reverse = True
        
    # Ordenar
    if chave_sort == 'data_nascimento':
        clientes_dados.sort(key=lambda x: str(x[chave_sort]), reverse=reverse)
    elif chave_sort == 'nome':
        clientes_dados.sort(key=lambda x: str(x[chave_sort]).lower(), reverse=reverse)
    else:
        clientes_dados.sort(key=lambda x: float(x[chave_sort] or 0), reverse=reverse)
        
    print("\n" + "="*55)
    print(f"{'NOME DO CLIENTE':<35} | {nome_coluna}")
    print("="*55)
    for c in clientes_dados:
        nome_str = c['nome'][:33]
        val_str = c[chave_sort]
        if chave_sort == 'tempo_audio':
            val_str = f"{val_str:.2f} min"
        print(f"{nome_str:<35} | {val_str}")
        
    print("="*55)
