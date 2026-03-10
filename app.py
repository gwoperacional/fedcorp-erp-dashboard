import os
import shutil
import unicodedata
import re
import pdfplumber
import tempfile
import json
from flask import Flask, jsonify, send_from_directory, request, send_file
from datetime import datetime
from typing import List, Dict, Any
from openpyxl import load_workbook
from werkzeug.utils import secure_filename
from io import BytesIO
import zipfile

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
BASE_CONDOMINIOS_PATH = os.path.join(BASE_PATH, "BASE", "DADOS_CONDOMINIOS.xlsx")
PASTA_DOCS_PATH = os.path.join(BASE_PATH, "DOCUMENTOS_ANEXADOS")
PASTA_DOCUMENTOS_FINAL = os.path.join(BASE_PATH, "DOCUMENTOS")

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

def remover_acentos(texto):
    if not texto: return ""
    return unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")

def fixo(texto, tamanho):
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
            match_linha = re.search(r"(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d+\s+\d{14})", texto_completo)
            if match_linha:
                dados["linha_digitavel"] = match_linha.group(1).replace(" ", "")
            
            # Extrair vencimento (formato DD/MM/YYYY)
            match_vencimento = re.search(r"(\d{2}/\d{2}/\d{4})", texto_completo)
            if match_vencimento:
                dados["vencimento"] = match_vencimento.group(1)
            
            # Extrair valor (formato 1.234,56)
            match_valor = re.search(r"R\$\s*([\d.,]+)", texto_completo)
            if match_valor:
                valor_str = match_valor.group(1).replace(".", "").replace(",", ".")
                dados["valor"] = float(valor_str)
            
            # Usar primeiros dígitos como número da nota
            if dados["linha_digitavel"]:
                dados["numero_nota"] = dados["linha_digitavel"][:10]
    except Exception as e:
        print(f"Erro ao extrair dados do PDF: {e}")
    
    return dados

def converter_linha_para_codigo_barras(linha_digitavel):
    if not linha_digitavel or len(linha_digitavel) != 47:
        return None
    
    try:
        banco = linha_digitavel[0:3]
        moeda = linha_digitavel[3]
        vencimento = linha_digitavel[4:8]
        valor = linha_digitavel[8:18]
        campo_livre = linha_digitavel[18:47]
        
        codigo_barras = banco + moeda + vencimento + valor + campo_livre
        return codigo_barras
    except:
        return None

def carregar_condominios():
    condominios = {}
    try:
        if os.path.exists(BASE_CONDOMINIOS_PATH):
            wb = load_workbook(BASE_CONDOMINIOS_PATH)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[0]:  # CNPJ na coluna A
                    condominios[str(row[0])] = {
                        "nome": str(row[1]) if row[1] else "",
                        "codigo": str(row[2]) if row[2] else "0000"
                    }
    except Exception as e:
        print(f"Erro ao carregar condominios: {e}")
    
    return condominios

def processar_arquivo(nome_arquivo, caminho_entrada=None):
    resultado = {
        "arquivo": nome_arquivo,
        "status": "erro",
        "mensagem": "",
        "detalhes": {}
    }
    
    try:
        if caminho_entrada is None:
            caminho_entrada = os.path.join(ENTRADA_PATH, nome_arquivo)
        
        if not os.path.exists(caminho_entrada):
            resultado["mensagem"] = f"Arquivo não encontrado: {nome_arquivo}"
            return resultado
        
        # Extrair CNPJ do nome do arquivo
        cnpj_condominio = extrair_cnpj_do_nome_arquivo(nome_arquivo)
        if not cnpj_condominio:
            resultado["mensagem"] = "CNPJ não encontrado no nome do arquivo"
            if os.path.exists(caminho_entrada):
                try:
                    shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
                except:
                    pass
            return resultado
        
        # Carregar dados de condominios
        condominios = carregar_condominios()
        if cnpj_condominio not in condominios:
            resultado["mensagem"] = f"Condomínio com CNPJ {cnpj_condominio} não cadastrado"
            if os.path.exists(caminho_entrada):
                try:
                    shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
                except:
                    pass
            return resultado
        
        cond_info = condominios[cnpj_condominio]
        
        # Extrair dados do PDF
        dados_pdf = extrair_dados_pdf(caminho_entrada)
        if not dados_pdf["linha_digitavel"]:
            resultado["mensagem"] = "Não foi possível extrair a linha digitável do PDF"
            if os.path.exists(caminho_entrada):
                try:
                    shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
                except:
                    pass
            return resultado
        
        # Converter para código de barras
        codigo_barras = converter_linha_para_codigo_barras(dados_pdf["linha_digitavel"])
        if not codigo_barras:
            resultado["mensagem"] = "Código de barras inválido"
            if os.path.exists(caminho_entrada):
                try:
                    shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
                except:
                    pass
            return resultado
        
        # Preparar dados para arquivo de remessa
        vencimento = dados_pdf["vencimento"] or datetime.now().strftime("%d/%m/%Y")
        valor = dados_pdf["valor"] or 0.0
        numero_nota = dados_pdf["numero_nota"] or "0000000001"
        
        # Criar arquivo de remessa
        data_atual = datetime.now()
        competencia = data_atual.strftime("%m%Y")
        sequencial = "0001"
        
        # Registro 0 (Header)
        registro_0 = (
            "0" +
            fixo(FORNECEDOR_CNPJ, 14) +
            fixo(remover_acentos(FORNECEDOR_NOME), 60) +
            fixo(CNPJ_ADMIN, 14) +
            fixo(remover_acentos(NOME_ADMIN), 60) +
            fixo(competencia, 6) +
            fixo("", 241) +
            fixo(sequencial, 4)
        )
        
        # Registro 1 (Detalhe NF)
        codigo_cond_formatado = fixo(cond_info["codigo"], 4)
        registro_1 = (
            "1" +
            codigo_cond_formatado +
            fixo("", 4) +
            fixo(cnpj_condominio, 14) +
            fixo(remover_acentos(cond_info["nome"]), 60) +
            fixo(vencimento, 10) +
            fixo(f"{valor:012.2f}".replace(".", ","), 12) +
            fixo(codigo_barras, 44) +
            fixo(f"{valor:012.2f}".replace(".", ","), 12) +
            fixo("000000000,00", 12) +
            fixo("000000000,00", 12) +
            fixo("000000000,00", 12) +
            fixo("000000000,00", 12) +
            fixo("000000000,00", 12) +
            fixo("N", 1) +
            fixo(vencimento, 10) +
            fixo(numero_nota, 10) +
            fixo("", 95) +
            fixo(sequencial, 4)
        )
        
        # Registro 2 (Detalhe Itens)
        registro_2 = (
            "2" +
            fixo("", 10) +
            fixo("", 60) +
            fixo("000000000,00", 12) +
            fixo(f"{valor:012.2f}".replace(".", ","), 12) +
            fixo(f"{valor:012.2f}".replace(".", ","), 12) +
            fixo("", 263) +
            fixo(sequencial, 4)
        )
        
        # Registro 3 (Documentos)
        ano_mes = data_atual.strftime("%Y/%m")
        url_documento = f"https://fedcorp-erp-dashboard.onrender.com/docs/{ano_mes}/{nome_arquivo}"
        registro_3 = (
            "3" +
            fixo(sequencial, 4) +
            fixo(numero_nota, 10) +
            fixo(url_documento, 300) +
            fixo("", 81) +
            fixo(sequencial, 4)
        )
        
        # Salvar arquivo de remessa
        nome_remessa = f"remessa_{data_atual.strftime('%Y%m%d_%H%M%S')}.txt"
        caminho_remessa = os.path.join(GERADAS_PATH, nome_remessa)
        
        os.makedirs(GERADAS_PATH, exist_ok=True)
        with open(caminho_remessa, 'w', encoding='utf-8') as f:
            f.write(registro_0 + "\n")
            f.write(registro_1 + "\n")
            f.write(registro_2 + "\n")
            f.write(registro_3 + "\n")
        
        # Copiar PDF para pasta de documentos
        os.makedirs(os.path.join(PASTA_DOCS_PATH, ano_mes), exist_ok=True)
        caminho_docs = os.path.join(PASTA_DOCS_PATH, ano_mes, nome_arquivo)
        try:
            shutil.copy2(caminho_entrada, caminho_docs)
        except:
            pass
        
        # Mover PDF para pasta final (apenas se for do ENTRADA_PATH)
        if caminho_entrada == os.path.join(ENTRADA_PATH, nome_arquivo):
            os.makedirs(PASTA_DOCUMENTOS_FINAL, exist_ok=True)
            try:
                shutil.move(caminho_entrada, os.path.join(PASTA_DOCUMENTOS_FINAL, nome_arquivo))
            except:
                pass
        
        resultado["status"] = "sucesso"
        resultado["mensagem"] = f"Arquivo processado com sucesso"
        resultado["detalhes"] = {
            "remessa": nome_remessa,
            "condominio": cond_info["nome"],
            "valor": f"R$ {valor:.2f}",
            "vencimento": vencimento,
            "cnpj": cnpj_condominio
        }
    
    except Exception as e:
        resultado["mensagem"] = f"Erro ao processar: {str(e)}"
    
    return resultado

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
        resultados = {
            "total": len(files),
            "sucesso": 0,
            "erros": 0,
            "detalhes": []
        }
        
        for file in files:
            if file and file.filename.lower().endswith('.pdf'):
                try:
                    # Salvar arquivo temporário
                    filename = secure_filename(file.filename)
                    temp_path = os.path.join(TEMP_UPLOAD_PATH, filename)
                    file.save(temp_path)
                    
                    # Processar arquivo
                    resultado = processar_arquivo(filename, temp_path)
                    resultados["detalhes"].append(resultado)
                    
                    if resultado["status"] == "sucesso":
                        resultados["sucesso"] += 1
                    else:
                        resultados["erros"] += 1
                    
                    # Limpar arquivo temporário
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
        
        return jsonify(resultados)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/api/download-remessas', methods=['GET'])
def download_remessas():
    try:
        os.makedirs(GERADAS_PATH, exist_ok=True)
        
        # Listar todos os arquivos de remessa
        remessas = [f for f in os.listdir(GERADAS_PATH) if f.endswith('.txt')]
        
        if not remessas:
            return jsonify({"erro": "Nenhuma remessa disponível"}), 404
        
        # Criar ZIP com todas as remessas
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
        
        arquivos = [f for f in os.listdir(ENTRADA_PATH) if f.lower().endswith('.pdf')]
        
        resultados = {
            "total": len(arquivos),
            "sucesso": 0,
            "avisos": 0,
            "erros": 0,
            "detalhes": []
        }
        
        for arquivo in arquivos:
            resultado = processar_arquivo(arquivo)
            resultados["detalhes"].append(resultado)
            
            if resultado["status"] == "sucesso":
                resultados["sucesso"] += 1
            elif resultado["status"] == "aviso":
                resultados["avisos"] += 1
            else:
                resultados["erros"] += 1
        
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
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
