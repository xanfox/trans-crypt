import os
import sys

# Bibliotecas do Google API
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("\n❌ ERRO: Bibliotecas do Google não encontradas.")
    print("Instale rodando: pip install -r requirements.txt")
    sys.exit(1)

import config
import utils

# Escopo restrito: o app só pode ver, editar, criar e deletar os arquivos específicos
# que o PRÓPRIO app criou no Google Drive. Ele NÃO TEM ACESSO aos seus outros arquivos pessoais.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def autenticar_google():
    """Lida com o fluxo OAuth2 de autenticação com o Google Drive."""
    creds = None
    # O arquivo token.json armazena os tokens de acesso e atualização do usuário e
    # é criado automaticamente quando o fluxo de autorização conclui pela primeira vez.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # Se não há credenciais válidas disponíveis, peça ao usuário para logar.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("\n❌ ERRO FATAL: O arquivo 'credentials.json' não foi encontrado na pasta raiz.")
                print("Por favor, baixe o arquivo no painel do Google Cloud Console e coloque-o na pasta do trans-crypt.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Salva as credenciais para o próximo uso
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return creds

def run(pasta_cliente=None):
    """
    Sobe o histórico consolidado do cliente para o Google Drive
    e o converte nativamente para um documento do Google Docs.
    """
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()

    caminho_historico = os.path.join(pasta_cliente, config.ARQUIVO_HISTORICO)

    if not os.path.exists(caminho_historico):
        print(f"\n❌ ERRO: O arquivo {config.ARQUIVO_HISTORICO} não existe nesta pasta.")
        print("Você precisa rodar o Passo 2 antes de publicar.")
        return

    print(f"\n☁️ Autenticando com o Google Drive...")
    creds = autenticar_google()
    if not creds:
        return

    try:
        service = build('drive', 'v3', credentials=creds)

        nome_exibicao = utils.formatar_nome_display(pasta_cliente)
        nome_arquivo_drive = f"Auditoria: {nome_exibicao}"
        
        print(f"📄 Preparando upload: '{nome_arquivo_drive}'")

        # Configuração do metadata (mimeType final que queremos no Drive = Google Docs)
        file_metadata = {
            'name': nome_arquivo_drive,
            'mimeType': 'application/vnd.google-apps.document',
            'parents': [config.GOOGLE_DRIVE_FOLDER_ID]
        }
        
        # Mimetype de origem é texto puro
        media = MediaFileUpload(caminho_historico, mimetype='text/plain', resumable=True)

        print("🚀 Enviando e convertendo... (isso pode levar alguns segundos)")
        
        # Cria e faz upload convertendo para Docs
        file = service.files().create(
            body=file_metadata, 
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        print("\n✅ SUCESSO! Histórico publicado no Google Drive.")
        print(f"🔗 Link do Google Docs: {file.get('webViewLink')}")

    except HttpError as error:
        print(f"\n❌ Ocorreu um erro de API com o Google Drive: {error}")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")

if __name__ == '__main__':
    run()
