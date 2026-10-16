from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from auth import role_required
from db import query
from datetime import datetime

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Dicionário de ícones por categoria — usado para exibir emoji nos cards
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

# Retorna quantidade de OS abertas — usado para o badge da sidebar
def _contar_pendentes():
    r = query("SELECT COUNT(*) AS n FROM service_orders WHERE status='aberta'", fetchone=True)
    return r["n"] if r else 0

# Soma o valor_confirmado das OS finalizadas no mês atual
def _faturamento_mes():
    r = query(
        """SELECT COALESCE(SUM(valor_confirmado), 0) AS total
           FROM service_orders
           WHERE status = 'finalizada'
           AND DATE_TRUNC('month', updated_at) = DATE_TRUNC('month', CURRENT_DATE)""",
        fetchone=True)
    return float(r["total"]) if r else 0.0

# --------------------------------------------------------------
# Verifica OS 'atribuida' que passaram do prazo de resposta do
# técnico (config 'prazo_resposta_tecnico_horas') e devolve pra
# fila (volta pra 'aberta', sem técnico). Não existe um robô
# rodando sozinho em segundo plano — essa checagem roda de verdade
# toda vez que o admin abre o dashboard, que é a tela mais usada.
# --------------------------------------------------------------
def _reatribuir_os_vencidas():
    # ------------------------------------------------------------------
    # Essa função verifica se alguma OS "atribuida" já passou do prazo
    # que o técnico tinha pra responder, e se passou, devolve ela pra
    # fila sozinha. Ela não fica rodando o tempo todo em segundo plano —
    # é chamada manualmente toda vez que o admin abre o dashboard
    # (ver Edição 2), então a checagem só acontece nesse momento.
    # ------------------------------------------------------------------

    # 1) Busca na tabela system_config qual é o prazo configurado
    #    (em horas) pra chave 'prazo_resposta_tecnico_horas'.
    #    fetchone=True retorna só 1 linha (ou None se a chave não existir).
    prazo_row = query(
        "SELECT value FROM system_config WHERE key='prazo_resposta_tecnico_horas'",
        fetchone=True)

    # 2) Se a chave ainda não foi configurada (prazo_row é None) ou o
    #    valor guardado está vazio, a função para aqui — sem prazo
    #    definido, não tem como saber o que está "vencido".
    if not prazo_row or not prazo_row["value"]:
        return

    # 3) Converte o valor guardado (que vem sempre como texto do banco,
    #    ex: "24") pra número decimal, pra poder usar em cálculo de tempo.
    prazo_horas = float(prazo_row["value"])

    # 4) Roda o UPDATE que faz o trabalho de verdade:
    #    - Só mexe em OS com status='atribuida' (que já tem técnico,
    #      mas ele ainda não começou a atender)
    #    - AND atribuida_em IS NOT NULL: só considera OS que realmente
    #      têm a data de atribuição preenchida (evita erro em OS antigas
    #      criadas antes dessa coluna existir)
    #    - AND atribuida_em < NOW() - (%s || ' hours')::INTERVAL:
    #      esse é o cálculo do prazo. NOW() é a data/hora atual do banco.
    #      (%s || ' hours')::INTERVAL transforma o número de horas
    #      (ex: 24) num "intervalo de tempo" que o PostgreSQL entende
    #      (ex: 24 horas). NOW() - esse intervalo dá a data/hora limite
    #      — se a OS foi atribuída ANTES desse limite, já venceu.
    #    O SET devolve a OS pro estado de "recém-criada": tira o
    #    técnico (technician_id=NULL), volta o status pra 'aberta' e
    #    limpa a data de atribuição (atribuida_em=NULL), pronta pra
    #    ser atribuída de novo a outro técnico.
    query(
        """UPDATE service_orders
           SET technician_id=NULL, status='aberta', atribuida_em=NULL
           WHERE status='atribuida'
             AND atribuida_em IS NOT NULL
             AND atribuida_em < NOW() - (%s || ' hours')::INTERVAL""",
        (prazo_horas,), commit=True)

# Busca todas as OS com joins para pegar nome do cliente, categoria e técnico
def _buscar_ordens():
    return query(
        """SELECT so.id, so.status, so.descricao,
                  so.cidade, so.bairro, so.logradouro, so.numero,
                  so.complemento, so.data_agendamento,
                  so.valor_sugerido, so.valor_confirmado,
                  so.observacao_tecnico, so.created_at,
                  so.technician_id AS tecnico_id,
                  c.nome  AS categoria_nome,
                  u_cli.nome AS cliente_nome,
                  u_tec.nome AS tecnico_nome
           FROM service_orders so
           JOIN categories c       ON so.category_id  = c.id
           JOIN users u_cli        ON so.client_id     = u_cli.id
           LEFT JOIN technicians t ON so.technician_id = t.id
           LEFT JOIN users u_tec   ON t.user_id        = u_tec.id
           ORDER BY so.created_at DESC""",
        fetchall=True)


# ============================================================
# DASHBOARD — página principal do admin
# ============================================================




@admin_bp.route("/dashboard")
@role_required("admin", "super_admin")
def dashboard():
    ordens          = _buscar_ordens()
    total_os        = len(ordens)
    os_pendentes    = sum(1 for o in ordens if o["status"] == "aberta")
    os_andamento    = sum(1 for o in ordens if o["status"] == "em_andamento")
    os_finalizadas  = sum(1 for o in ordens if o["status"] == "finalizada")
    faturamento_mes = _faturamento_mes()

    # Monta lista de notificações para o sininho da topbar
    notificacoes = []

    aguardando = [o for o in ordens if o["valor_sugerido"] and not o["valor_confirmado"]]
    if aguardando:
        notificacoes.append(f"💰 {len(aguardando)} OS aguardando aprovação de valor")

    abertas = [o for o in ordens if o["status"] == "aberta"]
    if abertas:
        notificacoes.append(f"📋 {len(abertas)} OS abertas sem técnico")

    # Busca técnicos que ainda aguardam análise do administrador
    tecnicos_pendentes = query(
        """
        SELECT id, nome, prazo_analise
        FROM technicians
        WHERE status_aprovacao = 'pendente'
        ORDER BY created_at ASC
        """,
        fetchall=True
    )

    if tecnicos_pendentes:
        notificacoes.append(
            f"👨‍🔧 {len(tecnicos_pendentes)} técnico(s) aguardando aprovação"
        )

    config = query(
        "SELECT value FROM system_config WHERE key='whatsapp_number'",
        fetchone=True
    )

    # Busca a porcentagem da empresa configurada
    cfg_taxa = query(
        "SELECT value FROM system_config WHERE key='taxa_empresa'",
        fetchone=True
    )
    taxa_empresa = float(cfg_taxa["value"]) if cfg_taxa else 23.0

    return render_template(
        "admin_dashboard.html",
        ordens=ordens,
        total_os=total_os,
        os_pendentes=os_pendentes,
        os_andamento=os_andamento,
        os_finalizadas=os_finalizadas,
        faturamento_mes=faturamento_mes,
        notificacoes=notificacoes,
        notif_count=len(notificacoes),
        os_pendentes_count=os_pendentes,
        tecnicos_pendentes=tecnicos_pendentes,
        whatsapp=config["value"] if config else "",
        taxa_empresa=taxa_empresa
    )
# ============================================================
# ATRIBUIR TÉCNICO — GET mostra formulário, POST salva
# ============================================================
@admin_bp.route("/assign/<int:os_id>", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def assign_technician(os_id):
    if request.method == "POST":
        tecnico_id = request.form.get("technician_id")

        # --------------------------------------------------------
        # Verifica o limite de OS simultâneas por técnico (config
        # 'limite_os_simultaneas'). Conta quantas OS esse técnico já
        # tem em andamento ('atribuida' ou 'em_andamento') e bloqueia
        # a atribuição se já estiver no limite.
        # --------------------------------------------------------
        limite_row = query(
            "SELECT value FROM system_config WHERE key='limite_os_simultaneas'",
            fetchone=True)
        limite = int(limite_row["value"]) if limite_row and limite_row["value"] else 5

        os_ativas = query(
            """SELECT COUNT(*) AS total FROM service_orders
               WHERE technician_id=%s AND status IN ('atribuida', 'em_andamento')""",
            (tecnico_id,), fetchone=True)

        if os_ativas["total"] >= limite:
            flash(f"⚠️ Este técnico já atingiu o limite de {limite} OS simultâneas. "
                  f"Escolha outro técnico ou aguarde ele finalizar alguma OS.", "danger")
            return redirect(url_for("admin.assign_technician", os_id=os_id))

        query(
            """UPDATE service_orders
               SET technician_id=%s,
                   status='atribuida',
                   atribuida_em=NOW()
               WHERE id=%s""",
            (tecnico_id, os_id),
            commit=True
        )
        flash("✅ Técnico atribuído com sucesso!", "success")
        return redirect(url_for("admin.dashboard"))
    os = query("SELECT * FROM service_orders WHERE id=%s", (os_id,), fetchone=True)
    tecnicos = query(
        "SELECT t.id, u.nome FROM technicians t JOIN users u ON t.user_id=u.id ORDER BY u.nome",
        fetchall=True)
    return render_template("admin_assign.html", os=os, tecnicos=tecnicos,
                           os_pendentes_count=_contar_pendentes(),
                           notificacoes=[], notif_count=0)


# ============================================================
# AGENDAR VISITA — salva data/hora sem iniciar o serviço
# ============================================================
@admin_bp.route("/agendar/<int:os_id>", methods=["POST"])
@role_required("admin", "super_admin")
def agendar(os_id):
    try:
        data = datetime.fromisoformat(request.form.get("data_agendamento", ""))
    except ValueError:
        flash("Data inválida.", "danger")
        return redirect(url_for("admin.dashboard"))
    os_atual = query(
        """SELECT id, status, technician_id
           FROM service_orders
           WHERE id=%s""",
        (os_id,),
        fetchone=True
    )

    if not os_atual:
        flash("OS não encontrada.", "danger")
        return redirect(url_for("admin.dashboard"))

    if os_atual["status"] != "atribuida":
        flash("A OS precisa estar atribuída a um técnico para ser agendada.", "danger")
        return redirect(url_for("admin.dashboard"))

    if not os_atual["technician_id"]:
        flash("A OS não possui técnico atribuído.", "danger")
        return redirect(url_for("admin.dashboard"))

    query(
        """UPDATE service_orders
           SET data_agendamento=%s
           WHERE id=%s AND status='atribuida'""",
        (data, os_id),
        commit=True
    )

    flash(f"📅 Agendado para {data.strftime('%d/%m/%Y às %H:%M')}.", "success")
    return redirect(url_for("admin.dashboard"))


# ============================================================
# CONFIRMAR VALOR — admin aprova o valor sugerido pelo técnico
# ============================================================
@admin_bp.route("/confirmar-valor/<int:os_id>", methods=["POST"])
@role_required("admin", "super_admin")
def confirmar_valor(os_id):
    try:
        valor = float(request.form.get("valor_confirmado", 0))

        if valor <= 0:
            flash("O valor confirmado deve ser maior que R$ 0,00.", "danger")
            return redirect(url_for("admin.dashboard"))

    except (ValueError, TypeError):
        flash("Valor inválido.", "danger")
        return redirect(url_for("admin.dashboard"))

    # --------------------------------------------------------
    # Busca a OS antes de atualizar.
    # Isso garante que ela existe e possui valor sugerido.
    # --------------------------------------------------------
    os_atual = query(
        """SELECT id, valor_sugerido, valor_confirmado
           FROM service_orders
           WHERE id=%s
             AND valor_sugerido IS NOT NULL
             AND valor_sugerido > 0""",
        (os_id,),
        fetchone=True
    )


    if not os_atual:
        flash(
            "Não foi possível confirmar o valor: OS não encontrada "
            "ou ainda não possui um valor sugerido válido.",
            "danger"
        )
        return redirect(url_for("admin.dashboard"))

    # --------------------------------------------------------
    # Atualiza somente uma OS que foi validada acima.
    # --------------------------------------------------------
    query(
        """UPDATE service_orders
           SET valor_confirmado=%s
           WHERE id=%s""",
        (valor, os_id),
        commit=True
    )

    flash("Valor confirmado com sucesso.", "success")
    return redirect(url_for("admin.dashboard"))
# ============================================================
# FINALIZAR OS — muda status para finalizada
# ============================================================
@admin_bp.route("/finish/<int:os_id>", methods=["POST"])
@role_required("admin", "super_admin")
def finish_os(os_id):
    query(
        "UPDATE service_orders SET status='finalizada' WHERE id=%s",
        (os_id,), commit=True)
    flash("✅ OS finalizada com sucesso!", "success")
    return redirect(url_for("admin.dashboard"))

# ============================================================
# ORDENS DE SERVIÇO — lista todas as OS
# ============================================================
@admin_bp.route("/os")
@role_required("admin", "super_admin")
def ordens_servico():
    ordens = _buscar_ordens()

    return render_template(
        "admin_os.html",
        ordens=ordens,
        os_pendentes_count=_contar_pendentes(),
        notificacoes=[],
        notif_count=0
    )

# ============================================================
# VER OS INDIVIDUAL — detalhes completos de uma ordem
# ============================================================
@admin_bp.route("/os/<int:os_id>/cancelar", methods=["POST"])
@role_required("admin", "super_admin")
def cancelar_os(os_id):
    motivo = request.form.get("motivo", "").strip()

    # Admin não precisa de checagem de ownership (pode cancelar
    # qualquer OS), só do status permitido
    query(
        """UPDATE service_orders
           SET status='cancelada', motivo_cancelamento=%s
           WHERE id=%s AND status IN ('aberta', 'atribuida', 'em_andamento')""",
        (motivo, os_id), commit=True)

    flash("✅ OS cancelada.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/os/<int:os_id>")
@role_required("admin", "super_admin")
def ver_os(os_id):
    os = query(
        """SELECT so.*, c.nome AS categoria_nome,
                  u_cli.nome AS cliente_nome, u_cli.email AS cliente_email,
                  u_tec.nome AS tecnico_nome
           FROM service_orders so
           JOIN categories c       ON so.category_id  = c.id
           JOIN users u_cli        ON so.client_id     = u_cli.id
           LEFT JOIN technicians t ON so.technician_id = t.id
           LEFT JOIN users u_tec   ON t.user_id        = u_tec.id
           WHERE so.id=%s""",
        (os_id,), fetchone=True)

    if not os:
        flash("OS não encontrada.", "danger")
        return redirect(url_for("admin.dashboard"))

    tecnicos = query(
        "SELECT t.id, u.nome FROM technicians t JOIN users u ON t.user_id=u.id ORDER BY u.nome",
        fetchall=True)

    # Busca a porcentagem da empresa configurada (padrão 23 se não existir)
    cfg_taxa = query("SELECT value FROM system_config WHERE key='taxa_empresa'", fetchone=True)
    taxa_empresa = float(cfg_taxa["value"]) if cfg_taxa else 23.0

    return render_template("admin_os_detalhe.html", os=os, tecnicos=tecnicos,
                           os_pendentes_count=_contar_pendentes(),
                           notificacoes=[], notif_count=0,
                           taxa_empresa=taxa_empresa)
@admin_bp.route("/configuracoes", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def configuracoes():
    if request.method == "POST":
        # --------------------------------------------------------
        # Lê cada campo enviado pelo formulário. checkbox só vem
        # no request.form se estiver marcado, por isso o
        # request.form.get("taxa_visita_ativa") retorna None
        # quando desmarcado — daí o "true"/"false" manual
        # --------------------------------------------------------
        numero = request.form.get("whatsapp", "").strip()
        taxa_empresa = request.form.get("taxa_empresa", "23").strip()
        taxa_visita_ativa = "true" if request.form.get("taxa_visita_ativa") else "false"
        taxa_visita_valor = request.form.get("taxa_visita_valor", "0").strip()

        # --------------------------------------------------------
        # Dicionário com todas as configurações a salvar — assim
        # dá pra reaproveitar o mesmo bloco de INSERT pra todas,
        # em vez de repetir a query 4 vezes
        # --------------------------------------------------------
        # E-mail e telefone de suporte — canal separado do WhatsApp,
        # pra reclamações formais ou parcerias
        suporte_email = request.form.get("suporte_email", "").strip()
        suporte_telefone = request.form.get("suporte_telefone", "").strip()

        # Modo manutenção — checkbox, mesmo padrão do taxa_visita_ativa
        modo_manutencao = "true" if request.form.get("modo_manutencao") else "false"

        # Mensagem da taxa de visita — editável pelo admin. Use {valor}
        # dentro do texto pra indicar onde o valor em R$ deve entrar
        taxa_visita_mensagem = request.form.get("taxa_visita_mensagem", "").strip()

        # Nota mínima (0-10) que o técnico precisa manter pra continuar
        # recebendo OS. Guardado desde já, mas ainda sem efeito prático
        # porque o sistema de avaliação de técnicos ainda não existe.
        nota_minima_tecnico = request.form.get("nota_minima_tecnico", "6").strip()

        # Limite de OS simultâneas ('atribuida' ou 'em_andamento') que um
        # técnico pode ter ao mesmo tempo. Verificado de verdade na hora
        # de atribuir um técnico a uma OS (rota assign_technician).
        limite_os_simultaneas = request.form.get("limite_os_simultaneas", "5").strip()


        # Prazo (em horas) que o técnico tem pra responder a uma OS atribuída
        # antes dela voltar sozinha pra fila.
        prazo_resposta_tecnico_horas = request.form.get("prazo_resposta_tecnico_horas", "24").strip()

        # Prazo de cancelamento gratuito (em horas) — guardado, sem uso real ainda
        prazo_cancelamento_horas = request.form.get("prazo_cancelamento_horas", "24").strip()
        


        configs = {
            "whatsapp_number": numero,
            "taxa_empresa": taxa_empresa,
            "taxa_visita_ativa": taxa_visita_ativa,
            "taxa_visita_valor": taxa_visita_valor,
            "suporte_email": suporte_email,
            "suporte_telefone": suporte_telefone,
            "modo_manutencao": modo_manutencao,
            "taxa_visita_mensagem": taxa_visita_mensagem,
            "nota_minima_tecnico": nota_minima_tecnico,
            "limite_os_simultaneas": limite_os_simultaneas,
            "prazo_resposta_tecnico_horas": prazo_resposta_tecnico_horas,
            "prazo_cancelamento_horas": prazo_cancelamento_horas,
        }
        # --------------------------------------------------------
        # Salva cada configuração como uma linha key/value,
        # usando ON CONFLICT pra atualizar se a chave já existir
        # (mesmo padrão que já era usado só pro whatsapp)
        # --------------------------------------------------------
        for chave, valor in configs.items():
            query(
                """INSERT INTO system_config (key, value) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (chave, valor), commit=True)

        flash("✅ Configurações salvas.", "success")
        return redirect(url_for("admin.configuracoes"))

    # --------------------------------------------------------
    # Busca todas as configurações relevantes numa única query
    # (mais eficiente que uma query separada por chave) e monta
    # um dicionário {chave: valor} pra facilitar o acesso abaixo
    # --------------------------------------------------------
    linhas = query(
        "SELECT key, value FROM system_config WHERE key IN "
        "('whatsapp_number', 'taxa_empresa', 'taxa_visita_ativa', 'taxa_visita_valor', "
        "'suporte_email', 'suporte_telefone', 'modo_manutencao', 'taxa_visita_mensagem', "
                "'nota_minima_tecnico', 'limite_os_simultaneas', 'prazo_resposta_tecnico_horas', "
        "'prazo_cancelamento_horas')",
        fetchall=True)
    cfg = {linha["key"]: linha["value"] for linha in linhas}

    return render_template(
        "admin_configuracoes.html",
        whatsapp=cfg.get("whatsapp_number", ""),
        taxa_empresa=cfg.get("taxa_empresa", "23"),
        taxa_visita_ativa=cfg.get("taxa_visita_ativa", "false") == "true",
        taxa_visita_valor=cfg.get("taxa_visita_valor", "0"),
        suporte_email=cfg.get("suporte_email", ""),
        suporte_telefone=cfg.get("suporte_telefone", ""),
        modo_manutencao=cfg.get("modo_manutencao", "false") == "true",
        taxa_visita_mensagem=cfg.get("taxa_visita_mensagem",
                                     "✅ Visita técnica solicitada! Entraremos em contato para agendar. "
                                     "Lembre-se: R$ {valor} pagos no dia da visita."),
        nota_minima_tecnico=cfg.get("nota_minima_tecnico", "6"),
        limite_os_simultaneas=cfg.get("limite_os_simultaneas", "5"),
        prazo_resposta_tecnico_horas=cfg.get("prazo_resposta_tecnico_horas", "24"),
        prazo_cancelamento_horas=cfg.get("prazo_cancelamento_horas", "24"),
        os_pendentes_count=_contar_pendentes(),
        notif_count=0
    )
# ============================================================
# CATEGORIAS — listar todas as categorias cadastradas
# ============================================================
@admin_bp.route("/categorias")
@role_required("admin", "super_admin")
def categorias():
    # Busca todas as categorias, já contando quantos técnicos
    # atendem cada uma (útil pra decidir se pode excluir depois),
    # agora ordenadas pela coluna 'ordem' (arrastável na tela)
    lista = query(
        """SELECT c.id, c.nome, c.descricao, c.ordem,
                  COUNT(tc.technician_id) AS total_tecnicos
           FROM categories c
           LEFT JOIN technician_categories tc ON tc.category_id = c.id
           GROUP BY c.id, c.nome, c.descricao, c.ordem
           ORDER BY c.ordem""",
        fetchall=True)

    return render_template("admin_categorias.html", categorias=lista,
                           os_pendentes_count=_contar_pendentes(),
                           notificacoes=[], notif_count=0)

# ============================================================
# CATEGORIAS — salva a nova ordem depois de arrastar e soltar.
# Recebe uma lista de IDs na ordem final (via JavaScript/fetch,
# não é um formulário comum) e atualiza a coluna 'ordem' de cada
# categoria de acordo com a posição dela na lista recebida.
# ============================================================
@admin_bp.route("/categorias/reordenar", methods=["POST"])
@role_required("admin", "super_admin")
def categoria_reordenar():
    dados = request.get_json()
    ids_em_ordem = dados.get("ids", [])

    # Pra cada ID, salva a posição dele na lista (0, 1, 2...) como ordem
    for posicao, categoria_id in enumerate(ids_em_ordem):
        query(
            "UPDATE categories SET ordem=%s WHERE id=%s",
            (posicao, categoria_id), commit=True)

    return {"sucesso": True}

# ============================================================
# CATEGORIAS — criar uma nova categoria
# ============================================================
@admin_bp.route("/categorias/criar", methods=["POST"])
@role_required("admin", "super_admin")
def categoria_criar():
    # Pega os dados do formulário enviado pela tela de Categorias
    nome = request.form.get("nome", "").strip()
    descricao = request.form.get("descricao", "").strip()

    # Validação simples: nome é obrigatório
    if not nome:
        flash("Informe o nome da categoria.", "danger")
        return redirect(url_for("admin.categorias"))

    # Tenta inserir. Como "nome" é UNIQUE no banco (ver schema.sql),
    # se já existir uma categoria com esse nome, o banco recusa —
    # e o "except" abaixo captura esse erro pra mostrar mensagem amigável
    try:
        query(
            """INSERT INTO categories (nome, descricao, ordem)
               VALUES (%s, %s, (SELECT COALESCE(MAX(ordem), -1) + 1 FROM categories))""",
            (nome, descricao),
            commit=True)
        flash(f"✅ Categoria '{nome}' criada com sucesso!", "success")
    except Exception:
        flash(f"Já existe uma categoria chamada '{nome}'.", "danger")
    return redirect(url_for("admin.categorias"))

# ============================================================
# CATEGORIAS — editar nome/descrição de uma categoria existente
# ============================================================
@admin_bp.route("/categorias/editar/<int:categoria_id>", methods=["POST"])
@role_required("admin", "super_admin")
def categoria_editar(categoria_id):
    nome = request.form.get("nome", "").strip()
    descricao = request.form.get("descricao", "").strip()

    if not nome:
        flash("Informe o nome da categoria.", "danger")
        return redirect(url_for("admin.categorias"))

    # Mesmo cuidado da criação: nome é UNIQUE, então captura erro
    # de duplicidade caso o admin tente renomear pra um nome já usado
    try:
        query(
            "UPDATE categories SET nome=%s, descricao=%s WHERE id=%s",
            (nome, descricao, categoria_id),
            commit=True)
        flash(f"✅ Categoria atualizada com sucesso!", "success")
    except Exception:
        flash(f"Já existe uma categoria chamada '{nome}'.", "danger")

    return redirect(url_for("admin.categorias"))

# ============================================================
# CATEGORIAS — excluir (bloqueia se houver técnico vinculado)
# ============================================================
@admin_bp.route("/categorias/excluir/<int:categoria_id>", methods=["POST"])
@role_required("admin", "super_admin")
def categoria_excluir(categoria_id):
    # Conta quantos técnicos atendem essa categoria
    vinculo = query(
        "SELECT COUNT(*) AS n FROM technician_categories WHERE category_id=%s",
        (categoria_id,), fetchone=True)

    # Se tiver pelo menos 1 técnico vinculado, não deixa excluir
    if vinculo["n"] > 0:
        flash("❌ Não é possível excluir: existem técnicos vinculados a esta categoria.", "danger")
        return redirect(url_for("admin.categorias"))

    query("DELETE FROM categories WHERE id=%s", (categoria_id,), commit=True)
    flash("✅ Categoria excluída com sucesso!", "success")
    return redirect(url_for("admin.categorias"))

# ============================================================
# TÉCNICOS — listar todos os técnicos cadastrados
# ============================================================
@admin_bp.route("/tecnicos")
@role_required("admin", "super_admin")
def tecnicos():
    # Junta technicians com users (pra pegar email) e agrupa as
    # categorias que cada técnico atende (STRING_AGG junta os nomes
    # das categorias numa única string separada por vírgula)
    # Busca os dados dos técnicos, incluindo informações necessárias
    # para o administrador analisar o cadastro antes de aprovar ou recusar.
    lista = query(
        """SELECT t.id, t.nome, t.telefone, t.status,
                  t.status_aprovacao, t.prazo_analise,
                  t.data_analise, t.motivo_recusa,
                  t.cpf, t.data_nascimento,
                  t.endereco, t.cidade, t.bairro,
                  t.habilidades, t.foto_perfil, t.chave_pix,
                  u.email,
                  STRING_AGG(c.nome, ', ' ORDER BY c.nome) AS categorias
           FROM technicians t
           JOIN users u ON t.user_id = u.id
           LEFT JOIN technician_categories tc ON tc.technician_id = t.id
           LEFT JOIN categories c ON c.id = tc.category_id
           GROUP BY t.id,
                    t.nome,
                    t.telefone,
                    t.status,
                    t.status_aprovacao,
                    t.prazo_analise,
                    t.data_analise,
                    t.motivo_recusa,
                    t.cpf,
                    t.data_nascimento,
                    t.endereco,
                    t.cidade,
                    t.bairro,
                    t.habilidades,
                    t.foto_perfil,
                    t.chave_pix,
                    u.email
           ORDER BY t.nome""",
        fetchall=True)

    return render_template("admin_tecnicos.html", tecnicos=lista,
                           tecnicos_pendentes=[t for t in lista if t["status_aprovacao"] == "pendente"],
                           os_pendentes_count=_contar_pendentes(),
                           notificacoes=[], notif_count=0)
# ============================================================
# APROVAR TÉCNICO
# ============================================================
@admin_bp.route("/tecnicos/aprovar/<int:technician_id>", methods=["POST"])
@role_required("admin", "super_admin")
def tecnico_aprovar(technician_id):
    tecnico = query(
        """SELECT id, nome
           FROM technicians
           WHERE id=%s AND status_aprovacao='pendente'""",
        (technician_id,),
        fetchone=True
    )

    if not tecnico:
        flash("Técnico não encontrado ou já analisado.", "danger")
        return redirect(url_for("admin.tecnicos"))

    query(
        """UPDATE technicians
           SET status='disponivel',
               status_aprovacao='aprovado',
               data_analise=NOW(),
               motivo_recusa=NULL
           WHERE id=%s""",
        (technician_id,),
        commit=True
    )

    flash(f"✅ Técnico '{tecnico['nome']}' aprovado como parceiro.", "success")
    return redirect(url_for("admin.tecnicos"))


# ============================================================
# RECUSAR TÉCNICO
# ============================================================
@admin_bp.route("/tecnicos/recusar/<int:technician_id>", methods=["POST"])
@role_required("admin", "super_admin")
def tecnico_recusar(technician_id):
    motivo = request.form.get("motivo_recusa", "").strip()

    if not motivo:
        flash("Informe o motivo da recusa.", "danger")
        return redirect(url_for("admin.tecnicos"))

    tecnico = query(
        """SELECT id, nome
           FROM technicians
           WHERE id=%s AND status_aprovacao='pendente'""",
        (technician_id,),
        fetchone=True
    )

    if not tecnico:
        flash("Técnico não encontrado ou já analisado.", "danger")
        return redirect(url_for("admin.tecnicos"))

    query(
        """UPDATE technicians
           SET status='inativo',
               status_aprovacao='recusado',
               data_analise=NOW(),
               motivo_recusa=%s
           WHERE id=%s""",
        (motivo, technician_id),
        commit=True
    )

    flash(f"❌ Cadastro do técnico '{tecnico['nome']}' recusado.", "warning")
    return redirect(url_for("admin.tecnicos"))


# ============================================================
# CLIENTES — listar todos os clientes cadastrados
# ============================================================
@admin_bp.route("/clientes")
@role_required("admin", "super_admin")
def clientes():
    # Busca todos os usuários com role='client', e conta quantas
    # OS cada um já abriu (útil pra ter uma noção de uso da plataforma)
    lista = query(
        """SELECT u.id, u.nome, u.email, u.telefone, u.created_at,
                  COUNT(so.id) AS total_os
           FROM users u
           LEFT JOIN service_orders so ON so.client_id = u.id
           WHERE u.role = 'client'
           GROUP BY u.id, u.nome, u.email, u.telefone, u.created_at
           ORDER BY u.nome""",
        fetchall=True)

    return render_template("admin_clientes.html", clientes=lista,
                           os_pendentes_count=_contar_pendentes(),
                           notificacoes=[], notif_count=0)

# ============================================================
# FINANCEIRO — lista OS finalizadas para controle de repasses
# ============================================================
@admin_bp.route("/financeiro")
@role_required("admin", "super_admin")
def financeiro():

    # Busca cada OS finalizada que possui valor confirmado.
    # Cada OS terá seu próprio status de pagamento.
    lista = query(
        """SELECT
               so.id,
               so.technician_id,
               so.valor_confirmado,
               so.repasse_pago,
               so.repasse_pago_em,
               so.created_at,

               t.nome AS tecnico_nome,
               t.chave_pix,

               c.nome AS categoria_nome

           FROM service_orders so

           JOIN technicians t
             ON so.technician_id = t.id

           JOIN categories c
             ON so.category_id = c.id

           WHERE so.status = 'finalizada'
             AND so.valor_confirmado IS NOT NULL

           ORDER BY
               so.repasse_pago ASC,
               so.created_at DESC""",
        fetchall=True
    )

    # Busca a porcentagem da empresa.
    cfg_taxa = query(
        "SELECT value FROM system_config WHERE key='taxa_empresa'",
        fetchone=True
    )

    taxa_empresa = float(
        cfg_taxa["value"]
    ) if cfg_taxa else 23.0

    # Calcula quanto pertence ao técnico em cada OS.
    for os in lista:
        os["valor_confirmado"] = float(
            os["valor_confirmado"] or 0
        )

        os["repasse_tecnico"] = (
                os["valor_confirmado"]
                * (1 - taxa_empresa / 100)
        )

    # ========================================================
    # RESUMO DOS REPASSES
    # ========================================================

    total_repasses = sum(
        os["repasse_tecnico"]
        for os in lista
    )

    total_pago = sum(
        os["repasse_tecnico"]
        for os in lista
        if os["repasse_pago"]
    )

    total_pendente = total_repasses - total_pago
    return render_template(
        "admin_financeiro.html",
        ordens=lista,
        taxa_empresa=taxa_empresa,
        total_repasses=total_repasses,
        total_pago=total_pago,
        total_pendente=total_pendente,
        os_pendentes_count=_contar_pendentes(),
        notificacoes=[],
        notif_count=0
    )
# ============================================================
# RELATÓRIOS — DESEMPENHO DOS TÉCNICOS
# ============================================================
@admin_bp.route("/relatorios")
@role_required("admin", "super_admin")
def relatorios():

    from datetime import date, timedelta

    hoje = date.today()

    # --------------------------------------------------------
    # PERÍODO
    # Padrão: últimos 30 dias
    # --------------------------------------------------------
    periodo = request.args.get("periodo", "30_dias")

    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")

    # --------------------------------------------------------
    # Define o período selecionado
    # --------------------------------------------------------
    if periodo == "30_dias":

        inicio_data = hoje - timedelta(days=29)
        fim_data = hoje

    elif periodo == "7_dias":

        inicio_data = hoje - timedelta(days=6)
        fim_data = hoje

    elif periodo == "15_dias":

        inicio_data = hoje - timedelta(days=14)
        fim_data = hoje
    elif periodo == "3_meses":

        inicio_data = hoje - timedelta(days=89)
        fim_data = hoje

    elif periodo == "6_meses":

        inicio_data = hoje - timedelta(days=179)
        fim_data = hoje

    elif periodo == "1_ano":

        inicio_data = hoje - timedelta(days=364)
        fim_data = hoje

    elif periodo == "2_anos":

        inicio_data = hoje - timedelta(days=729)
        fim_data = hoje

    elif periodo == "personalizado":

        try:
            inicio_data = date.fromisoformat(data_inicio)
            fim_data = date.fromisoformat(data_fim)

            if inicio_data > fim_data:
                raise ValueError

        except (TypeError, ValueError):
            flash("Informe um período personalizado válido.", "warning")

            periodo = "30_dias"
            inicio_data = hoje - timedelta(days=29)
            fim_data = hoje

    elif periodo == "todos":

        inicio_data = None
        fim_data = None

    else:

        periodo = "30_dias"
        inicio_data = hoje - timedelta(days=29)
        fim_data = hoje

    # --------------------------------------------------------
    # Busca a taxa da PrimeFix
    # --------------------------------------------------------
    cfg_taxa = query(
        "SELECT value FROM system_config WHERE key='taxa_empresa'",
        fetchone=True
    )

    taxa_empresa = (
        float(cfg_taxa["value"])
        if cfg_taxa and cfg_taxa["value"]
        else 23.0
    )

    # --------------------------------------------------------
    # Busca todos os técnicos e suas OS finalizadas
    #
    # updated_at é usado porque representa a última alteração
    # da OS e, neste fluxo, é atualizado quando ela é finalizada.
    # --------------------------------------------------------
    if periodo == "todos":

        tecnicos = query(
            """SELECT
                   t.id,
                   t.nome,
                   COUNT(so.id) AS quantidade_servicos,
                   COALESCE(
                       SUM(so.valor_confirmado),
                       0
                   ) AS total_bruto
               FROM technicians t

               LEFT JOIN service_orders so
                 ON so.technician_id = t.id
                AND so.status = 'finalizada'
                AND so.valor_confirmado IS NOT NULL

               GROUP BY t.id, t.nome

               ORDER BY total_bruto DESC""",
            fetchall=True
        )

    else:

        tecnicos = query(
            """SELECT
                   t.id,
                   t.nome,
                   COUNT(so.id) AS quantidade_servicos,
                   COALESCE(
                       SUM(so.valor_confirmado),
                       0
                   ) AS total_bruto
               FROM technicians t

               LEFT JOIN service_orders so
                 ON so.technician_id = t.id
                AND so.status = 'finalizada'
                AND so.valor_confirmado IS NOT NULL
                AND so.updated_at >= %s
                AND so.updated_at < (%s + INTERVAL '1 day')

               GROUP BY t.id, t.nome

               ORDER BY total_bruto DESC""",
            (
                inicio_data,
                fim_data
            ),
            fetchall=True
        )

    # --------------------------------------------------------
    # Calcula os valores de cada técnico
    # --------------------------------------------------------
    total_geral = 0.0
    total_repasse = 0.0

    for tec in tecnicos:

        tec["quantidade_servicos"] = int(
            tec["quantidade_servicos"] or 0
        )

        tec["total_bruto"] = float(
            tec["total_bruto"] or 0
        )

        # Parte destinada ao técnico
        tec["repasse_tecnico"] = (
            tec["total_bruto"]
            * (1 - taxa_empresa / 100)
        )

        # Parte destinada à PrimeFix
        tec["taxa_empresa"] = (
            tec["total_bruto"]
            * (taxa_empresa / 100)
        )

        total_geral += tec["total_bruto"]
        total_repasse += tec["repasse_tecnico"]

    # --------------------------------------------------------
    # Receita total da PrimeFix no período
    # --------------------------------------------------------
    total_taxa = total_geral * (taxa_empresa / 100)

    return render_template(
        "admin_desempenho_tecnicos.html",

        tecnicos=tecnicos,

        periodo=periodo,

        data_inicio=(
            inicio_data.isoformat()
            if inicio_data
            else ""
        ),

        data_fim=(
            fim_data.isoformat()
            if fim_data
            else ""
        ),

        total_geral=total_geral,

        total_repasse=total_repasse,

        total_taxa=total_taxa,

        taxa_empresa=taxa_empresa
    )
# ============================================================
# FINANCEIRO — marca UMA OS específica como paga
# ============================================================
@admin_bp.route("/financeiro/marcar-pago/os/<int:os_id>", methods=["POST"])
@role_required("admin", "super_admin")
def financeiro_marcar_pago_os(os_id):

    os_pagamento = query(
        """SELECT id, technician_id, status, valor_confirmado, repasse_pago
           FROM service_orders
           WHERE id=%s""",
        (os_id,),
        fetchone=True
    )

    if not os_pagamento:
        flash("OS não encontrada.", "danger")
        return redirect(url_for("admin.financeiro"))

    if os_pagamento["status"] != "finalizada":
        flash("Somente OS finalizadas podem ser marcadas como pagas.", "warning")
        return redirect(url_for("admin.financeiro"))

    if os_pagamento["valor_confirmado"] is None:
        flash("Esta OS ainda não possui valor confirmado.", "warning")
        return redirect(url_for("admin.financeiro"))

    if os_pagamento["repasse_pago"]:
        flash("O repasse desta OS já foi marcado como pago.", "info")
        return redirect(url_for("admin.financeiro"))

    query(
        """UPDATE service_orders
           SET repasse_pago=TRUE,
               repasse_pago_em=NOW()
           WHERE id=%s""",
        (os_id,),
        commit=True
    )

    flash(
        f"✅ Repasse da OS #{os_id} marcado como pago.",
        "success"
    )

    return redirect(url_for("admin.financeiro"))
# ============================================================
# EXCLUIR TÉCNICO — desvincula OS ativas (voltam pra 'aberta'
# sem técnico) e registra no log antes de apagar
# ============================================================
@admin_bp.route("/tecnicos/excluir/<int:technician_id>", methods=["POST"])
@role_required("admin", "super_admin")
def tecnico_excluir(technician_id):
    admin_id = session["user_id"]
    motivo = request.form.get("motivo", "").strip()

    # Busca nome/email do técnico ANTES de excluir, pra registrar no log
    tec = query(
        """SELECT t.nome, u.email FROM technicians t
           JOIN users u ON t.user_id = u.id WHERE t.id=%s""",
        (technician_id,), fetchone=True)

    if not tec:
        flash("Técnico não encontrado.", "danger")
        return redirect(url_for("admin.tecnicos"))

    # Desvincula qualquer OS ativa desse técnico — ela volta pra
    # 'aberta' SEM técnico, nunca fica o cliente sem atendimento
    query(
        """UPDATE service_orders
           SET technician_id=NULL, status='aberta'
           WHERE technician_id=%s AND status IN ('atribuida','em_andamento')""",
        (technician_id,), commit=True)

    # Registra a exclusão no log ANTES de apagar de fato
    query(
        """INSERT INTO admin_exclusoes (admin_id, tipo_excluido, nome_excluido, email_excluido, motivo)
           VALUES (%s, 'technician', %s, %s, %s)""",
        (admin_id, tec["nome"], tec["email"], motivo), commit=True)

    # Apaga o técnico (o usuário vinculado é apagado em cascata,
    # conforme o ON DELETE CASCADE da FK technicians.user_id)
    query(
        """DELETE FROM users WHERE id = (SELECT user_id FROM technicians WHERE id=%s)""",
        (technician_id,), commit=True)

    flash(f"✅ Técnico '{tec['nome']}' excluído. OS ativas voltaram para 'aberta'.", "success")
    return redirect(url_for("admin.tecnicos"))


# ============================================================
# EXCLUIR CLIENTE — registra no log antes de apagar
# ============================================================
@admin_bp.route("/clientes/excluir/<int:client_id>", methods=["POST"])
@role_required("admin", "super_admin")
def cliente_excluir(client_id):
    admin_id = session["user_id"]
    motivo = request.form.get("motivo", "").strip()

    cli = query("SELECT nome, email FROM users WHERE id=%s AND role='client'",
                (client_id,), fetchone=True)

    if not cli:
        flash("Cliente não encontrado.", "danger")
        return redirect(url_for("admin.clientes"))

    query(
        """INSERT INTO admin_exclusoes (admin_id, tipo_excluido, nome_excluido, email_excluido, motivo)
           VALUES (%s, 'client', %s, %s, %s)""",
        (admin_id, cli["nome"], cli["email"], motivo), commit=True)

    # OS antigas do cliente ficam no banco — client_id vira NULL
    # automaticamente (confirmamos que a FK usa ON DELETE SET NULL)
    query("DELETE FROM users WHERE id=%s", (client_id,), commit=True)

    flash(f"✅ Cliente '{cli['nome']}' excluído.", "success")
    return redirect(url_for("admin.clientes"))





