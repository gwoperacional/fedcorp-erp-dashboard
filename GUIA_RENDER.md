# 🚀 Guia Completo - Deploy no Render

## O que é Render?

**Render** é uma plataforma de nuvem gratuita que permite hospedar aplicações web sem custo. Perfeita para o seu dashboard, pois:

- ✅ **Gratuito** - Sem limite de tempo (apenas 750 horas/mês, suficiente para uso corporativo)
- ✅ **Sempre ligado** - Não depende de nenhuma máquina local
- ✅ **Acesso de qualquer lugar** - Qualquer pessoa na rede acessa
- ✅ **Fácil de usar** - Interface intuitiva
- ✅ **Automático** - Deploy com um clique

## Pré-requisitos

1. **Conta GitHub** (gratuita) - https://github.com/signup
2. **Conta Render** (gratuita) - https://render.com

## Passo 1: Criar Repositório no GitHub

### 1.1 Criar conta GitHub (se não tiver)
1. Acesse: https://github.com/signup
2. Preencha o formulário com seus dados
3. Confirme o email

### 1.2 Criar novo repositório
1. Acesse: https://github.com/new
2. Preencha os dados:
   - **Repository name:** `fedcorp-erp-dashboard`
   - **Description:** `Dashboard para importação de remessas ERP Ahreas`
   - **Visibility:** `Public` (necessário para Render gratuito)
3. Clique em **"Create repository"**

### 1.3 Fazer upload dos arquivos

**Opção A: Usando Git (Recomendado)**

Se você tem Git instalado:

```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/fedcorp-erp-dashboard.git
cd fedcorp-erp-dashboard

# Copie os arquivos da pasta FEDCORP_RENDER_DEPLOY para aqui
# (app.py, requirements.txt, Procfile, dist/, etc.)

# Faça o commit
git add .
git commit -m "Initial commit - ERP Dashboard"
git push origin main
```

**Opção B: Usando a Interface Web (Mais Simples)**

1. No repositório GitHub, clique em **"Add file"** → **"Upload files"**
2. Arraste os arquivos:
   - `app.py`
   - `requirements.txt`
   - `Procfile`
   - `.gitignore`
   - Pasta `dist/` completa
3. Clique em **"Commit changes"**

## Passo 2: Criar Conta no Render

1. Acesse: https://render.com
2. Clique em **"Sign Up"**
3. Escolha **"Continue with GitHub"**
4. Autorize o Render a acessar sua conta GitHub
5. Confirme o email

## Passo 3: Fazer Deploy no Render

### 3.1 Criar novo Web Service
1. No dashboard do Render, clique em **"New +"**
2. Selecione **"Web Service"**
3. Clique em **"Connect"** ao lado do seu repositório `fedcorp-erp-dashboard`
4. Se não aparecer, clique em **"Configure account"** para sincronizar com GitHub

### 3.2 Configurar o Web Service
Preencha os campos:

| Campo | Valor |
| --- | --- |
| **Name** | `fedcorp-erp-dashboard` |
| **Environment** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python app.py` |
| **Plan** | `Free` |

### 3.3 Adicionar Variáveis de Ambiente (Importante!)

Clique em **"Advanced"** e adicione a variável:

```
BASE_PATH = G:\Wallpaper\FEDCORP_PROCESSADOR
```

**Nota:** Se você estiver usando um caminho diferente, altere para o seu caminho real.

### 3.4 Fazer Deploy
1. Clique em **"Deploy"**
2. Aguarde o build (pode levar 2-3 minutos)
3. Quando terminar, você verá uma URL como: `https://fedcorp-erp-dashboard.onrender.com`

## Passo 4: Acessar o Dashboard

Depois que o deploy terminar:

1. Acesse: `https://fedcorp-erp-dashboard.onrender.com`
2. Você deve ver o dashboard com o botão "Processar Agora"
3. Compartilhe esse link com as outras pessoas

## Passo 5: Configurar o Processamento

### 5.1 Conectar ao Servidor Local

O Render está na nuvem, mas precisa acessar os arquivos no servidor `10.10.64.6`. Para isso:

1. **Opção A: Usar um Proxy/Tunnel (Recomendado)**
   - Use **ngrok** para expor o servidor local
   - Ou configure um **VPN** corporativo

2. **Opção B: Mover os Arquivos para Render**
   - Use um serviço como **AWS S3** ou **Google Drive** para armazenar os PDFs
   - O Render baixa os PDFs, processa e salva de volta

3. **Opção C: Manter Local (Mais Simples)**
   - Continue usando o `app_v22.py` localmente
   - Use o Render apenas como interface visual

**Recomendação:** Use a **Opção C** por enquanto. O Render funciona como interface, mas o processamento acontece no servidor local.

## Passo 6: Atualizar o Código

Sempre que você fizer mudanças no código:

1. Faça o commit no GitHub:
   ```bash
   git add .
   git commit -m "Descrição da mudança"
   git push origin main
   ```

2. O Render detecta automaticamente e faz novo deploy (pode levar alguns minutos)

## Troubleshooting

### Erro: "Build failed"
- Verifique se o `requirements.txt` está correto
- Verifique se o `Procfile` existe e está correto
- Veja os logs no Render para mais detalhes

### Erro: "Application failed to start"
- Verifique se o `app.py` está correto
- Verifique se a variável `BASE_PATH` está configurada
- Veja os logs no Render

### Dashboard não carrega
- Limpe o cache do navegador (Ctrl + Shift + Delete)
- Tente em outro navegador
- Verifique se os arquivos em `dist/` foram enviados

### Processamento não funciona
- Verifique se o servidor local `10.10.64.6` está acessível
- Verifique se a pasta `ENTRADA` existe e tem PDFs
- Verifique os logs no Render

## Monitoramento

No dashboard do Render, você pode:

- Ver logs em tempo real
- Monitorar CPU e memória
- Reiniciar a aplicação
- Ver histórico de deploys

## Limites do Plano Gratuito

- **750 horas/mês** (suficiente para uso corporativo)
- **Hibernação automática** se sem requisições por 15 minutos (acorda quando alguém acessa)
- **Sem limite de requisições** (dentro das 750 horas)

## Próximos Passos

1. ✅ Criar repositório GitHub
2. ✅ Fazer upload dos arquivos
3. ✅ Criar Web Service no Render
4. ✅ Fazer deploy
5. ✅ Testar o dashboard
6. ✅ Compartilhar o link com as pessoas

---

**Versão:** 1.0  
**Data:** Março de 2026  
**Desenvolvido por:** Manus AI

## Suporte Render

- Documentação: https://render.com/docs
- Status: https://render-status.com
- Email: support@render.com
