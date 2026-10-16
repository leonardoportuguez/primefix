# ============================================================
# app.py - ARQUIVO PRINCIPAL DA APLICAÇÃO PRIMEFIX
# ============================================================
# Este é o ponto de entrada do sistema Flask.
# Aqui ficam:
#   - A criação do app Flask
#   - O registro dos blueprints (módulos de rotas separados)
#   - As rotas "gerais" do sistema: página inicial, login,
#     cadastro e logout
#
# As rotas específicas de cada tipo de usuário (admin, cliente,
# técnico) estão organizadas em arquivos separados dentro da
# pasta routes/.
# ============================================================
import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from dotenv import load_dotenv

# Funções de autenticação (login, cadastro, redirecionamento por papel)
from auth import register_user, authenticate_user, get_dashboard_url

# Blueprints: cada um agrupa as rotas de um tipo de usuário
from routes.admin import admin_bp
from routes.client import client_bp
from routes.technician import technician_bp

# Função para fazer consultas ao banco PostgreSQL
from db import query


# ------------------------------------------------------------
# Carrega as variáveis de ambiente do arquivo .env
# (DATABASE_URL, SECRET_KEY, MAIL_USERNAME, MAIL_PASSWORD, etc.)
# ------------------------------------------------------------
load_dotenv()


# ------------------------------------------------------------
# Cria a aplicação Flask
# ------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")


# ------------------------------------------------------------
# Configuração do Flask-Mail — usa Gmail SMTP com senha de
# app (nunca a senha normal da conta). Credenciais vêm do .env
# ------------------------------------------------------------
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME")
mail = Mail(app)

# ------------------------------------------------------------
# Registra os blueprints (rotas de admin, cliente e técnico)
# Cada blueprint tem seu próprio prefixo de URL, definido
# dentro do respectivo arquivo em routes/
# ------------------------------------------------------------
app.register_blueprint(admin_bp)
app.register_blueprint(client_bp)
app.register_blueprint(technician_bp)


# ------------------------------------------------------------
# Mapa de ícones (emoji) para cada categoria de serviço.
# Usado apenas para exibição na página inicial.
#
# Se você cadastrar uma categoria nova que não está nesta
# lista, o ícone padrão "🛠️" será usado automaticamente.
#
# Para adicionar um ícone novo, basta incluir uma linha no
# formato: "Nome exato da categoria": "emoji",
# ------------------------------------------------------------
CATEGORY_ICONS = {
    "Elétrica": "⚡",
    "Hidráulica": "🚰",
    "Ar Condicionado": "❄️",
    "Eletrodomésticos": "🔌",
    "Pintura": "🎨",
    "Câmeras de Segurança": "📷",
    "Montagem de Móveis": "🪑",
    "Cortinas e Persianas": "🪟",
    "Manutenção Geral": "🔧",
}


# ============================================================
# ROTA: Página inicial ("/")
# ============================================================
# - Se o usuário já estiver logado, redireciona direto para
#   o dashboard correspondente ao seu papel (admin/cliente/técnico).
# - Se não estiver logado, mostra a landing page com a lista
#   de categorias de serviço cadastradas no banco.
# ============================================================
@app.route("/")
def index():
  
    # Busca todas as categorias cadastradas na tabela "categories"
    categorias_db = query(
        "SELECT nome, descricao FROM categories ORDER BY ordem",
        fetchall=True,
    )

    # Monta a lista final, já incluindo o ícone de cada categoria
    categorias = []
    for c in categorias_db:
        categorias.append({
            "nome": c["nome"],
            "descricao": c["descricao"],
            "icone": CATEGORY_ICONS.get(c["nome"], "🛠️"),
        })

    return render_template("index.html", categorias=categorias)


# ============================================================
# ROTA: Cadastro de novos usuários ("/cadastro")
# ============================================================
# - GET: mostra o formulário de cadastro
# - POST: processa o formulário e cria o usuário
#
# Cadastro público só permite os papéis "client" (cliente)
# e "technician" (técnico). Admin e super_admin NÃO podem
# ser criados por aqui (ver auth.py -> register_user).
# ============================================================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    # --------------------------------------------------------
    # Modo manutenção: se estiver ativo, bloqueia novos
    # cadastros (tanto GET quanto POST), redirecionando pra
    # home com uma mensagem explicando o motivo
    # --------------------------------------------------------
    config_manut = query(
        "SELECT value FROM system_config WHERE key='modo_manutencao'",
        fetchone=True)
    if config_manut and config_manut["value"] == "true":
        flash("🚧 Estamos em manutenção no momento. Novos cadastros "
              "estão temporariamente indisponíveis.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        role = request.form.get("role", "client")

        if not nome or not email or not senha:
            flash("Preencha todos os campos.", "danger")
            return redirect(url_for("cadastro"))

        sucesso, mensagem = register_user(nome, email, senha, role)

        if sucesso:
            flash(mensagem, "success")
            return redirect(url_for("login"))
        else:
            flash(mensagem, "danger")
            return redirect(url_for("cadastro"))

    return render_template("cadastro.html")


# ============================================================
# ROTA: Login ("/login")
# ============================================================
# - GET: mostra o formulário de login
# - POST: valida e-mail/senha e cria a sessão do usuário
#
# Após o login, o usuário é redirecionado automaticamente
# para o dashboard correspondente ao seu papel (role):
#   - admin / super_admin -> /admin/dashboard
#   - client              -> /cliente/home
#   - technician          -> /tecnico/dashboard
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        usuario = authenticate_user(email, senha)

        if usuario:
            # Salva os dados do usuário na sessão
            session["user_id"] = usuario["id"]
            session["nome"] = usuario["nome"]
            session["role"] = usuario["role"]
            flash(f"Bem-vindo, {usuario['nome']}!", "success")
            return redirect(get_dashboard_url(usuario["role"]))
        else:
            flash("E-mail ou senha incorretos.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


# ============================================================
# ROTA: Solicitar recuperação de senha ("/esqueci-senha")
# ============================================================
# - GET: mostra o formulário pedindo o e-mail
# - POST: se o e-mail existir, gera um token temporário
#   (válido por 1 hora) e envia um link de redefinição por
#   e-mail. Por segurança, a mensagem de sucesso é sempre a
#   mesma, exista ou não o e-mail cadastrado — assim ninguém
#   consegue descobrir quais e-mails estão no sistema só
#   testando no formulário
# ============================================================
@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = query("SELECT id, nome FROM users WHERE email=%s", (email,), fetchone=True)

        if usuario:
            # Gera um token aleatório seguro e válido por 1 hora
            token = secrets.token_urlsafe(32)
            expira_em = datetime.now() + timedelta(hours=1)

            query(
                "INSERT INTO password_reset_tokens (user_id, token, expira_em) VALUES (%s, %s, %s)",
                (usuario["id"], token, expira_em), commit=True)

            link = url_for("redefinir_senha", token=token, _external=True)

            try:
                msg = Message("Recuperação de senha — PrimeFix", recipients=[email])
                msg.body = (
                    f"Olá, {usuario['nome']}!\n\n"
                    f"Recebemos uma solicitação para redefinir sua senha no PrimeFix.\n"
                    f"Clique no link abaixo para criar uma nova senha (válido por 1 hora):\n\n"
                    f"{link}\n\n"
                    f"Se você não solicitou isso, pode ignorar este e-mail."
                )
                mail.send(msg)
            except Exception:
                # Se o envio falhar (ex: credenciais erradas), não
                # expõe o erro técnico pro usuário final
                flash("Não foi possível enviar o e-mail agora. Tente novamente mais tarde.", "danger")
                return redirect(url_for("esqueci_senha"))

        flash("Se o e-mail estiver cadastrado, você receberá um link de recuperação.", "success")
        return redirect(url_for("login"))

    return render_template("esqueci_senha.html")


# ============================================================
# ROTA: Redefinir senha via token ("/redefinir-senha/<token>")
# ============================================================
# - Valida se o token existe, não expirou e não foi usado antes
# - GET: mostra o formulário de nova senha
# - POST: grava a nova senha (com hash) e invalida o token,
#   pra ele não poder ser reaproveitado
# ============================================================
@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    registro = query(
        "SELECT user_id, expira_em, usado FROM password_reset_tokens WHERE token=%s",
        (token,), fetchone=True)

    if not registro or registro["usado"] or registro["expira_em"] < datetime.now():
        flash("Link inválido ou expirado. Solicite a recuperação novamente.", "danger")
        return redirect(url_for("esqueci_senha"))

    if request.method == "POST":
        from werkzeug.security import generate_password_hash

        nova_senha = request.form.get("senha", "")
        confirmar = request.form.get("confirmar_senha", "")

        if not nova_senha or nova_senha != confirmar:
            flash("As senhas não coincidem.", "danger")
            return redirect(url_for("redefinir_senha", token=token))

        senha_hash = generate_password_hash(nova_senha)
        query("UPDATE users SET senha_hash=%s WHERE id=%s",
              (senha_hash, registro["user_id"]), commit=True)

        # Marca o token como usado, pra não poder ser reaproveitado
        query("UPDATE password_reset_tokens SET usado=TRUE WHERE token=%s",
              (token,), commit=True)

        flash("✅ Senha redefinida com sucesso! Faça login com a nova senha.", "success")
        return redirect(url_for("login"))

    return render_template("redefinir_senha.html", token=token)


# ============================================================
# ROTA: Logout ("/logout")
# ============================================================
# Limpa a sessão do usuário e volta para a página inicial.
# ============================================================
@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu do sistema.", "success")
    return redirect(url_for("index"))


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================
# Quando este arquivo é executado diretamente (python app.py
# ou py app.py), inicia o servidor de desenvolvimento do Flask.
#
# Em produção (Render), quem inicia a aplicação é o Gunicorn,
# conforme configurado no arquivo "Procfile".
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)
