# 🎯 ERP Ahreas Import Dashboard

Dashboard profissional para importação automatizada de remessas de boletos no ERP Ahreas. Processa PDFs de boletos, extrai dados automaticamente e gera arquivos de importação no formato esperado pelo sistema.

## ✨ Funcionalidades

- 📊 **Dashboard Intuitivo** - Interface web moderna e responsiva
- 🤖 **Processamento Automático** - Extrai dados de PDFs de boletos
- 📄 **Geração de Remessas** - Cria arquivos `.txt` no formato Ahreas
- ⚠️ **Tratamento de Erros** - Identifica e relata problemas
- 📁 **Organização Automática** - Move arquivos para pastas apropriadas
- 🔗 **Vínculo de Documentos** - Anexa PDFs automaticamente

## 🚀 Quick Start

### Opção 1: Deploy no Render (Nuvem - Recomendado)

1. Crie uma conta no [GitHub](https://github.com/signup) e [Render](https://render.com)
2. Faça upload dos arquivos para um repositório GitHub
3. Conecte o repositório ao Render
4. Acesse a URL gerada (ex: `https://fedcorp-erp-dashboard.onrender.com`)

Veja o **[GUIA_RENDER.md](GUIA_RENDER.md)** para instruções detalhadas.

### Opção 2: Executar Localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar o servidor
python app.py

# Acessar em http://localhost:5000
```

## 📋 Requisitos

- Python 3.7+
- Flask 2.3+
- Pandas 2.0+
- pdfplumber 0.10+
- Arquivo Excel com dados dos condomínios (`DADOS_CONDOMINIOS.xlsx`)

## 📁 Estrutura de Pastas

```
G:\Wallpaper\FEDCORP_PROCESSADOR\
├── ENTRADA/                    (Coloque os PDFs aqui)
├── REMESSAS_GERADAS/          (Arquivos .txt gerados)
├── NAO_PROCESSADOS/           (Arquivos com erro)
├── DOCUMENTOS_ANEXADOS/       (Cópia dos PDFs)
├── DOCUMENTOS/                (PDFs movidos após processamento)
└── BASE/
    └── DADOS_CONDOMINIOS.xlsx (Base de dados)
```

## 🔧 Configuração

Edite o arquivo `app.py` e ajuste:

```python
BASE_PATH = r"G:\Wallpaper\FEDCORP_PROCESSADOR"
```

Para o seu caminho real.

## 📖 Como Usar

1. **Coloque os PDFs** na pasta `ENTRADA`
   - Nome do arquivo deve conter o CNPJ (14 dígitos)
   - Exemplo: `boleto_26269738000142_CONDOMINIO.pdf`

2. **Acesse o dashboard** em `http://localhost:5000` (ou URL do Render)

3. **Clique em "Processar Agora"**

4. **Acompanhe os resultados:**
   - ✅ Verde = Sucesso
   - ⚠️ Amarelo = Aviso (arquivo movido para NAO_PROCESSADOS)
   - ❌ Vermelho = Erro

## 🎨 Interface

- **Dashboard Responsivo** - Funciona em desktop, tablet e mobile
- **Indicadores Visuais** - Cores e ícones claros
- **Relatório Detalhado** - Mensagens específicas para cada arquivo
- **Estatísticas** - Acompanhamento de processamentos

## 🔐 Segurança

- Validação de CNPJ
- Tratamento de erros robusto
- Isolamento de arquivos problemáticos
- Sem armazenamento de dados sensíveis

## 📊 Endpoints da API

| Endpoint | Método | Descrição |
| --- | --- | --- |
| `/` | GET | Dashboard principal |
| `/api/pending-files` | GET | Lista arquivos pendentes |
| `/processar` | POST | Processa os arquivos |
| `/docs/<ano>/<mes>/<arquivo>` | GET | Serve PDFs |
| `/health` | GET | Health check |

## 🐛 Troubleshooting

### Erro: "Base de condomínios não encontrada"
- Verifique se `DADOS_CONDOMINIOS.xlsx` existe em `BASE/`

### Erro: "Condomínio não cadastrado"
- Verifique se o CNPJ do arquivo existe na base de dados

### Erro: "Linha digitável não encontrada"
- O PDF pode estar corrompido ou em formato não suportado

## 📝 Logs

Verifique os logs no console para mais informações sobre erros.

## 🤝 Suporte

Para problemas ou dúvidas, consulte:
- Documentação do Render: https://render.com/docs
- Documentação do Flask: https://flask.palletsprojects.com

## 📄 Licença

Desenvolvido por **Manus AI** - Março de 2026

---

**Versão:** 1.0  
**Status:** Produção  
**Última Atualização:** Março de 2026
