from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from auth import role_required, login_required
from db import query

client_bp = Blueprint("client", __name__, url_prefix="/cliente")


# Dicionário de ícones por categoria
CATEGORY_ICONS = {
    "Elétrica":                "⚡",
    "Hidráulica":              "🚰",
    "Ar Condicionado":         "❄️",
    "Eletrodomésticos":        "🔌",
    "Pintura":                 "🎨",
    "Câmeras de Segurança":    "📷",
    "Montagem de Móveis":      "🪑",
    "Cortinas e Persianas":    "🪟",
    "Manutenção Geral":        "🔧",
    "Paisagismo e Jardinagem": "🌿",
    "Outro":                   "🛠️",
}


# ============================================================
# HOME DO CLIENTE
# ============================================================
@client_bp.route("/home")
@role_required("client")
def home():
    user_id = session["user_id"]

    cats_db = query("SELECT id, nome FROM categories ORDER BY ordem", fetchall=True)
    categorias = [
        {"id": c["id"], "nome": c["nome"], "icone": CATEGORY_ICONS.get(c["nome"], "🛠️")}
        for c in cats_db
    ]

    ordens = query(
        """SELECT so.id, so.status, so.descricao,
                  so.cidade, so.bairro, so.logradouro, so.numero,
                  so.complemento, so.referencia,
                  so.data_agendamento, so.valor_confirmado,
                  so.tipo_solicitacao, so.valor_visita,
                  c.nome AS categoria_nome,
                  u.nome AS tecnico_nome
           FROM service_orders so
           JOIN categories c ON so.category_id = c.id
           LEFT JOIN technicians t ON so.technician_id = t.id
           LEFT JOIN users u ON t.user_id = u.id
           WHERE so.client_id = %s
           ORDER BY so.created_at DESC""",
        (user_id,), fetchall=True)

    config = query("SELECT value FROM system_config WHERE key='whatsapp_number'", fetchone=True)

    return render_template("cliente_home.html",
                           categorias=categorias,
                           ordens=ordens,
                           whatsapp=config["value"] if config else None)


# ============================================================
# CRIAR OS — salva tipo de solicitação e valor da visita
# ============================================================
@client_bp.route("/criar-os", methods=["POST"])
@role_required("client")
def criar_os():
    # --------------------------------------------------------
    # Modo manutenção: se estiver ativo, bloqueia criação de
    # novas OS, mantendo o cliente na própria home com aviso
    # --------------------------------------------------------
    config_manut = query(
        "SELECT value FROM system_config WHERE key='modo_manutencao'",
        fetchone=True)
    if config_manut and config_manut["value"] == "true":
        flash("🚧 Estamos em manutenção no momento. Novas solicitações "
              "estão temporariamente indisponíveis.", "warning")
        return redirect(url_for("client.home"))

    user_id          = session["user_id"]
    categoria_id     = request.form.get("categoria_id", "").strip()
    descricao        = request.form.get("descricao", "").strip()
    cidade           = request.form.get("cidade", "").strip()
    bairro           = request.form.get("bairro", "").strip()
    logradouro       = request.form.get("logradouro", "").strip()
    numero           = request.form.get("numero", "").strip()
    complemento      = request.form.get("complemento", "").strip()
    referencia       = request.form.get("referencia", "").strip()
    tipo_solicitacao = request.form.get("tipo_solicitacao", "orcamento_online").strip()

    # Se escolheu "Outro" no bairro usa o campo manual
    if bairro == "__outro__":
        bairro = request.form.get("bairro_manual", "").strip()

    # Validação dos campos obrigatórios
    if not categoria_id or not descricao or not cidade or not bairro or not logradouro:
        flash("Preencha todos os campos obrigatórios.", "danger")
        return redirect(url_for("client.home"))

    if tipo_solicitacao not in ["orcamento_online", "visita_tecnica"]:
        flash("Selecione o tipo de solicitação.", "danger")
        return redirect(url_for("client.home"))

    # --------------------------------------------------------
    # Se for visita técnica, busca o valor configurável salvo
    # em system_config (em vez do valor fixo de antes). Se a
    # taxa estiver desativada pelo admin, a visita fica sem custo
    # --------------------------------------------------------
    valor_visita = None
    if tipo_solicitacao == "visita_tecnica":
        cfg_visita = query(
            "SELECT key, value FROM system_config WHERE key IN "
            "('taxa_visita_ativa', 'taxa_visita_valor')",
            fetchall=True)
        cfg_visita = {linha["key"]: linha["value"] for linha in cfg_visita}
        if cfg_visita.get("taxa_visita_ativa") == "true":
            valor_visita = float(cfg_visita.get("taxa_visita_valor", 0))

    # Monta string de endereço completo
    endereco = f"{logradouro}{', ' + numero if numero else ''} — {bairro}, {cidade}"
    if referencia:
        endereco += f" (Ref: {referencia})"

    query(
        """INSERT INTO service_orders
               (client_id, category_id, status, descricao,
                cidade, bairro, logradouro, numero, complemento,
                referencia, endereco, tipo_solicitacao, valor_visita)
           VALUES (%s, %s, 'aberta', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, categoria_id, descricao, cidade, bairro,
         logradouro, numero, complemento, referencia,
         endereco, tipo_solicitacao, valor_visita),
        commit=True)

    # Mensagem personalizada conforme o tipo
    if tipo_solicitacao == "visita_tecnica":
        if valor_visita:
            # Busca a mensagem configurável do admin e troca {valor}
            # pelo valor formatado em reais
            cfg_msg = query(
                "SELECT value FROM system_config WHERE key='taxa_visita_mensagem'",
                fetchone=True)
            template_msg = cfg_msg["value"] if cfg_msg and cfg_msg["value"] else (
                "✅ Visita técnica solicitada! Entraremos em contato para agendar. "
                "Lembre-se: R$ {valor} pagos no dia da visita.")
            mensagem = template_msg.replace("{valor}", f"{valor_visita:.2f}")
            flash(mensagem, "success")
        else:
            flash("✅ Visita técnica solicitada! Entraremos em contato para agendar.", "success")
    else:
        flash("✅ Orçamento online solicitado! Em breve entraremos em contato.", "success")
    return redirect(url_for("client.home"))


# ============================================================
# VER OS INDIVIDUAL
# ============================================================
@client_bp.route("/os/<int:os_id>/cancelar", methods=["POST"])
@role_required("client")
def cancelar_os(os_id):
    user_id = session["user_id"]
    motivo = request.form.get("motivo", "").strip()

    # --------------------------------------------------------
    # Só cancela se a OS pertencer a este cliente (ownership) E
    # estiver em um dos 3 status que ainda permitem cancelamento.
    # Se não bater as duas condições, o UPDATE não afeta nenhuma
    # linha — nem precisa de checagem manual de erro depois.
    # --------------------------------------------------------
    query(
        """UPDATE service_orders
           SET status='cancelada', motivo_cancelamento=%s
           WHERE id=%s AND client_id=%s
             AND status IN ('aberta', 'atribuida', 'em_andamento')""",
        (motivo, os_id, user_id), commit=True)

    flash("✅ Solicitação cancelada.", "success")
    return redirect(url_for("client.home"))


@client_bp.route("/os/<int:os_id>")
@role_required("client")
def ver_os(os_id):
    user_id = session["user_id"]

    os = query(
        """SELECT so.*, c.nome AS categoria_nome, u.nome AS tecnico_nome
           FROM service_orders so
           JOIN categories c ON so.category_id = c.id
           LEFT JOIN technicians t ON so.technician_id = t.id
           LEFT JOIN users u ON t.user_id = u.id
           WHERE so.id = %s AND so.client_id = %s""",
        (os_id, user_id), fetchone=True)

    if not os:
        flash("OS não encontrada.", "danger")
        return redirect(url_for("client.home"))

    # Busca as especialidades (categorias) do técnico atribuído a esta OS,
    # para mostrar nos flash cards de habilidades na tela do cliente.
    # Os ícones são reutilizados do dicionário CATEGORY_ICONS já existente,
    # sem criar uma nova coluna no banco de dados.
    habilidades = []

    if os["technician_id"]:
        categorias_tecnico = query(
            """SELECT c.nome
               FROM technician_categories tc
               JOIN categories c ON tc.category_id = c.id
               WHERE tc.technician_id = %s
               ORDER BY c.nome""",
            (os["technician_id"],), fetchall=True)

        habilidades = [
            {
                "nome": categoria["nome"],
                "icone": CATEGORY_ICONS.get(categoria["nome"], "🛠️")
            }
            for categoria in categorias_tecnico
        ]

    return render_template("cliente_os_detalhe.html", os=os, habilidades=habilidades)

# Cliente aprova ou recusa o serviço após o admin confirmar o valor.
@client_bp.route("/os/<int:os_id>/aprovar", methods=["POST"])
@login_required
def aprovar_servico(os_id):
    user_id = session["user_id"]

    os = query(
        """SELECT id, status, valor_confirmado
           FROM service_orders
           WHERE id = %s AND client_id = %s""",
        (os_id, user_id),
        fetchone=True
    )

    if not os:
        flash("OS não encontrada.", "danger")
        return redirect(url_for("client.home"))

    if not os["valor_confirmado"]:
        flash("O valor do serviço ainda não foi confirmado pelo administrador.", "warning")
        return redirect(url_for("client.ver_os", os_id=os_id))

    query(
        """UPDATE service_orders
           SET aprovacao_cliente = 'aprovado'
           WHERE id = %s AND client_id = %s""",
        (os_id, user_id),
        commit=True
    )
    flash("Serviço aprovado com sucesso!", "success")
    return redirect(url_for("client.ver_os", os_id=os_id))


# Cliente recusa o serviço após o admin confirmar o valor.
@client_bp.route("/os/<int:os_id>/recusar", methods=["POST"])
@login_required
def recusar_servico(os_id):
    user_id = session["user_id"]

    os = query(
        """SELECT id, status, valor_confirmado
           FROM service_orders
           WHERE id = %s AND client_id = %s""",
        (os_id, user_id),
        fetchone=True
    )

    if not os:
        flash("OS não encontrada.", "danger")
        return redirect(url_for("client.home"))

    if not os["valor_confirmado"]:
        flash("O valor do serviço ainda não foi confirmado pelo administrador.", "warning")
        return redirect(url_for("client.ver_os", os_id=os_id))

    query(
        """UPDATE service_orders
           SET aprovacao_cliente = 'recusado'
           WHERE id = %s AND client_id = %s""",
        (os_id, user_id),
        commit=True
    )
    flash("Serviço recusado.", "warning")
    return redirect(url_for("client.ver_os", os_id=os_id))

