# PrimeFix — Gestão de Serviços Técnicos

Aplicação web desenvolvida como projeto de portfólio para organizar solicitações de serviços, atribuição de técnicos e acompanhamento de ordens de serviço em um fluxo centralizado.

> **Status:** projeto de portfólio em desenvolvimento. Antes de usar em produção, é necessário revisar e testar configurações, segurança, banco de dados, envio de e-mails e implantação.

## Visão geral

O PrimeFix possui áreas separadas para clientes, técnicos e administração. O objetivo é organizar o ciclo de uma ordem de serviço, desde a solicitação até a execução e o encerramento.

### Funcionalidades implementadas no projeto

- Cadastro e autenticação de usuários.
- Perfis de acesso para cliente, técnico e administração.
- Cadastro de solicitações de serviço (ordens de serviço) pelo cliente.
- Acompanhamento e visualização dos detalhes das ordens de serviço.
- Atribuição e gerenciamento de ordens de serviço pela administração.
- Aprovação ou recusa de técnicos cadastrados.
- Sugestão e aprovação de valores do serviço.
- Atualização do andamento da ordem de serviço pelo técnico.
- Gerenciamento de categorias de serviços.
- Perfil, especialidades e disponibilidade do técnico.
- Painéis administrativos, área financeira e relatórios.
- Fluxo de recuperação de senha por e-mail, configurado para SMTP do Gmail.

## Tecnologias utilizadas

- **Python**
- **Flask** — aplicação web e rotas
- **PostgreSQL** — banco de dados relacional
- **psycopg** — conexão com o PostgreSQL
- **Jinja2** — renderização dos templates HTML
- **HTML, CSS e JavaScript**
- **Bootstrap** — componentes e layout da interface
- **Flask-Mail** — envio de e-mails
- **python-dotenv** — carregamento de variáveis de ambiente
- **Git e GitHub** — versionamento do código

## Capturas de tela

As imagens da interface estão na pasta [`screenshots/`](screenshots/). Elas incluem a página inicial, categorias de serviços e telas das áreas administrativas e de usuários.

### Página inicial

![Página inicial do PrimeFix](<screenshots/pagina inicial - parte 1.jpeg>)

### Categorias de serviços

![Categorias de serviços do PrimeFix](<screenshots/WhatsApp Image 2.jpeg>)

### Gerenciamento de ordens de serviço

![Lista de ordens de serviço](<screenshots/WhatsApp Image 2026-10-14 at 15.43.48.jpeg>)

## Estrutura do projeto

```text
primefix/
├── app.py                  # Inicialização da aplicação e rotas gerais
├── auth.py                 # Autenticação, cadastro e controle de acesso
├── db.py                   # Conexão e consultas ao PostgreSQL
├── routes/
│   ├── admin.py             # Rotas administrativas
│   ├── client.py            # Rotas da área do cliente
│   └── technician.py        # Rotas da área do técnico
├── templates/               # Templates HTML/Jinja2
├── static/                  # Arquivos estáticos, como CSS
├── db/                      # Scripts SQL do banco de dados
├── screenshots/             # Capturas de tela do projeto
├── requirements.txt         # Dependências Python
├── .env.example             # Modelo de variáveis de ambiente
├── .gitignore               # Arquivos que não devem ser versionados
├── Procfile                 # Comando de inicialização para hospedagem compatível
└── DEPLOY.md                # Orientações de publicação
```

## Requisitos

- Python instalado (recomenda-se Python 3.11 ou 3.12 para começar; a compatibilidade deve ser validada no ambiente utilizado).
- PostgreSQL instalado e em execução, ou uma instância acessível.
- Git, caso deseje clonar o repositório.

## Como executar localmente

Os comandos abaixo são um guia inicial para Windows usando PowerShell. Execute-os na pasta raiz do projeto, onde está o arquivo `app.py`.

### 1. Clonar o repositório

```powershell
git clone URL_DO_REPOSITORIO
cd primefix
```

Substitua `URL_DO_REPOSITORIO` pelo endereço do repositório no GitHub. Se você já tem o projeto no computador, entre diretamente na pasta que contém `app.py`.

### 2. Criar e ativar o ambiente virtual

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativação do ambiente, não altere políticas de segurança sem entender a mensagem. É possível continuar usando o executável do ambiente virtual diretamente.

### 3. Instalar as dependências

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar as variáveis de ambiente

Faça uma cópia de `.env.example` com o nome `.env` na raiz do projeto e preencha os valores para o seu ambiente. Configure, no mínimo:

```env
DATABASE_URL=postgresql://usuario:senha@localhost:5432/primefix
SECRET_KEY=gere-uma-chave-aleatoria-e-segura
MAIL_USERNAME=seu-email@gmail.com
MAIL_PASSWORD=sua-senha-de-aplicativo
```

Use uma senha de aplicativo do Gmail, se habilitar o envio de e-mails. Não use sua senha normal da conta. Os valores acima são exemplos: substitua-os pelos dados do seu ambiente.

**Nunca publique o arquivo `.env` nem credenciais reais no GitHub.** O arquivo `.env` deve permanecer ignorado pelo Git.

### 5. Preparar o banco de dados

Crie um banco PostgreSQL chamado `primefix` (ou ajuste a `DATABASE_URL` para o nome escolhido). Revise o script SQL apropriado dentro de `db/` e execute-o no banco antes de iniciar a aplicação.

O projeto contém mais de um arquivo de schema SQL. Confirme qual versão corresponde ao código atual antes de executar qualquer script, principalmente em um banco que já contenha dados.

### 6. Iniciar a aplicação

```powershell
python app.py
```

Depois, abra no navegador o endereço local informado pelo Flask no terminal (normalmente `http://127.0.0.1:5000/`).

> A inicialização depende de um banco configurado corretamente e das variáveis de ambiente necessárias. As contas de teste e o usuário administrador devem ser configurados no seu ambiente; não compartilhe senhas no repositório.

## Segurança e boas práticas

- Não versionar `.env`, senhas, tokens ou URLs de banco com credenciais.
- Não incluir o ambiente virtual `.venv/`, arquivos `__pycache__/` ou configurações pessoais da IDE.
- Usar uma `SECRET_KEY` forte e exclusiva fora do ambiente local.
- Validar permissões por perfil e acesso às ordens de serviço antes de qualquer uso real.
- Testar fluxos de autenticação, recuperação de senha, operações de banco e tratamento de erros.
- Revisar as configurações de produção antes de publicar a aplicação na internet.

## Próximas melhorias

- Automatizar testes dos principais fluxos e permissões.
- Documentar o modelo do banco de dados e a criação inicial do administrador.
- Validar e padronizar os scripts SQL de schema.
- Melhorar a documentação de configuração e implantação.
- Preparar uma demonstração hospedada, quando a aplicação estiver revisada para esse objetivo.

## Autor

**Leonardo Portuguez**  
Estudante de Análise e Desenvolvimento de Sistemas, com foco em desenvolvimento web e soluções com Python e bancos de dados.

- GitHub: [leonardoportuguez](https://github.com/leonardoportuguez)
