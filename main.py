import os
import subprocess
import utils
import step0
import step1
import step2
import step3
import step4
import step4_menu
def mostrar_menu():
    print("\n" + "="*35)
    print("      TRANS-CRYPT - MENU GERAL")
    print("="*35)
    print("[0] Extrair e Mesclar Zips (Step 0)")
    print("[1] Transcrever Áudios (Step 1)")
    print("[2] Gerar Histórico Texto (Step 2)")
    print("[3] Gerar Conferência Visual (Step 3)")
    print("[4] Anonimizar Histórico Localmente (Step 4)")
    print("[5] Rodar Passos 1 ao 3 (P/ 1 Cliente)")
    print("[6] Abrir Editor Visual (Interativo)")
    print("[7] Publicar no Google Drive (Step 6)")
    print("[9] Sair")
    print("="*35)

def main():
    while True:
        mostrar_menu()
        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == '9':
            print("Saindo...")
            # Força o encerramento em nível de SO para matar threads
            # filhas de C++ do Whisper que travam o terminal.
            os._exit(0)
            
        elif escolha == '0':
            step0.run()
            os.system("stty sane")  # ffmpeg pode bagunçar o estado do terminal
            input("\nPressione Enter para continuar...")
            
        elif escolha in ('1', '2', '3', '4', '5', '6', '7'):
            # Todos os passos precisam saber qual o cliente. 
            # Pedimos apenas uma vez aqui se for rodar tudo, ou passo individual.
            pasta_cliente = utils.escolher_pasta_cliente()

            if escolha == '1':
                step1.run(pasta_cliente)
            elif escolha == '2':
                step1.limpar_memoria()
                step2.run(pasta_cliente)
            elif escolha == '3':
                step1.limpar_memoria()
                step3.run(pasta_cliente)
            elif escolha == '4':
                step1.limpar_memoria()
                step4_menu.run(pasta_cliente)
            elif escolha == '5':
                print("\n>>> INICIANDO PASSO 1: TRANSCRIÇÃO")
                step1.run(pasta_cliente)
                step1.limpar_memoria()
                print("\n>>> INICIANDO PASSO 2: HISTÓRICO")
                step2.run(pasta_cliente)
                print("\n>>> INICIANDO PASSO 3: HTML VISUAL")
                step3.run(pasta_cliente)
            elif escolha == '6':
                step1.limpar_memoria()
                print("\nQual conferência abrir?")
                print("[1] Conferência Visual (original)")
                print("[2] Conferência Anonimizada")
                sub = input("\nEscolha: ").strip()
                modo = "anon" if sub == "2" else "normal"
                try:
                    import editor_server
                    editor_server.start_server(pasta_cliente, modo=modo)
                except ModuleNotFoundError:
                    print("\n❌ ERRO: O módulo 'flask' não foi encontrado neste ambiente Python.")
                    print("Por favor, instale-o rodando o comando no seu terminal:")
                    print("    pip install flask")
            elif escolha == '7':
                step1.limpar_memoria()
                try:
                    import step6
                    step6.run(pasta_cliente)
                except ModuleNotFoundError:
                    print("\n❌ ERRO: Bibliotecas do Google não instaladas.")
                    print("Rode: pip install -r requirements.txt")
                
            os.system("stty sane")  # restaura o terminal após subprocessos paralelos
            input("\nPressione Enter para continuar...")
        else:
            print("Opção inválida.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Processo cancelado pelo usuário. Limpando processos em segundo plano...")
        try:
            # Mata agressivamente qualquer ffmpeg para evitar consumo de CPU
            subprocess.run(["pkill", "-9", "-f", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
            
        print("✅ Encerrado com segurança.")
        
        # Restaura o estado do terminal para evitar que ele fique "congelado/travado"
        try:
            import sys
            sys.stdout.flush()
            os.system("stty sane")
        except Exception:
            pass
            
        os._exit(0)
