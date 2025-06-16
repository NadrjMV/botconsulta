import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from urllib.parse import quote
import re

# --- CONFIGS ---
UFS_INTERESSE = ['SP', 'MG', 'RJ', 'ES', 'PR', 'SC', 'RS', 'DF'] 

PALAVRAS_CHAVE = [
    "vigilancia",
    "seguranca",
    "videomonitoramento",
    "cftv",
    "monitoramento"
]

PALAVRAS_EXCLUIDAS = [
    'sanitaria', 'sanitario', 'saude', 'epidemiologica', 'glicemia', 'hospitalar', 'ambulatorial',
    'uniformes', 'mochilas', 'crachas', 'coletes', 'veiculos', 'viatura',
    'tablets', 'informatica', 'software', 'sistema',
    'obras', 'engenharia', 'passeios', 'construcao', 'guarita',
    'alimentacao', 'cartao', 'beneficio', 'material didatico',
    'mesa', 'pia', 'inox', 'leitor de codigo', 'impressora', 'transporte', 'cartão',
    'alimentação', 'condicionado'
]

NOME_PLANILHA = "tabelapy"
NOME_ABA = "Página1"
RODAR_NAVEGADOR_VISIVEL = True
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

def setup_driver():
    """Configura e retorna o driver do Selenium."""
    print("Configurando o navegador automatizado (Chrome)...")
    try:
        options = webdriver.ChromeOptions()
        if not RODAR_NAVEGADOR_VISIVEL:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("start-maximized")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("Navegador configurado com sucesso.")
        return driver
    except WebDriverException as e:
        print(f"ERRO CRÍTICO ao configurar o WebDriver: {e}")
        return None

def extrair_valor_e_prazo(driver, link_portal):
    """Navega até a página de detalhes, extrai o prazo e calcula o valor total dos itens."""
    prazo_proposta = "Não encontrado"
    valor_total = 0.0
    
    try:
        driver.get(link_portal)
        wait = WebDriverWait(driver, 25)
        
        # 1. Extrai o Prazo da Proposta (Lógica Final e Corrigida)
        try:
            datas_container = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.half-side > div > p.subtitle")))
            html_datas = datas_container.get_attribute('innerHTML')
            for line in html_datas.split('<br>'):
                if "Limite p/ Recebimento das Propostas:" in line:
                    prazo_proposta = re.sub('<[^<]+?>', '', line).replace("Limite p/ Recebimento das Propostas:", "").strip()
                    break
        except TimeoutException:
            print("  - Aviso: Seção de datas não encontrada.")

        # 2. Calcula o Valor Total dos Itens (Lógica Final e Corrigida)
        try:
            wait.until(EC.presence_of_element_located((By.ID, 'nav-itens-processo')))
        except TimeoutException:
            print("  - Aviso: Seção de 'Itens' não encontrada.")
            return prazo_proposta, f"R$ {0:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # Loop de Paginação
        while True:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.lista-registros .item, div.empty-list-container')))
            time.sleep(3) 
            
            page_soup = BeautifulSoup(driver.page_source, 'lxml')
            
            if page_soup.find('div', class_='empty-list-container'):
                break

            itens_rows = page_soup.select('div.lista-registros div.item')
            if not itens_rows: break 

            for row in itens_rows:
                spans = row.find_all('span')
                quantidade_str, valor_ref_str = "0", "0"
                
                # Extração robusta baseada no texto da tag <b>
                for span in spans:
                    b_tag = span.find('b')
                    if b_tag:
                        text_b = b_tag.get_text(strip=True)
                        if "Quantidade" in text_b:
                            if b_tag.next_sibling and isinstance(b_tag.next_sibling, str):
                                quantidade_str = b_tag.next_sibling.strip()
                        elif "V. Referência" in text_b:
                             # Esta lógica é um fallback, a principal está abaixo
                             pass
                
                # Lógica principal e mais confiável para V. Referência
                valor_span = row.find('span', class_='s12')
                if valor_span: 
                    valor_ref_str = valor_span.get_text(strip=True)

                try:
                    # Limpeza e conversão segura dos números
                    quantidade = float(re.sub(r'[^\d,]', '', quantidade_str).replace(',', '.'))
                    valor_ref = float(re.sub(r'[^\d,]', '', valor_ref_str).replace(',', '.'))
                    valor_total += quantidade * valor_ref
                except (ValueError, IndexError):
                    continue

            # Lógica de Paginação corrigida
            try:
                # Procura pelo botão "próxima" que NÃO esteja desabilitado
                next_button_li = driver.find_element(By.CSS_SELECTOR, 'li.page-item.pagination-next:not(.pagination-default-disabled)')
                next_button_a = next_button_li.find_element(By.TAG_NAME, 'a')
                print("  - Navegando para a próxima página de itens...")
                driver.execute_script("arguments[0].click();", next_button_a)
            except NoSuchElementException:
                break # Sai do loop se não houver botão "próximo" ativo
    
    except Exception as e:
        print(f"  - Aviso: Erro inesperado ao extrair detalhes: {e}")

    # Formatação final da moeda
    valor_formatado = f"R$ {valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return prazo_proposta, valor_formatado

def main():
    """Função principal que executa o robô."""
    worksheet = setup_google_sheets()
    if not worksheet: return

    print("Iniciando sincronização da planilha...")
    try:
        # Limpa o CONTEÚDO das linhas abaixo do cabeçalho, sem apagar as linhas em si.
        if worksheet.row_count > LINHA_CABECALHO:
            range_to_clear = f'A{LINHA_CABECALHO + 1}:J{worksheet.row_count}' # Agora até a coluna J (Valor)
            worksheet.batch_clear([range_to_clear])
        print(f"Dados antigos (abaixo da linha {LINHA_CABECALHO}) limpos.")
    except Exception as e:
        print(f"ERRO ao limpar a planilha: {e}")
        return
    
    links_salvos = set()
    hoje_formatado = datetime.now().strftime('%d/%m/%Y')
    novas_licitacoes_encontradas = 0
    driver = setup_driver()

    if not driver: return

    print("\n--- INICIANDO BUSCA NO PORTAL DE COMPRAS PÚBLICAS ---")

    try:
        driver.get("https://www.portaldecompraspublicas.com.br/processos")
        wait = WebDriverWait(driver, 20)
        try:
            cookie_button = wait.until(EC.element_to_be_clickable((By.ID, 'btn-aceitar-cookie')))
            driver.execute_script("arguments[0].click();", cookie_button)
            print("Cookies aceitos.")
        except TimeoutException:
            print("Aviso de cookies não encontrado ou já aceito.")

        for palavra in PALAVRAS_CHAVE:
            for uf_sigla in UFS_INTERESSE:
                print(f"\nBuscando por '{palavra}' em '{uf_sigla}'...")
                
                try:
                    termo_busca = quote(palavra)
                    url_busca = (f"https://www.portaldecompraspublicas.com.br/processos?"
                                 f"objeto={termo_busca}&uf_ge={uf_sigla}&codigoStatus=1")
                    
                    driver.get(url_busca)
                    
                    wait_long = WebDriverWait(driver, 45)
                    
                    print("Aguardando resultados...")
                    wait_long.until(EC.any_of(
                        EC.presence_of_element_located((By.CLASS_NAME, 'item')),
                        EC.presence_of_element_located((By.CLASS_NAME, 'empty-list-container'))
                    ))
                    
                    print("Página carregada e resultados prontos.")
                    time.sleep(2)

                    soup = BeautifulSoup(driver.page_source, 'lxml')
                    
                    if soup.find('div', class_='empty-list-container'):
                        print("Nenhum resultado encontrado para esta combinação.")
                        continue
                    
                    itens_licitacao = soup.find_all('div', class_='item')
                    print(f"Encontrados {len(itens_licitacao)} itens. Filtrando com mais precisão...")

                    for item in itens_licitacao:
                        link_tag = item.find('a', class_='btn-default')
                        titulo_tag = item.find('h2')

                        if not all([link_tag, titulo_tag]): continue
                        
                        link_portal = "https://www.portaldecompraspublicas.com.br" + link_tag['href']
                        if link_portal in links_salvos: continue

                        objeto_raw = titulo_tag.find('a').get_text(strip=True) if titulo_tag.find('a') else "N/A"
                        objeto = objeto_raw.lower()
                        
                        if any(p_excluida in objeto for p_excluida in PALAVRAS_EXCLUIDAS): continue
                        
                        spans = item.find_all('span')
                        data_ab, orgao, uf_encontrada = "N/A", "N/A", "N/A"
                        
                        for span in spans:
                            if span.find('i', class_='cp-calendario'): data_ab = span.get_text(strip=True)
                            elif span.find('i', class_='cp-pin-mapa'):
                                orgao_uf_text = span.get_text(strip=True)
                                orgao_uf_split = orgao_uf_text.rsplit(' - ', 1)
                                orgao = orgao_uf_split[0]
                                if len(orgao_uf_split) > 1: uf_encontrada = orgao_uf_split[1]

                        if uf_encontrada != uf_sigla: continue
                        
                        print(f"  - Coletando detalhes de: {link_portal.split('/')[-1]}")
                        prazo_proposta, valor_total = extrair_valor_e_prazo(driver, link_portal)

                        num_lic_text = titulo_tag.find('span').get_text(strip=True) if titulo_tag.find('span') else "N/A"
                        
                        novas_licitacoes_encontradas += 1
                        print(f"  -> OPORTUNIDADE VÁLIDA: {orgao} ({uf_sigla}) - {num_lic_text} - Valor: {valor_total}")
                        
                        # Limpa as datas, pegando apenas a primeira parte (dd/mm/aaaa)
                        data_ab_limpa = data_ab.split(' ')[0]
                        prazo_proposta_limpo = prazo_proposta.split(' ')[0]

                        nova_linha = ['Aberto', data_ab_limpa, prazo_proposta_limpo, uf_sigla, orgao, num_lic_text, objeto_raw, link_portal, hoje_formatado, valor_total]
                        
                        worksheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                        links_salvos.add(link_portal)
                        time.sleep(1)

                except TimeoutException:
                    print(f"ERRO: A página demorou muito para responder ou não encontrou os resultados.")
                except Exception as e:
                    print(f"Ocorreu um erro ao processar a busca: {e}")

    except Exception as e:
        print(f"Ocorreu um erro geral durante a automação: {e}")
    finally:
        if driver:
            driver.quit()
        print(f"\n--- FIM DA BUSCA ---")
        print(f"Total de novas licitações adicionadas: {novas_licitacoes_encontradas}")

if __name__ == "__main__":
    main()

# Created by Jordanlvs 💼 All Rights Reserved. ®
