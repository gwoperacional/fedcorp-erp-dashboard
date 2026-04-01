import os
import shutil
import unicodedata
import re
import pdfplumber
import tempfile
import json
import subprocess
from flask import Flask, jsonify, send_from_directory, request, send_file
from datetime import datetime
from typing import List, Dict, Any
from openpyxl import load_workbook
from werkzeug.utils import secure_filename
from io import BytesIO
import zipfile

# Google Drive não requer imports especiais - usaremos rclone ou URL direta

# Configurar o caminho correto para os arquivos estáticos
static_folder = os.path.join(os.path.dirname(__file__), 'dist', 'public')
if not os.path.exists(static_folder):
    static_folder = os.path.join(os.path.dirname(__file__), 'dist')

app = Flask(__name__, static_folder=static_folder, static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Configurações de Caminhos
BASE_PATH = os.getenv("BASE_PATH", r"G:\Wallpaper\FEDCORP_PROCESSADOR")
ENTRADA_PATH = os.path.join(BASE_PATH, "ENTRADA")
GERADAS_PATH = os.path.join(BASE_PATH, "REMESSAS_GERADAS")
NAO_PROCESSADOS_PATH = os.path.join(BASE_PATH, "NAO_PROCESSADOS")
PASTA_DOCS_PATH = os.path.join(BASE_PATH, "DOCUMENTOS_ANEXADOS")

# Google Drive Configuration
GOOGLE_DRIVE_FOLDER_ID = "1d-JrBnAEc9Al8wyKQkjENiIk6pte9Jqv"
GOOGLE_DRIVE_CREDENTIALS = {
    "type": "service_account",
    "project_id": "fedcorp-dashboard",
    "private_key_id": "639e51866beca0e27781366862ec4b687a823fd4",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDWBHU5cWKMqZg+\nQuHCfEIgMrqsO8877sBjRMbv34rPLKufIgGia1d/QXZ7oOn4B/HPg+adZQLd9coL\nX1mu6G2qHV7i7mDpYmOzWylUKqsgp8cUv7TpuZz36JEQVOjyLO+H1aarghCV08sn\ndlfqnRqawyt4H2FpUR8ubzgaHNP/t0+fYlqc6GkGCktndQo/toDzytPYzNXIb30I\nWCX5pcMpd2cLS1OBebRrqrJsYqtFvxOl8GdYrBwv6KVwm1hp+1qyMs/nkZ31xU7u\n3Q4nJ0U7ApnIy7JuKhgcdrhNuQJV+fQ0OiR/p3heQmgYHZz/qwVP30BZcWuF9ibP\nfBioSJ75AgMBAAECggEAQ0k2g79asQe3Bkgny2oerhnU58aMEncvRGaAtzTMYvNT\n592crvBZm3g85ISEWsdAprH9BNoXqyoWAjpRq3SG2feO+ADjNi0JVH/iQASENemZ\n5TOakOsa5zRWu1A+xrkK++VXl892IGzsj7Uc0fXfwe1/kq4nBaIMECDGfis3Gct4\ni8+8rryNYZLfbmQ8rmuyvTnUp/F43TtF5gpcd8KgbDkjDFcm+uIBPiW+cm1yv01q\nJVGt8g0oZPFJPBjonweGNzyds9FM6bZiUh2ZPs4YQznJdjoWR6iWa2NsLynl5KcA\nEjk6eWMusK+0JwBlL3fyMqkA8RSkSTL67M8xjK4lawKBgQDse9ATBfxqeyCIiBkR\nVFsELr1T6TferopbTIX81nd4WTsLqrryBKBc+XegSE3wGkZtNyy8wJadFT+rsKwW\np0nVck/NDv1Qd+5ILc1YDa5RZrXD80ySFe9+fg4Lx5IWIVBrTUZa8P5l37tMPsdc\nkhX8CVGUCyVMhP62DhBQ3jfXjwKBgQDnrgBXhjVA9MEIo4og2xn4nig1JkqdBwVE\nG7jiDJ9+2u0hAd/mT6FckCYa0TrNwonVdNX6DUn3OQEsuPs4C5xgkbwsSE5rHIDB\ntIUWR01Xe2PX0/L6baZ8q4mMVMazXo1711yw3k/QWq2jmja8E/zYyawsg04pDqFT\nLO2xQ+wc9wKBgQDprvuRINQqgJtIb3yd9EawXmN2XLp50O4lg/vPOjr6cOp4//AW\nId45ocbFW02w2rYHTINnzcPHW+z8Auw6wnqicoBK+On2r1yGdMQ6o+JCzAUHqg9b\nOFPeIkBNAZvpRGhMcCL60LQDBU/26v5kCnOxB6BWc6Ea+T0dt84Fq2FxHwKBgQC7\ncB06sowXN22NLbKtDlaevGZPSeGH1Yw/JCaaTBgmK705vSiGTtp/5ufNPoXSvpeB\nKPuNSH8VEvuOUUJ+f3ZO8tlJAl7fbboF/aTG93ztUBjhHsswLNJLfwTTkisIJ3FU\nRlLpjZMJQLPG7xdlZs5kHhW8FaeAtCN1BZ5wkkFO1QKBgHcKhaNg3dZbZl7dNf2A\npmgKicG5D3QdBqgJJeWpYGQGfJjmdE0Nl0rCzvxDmjunsfEOR+Gpv5JdB4r4FkA+\n4MXnwaZHrV/EbVxa+dkpt/2OpoVFaDsYn/L+wAqaiBKWHUFHagICYpqf6Jy7Tm4c\np0XxpIRacyqnvNufYIVRutg5\n-----END PRIVATE KEY-----\n",
    "client_email": "fedcorp-uploader@fedcorp-dashboard.iam.gserviceaccount.com",
    "client_id": "108990766178617167931",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/fedcorp-uploader%40fedcorp-dashboard.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

# Possíveis caminhos para o arquivo de condominios
POSSIBLE_PATHS = [
    os.path.join(BASE_PATH, "BASE", "DADOS_CONDOMINIOS.xlsx"),
    os.path.join(os.path.dirname(__file__), "BASE", "DADOS_CONDOMINIOS.xlsx"),
    os.path.join(os.path.dirname(__file__), "DADOS_CONDOMINIOS.xlsx"),
    "/app/BASE/DADOS_CONDOMINIOS.xlsx",
    "BASE/DADOS_CONDOMINIOS.xlsx",
]

# Pasta temporária para uploads
TEMP_UPLOAD_PATH = os.path.join(tempfile.gettempdir(), "fedcorp_uploads")
os.makedirs(TEMP_UPLOAD_PATH, exist_ok=True)

# Dados Fixos para Seguro de Vida (FEDCORP)
CNPJ_ADMIN = "26231209000150"
NOME_ADMIN = "GW ADMINISTRADORA DE CONDOMINIOS LTDA"
FORNECEDOR_CNPJ = "35315360000167"
FORNECEDOR_NOME = "FEDCORP ADMINISTRADORA DE BENEFICIOS LTDA"
COD_FORNECEDOR_ERP = "24196"
COD_PRODUTO_ERP = "SEGUROVIDA"
DESC_PRODUTO_ERP = ""

# Cache de condominios em memória
CONDOMINIOS_CACHE = None
CACHE_TIMESTAMP = None

def fazer_upload_google_drive(caminho_arquivo, nome_arquivo):
    """Tenta fazer upload para Google Drive usando rclone"""
    try:
        print(f"📤 Tentando upload para Google Drive: {nome_arquivo}")
        
        # Tentar usar rclone
        resultado = subprocess.run(
            ["rclone", "copy", caminho_arquivo, f"gdrive:{GOOGLE_DRIVE_FOLDER_ID}/"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if resultado.returncode == 0:
            print(f"✅ Upload rclone bem-sucedido")
            # Retornar URL da pasta como fallback
            return f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}?usp=sharing"
        else:
            print(f"⚠️ rclone não disponível ou erro: {resultado.stderr}")
            # Usar URL da pasta como fallback
            return f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}?usp=sharing"
    
    except Exception as e:
        print(f"⚠️ Erro ao fazer upload: {e}")
        # Usar URL da pasta como fallback
        return f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}?usp=sharing"

def remover_acentos(texto):
    if not texto: return ""
    return unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")

def fixo(texto, tamanho):
    """Preenche texto com espaços em branco até o tamanho especificado"""
    return str(texto).ljust(tamanho)[:tamanho]

def extrair_cnpj_do_nome_arquivo(nome_arquivo):
    match = re.search(r"\d{14}", nome_arquivo)
    return match.group() if match else None

def extrair_dados_pdf(pdf_path):
    dados = {"linha_digitavel": None, "numero_nota": None, "vencimento": None, "valor": None}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto_completo = ""
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t: texto_completo += t + "\n"
            
            # Extrair linha digitável
            regex_linha = r"\d{5}[\.\s]?\d{5}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d[\.\s]?\d{14}"
            match_linha = re.search(regex_linha, texto_completo)
            if match_linha:
                dados["linha_digitavel"] = re.sub(r"\D", "", match_linha.group())
            
            # Extrair número da nota
            match_nota = re.search(r"(?:FATURA|NOTA|DOC|Nº|NUMERO)[:\s]+(\d+)", texto_completo, re.IGNORECASE)
            if match_nota:
                dados["numero_nota"] = match_nota.group(1)
            
            # Extrair vencimento
            match_venc = re.search(r"Vencimento\s+(\d{2}/\d{2}/\d{4})", texto_completo, re.IGNORECASE)
            if match_venc:
                dados["vencimento"] = match_venc.group(1)
            else:
                match_venc = re.search(r"ATE O VENCIMENTO\s+(\d{2}/\d{2}/\d{4})", texto_completo)
                if match_venc:
                    dados["vencimento"] = match_venc.group(1)
            
            # Extrair valor
            match_valor = re.search(r"VALOR TOTAL:?\s*R\$\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
            if match_valor:
                dados["valor"] = match_valor.group(1).replace(".", "").replace(",", ".")
    except Exception as e:
        print(f"Erro ao extrair dados do PDF: {e}")
    
    return dados

def linha_digitavel_para_codigo_barras(linha):
    """Converte linha digitável para código de barras"""
    linha = re.sub(r"\D", "", linha)
    
    if len(linha) == 50:
        linha = linha[:47]
    
    if len(linha) != 47:
        return None
    
    try:
        banco = linha[0:3]
        moeda = linha[3:4]
        campo1 = linha[4:9]
        campo2 = linha[10:20]
        campo3 = linha[21:31]
        dv_geral = linha[32:33]
        fator_venc_valor = linha[33:47]
        
        codigo_barras = banco + moeda + dv_geral + fator_venc_valor + campo1 + campo2 + campo3
        return codigo_barras
    except:
        return None

def formatar_valor_ahreas(valor_float):
    """Formata valor para 12 posições com vírgula"""
    return f"{valor_float:012.2f}".replace(".", ",")

def carregar_condominios():
    """Carrega condominios de arquivo Excel"""
    global CONDOMINIOS_CACHE, CACHE_TIMESTAMP
    
    if CONDOMINIOS_CACHE is not None:
        if CACHE_TIMESTAMP and (datetime.now() - CACHE_TIMESTAMP).seconds < 300:
            return CONDOMINIOS_CACHE
    
    condominios = {}
    arquivo_encontrado = None
    
    for caminho in POSSIBLE_PATHS:
        if os.path.exists(caminho):
            arquivo_encontrado = caminho
            print(f"✅ Arquivo de condominios encontrado em: {caminho}")
            break
    
    if arquivo_encontrado:
        try:
            wb = load_workbook(arquivo_encontrado)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[3]:
                    cnpj = str(row[3]).strip()
                    cnpj = cnpj.replace(".", "").replace("-", "").replace("/", "")
                    if len(cnpj) >= 14:
                        cnpj = cnpj[:14]
                    
                    condominios[cnpj] = {
                        "nome": str(row[1]) if row[1] else "",
                        "codigo": str(int(row[0])).zfill(4) if row[0] else "0000"
                    }
            print(f"✅ Carregados {len(condominios)} condominios")
        except Exception as e:
            print(f"⚠️ Erro ao carregar: {e}")
    else:
        print("⚠️ Arquivo não encontrado, usando dados embutidos")
    
    if not condominios:
        condominios = {
            "65169906000180": {
                "nome": "CONDOMINIO EDIFICIO GROPIUS",
                "codigo": "0762"
            }
        }
    
    CONDOMINIOS_CACHE = condominios
    CACHE_TIMESTAMP = datetime.now()
    
    return condominios

def processar_arquivo(nome_arquivo, caminho_entrada=None):
    """Processa um arquivo PDF"""
    resultado = {
        "arquivo": nome_arquivo,
        "status": "erro",
        "mensagem": "",
        "dados": None
    }
    
    try:
        if caminho_entrada is None:
            caminho_entrada = os.path.join(ENTRADA_PATH, nome_arquivo)
        
        if not os.path.exists(caminho_entrada):
            resultado["mensagem"] = f"Arquivo não encontrado"
            return resultado
        
        # Extrair CNPJ
        cnpj_condominio = extrair_cnpj_do_nome_arquivo(nome_arquivo)
        if not cnpj_condominio:
            resultado["mensagem"] = "CNPJ não encontrado no nome"
            return resultado
        
        # Carregar condominios
        condominios = carregar_condominios()
        
        if cnpj_condominio not in condominios:
            cnpj_limpo = cnpj_condominio.replace(".", "").replace("-", "").replace("/", "")
            if len(cnpj_limpo) >= 14:
                cnpj_limpo = cnpj_limpo[:14]
            if cnpj_limpo not in condominios:
                resultado["mensagem"] = f"Condomínio com CNPJ {cnpj_condominio} não cadastrado"
                return resultado
            cnpj_condominio = cnpj_limpo
        
        cond_info = condominios[cnpj_condominio]
        
        # Extrair dados do PDF
        dados_pdf = extrair_dados_pdf(caminho_entrada)
        if not dados_pdf["linha_digitavel"]:
            resultado["mensagem"] = "Não foi possível extrair a linha digitável"
            return resultado
        
        # Converter para código de barras
        codigo_barras = linha_digitavel_para_codigo_barras(dados_pdf["linha_digitavel"])
        if not codigo_barras:
            resultado["mensagem"] = "Código de barras inválido"
            return resultado
        
        # Preparar dados
        agora = datetime.now()
        vencimento = dados_pdf["vencimento"] if dados_pdf["vencimento"] else agora.strftime("%d/%m/%Y")
        data_emissao = agora.strftime("%d/%m/%Y")
        valor_float = float(dados_pdf["valor"]) if dados_pdf["valor"] else 0.0
        valor_formatado = formatar_valor_ahreas(valor_float)
        cod_cond_erp = cond_info["codigo"].zfill(4)
        nome_cond_erp = fixo(remover_acentos(cond_info["nome"]).upper(), 50)
        
        # Copiar para pasta local
        ano_atual = agora.strftime("%Y")
        mes_atual = agora.strftime("%m")
        pasta_destino_docs = os.path.join(PASTA_DOCS_PATH, ano_atual, mes_atual)
        os.makedirs(pasta_destino_docs, exist_ok=True)
        caminho_pdf_destino = os.path.join(pasta_destino_docs, nome_arquivo)
        try:
            shutil.copy(caminho_entrada, caminho_pdf_destino)
        except Exception as e:
            print(f"Aviso: Não foi possível copiar para pasta local: {e}")
        
        # Fazer upload para Google Drive
        url_google_drive = fazer_upload_google_drive(caminho_entrada, nome_arquivo)
        
        # Retornar dados
        resultado["status"] = "sucesso"
        resultado["mensagem"] = "Arquivo processado com sucesso"
        resultado["dados"] = {
            "cnpj": cnpj_condominio,
            "cod_cond": cod_cond_erp,
            "nome_cond": nome_cond_erp,
            "vencimento": vencimento,
            "data_emissao": data_emissao,
            "valor_formatado": valor_formatado,
            "valor_float": valor_float,
            "codigo_barras": codigo_barras,
            "nome_arquivo": nome_arquivo,
            "caminho_pdf": caminho_pdf_destino,
            "url_google_drive": url_google_drive if url_google_drive else "",
            "ano": ano_atual,
            "mes": mes_atual
        }
    
    except Exception as e:
        resultado["mensagem"] = f"Erro ao processar: {str(e)}"
        import traceback
        print(traceback.format_exc())
    
    return resultado

def gerar_remessa_lote(lista_dados, competencia=None):
    """Gera remessa única com múltiplos registros"""
    if not lista_dados:
        return None
    
    agora = datetime.now()
    if not competencia:
        competencia = agora.strftime("%m%Y")
    
    linhas = []
    
    # REGISTRO 0 - HEADER
    header = (
        "0" +
        FORNECEDOR_CNPJ.zfill(14) +
        fixo(remover_acentos(FORNECEDOR_NOME).upper(), 60) +
        CNPJ_ADMIN.zfill(14) +
        fixo(remover_acentos(NOME_ADMIN).upper(), 60) +
        competencia +
        " " * 241 +
        "0001"
    )
    linhas.append(fixo(header, 400))
    
    # REGISTROS 1, 2 e 3 para cada boleto
    sequencial = 2
    for dados in lista_dados:
        # REGISTRO 1
        registro_1 = (
            "1" +
            dados["cod_cond"] +
            "    " +
            dados["cnpj"].zfill(14) +
            dados["nome_cond"] +
            dados["vencimento"] +
            dados["valor_formatado"] +
            dados["codigo_barras"] +
            dados["valor_formatado"] +
            "000000000,00" +
            "000000000,00" +
            "000000000,00" +
            "000000000,00" +
            "000000000,00" +
            "N" +
            "          " +
            "          " +
            "     " +
            "     " +
            " " * 154 +
            str(sequencial).zfill(4)
        )
        linhas.append(fixo(registro_1, 400))
        
        # REGISTRO 2
        registro_2 = (
            "2" +
            fixo(COD_PRODUTO_ERP, 10) +
            fixo(DESC_PRODUTO_ERP, 60) +
            "000000000,00" +
            dados["valor_formatado"] +
            dados["valor_formatado"] +
            " " * 289 +
            str(sequencial).zfill(4)
        )
        linhas.append(fixo(registro_2, 400))
        
        # REGISTRO 3 com URL
        url_pdf = dados.get("url_google_drive", "")
        if not url_pdf:
            url_pdf = ""
        
        tamanho_fixo = 1 + 6 + 6 + 12 + 4
        tamanho_url = len(url_pdf)
        tamanho_espacos = 400 - tamanho_fixo - tamanho_url
        
        trailer_boleto = (
            "3" +
            "000001" +
            "000001" +
            dados["valor_formatado"] +
            url_pdf +
            " " * max(0, tamanho_espacos) +
            str(sequencial).zfill(4)
        )
        linhas.append(fixo(trailer_boleto, 400))
        
        sequencial += 1
    
    return "\n".join(linhas)

# Rotas da API
@app.route('/')
def index():
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, 'index.html')
    else:
        return jsonify({
            "status": "error",
            "message": "index.html não encontrado",
            "static_folder": app.static_folder
        }), 404

@app.route('/api/pending-files', methods=['GET'])
def pending_files():
    try:
        os.makedirs(ENTRADA_PATH, exist_ok=True)
        arquivos = [f for f in os.listdir(ENTRADA_PATH) if f.lower().endswith('.pdf')]
        return jsonify({
            "total": len(arquivos),
            "arquivos": arquivos
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({"erro": "Nenhum arquivo enviado"}), 400
        
        files = request.files.getlist('files')
        modo_lote = request.form.get('modo_lote', 'false').lower() == 'true'
        
        resultados = {
            "total": len(files),
            "sucesso": 0,
            "erros": 0,
            "modo_lote": modo_lote,
            "remessa": None,
            "detalhes": []
        }
        
        lista_dados_processados = []
        
        for file in files:
            if file and file.filename.lower().endswith('.pdf'):
                try:
                    filename = secure_filename(file.filename)
                    temp_path = os.path.join(TEMP_UPLOAD_PATH, filename)
                    file.save(temp_path)
                    
                    resultado = processar_arquivo(filename, temp_path)
                    resultados["detalhes"].append(resultado)
                    
                    if resultado["status"] == "sucesso":
                        resultados["sucesso"] += 1
                        if modo_lote:
                            lista_dados_processados.append(resultado["dados"])
                    else:
                        resultados["erros"] += 1
                    
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                
                except Exception as e:
                    resultados["erros"] += 1
                    resultados["detalhes"].append({
                        "arquivo": file.filename,
                        "status": "erro",
                        "mensagem": str(e)
                    })
        
        # Se modo lote
        if modo_lote and lista_dados_processados:
            try:
                agora = datetime.now()
                competencia = agora.strftime("%m%Y")
                conteudo_remessa = gerar_remessa_lote(lista_dados_processados, competencia)
                
                nome_remessa = f"REMESSA_FEDCORP_LOTE_{agora.strftime('%Y%m%d%H%M%S')}.txt"
                caminho_remessa = os.path.join(GERADAS_PATH, nome_remessa)
                
                os.makedirs(GERADAS_PATH, exist_ok=True)
                with open(caminho_remessa, 'w', encoding='utf-8') as f:
                    f.write(conteudo_remessa)
                
                resultados["remessa"] = nome_remessa
                
                for dados in lista_dados_processados:
                    try:
                        caminho_origem = os.path.join(ENTRADA_PATH, dados["nome_arquivo"])
                        if os.path.exists(caminho_origem):
                            shutil.move(caminho_origem, os.path.join(GERADAS_PATH, dados["nome_arquivo"]))
                    except:
                        pass
            
            except Exception as e:
                resultados["erro_lote"] = str(e)
        
        return jsonify(resultados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/api/download-remessas', methods=['GET'])
def download_remessas():
    try:
        os.makedirs(GERADAS_PATH, exist_ok=True)
        
        remessas = [f for f in os.listdir(GERADAS_PATH) if f.endswith('.txt')]
        
        if not remessas:
            return jsonify({"erro": "Nenhuma remessa disponível"}), 404
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for remessa in remessas:
                remessa_path = os.path.join(GERADAS_PATH, remessa)
                zip_file.write(remessa_path, arcname=remessa)
        
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'remessas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/processar', methods=['POST'])
def processar():
    try:
        os.makedirs(ENTRADA_PATH, exist_ok=True)
        os.makedirs(GERADAS_PATH, exist_ok=True)
        os.makedirs(NAO_PROCESSADOS_PATH, exist_ok=True)
        
        modo_lote = request.json.get('modo_lote', False) if request.json else False
        
        arquivos = [f for f in os.listdir(ENTRADA_PATH) if f.lower().endswith('.pdf')]
        
        resultados = {
            "total": len(arquivos),
            "sucesso": 0,
            "avisos": 0,
            "erros": 0,
            "modo_lote": modo_lote,
            "remessa": None,
            "detalhes": []
        }
        
        lista_dados_processados = []
        
        for arquivo in arquivos:
            resultado = processar_arquivo(arquivo)
            if resultado["status"] == "sucesso":
                resultados["sucesso"] += 1
                if modo_lote:
                    lista_dados_processados.append(resultado.get("dados"))
            else:
                resultados["erros"] += 1
            resultados["detalhes"].append(resultado)
        
        if modo_lote and lista_dados_processados:
            try:
                agora = datetime.now()
                competencia = agora.strftime("%m%Y")
                conteudo_remessa = gerar_remessa_lote(lista_dados_processados, competencia)
                
                nome_remessa = f"REMESSA_FEDCORP_LOTE_{agora.strftime('%Y%m%d%H%M%S')}.txt"
                caminho_remessa = os.path.join(GERADAS_PATH, nome_remessa)
                
                os.makedirs(GERADAS_PATH, exist_ok=True)
                with open(caminho_remessa, 'w', encoding='utf-8') as f:
                    f.write(conteudo_remessa)
                
                resultados["remessa"] = nome_remessa
                
                for arquivo in arquivos:
                    try:
                        caminho_origem = os.path.join(ENTRADA_PATH, arquivo)
                        if os.path.exists(caminho_origem):
                            shutil.move(caminho_origem, os.path.join(GERADAS_PATH, arquivo))
                    except:
                        pass
            
            except Exception as e:
                resultados["erro_lote"] = str(e)
        
        return jsonify(resultados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/docs/<ano>/<mes>/<arquivo>')
def servir_documento(ano, mes, arquivo):
    try:
        caminho = os.path.join(PASTA_DOCS_PATH, ano, mes, arquivo)
        if os.path.exists(caminho):
            return send_from_directory(os.path.dirname(caminho), arquivo)
        return jsonify({"erro": "Arquivo não encontrado"}), 404
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/<path:filename>')
def static_files(filename):
    try:
        return send_from_directory(app.static_folder, filename)
    except:
        try:
            return send_from_directory(app.static_folder, 'index.html')
        except:
            return jsonify({"erro": "Arquivo não encontrado"}), 404

if __name__ == '__main__':
    print("🚀 Iniciando FEDCORP ERP Dashboard...")
    print(f"📁 BASE_PATH: {BASE_PATH}")
    print(f"☁️ Google Drive Folder: {GOOGLE_DRIVE_FOLDER_ID}")
    
    # Pré-carregar condominios
    print("📝 Carregando dados de condominios...")
    condominios = carregar_condominios()
    print(f"✅ {len(condominios)} condominio(s) carregado(s)")
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
