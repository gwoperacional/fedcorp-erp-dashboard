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
PASTA_DOCS_PATH = os.path.join(BASE_PATH, "DOCUMENTOS_ANEXADOS")

# Possíveis caminhos para o arquivo de condominios
POSSIBLE_PATHS = [
    os.path.join(BASE_PATH, "BASE", "DADOS_CONDOMINIOS.xlsx"),
    os.path.join(os.path.dirname(__file__), "BASE", "DADOS_CONDOMINIOS.xlsx"),
    os.path.join(os.path.dirname(__file__), "DADOS_CONDOMINIOS.xlsx"),
    "/app/BASE/DADOS_CONDOMINIOS.xlsx",  # Render path
    "BASE/DADOS_CONDOMINIOS.xlsx",
]

# Pasta temporária para uploads
TEMP_UPLOAD_PATH = os.path.join(tempfile.gettempdir(), "fedcorp_uploads")
os.makedirs(TEMP_UPLOAD_PATH, exist_ok=True)

# Pasta para armazenar PDFs processados (no Render)
DOCS_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "docs")
os.makedirs(DOCS_STORAGE_PATH, exist_ok=True)

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
            
            # Extrair linha digitável com regex flexível
            regex_linha = r"\d{5}[\.\s]?\d{5}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d[\.\s]?\d{14}"
            match_linha = re.search(regex_linha, texto_completo)
            if match_linha:
                dados["linha_digitavel"] = re.sub(r"\D", "", match_linha.group())
            
            # Extrair número da nota
            match_nota = re.search(r"(?:FATURA|NOTA|DOC|Nº|NUMERO)[:\s]+(\d+)", texto_completo, re.IGNORECASE)
            if match_nota:
                dados["numero_nota"] = match_nota.group(1)
            
            # Extrair vencimento - procurar por "Vencimento" primeiro
            match_venc = re.search(r"Vencimento\s+(\d{2}/\d{2}/\d{4})", texto_completo, re.IGNORECASE)
            if match_venc:
                dados["vencimento"] = match_venc.group(1)
            else:
                # Fallback: procurar por "ATE O VENCIMENTO"
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
    """Converte linha digitável para código de barras usando algoritmo correto"""
    linha = re.sub(r"\D", "", linha)
    
    # Aceitar 47 ou 50 caracteres
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
    """Formata valor para 12 posições com vírgula: 000000000,00"""
    return f"{valor_float:012.2f}".replace(".", ",")

def carregar_condominios():
    """Carrega condominios de arquivo Excel com fallback para dados embutidos"""
    global CONDOMINIOS_CACHE, CACHE_TIMESTAMP
    
    # Usar cache se disponível (válido por 5 minutos)
    if CONDOMINIOS_CACHE is not None:
        if CACHE_TIMESTAMP and (datetime.now() - CACHE_TIMESTAMP).seconds < 300:
            return CONDOMINIOS_CACHE
    
    condominios = {}
    arquivo_encontrado = None
    
    # Tentar encontrar o arquivo em vários caminhos
    for caminho in POSSIBLE_PATHS:
        if os.path.exists(caminho):
            arquivo_encontrado = caminho
            print(f"✅ Arquivo de condominios encontrado em: {caminho}")
            break
    
    # Se encontrou o arquivo, carrega
    if arquivo_encontrado:
        try:
            wb = load_workbook(arquivo_encontrado)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                # Estrutura: COD(0), CONDOMINIO(1), GESTAO(2), CNPJ(3)
                if row[3]:  # CNPJ na coluna D (índice 3)
                    cnpj = str(row[3]).strip()
                    # Remover pontos e barras se houver
                    cnpj = cnpj.replace(".", "").replace("-", "").replace("/", "")
                    # Garantir 14 dígitos
                    if len(cnpj) >= 14:
                        cnpj = cnpj[:14]
                    
                    condominios[cnpj] = {
                        "nome": str(row[1]) if row[1] else "",
                        "codigo": str(int(row[0])).zfill(4) if row[0] else "0000"
                    }
            print(f"✅ Carregados {len(condominios)} condominios do arquivo")
        except Exception as e:
            print(f"⚠️ Erro ao carregar arquivo de condominios: {e}")
            print("Usando dados embutidos como fallback...")
    else:
        print("⚠️ Arquivo de condominios não encontrado em nenhum caminho")
        print("Usando dados embutidos como fallback...")
    
    # Se não conseguiu carregar do arquivo, usa dados embutidos (fallback)
    if not condominios:
        print("📝 Carregando dados embutidos de condominios...")
        condominios = {
            "65169906000180": {
                "nome": "CONDOMINIO EDIFICIO GROPIUS",
                "codigo": "0762"
            }
        }
    
    # Cachear os dados
    CONDOMINIOS_CACHE = condominios
    CACHE_TIMESTAMP = datetime.now()
    
    return condominios

def processar_arquivo(nome_arquivo, caminho_entrada=None):
    """Processa um arquivo PDF e retorna dados para remessa"""
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
            resultado["mensagem"] = f"Arquivo não encontrado: {nome_arquivo}"
            return resultado
        
        # Extrair CNPJ do nome do arquivo
        cnpj_condominio = extrair_cnpj_do_nome_arquivo(nome_arquivo)
        if not cnpj_condominio:
            resultado["mensagem"] = "CNPJ não encontrado no nome do arquivo"
            return resultado
        
        # Carregar dados de condominios
        condominios = carregar_condominios()
        
        # Tentar com CNPJ original e também sem formatação
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
            resultado["mensagem"] = "Não foi possível extrair a linha digitável do PDF"
            return resultado
        
        # Converter para código de barras
        codigo_barras = linha_digitavel_para_codigo_barras(dados_pdf["linha_digitavel"])
        if not codigo_barras:
            resultado["mensagem"] = "Código de barras inválido"
            return resultado
        
        # Preparar dados para arquivo de remessa
        agora = datetime.now()
        vencimento = dados_pdf["vencimento"] if dados_pdf["vencimento"] else agora.strftime("%d/%m/%Y")
        data_emissao = agora.strftime("%d/%m/%Y")
        valor_float = float(dados_pdf["valor"]) if dados_pdf["valor"] else 0.0
        valor_formatado = formatar_valor_ahreas(valor_float)
        cod_cond_erp = cond_info["codigo"].zfill(4)
        nome_cond_erp = fixo(remover_acentos(cond_info["nome"]).upper(), 50)
        
        # Copiar PDF para pasta de documentos (LOCAL)
        ano_atual = agora.strftime("%Y")
        mes_atual = agora.strftime("%m")
        pasta_destino_docs = os.path.join(PASTA_DOCS_PATH, ano_atual, mes_atual)
        os.makedirs(pasta_destino_docs, exist_ok=True)
        caminho_pdf_destino = os.path.join(pasta_destino_docs, nome_arquivo)
        try:
            shutil.copy(caminho_entrada, caminho_pdf_destino)
        except Exception as e:
            print(f"Aviso: Não foi possível copiar para pasta local: {e}")
        
        # Copiar PDF para pasta de documentos (RENDER)
        pasta_destino_render = os.path.join(DOCS_STORAGE_PATH, ano_atual, mes_atual)
        os.makedirs(pasta_destino_render, exist_ok=True)
        caminho_pdf_render = os.path.join(pasta_destino_render, nome_arquivo)
        try:
            shutil.copy(caminho_entrada, caminho_pdf_render)
            print(f"PDF salvo em: {caminho_pdf_render}")
        except Exception as e:
            print(f"Erro ao salvar PDF no Render: {e}")
        
        # Retornar dados processados
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
            "ano": ano_atual,
            "mes": mes_atual
        }
    
    except Exception as e:
        resultado["mensagem"] = f"Erro ao processar: {str(e)}"
        import traceback
        print(traceback.format_exc())
    
    return resultado

def gerar_remessa_lote(lista_dados, competencia=None):
    """Gera um arquivo de remessa único com múltiplos registros"""
    if not lista_dados:
        return None
    
    agora = datetime.now()
    if not competencia:
        competencia = agora.strftime("%m%Y")
    
    linhas = []
    
    # REGISTRO 0 - HEADER
    header = (
        "0" +                                         # 01 - Tipo Registro
        FORNECEDOR_CNPJ.zfill(14) +                   # 02 - CNPJ Fornecedor
        fixo(remover_acentos(FORNECEDOR_NOME).upper(), 60) + # 03 - Nome Fornecedor
        CNPJ_ADMIN.zfill(14) +                        # 04 - CNPJ Administradora
        fixo(remover_acentos(NOME_ADMIN).upper(), 60) + # 05 - Nome Administradora
        competencia +                                 # 06 - Mês/Ano Referência
        " " * 241 +                                   # 07 - Uso Ahreas
        "0001"                                        # 08 - Sequencial
    )
    linhas.append(fixo(header, 400))
    
    # REGISTROS 1 e 2 para cada boleto
    sequencial = 2
    for dados in lista_dados:
        # REGISTRO 1 - DETALHE NF
        registro_1 = (
            "1" +                                     # 01 - Tipo
            dados["cod_cond"] +                       # 02 - Cod Condomínio
            "    " +                                  # 03 - Espaços
            dados["cnpj"].zfill(14) +                 # 04 - CNPJ Condomínio
            dados["nome_cond"] +                      # 05 - Nome Condomínio
            dados["vencimento"] +                     # 06 - Vencimento
            dados["valor_formatado"] +                # 07 - Valor
            dados["codigo_barras"] +                  # 08 - Código de Barras
            dados["valor_formatado"] +                # 09 - Valor Total
            "000000000,00" +                          # 10 - IRRF
            "000000000,00" +                          # 11 - ISS
            "000000000,00" +                          # 12 - INSS
            "000000000,00" +                          # 13 - CSSL
            "000000000,00" +                          # 14 - Descontos
            "N" +                                     # 15 - Nota Fiscal S/N
            "          " +                            # 16 - Data Emissão NF
            "          " +                            # 17 - Número NF
            "     " +                                 # 18 - Série NF
            "     " +                                 # 19 - Tipo NF
            " " * 154 +                               # 20-23 - Uso Ahreas
            str(sequencial).zfill(4)                  # 24 - Sequencial
        )
        linhas.append(fixo(registro_1, 400))
        
        # REGISTRO 2 - DETALHE ITENS
        registro_2 = (
            "2" +                                     # 01 - Tipo
            fixo(COD_PRODUTO_ERP, 10) +               # 02 - Cod Produto
            fixo(DESC_PRODUTO_ERP, 60) +              # 03 - Descrição
            "000000000,00" +                          # 04 - Valor Item Prod
            dados["valor_formatado"] +                # 05 - Valor Item Serv
            dados["valor_formatado"] +                # 06 - Valor Total Item
            " " * 289 +                               # 07 - Uso Ahreas
            str(sequencial).zfill(4)                  # 08 - Sequencial
        )
        linhas.append(fixo(registro_2, 400))
        
        # REGISTRO 3 - TRAILER COM URL DO PDF (um para cada boleto)
        ano = dados.get("ano", agora.strftime("%Y"))
        mes = dados.get("mes", agora.strftime("%m"))
        url_pdf = f"https://fedcorp-erp-dashboard.onrender.com/docs/{ano}/{mes}/{dados['nome_arquivo']}"
        
        # Calcular espaços de preenchimento
        tamanho_fixo = 1 + 6 + 6 + 12 + 4  # Tipo + 2 campos + valor + sequencial
        tamanho_url = len(url_pdf)
        tamanho_espacos = 400 - tamanho_fixo - tamanho_url
        
        # DEBUG: Log da URL
        print(f"URL gerada: {url_pdf}")
        print(f"Arquivo: {dados['nome_arquivo']}, Tamanho URL: {tamanho_url}, Espaços: {tamanho_espacos}")
        
        trailer_boleto = (
            "3" +                                     # 01 - Tipo
            "000001" +                                # 02 - Sequencial de registros
            "000001" +                                # 03 - Total de títulos
            dados["valor_formatado"] +                # 04 - Valor Total
            url_pdf +                                 # 05 - URL do PDF
            " " * max(0, tamanho_espacos) +           # Espaços de preenchimento
            str(sequencial).zfill(4)                  # 06 - Sequencial
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
                    # Salvar arquivo temporário
                    filename = secure_filename(file.filename)
                    temp_path = os.path.join(TEMP_UPLOAD_PATH, filename)
                    file.save(temp_path)
                    
                    # Processar arquivo
                    resultado = processar_arquivo(filename, temp_path)
                    resultados["detalhes"].append(resultado)
                    
                    if resultado["status"] == "sucesso":
                        resultados["sucesso"] += 1
                        if modo_lote:
                            lista_dados_processados.append(resultado["dados"])
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
        
        # Se modo lote, gerar remessa única
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
                
                # Mover PDFs para pasta de processados
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
        
        # Se modo lote, gerar remessa única
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
                
                # Mover PDFs para pasta de processados
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
        # Tentar primeiro no Render
        caminho_render = os.path.join(DOCS_STORAGE_PATH, ano, mes, arquivo)
        if os.path.exists(caminho_render):
            print(f"Servindo arquivo do Render: {caminho_render}")
            return send_from_directory(os.path.dirname(caminho_render), arquivo)
        
        # Tentar depois na pasta local
        caminho_local = os.path.join(PASTA_DOCS_PATH, ano, mes, arquivo)
        if os.path.exists(caminho_local):
            print(f"Servindo arquivo local: {caminho_local}")
            return send_from_directory(os.path.dirname(caminho_local), arquivo)
        
        print(f"Arquivo nao encontrado: {caminho_render} ou {caminho_local}")
        return jsonify({"erro": "Arquivo nao encontrado"}), 404
    except Exception as e:
        print(f"Erro ao servir documento: {e}")
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
    print(f"📁 ENTRADA_PATH: {ENTRADA_PATH}")
    print(f"📁 GERADAS_PATH: {GERADAS_PATH}")
    
    # Pré-carregar condominios
    print("📝 Carregando dados de condominios...")
    condominios = carregar_condominios()
    print(f"✅ {len(condominios)} condominio(s) carregado(s)")
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
