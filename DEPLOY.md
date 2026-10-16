# 🚀 PrimeFix — Guia de Deploy (GitHub + Render)

Este guia mostra o passo a passo completo para subir o projeto no GitHub e colocá-lo online no Render, com banco PostgreSQL incluso.

---

## PARTE 1 — Subir o projeto no GitHub

### 1. Crie uma conta no GitHub
Se ainda não tiver, crie em https://github.com (gratuito).

### 2. Crie um novo repositório
1. No GitHub, clique em **New repository**.
2. Dê um nome, por exemplo: `primefix`.
3. Deixe como **Public** ou **Private** (qualquer um funciona no Render).
4. **NÃO** marque "Add README" (vamos subir os arquivos já existentes).
5. Clique em **Create repository**.

### 3. Suba os arquivos do projeto

No seu computador, dentro da pasta do projeto `primefix/`, abra o terminal e rode:

```bash
git init
git add .
git commit -m "Primeira versão do PrimeFix"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/primefix.git
git push -u origin main
```

Substitua `SEU_USUARIO` pelo seu nome de usuário do GitHub.

> ⚠️ Se for a primeira vez usando git, talvez seja preciso configurar seu nome e e-mail:
> ```bash
> git config --global user.name "Seu Nome"
> git config --global user.email "seu-email@exemplo.com"
> ```

> ✅ O arquivo `.gitignore` já está configurado para não subir `.env`, `venv/` e arquivos temporários.

---

## PARTE 2 — Criar o banco PostgreSQL no Render

### 1. Crie uma conta no Render
Acesse https://render.com e crie sua conta (pode usar login do GitHub).

### 2. Crie o banco de dados
1. No painel do Render, clique em **New +** → **PostgreSQL**.
2. Dê um nome, por exemplo: `primefix-db`.
3. Escolha a região (de preferência mais próxima do Brasil, ex: Ohio ou Oregon — o Render não tem região no Brasil ainda).
4. Escolha o plano **Free** (para testes).
5. Clique em **Create Database**.

### 3. Copie a URL de conexão
1. Após criado, abra o banco.
2. Procure por **Internal Database URL** (para usar dentro do Render) e **External Database URL** (para usar do seu computador).
3. Guarde a **External Database URL** — você vai usar agora para criar as tabelas.

### 4. Crie as tabelas (schema.sql)
No seu computador, com o `psql` instalado, rode:

```bash
psql "COLE_AQUI_A_EXTERNAL_DATABASE_URL" -f db/schema.sql
```

Isso vai criar todas as tabelas, enums, triggers e os dados iniciais (config do WhatsApp e categorias).

### 5. Crie o super admin
Rode localmente:

```bash
pip install werkzeug
python gerar_hash_senha.py
```

Digite a senha desejada. O script vai gerar um comando `INSERT INTO users ...`. Copie esse comando e rode:

```bash
psql "COLE_AQUI_A_EXTERNAL_DATABASE_URL" -c "INSERT INTO users (nome, email, senha_hash, role) VALUES (...);"
```

(ou cole o comando inteiro gerado pelo script)

---

## PARTE 3 — Subir a aplicação Flask no Render

### 1. Crie um novo Web Service
1. No painel do Render, clique em **New +** → **Web Service**.
2. Conecte sua conta do GitHub (se ainda não conectou).
3. Selecione o repositório `primefix`.

### 2. Configure o serviço
- **Name**: `primefix` (ou o nome que quiser)
- **Region**: a mesma do banco de dados (importante para conectar via Internal URL)
- **Branch**: `main`
- **Runtime**: `Python 3`
- **Build Command**:
  ```
  pip install -r requirements.txt
  ```
- **Start Command**:
  ```
  gunicorn app:app
  ```
- **Plan**: Free

### 3. Configure as variáveis de ambiente
Na seção **Environment Variables**, adicione:

| Nome | Valor |
|------|-------|
| `DATABASE_URL` | a **Internal Database URL** do banco criado na Parte 2 |
| `SECRET_KEY` | qualquer string aleatória e segura (ex: gere com `python -c "import secrets; print(secrets.token_hex(32))"`) |

### 4. Deploy
Clique em **Create Web Service**. O Render vai:
1. Clonar seu repositório do GitHub
2. Instalar as dependências (`requirements.txt`)
3. Iniciar a aplicação com `gunicorn app:app`

Após alguns minutos, sua aplicação estará disponível em uma URL como:

```
https://primefix.onrender.com
```

---

## PARTE 4 — Atualizações futuras

Toda vez que você quiser atualizar o sistema online, basta:

```bash
git add .
git commit -m "Descrição da alteração"
git push
```

O Render detecta o push automaticamente e refaz o deploy.

---

## ⚠️ Observações importantes

- O plano **Free** do Render "dorme" o serviço após um tempo sem uso — a primeira requisição depois disso pode demorar ~30s para responder.
- O banco PostgreSQL gratuito do Render expira após um tempo (geralmente 90 dias) — verifique a política atual no painel do Render antes de usar em produção real.
- Nunca suba o arquivo `.env` para o GitHub (ele já está no `.gitignore`). As variáveis de ambiente reais (senhas, URLs do banco) ficam configuradas direto no painel do Render.
- O **super_admin** não tem cadastro público — é criado apenas via SQL direto no banco, como mostrado na Parte 2.

---

## ✅ Checklist final

- [ ] Projeto no GitHub
- [ ] Banco PostgreSQL criado no Render
- [ ] Tabelas criadas (`schema.sql`)
- [ ] Super admin criado
- [ ] Web Service criado no Render
- [ ] Variáveis `DATABASE_URL` e `SECRET_KEY` configuradas
- [ ] Deploy concluído e site acessível
