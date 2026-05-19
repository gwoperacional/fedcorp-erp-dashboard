#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONDOMED ERP Import Dashboard
Processador de Notas Fiscais de Serviço (NFS-e) para importação no ERP Ahreas
Baseado na documentação oficial de layout de importação
"""

import os
import re
import gc
import json
import pdfplumber
import tempfile
import unicodedata
from datetime import datetime
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename
from openpyxl import load_workbook
from io import BytesIO

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Caminhos
BASE_PATH = os.path.dirname(__file__)
PASTA_DOCS_PATH = os.path.join(BASE_PATH, "docs_anexados")
TEMP_UPLOAD_PATH = os.path.join(tempfile.gettempdir(), "condomed_uploads")

os.makedirs(PASTA_DOCS_PATH, exist_ok=True)
os.makedirs(TEMP_UPLOAD_PATH, exist_ok=True)

# Dados CONDOMED
CNPJ_ADMIN = "26231209000150"
NOME_ADMIN = "GW ADMINISTRADORA DE CONDOMINIOS LTDA"
FORNECEDOR_CNPJ = "27892999000187"
FORNECEDOR_NOME = "CONDOMED RIO SEGURANCA E MEDICINA DO TRABALHO LTDA"
COD_FORNECEDOR_ERP = "24367"
COD_PRODUTO_ERP = "MST"
DESC_PRODUTO_ERP = ""

# Cache de condominios
CONDOMINIOS_CACHE = {}
CACHE_TIMESTAMP = None

# ============================================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================================

def remover_acentos(texto):
    """Remove acentos de texto"""
    if not texto:
        return ""
    return unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")

def fixo(texto, tamanho):
    """Preenche texto com espaços até o tamanho especificado"""
    return str(texto).ljust(tamanho)[:tamanho]

def numerico(valor, tamanho):
    """Preenche número com zeros à esquerda"""
    return str(valor).zfill(tamanho)[:tamanho]

def linha_digitavel_para_codigo_barras(linha):
    """Converte linha digitável para código de barras (44 caracteres)"""
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
    """Formata valor para 12 posições com vírgula (999999999,99)"""
    try:
        return f"{float(valor_float):012.2f}".replace(".", ",")
    except:
        return "000000000,00"

def carregar_condominios():
    """Carrega condominios do arquivo Excel"""
    global CONDOMINIOS_CACHE, CACHE_TIMESTAMP
    
    # Usar cache se válido (5 minutos)
    if CONDOMINIOS_CACHE and CACHE_TIMESTAMP:
        if (datetime.now() - CACHE_TIMESTAMP).seconds < 300:
            return CONDOMINIOS_CACHE
    
    condominios = {}
    
    # Procurar arquivo em possíveis locais
    possible_paths = [
        os.path.join(BASE_PATH, "BASE", "DADOS_CONDOMINIOS.xlsx"),
        os.path.join(BASE_PATH, "DADOS_CONDOMINIOS.xlsx"),
        "/app/BASE/DADOS_CONDOMINIOS.xlsx",
    ]
    
    for caminho in possible_paths:
        if os.path.exists(caminho):
            try:
                wb = load_workbook(caminho)
                ws = wb.active
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if row and len(row) > 3 and row[3]:
                        cnpj = str(row[3]).strip()
                        cnpj = re.sub(r"\D", "", cnpj)
                        if len(cnpj) >= 14:
                            cnpj = cnpj[:14]
                            condominios[cnpj] = {
                                "nome": str(row[1]) if row[1] else "",
                                "codigo": numerico(row[0], 4) if row[0] else "0000"
                            }
                CONDOMINIOS_CACHE = condominios
                CACHE_TIMESTAMP = datetime.now()
                return condominios
            except Exception as e:
                print(f"Erro ao carregar condominios: {e}")
                continue
    
    return {}

# ============================================================================
# EXTRAÇÃO DE DADOS DO PDF
# ============================================================================

def extrair_dados_nfse(pdf_path):
    """Extrai dados da NFS-e do PDF"""
    dados = {
        "cnpj_pagador": None,
        "numero_nfse": None,
        "data_emissao": None,
        "data_vencimento": None,
        "valor": None,
        "linha_digitavel": None,
        "codigo_barras": None,
        "condominio": None,
        "condominio_codigo": None
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto_completo = ""
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    texto_completo += t + "\n"
            
            # Extrair CNPJ do pagador (tomador do serviço)
            match_cnpj = re.search(r"(?:CNPJ|CPF)[:\s]+(\d{2}\.?\d{3}\.?\d{3}/?0001-?\d{2})", texto_completo)
            if match_cnpj:
                cnpj = re.sub(r"\D", "", match_cnpj.group(1))
                if len(cnpj) >= 14:
                    dados["cnpj_pagador"] = cnpj[:14]
            
            # Extrair número da NFS-e
            match_nfse = re.search(r"(?:NFS-e|NF-e|Nota Fiscal)[:\s]+(\d+)", texto_completo, re.IGNORECASE)
            if match_nfse:
                dados["numero_nfse"] = match_nfse.group(1)
            
            # Extrair data de emissão
            match_emissao = re.search(r"(?:Data de Emissão|Emissão|Emitida em)[:\s]+(\d{2}/\d{2}/\d{4})", texto_completo, re.IGNORECASE)
            if match_emissao:
                dados["data_emissao"] = match_emissao.group(1)
            
            # Extrair data de vencimento
            match_venc = re.search(r"(?:Vencimento|Vence em)[:\s]+(\d{2}/\d{2}/\d{4})", texto_completo, re.IGNORECASE)
            if match_venc:
                dados["data_vencimento"] = match_venc.group(1)
            
            # Extrair valor
            match_valor = re.search(r"(?:Valor Total|Valor|Total)[:\s]+R\$\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
            if match_valor:
                valor_str = match_valor.group(1).replace(".", "").replace(",", ".")
                try:
                    dados["valor"] = float(valor_str)
                except:
                    pass
            
            # Extrair linha digitável do boleto
            regex_linha = r"\d{5}[\.\s]?\d{5}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d[\.\s]?\d{14}"
            match_linha = re.search(regex_linha, texto_completo)
            if match_linha:
                linha = re.sub(r"\D", "", match_linha.group())
                dados["linha_digitavel"] = linha
                dados["codigo_barras"] = linha_digitavel_para_codigo_barras(linha)
    
    except Exception as e:
        print(f"Erro ao extrair dados: {e}")
    
    return dados

# ============================================================================
# PROCESSAMENTO E GERAÇÃO DE REMESSA
# ============================================================================

def processar_arquivo(nome_arquivo, caminho_arquivo):
    """Processa um arquivo PDF e extrai dados"""
    try:
        dados = extrair_dados_nfse(caminho_arquivo)
        
        # Validações
        if not dados["cnpj_pagador"]:
            return {"status": "erro", "mensagem": "CNPJ do pagador não encontrado"}
        
        if not dados["numero_nfse"]:
            dados["numero_nfse"] = "0"
        
        if not dados["data_vencimento"]:
            return {"status": "erro", "mensagem": "Data de vencimento não encontrada"}
        
        if not dados["valor"]:
            return {"status": "erro", "mensagem": "Valor não encontrado"}
        
        if not dados["codigo_barras"]:
            return {"status": "erro", "mensagem": "Linha digitável/código de barras não encontrado"}
        
        # Procurar condominio
        condominios = carregar_condominios()
        condominio_info = condominios.get(dados["cnpj_pagador"], {})
        
        dados["condominio"] = condominio_info.get("nome", "")
        dados["condominio_codigo"] = condominio_info.get("codigo", "0000")
        
        # Salvar PDF
        data_agora = datetime.now()
        pasta_docs = os.path.join(PASTA_DOCS_PATH, str(data_agora.year), str(data_agora.month).zfill(2))
        os.makedirs(pasta_docs, exist_ok=True)
        
        caminho_destino = os.path.join(pasta_docs, nome_arquivo)
        with open(caminho_arquivo, 'rb') as src:
            with open(caminho_destino, 'wb') as dst:
                dst.write(src.read())
        
        dados["arquivo_salvo"] = caminho_destino
        dados["url_pdf"] = f"/docs/{data_agora.year}/{str(data_agora.month).zfill(2)}/{nome_arquivo}"
        
        return {"status": "sucesso", "dados": dados}
    
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}

def gerar_remessa_lote(lista_dados, competencia):
    """Gera remessa no formato Ahreas conforme documentação oficial"""
    linhas = []
    
    # Registro 0 (Header)
    header = (
        "0" +                                      # Tipo
        numerico(FORNECEDOR_CNPJ, 14) +           # CNPJ Fornecedor
        fixo(FORNECEDOR_NOME, 60) +               # Nome Fornecedor
        numerico(CNPJ_ADMIN, 14) +                # CNPJ Administradora
        fixo(NOME_ADMIN, 60) +                    # Nome Administradora
        numerico(competencia, 6) +                # Mês/Ano (MMAAAA)
        fixo("", 241) +                           # Uso Ahreas
        "0001"                                     # Sequencial
    )
    linhas.append(header)
    
    sequencial = 2
    
    for dados in lista_dados:
        # Registro 1 (Detalhe NF)
        registro_1 = (
            "1" +                                                    # Tipo
            numerico(dados.get("condominio_codigo", "0000"), 4) +   # Código Condominio
            fixo("", 4) +                                           # Código Bloco (4 espaços)
            numerico(dados.get("cnpj_pagador", ""), 14) +          # CNPJ Condominio
            fixo(dados.get("condominio", ""), 50) +                # Nome Condominio
            dados.get("data_vencimento", "01/01/2026") +           # Data Vencimento (DD/MM/AAAA)
            formatar_valor_ahreas(dados.get("valor", 0)) +         # Valor Título
            fixo(dados.get("codigo_barras", ""), 44) +             # Código Barras (44 chars)
            formatar_valor_ahreas(dados.get("valor", 0)) +         # Valor Total NF
            fixo("", 12) +                                          # IRRF
            fixo("", 12) +                                          # ISS
            fixo("", 12) +                                          # INSS
            fixo("", 12) +                                          # CSSL/PIS/COFINS
            fixo("", 12) +                                          # Descontos
            "N" +                                                   # NF Venda (S/N)
            dados.get("data_emissao", "01/01/2026") +              # Data Emissão NF (DD/MM/AAAA)
            numerico(dados.get("numero_nfse", "0"), 10) +          # Número NF
            fixo("", 5) +                                           # Série NF
            fixo("", 5) +                                           # Tipo NF
            fixo("", 12) +                                          # CSLL
            fixo("", 12) +                                          # PIS
            fixo("", 12) +                                          # COFINS
            fixo("", 118) +                                         # Uso Ahreas
            numerico(sequencial, 4)                                 # Sequencial
        )
        linhas.append(registro_1)
        
        # Registro 2 (Detalhe Itens)
        registro_2 = (
            "2" +                                                    # Tipo
            fixo(COD_PRODUTO_ERP, 10) +                            # Código Produto
            fixo(DESC_PRODUTO_ERP, 60) +                           # Descrição Produto
            fixo("", 12) +                                          # Valor Item Produtos
            fixo("", 12) +                                          # Valor Item Serviços
            formatar_valor_ahreas(dados.get("valor", 0)) +         # Valor Total Item
            fixo("", 289) +                                         # Uso Ahreas
            numerico(sequencial, 4)                                 # Sequencial
        )
        linhas.append(registro_2)
        
        # Registro 3 (Detalhe Documentos)
        numero_nfse_str = str(dados.get("numero_nfse", "0")).zfill(10)
        registro_3 = (
            "3" +                                                    # Tipo
            "0001" +                                                # Sequencial Imagens
            numero_nfse_str +                                       # Número NF (10 dígitos com zeros)
            fixo(dados.get("url_pdf", ""), 300) +                  # URL Documento
            fixo("", 300) +                                         # Uso Ahreas
            numerico(sequencial, 4)                                 # Sequencial
        )
        linhas.append(registro_3)
        
        sequencial += 1
        gc.collect()  # Limpar memória
    
    # Validar tamanho de cada linha
    for i, linha in enumerate(linhas, 1):
        if len(linha) != 400:
            print(f"⚠️ Linha {i} tem {len(linha)} chars (deveria ter 400)")
    
    return "\n".join(linhas)

# ============================================================================
# ROTAS FLASK
# ============================================================================

@app.route('/')
def index():
    """Página principal"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>CONDOMED ERP Import</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .header h1 { font-size: 24px; margin-bottom: 5px; }
            .header p { font-size: 14px; opacity: 0.9; }
            .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 15px; }
            .form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
            .form-group input, .form-group textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; }
            .btn { display: inline-block; padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
            .btn:hover { background: #2980b9; }
            .btn-danger { background: #e74c3c; }
            .btn-danger:hover { background: #c0392b; }
            .status { padding: 10px; border-radius: 4px; margin-top: 10px; }
            .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .file-list { max-height: 300px; overflow-y: auto; }
            .file-item { padding: 8px; background: #f9f9f9; margin: 5px 0; border-radius: 4px; font-size: 13px; }
            .progress { width: 100%; height: 20px; background: #eee; border-radius: 4px; overflow: hidden; margin: 10px 0; }
            .progress-bar { height: 100%; background: #3498db; transition: width 0.3s; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏢 CONDOMED ERP Import Dashboard</h1>
                <p>Processador de Notas Fiscais de Serviço (NFS-e)</p>
            </div>
            
            <div class="card">
                <h2>📤 Upload de Arquivos</h2>
                <div class="form-group">
                    <label>Competência (Mês/Ano):</label>
                    <input type="text" id="competencia" placeholder="052026" maxlength="6" value="">
                </div>
                <div class="form-group">
                    <label>Selecione os arquivos PDF:</label>
                    <input type="file" id="files" multiple accept=".pdf" />
                </div>
                <button class="btn" onclick="uploadArquivos()">📤 Upload e Processar</button>
                <div id="status"></div>
                <div class="progress" id="progress" style="display:none;">
                    <div class="progress-bar" id="progressBar" style="width:0%"></div>
                </div>
            </div>
            
            <div class="card">
                <h2>📋 Arquivos Processados</h2>
                <div class="file-list" id="fileList">
                    <p style="color: #999;">Nenhum arquivo processado ainda</p>
                </div>
            </div>
            
            <div class="card">
                <h2>💾 Remessa</h2>
                <button class="btn" onclick="gerarRemessa()">✅ Gerar Remessa</button>
                <button class="btn btn-danger" onclick="limparTudo()">🗑️ Limpar Tudo</button>
                <div id="remessaStatus"></div>
            </div>
        </div>
        
        <script>
            let arquivosProcessados = [];
            
            async function uploadArquivos() {
                const files = document.getElementById('files').files;
                const competencia = document.getElementById('competencia').value;
                
                if (!files.length) {
                    alert('Selecione pelo menos um arquivo');
                    return;
                }
                
                if (!competencia || competencia.length !== 6) {
                    alert('Competência deve estar no formato MMAAAA (ex: 052026)');
                    return;
                }
                
                const formData = new FormData();
                formData.append('competencia', competencia);
                for (let file of files) {
                    formData.append('files', file);
                }
                
                document.getElementById('progress').style.display = 'block';
                document.getElementById('status').innerHTML = '<div class="status">Processando...</div>';
                
                try {
                    const response = await fetch('/api/processar', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.status === 'sucesso') {
                        arquivosProcessados = data.arquivos;
                        atualizarLista();
                        document.getElementById('status').innerHTML = '<div class="status success">✅ ' + data.mensagem + '</div>';
                    } else {
                        document.getElementById('status').innerHTML = '<div class="status error">❌ ' + data.mensagem + '</div>';
                    }
                } catch (e) {
                    document.getElementById('status').innerHTML = '<div class="status error">❌ Erro: ' + e.message + '</div>';
                }
                
                document.getElementById('progress').style.display = 'none';
            }
            
            function atualizarLista() {
                const lista = document.getElementById('fileList');
                if (arquivosProcessados.length === 0) {
                    lista.innerHTML = '<p style="color: #999;">Nenhum arquivo processado</p>';
                    return;
                }
                
                lista.innerHTML = arquivosProcessados.map((arq, i) => `
                    <div class="file-item">
                        <strong>${i+1}. ${arq.arquivo}</strong><br>
                        CNPJ: ${arq.cnpj_pagador} | Valor: R$ ${arq.valor} | NFS-e: ${arq.numero_nfse}
                    </div>
                `).join('');
            }
            
            async function gerarRemessa() {
                if (arquivosProcessados.length === 0) {
                    alert('Nenhum arquivo processado');
                    return;
                }
                
                const competencia = document.getElementById('competencia').value;
                
                try {
                    const response = await fetch('/api/gerar-remessa', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ arquivos: arquivosProcessados, competencia: competencia })
                    });
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'REMESSA_CONDOMED_' + new Date().toISOString().slice(0,19).replace(/:/g,'-') + '.txt';
                        a.click();
                        document.getElementById('remessaStatus').innerHTML = '<div class="status success">✅ Remessa gerada com sucesso!</div>';
                    } else {
                        document.getElementById('remessaStatus').innerHTML = '<div class="status error">❌ Erro ao gerar remessa</div>';
                    }
                } catch (e) {
                    document.getElementById('remessaStatus').innerHTML = '<div class="status error">❌ Erro: ' + e.message + '</div>';
                }
            }
            
            function limparTudo() {
                if (confirm('Tem certeza que deseja limpar tudo?')) {
                    arquivosProcessados = [];
                    document.getElementById('files').value = '';
                    document.getElementById('competencia').value = '';
                    atualizarLista();
                    document.getElementById('status').innerHTML = '';
                    document.getElementById('remessaStatus').innerHTML = '';
                }
            }
        </script>
    </body>
    </html>
    '''

@app.route('/api/processar', methods=['POST'])
def api_processar():
    """API para processar arquivos"""
    try:
        competencia = request.form.get('competencia', '')
        files = request.files.getlist('files')
        
        if not files or not competencia:
            return jsonify({"status": "erro", "mensagem": "Arquivos ou competência não fornecidos"}), 400
        
        arquivos_processados = []
        
        for file in files:
            if file.filename == '':
                continue
            
            # Salvar temporariamente
            filename = secure_filename(file.filename)
            temp_path = os.path.join(TEMP_UPLOAD_PATH, filename)
            file.save(temp_path)
            
            # Processar
            resultado = processar_arquivo(filename, temp_path)
            
            if resultado["status"] == "sucesso":
                dados = resultado["dados"]
                arquivos_processados.append({
                    "arquivo": filename,
                    "cnpj_pagador": dados["cnpj_pagador"],
                    "numero_nfse": dados["numero_nfse"],
                    "valor": dados["valor"],
                    "data_vencimento": dados["data_vencimento"],
                    "data_emissao": dados["data_emissao"],
                    "condominio": dados["condominio"],
                    "condominio_codigo": dados["condominio_codigo"],
                    "codigo_barras": dados["codigo_barras"],
                    "url_pdf": dados["url_pdf"]
                })
            
            # Limpar
            try:
                os.remove(temp_path)
            except:
                pass
            
            gc.collect()
        
        return jsonify({
            "status": "sucesso",
            "mensagem": f"{len(arquivos_processados)} arquivo(s) processado(s) com sucesso",
            "arquivos": arquivos_processados
        })
    
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/gerar-remessa', methods=['POST'])
def api_gerar_remessa():
    """API para gerar remessa"""
    try:
        data = request.json
        arquivos = data.get('arquivos', [])
        competencia = data.get('competencia', '')
        
        if not arquivos or not competencia:
            return jsonify({"status": "erro", "mensagem": "Dados incompletos"}), 400
        
        remessa = gerar_remessa_lote(arquivos, competencia)
        
        # Retornar como arquivo
        buffer = BytesIO(remessa.encode('utf-8'))
        return send_file(
            buffer,
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'REMESSA_CONDOMED_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        )
    
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/docs/<year>/<month>/<filename>')
def servir_pdf(year, month, filename):
    """Serve PDFs salvos"""
    try:
        caminho = os.path.join(PASTA_DOCS_PATH, year, month, filename)
        if os.path.exists(caminho):
            return send_file(caminho, mimetype='application/pdf')
        else:
            return jsonify({"erro": "Arquivo não encontrado"}), 404
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
