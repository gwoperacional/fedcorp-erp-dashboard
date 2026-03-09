import os
import shutil
import unicodedata
import re
import pdfplumber
from flask import Flask, jsonify, send_from_directory
from datetime import datetime
from typing import List, Dict, Any
from openpyxl import load_workbook

# Configurar o caminho correto para os arquivos estáticos
static_folder = os.path.join(os.path.dirname(__file__), 'dist', 'public')
if not os.path.exists(static_folder):
    # Se dist/public não existir, tenta apenas dist
    static_folder = os.path.join(os.path.dirname(__file__), 'dist')

app = Flask(__name__, static_folder=static_folder, static_url_path='')

# Configurações de Caminhos
BASE_PATH = os.getenv("BASE_PATH", r"G:\Wallpaper\FEDCORP_PROCESSADOR")
ENTRADA_PATH = os.path.join(BASE_PATH, "ENTRADA")
GERADAS_PATH = os.path.join(BASE_PATH, "REMESSAS_GERADAS")
NAO_PROCESSADOS_PATH = os.path.join(BASE_PATH, "NAO_PROCESSADOS")
BASE_CONDOMINIOS_PATH = os.path.join(BASE_PATH, "BASE", "DADOS_CONDOMINIOS.xlsx")
PASTA_DOCS_PATH = os.path.join(BASE_PATH, "DOCUMENTOS_ANEXADOS")
PASTA_DOCUMENTOS_FINAL = os.path.join(BASE_PATH, "DOCUMENTOS")

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

def processar_arquivo(nome_arquivo):
    resultado = {
        "arquivo": nome_arquivo,
        "status": "erro",
        "mensagem": "",
        "detalhes": {}
    }
    
    try:
        caminho_entrada = os.path.join(ENTRADA_PATH, nome_arquivo)
        
        if not os.path.exists(caminho_entrada):
            resultado["mensagem"] = f"Arquivo não encontrado: {nome_arquivo}"
            return resultado
        
        # Extrair CNPJ do nome do arquivo
        cnpj_condominio = extrair_cnpj_do_nome_arquivo(nome_arquivo)
        if not cnpj_condominio:
            resultado["mensagem"] = "CNPJ não encontrado no nome do arquivo"
            shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
            return resultado
        
        # Carregar dados de condominios
        condominios = carregar_condominios()
        if cnpj_condominio not in condominios:
            resultado["mensagem"] = f"Condomínio com CNPJ {cnpj_condominio} não cadastrado"
            shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
            return resultado
        
        cond_info = condominios[cnpj_condominio]
        
        # Extrair dados do PDF
        dados_pdf = extrair_dados_pdf(caminho_entrada)
        if not dados_pdf["linha_digitavel"]:
            resultado["mensagem"] = "Não foi possível extrair a linha digitável do PDF"
            shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
            return resultado
        
        # Converter para código de barras
        codigo_barras = converter_linha_para_codigo_barras(dados_pdf["linha_digitavel"])
        if not codigo_barras:
            resultado["mensagem"] = "Código de barras inválido"
            shutil.move(caminho_entrada, os.path.join(NAO_PROCESSADOS_PATH, nome_arquivo))
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
        url_documento = f"http://127.0.0.1:5000/docs/{ano_mes}/{nome_arquivo}"
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
        
        with open(caminho_remessa, 'w', encoding='utf-8') as f:
            f.write(registro_0 + "\n")
            f.write(registro_1 + "\n")
            f.write(registro_2 + "\n")
            f.write(registro_3 + "\n")
        
        # Copiar PDF para pasta de documentos
        os.makedirs(os.path.join(PASTA_DOCS_PATH, ano_mes), exist_ok=True)
        caminho_docs = os.path.join(PASTA_DOCS_PATH, ano_mes, nome_arquivo)
        shutil.copy2(caminho_entrada, caminho_docs)
        
        # Mover PDF para pasta final
        os.makedirs(PASTA_DOCUMENTOS_FINAL, exist_ok=True)
        shutil.move(caminho_entrada, os.path.join(PASTA_DOCUMENTOS_FINAL, nome_arquivo))
        
        resultado["status"] = "sucesso"
        resultado["mensagem"] = f"Arquivo processado com sucesso"
        resultado["detalhes"] = {
            "remessa": nome_remessa,
            "condominio": cond_info["nome"],
            "valor": f"R$ {valor:.2f}",
            "vencimento": vencimento
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
        # Debug: mostrar o caminho que está procurando
        return jsonify({
            "status": "error",
            "message": "index.html não encontrado",
            "static_folder": app.static_folder,
            "index_path": index_path,
            "exists": os.path.exists(index_path),
            "files_in_static": os.listdir(app.static_folder) if os.path.exists(app.static_folder) else []
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
        # Se o arquivo não existir, serve o index.html (para client-side routing)
        try:
            return send_from_directory(app.static_folder, 'index.html')
        except:
            return jsonify({"erro": "Arquivo não encontrado"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
