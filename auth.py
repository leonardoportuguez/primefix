from functools import wraps
from datetime import datetime, timedelta
from datetime import datetime, timedelta
from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import query

def register_user(nome, email, senha, role):
    """
    Cadastra um novo usuário.
    Cadastro público só permite 'client' ou 'technician'.
    Retorna (sucesso: bool, mensagem: str)
    """
    if role not in ("client", "technician"):
        return False, "Tipo de cadastro inválido."

    existente = query(
        "SELECT id FROM users WHERE email = %s",
        (email,),
        fetchone=True,
    )
    if existente:
        return False, "Este e-mail já está cadastrado."

    senha_hash = generate_password_hash(senha)

    novo_usuario = query(
        """
        INSERT INTO users (nome, email, senha_hash, role)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (nome, email, senha_hash, role),
        fetchone=True,
        commit=True,
    )

    # Se for técnico, cria o cadastro como PENDENTE.
    #
    # O técnico ainda precisa ser analisado pelo administrador.
    # As 48 horas são apenas um prazo de acompanhamento.
    # O administrador pode aprovar ou recusar antes ou depois desse prazo.
    if role == "technician":
        prazo_analise = datetime.now() + timedelta(hours=48)

        query(
            """
            INSERT INTO technicians (
                user_id,
                nome,
                status,
                status_aprovacao,
                prazo_analise
            )
            VALUES (%s, %s, 'inativo', 'pendente', %s)
            """,
            (novo_usuario["id"], nome, prazo_analise),
            commit=True,
        )
    return True, "Cadastro realizado com sucesso."


def authenticate_user(email, senha):
    """
    Verifica e-mail e senha.
    Retorna o usuário (dict) se válido, ou None.
    """
    usuario = query(
        "SELECT id, nome, email, senha_hash, role FROM users WHERE email = %s",
        (email,),
        fetchone=True,
    )

    if usuario and check_password_hash(usuario["senha_hash"], senha):
        return usuario

    return None


def login_required(f):
    """Decorator: exige que o usuário esteja logado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator: exige que o usuário logado tenha um dos papéis informados."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Faça login para continuar.", "warning")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("Você não tem permissão para acessar esta página.", "danger")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_dashboard_url(role):
    """Retorna a rota de dashboard correta de acordo com o papel do usuário."""
    if role == "admin" or role == "super_admin":
        return url_for("admin.dashboard")
    elif role == "client":
        return url_for("client.home")
    elif role == "technician":
        return url_for("technician.dashboard")
    return url_for("login")
