import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
import unicodedata

# --- CONFIGS ---

FRASES_CHAVE_OBJETO = [
    "vigilancia armada", "vigilancia desarmada", "seguranca armada", "seguranca desarmada",
    "seguranca eletronica", "servicos de vigilancia", "vigilancia patrimonial", 
    "videomonitoramento", "cftv", "monitoramento", "vigilancia", "seguranca"
]

NOME_PLANILHA = "tabelapy"
NOME_ABA = "Página1"

LINHA_CABECALHO = 1 

# --- FIM DAS CONFIGS ---

def setup_google_sheets():
    """Configura a autenticação e retorna a aba da planilha."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open(NOME_PLANILHA).worksheet(NOME_ABA)
        print(f"Conectado com sucesso à planilha '{NOME_PLANILHA}' e aba '{NOME_ABA}'.")
        return sheet
    except Exception as e:
        print(f"ERRO ao conectar com Google Sheets: {e}")
        return None

def strip_accents(text):
    """Remove acentos de uma string."""
    try:
        text = unicode(text, 'utf-8')
    except (TypeError, NameError): # Py 2 e 3
        pass
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore')
    text = text.decode("utf-8")
    return str(text)

def encontrar_frase_especifica(objeto_original, frases_chave):
    """Encontra a primeira e mais específica frase-chave correspondente no objeto, ignorando acentos."""
    objeto_normalizado = strip_accents(objeto_original.lower())
    
    for frase in frases_chave:
        if frase in objeto_normalizado:
            return frase.title() # primeira letra maiúscula
    return None # None se nenhuma frase for encontrada

def limpar_nome_orgao(nome_orgao):
    """Remove prefixos comuns do nome do órgão para isolar o nome da cidade."""
    if not isinstance(nome_orgao, str):
        return nome_orgao

    prefixos = [
        "prefeitura municipal de", "municipio de", "câmara municipal de", 
        "fundo municipal de", "secretaria municipal de"
    ]
    nome_lower = nome_orgao.lower()
    for prefixo in prefixos:
        if nome_lower.startswith(prefixo):
            return nome_orgao[len(prefixo):].strip().title()
    return nome_orgao.title()

def main():
    """Função principal que executa o processamento da planilha."""
    worksheet = setup_google_sheets()
    if not worksheet: return

    print("Lendo dados da planilha...")
    try:
        todos_os_dados = worksheet.get_all_values()
        if len(todos_os_dados) <= LINHA_CABECALHO:
            print("Nenhum dado para processar encontrado abaixo do cabeçalho.")
            return
            
        cabecalho = todos_os_dados[LINHA_CABECALHO - 1]
        col_objeto_idx = cabecalho.index('Objeto da Licitação')
        col_orgao_idx = cabecalho.index('Órgão Licitante')

        print("Processando e limpando os dados...")
        
        objetos_processados = []
        orgaos_processados = []

        for linha in todos_os_dados[LINHA_CABECALHO:]:
            # Processa Objeto
            objeto_original = linha[col_objeto_idx]
            frase_encontrada = encontrar_frase_especifica(objeto_original, FRASES_CHAVE_OBJETO)
            objetos_processados.append([frase_encontrada if frase_encontrada else objeto_original])

            # Processa Órgão
            orgao_original = linha[col_orgao_idx]
            orgao_limpo = limpar_nome_orgao(orgao_original)
            orgaos_processados.append([orgao_limpo])

        if objetos_processados:
            range_objeto = f'{chr(ord("A") + col_objeto_idx)}{LINHA_CABECALHO + 1}:{chr(ord("A") + col_objeto_idx)}{LINHA_CABECALHO + len(objetos_processados)}'
            print(f"Atualizando {len(objetos_processados)} objetos na coluna 'Objeto da Licitação'...")
            worksheet.update(values=objetos_processados, range_name=range_objeto)
            time.sleep(1.5)

        if orgaos_processados:
            range_orgao = f'{chr(ord("A") + col_orgao_idx)}{LINHA_CABECALHO + 1}:{chr(ord("A") + col_orgao_idx)}{LINHA_CABECALHO + len(orgaos_processados)}'
            print(f"Atualizando {len(orgaos_processados)} órgãos na coluna 'Órgão Licitante'...")
            worksheet.update(values=orgaos_processados, range_name=range_orgao)

        print("\nProcessamento concluído com sucesso! Sua planilha foi otimizada.")

    except ValueError as e:
        print(f"\nERRO: Uma das colunas esperadas ('Objeto da Licitação' ou 'Órgão Licitante') não foi encontrada no cabeçalho. Verifique os nomes na sua planilha. Detalhe: {e}")
    except Exception as e:
        print(f"Ocorreu um erro geral durante o processamento: {e}")

if __name__ == "__main__":
    main()

# Created by Jordanlvs 💼 All Rights Reserved. ® 
