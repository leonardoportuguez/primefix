from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import os

from auth import role_required
from db import query

technician_bp = Blueprint("technician", __name__, url_prefix="/tecnico")


# ============================================================
# DASHBOARD DO TÉCNICO — lista todas as OS atribuídas a ele
# ============================================================
@technician_bp.route("/dashboard")
@role_required("technician")
def dashboard():
    user_id = session["user_id"]

    # Busca o registro do técnico na tabela technicians pelo user_id
    tec = query("SELECT id, foto_perfil FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # Busca todas as OS atribuídas a este técnico
    ordens = query(
        """SELECT so.id, so.status, so.descricao,
                  so.cidade, so.bairro, so.logradouro, so.numero,
                  so.complemento, so.data_agendamento,
                  so.valor_sugerido, so.valor_confirmado,
                  so.observacao_tecnico,
                  c.nome AS categoria_nome,
                  u.nome AS cliente_nome
           FROM service_orders so
           JOIN categories c ON so.category_id = c.id
           JOIN users u ON so.client_id = u.id
           WHERE so.technician_id = %s
           ORDER BY so.created_at DESC""",
        (tec["id"],), fetchall=True)

    # Busca a porcentagem da empresa configurada (padrão 23 se não existir)
    cfg_taxa = query("SELECT value FROM system_config WHERE key='taxa_empresa'", fetchone=True)
    taxa_empresa = float(cfg_taxa["value"]) if cfg_taxa else 23.0

    # ========================================================
    # RESUMO FINANCEIRO — OS FINALIZADAS
    # ========================================================
    resumo_financeiro = query(
        """SELECT
               COUNT(*) AS total_finalizadas,
               COALESCE(SUM(valor_confirmado), 0) AS total_bruto,

               COALESCE(
                   SUM(
                       CASE
                           WHEN repasse_pago = TRUE
                           THEN valor_confirmado
                           ELSE 0
                       END
                   ),
                   0
               ) AS total_pago
           FROM service_orders
           WHERE technician_id=%s
             AND status='finalizada'""",
        (tec["id"],),
        fetchone=True
    )

    total_bruto = float(resumo_financeiro["total_bruto"] or 0)

    # Parte que pertence à PrimeFix
    total_taxa = total_bruto * (taxa_empresa / 100)

    # Parte que pertence ao técnico
    total_repasse = total_bruto - total_taxa

    # Valor bruto das OS que já tiveram o repasse marcado como pago
    total_pago_bruto = float(resumo_financeiro["total_pago"] or 0)

    # Valor efetivamente recebido pelo técnico
    total_recebido = total_pago_bruto * (1 - taxa_empresa / 100)

    # O que ainda falta receber
    total_pendente = total_repasse - total_recebido

    # Evita aparecer valor negativo
    if total_pendente < 0:
        total_pendente = 0

    return render_template(
        "tecnico_dashboard.html",
        ordens=ordens,
        tecnico_foto=tec["foto_perfil"],
        taxa_empresa=taxa_empresa,
        total_bruto=total_bruto,
        total_taxa=total_taxa,
        total_repasse=total_repasse,
        total_recebido=total_recebido,
        total_pendente=total_pendente
    )
# ============================================================
# DETALHES DA OS — técnico visualiza uma OS atribuída a ele
# ============================================================
@technician_bp.route("/os/<int:os_id>")
@role_required("technician")
def ver_os(os_id):
    user_id = session["user_id"]

    # Busca o técnico logado
    tec = query(
        "SELECT id FROM technicians WHERE user_id=%s",
        (user_id,),
        fetchone=True
    )

    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # Busca a OS somente se ela pertencer ao técnico logado
    os_detalhe = query(
        """SELECT so.id,
                  so.status,
                  so.descricao,
                  so.cidade,
                  so.bairro,
                  so.logradouro,
                  so.numero,
                  so.complemento,
                  so.data_agendamento,
                  so.valor_sugerido,
                  so.valor_confirmado,
                  so.observacao_tecnico,
                  c.nome AS categoria_nome,
                  u.nome AS cliente_nome
           FROM service_orders so
           JOIN categories c ON so.category_id = c.id
           JOIN users u ON so.client_id = u.id
           WHERE so.id=%s
             AND so.technician_id=%s""",
        (os_id, tec["id"]),
        fetchone=True
    )

    if not os_detalhe:
        flash("OS não encontrada ou não pertence a você.", "danger")
        return redirect(url_for("technician.dashboard"))

    return render_template(
        "tecnico_os_detalhe.html",
        os=os_detalhe
    )



# ============================================================
# SUGERIR VALOR — técnico informa o valor após visita
# O valor fica como "sugerido" até o admin aprovar
# ============================================================
@technician_bp.route("/sugerir-valor/<int:os_id>", methods=["POST"])
@role_required("technician")
def sugerir_valor(os_id):
    user_id = session["user_id"]

    # --------------------------------------------------------
    # Busca o id do técnico logado, pra usar na checagem de
    # ownership abaixo (mesmo padrão de client.ver_os)
    # --------------------------------------------------------
    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    try:
        valor = float(request.form.get("valor_sugerido", 0))

        if valor <= 0:
            flash("O valor do serviço deve ser maior que R$ 0,00.", "danger")
            return redirect(url_for("technician.dashboard"))
    except ValueError:
        flash("Valor inválido.", "danger")
        return redirect(url_for("technician.dashboard"))

    # Observação opcional — técnico pode descrever o que encontrou
    obs = request.form.get("observacao", "").strip()

    # --------------------------------------------------------
    # CORREÇÃO DE SEGURANÇA (IDOR): o WHERE agora exige que a OS
    # pertença ao técnico logado, além do id. Se a OS for de outro
    # técnico, o UPDATE simplesmente não afeta nenhuma linha
    # --------------------------------------------------------
    query(
        "UPDATE service_orders SET valor_sugerido=%s, observacao_tecnico=%s "
        "WHERE id=%s AND technician_id=%s",
        (valor, obs, os_id, tec["id"]), commit=True)

    flash("✅ Valor enviado para aprovação do admin!", "success")
    return redirect(url_for("technician.dashboard"))


# ============================================================
# ATUALIZAR STATUS — técnico pode marcar como em_andamento ou finalizada
# Validação garante que só esses dois status são aceitos
# ============================================================
@technician_bp.route("/atualizar-status/<int:os_id>", methods=["POST"])
@role_required("technician")
def atualizar_status(os_id):
    user_id = session["user_id"]

    tec = query(
        "SELECT id FROM technicians WHERE user_id=%s",
        (user_id,),
        fetchone=True
    )

    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    novo_status = request.form.get("status", "")

    if novo_status not in ["em_andamento", "finalizada"]:
        flash("Status inválido.", "danger")
        return redirect(url_for("technician.dashboard"))

    os_atual = query(
        """SELECT id, status, valor_confirmado, aprovacao_cliente
           FROM service_orders
           WHERE id=%s AND technician_id=%s""",
        (os_id, tec["id"]),
        fetchone=True
    )
    if not os_atual:
        flash("OS não encontrada ou não pertence a este técnico.", "danger")
        return redirect(url_for("technician.dashboard"))

    status_atual = os_atual["status"]

    # Iniciar serviço:
    # só pode iniciar uma OS atribuída e aprovada pelo cliente
    if novo_status == "em_andamento":

        if status_atual != "atribuida":
            flash("Esta OS não está disponível para iniciar.", "danger")
            return redirect(url_for("technician.dashboard"))

        if os_atual["aprovacao_cliente"] != "aprovado":
            flash("Aguarde a aprovação do cliente antes de iniciar o serviço.", "warning")
            return redirect(url_for("technician.dashboard"))

    # Finalizar serviço:
    # só pode finalizar uma OS que esteja em andamento
    if novo_status == "finalizada":
        if status_atual != "em_andamento":
            flash("A OS precisa estar em andamento para ser finalizada.", "danger")
            return redirect(url_for("technician.dashboard"))

        # Não permite finalizar sem valor aprovado pelo Admin
        if os_atual["valor_confirmado"] is None:
            flash("Aguarde a aprovação do valor pelo administrador.", "danger")
            return redirect(url_for("technician.dashboard"))

    query(
        """UPDATE service_orders
           SET status=%s
           WHERE id=%s AND technician_id=%s""",
        (novo_status, os_id, tec["id"]),
        commit=True
    )

    if novo_status == "em_andamento":
        flash("✅ Serviço iniciado!", "success")
    else:
        flash("✅ Serviço finalizado! Aguardando conferência do administrador.", "success")

    return redirect(url_for("technician.dashboard"))


# ============================================================
# ESPECIALIDADES DO TÉCNICO — listar, adicionar e remover
# ============================================================

# Lista todas as categorias que este técnico já atende
@technician_bp.route("/especialidades")
@role_required("technician")
def especialidades():
    user_id = session["user_id"]

    # Busca o id do técnico a partir do user_id logado
    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # Categorias que o técnico JÁ atende
    minhas_categorias = query(
        """SELECT tc.id AS vinculo_id, c.id AS categoria_id, c.nome
           FROM technician_categories tc
           JOIN categories c ON tc.category_id = c.id
           WHERE tc.technician_id = %s
           ORDER BY c.nome""",
        (tec["id"],), fetchall=True)

    # Categorias que ele AINDA NÃO atende (para mostrar no formulário de adicionar)
    todas_categorias = query("SELECT id, nome FROM categories ORDER BY ordem", fetchall=True)
    ids_ja_vinculados = {c["categoria_id"] for c in minhas_categorias}
    categorias_disponiveis = [c for c in todas_categorias if c["id"] not in ids_ja_vinculados]

    return render_template("tecnico_especialidades.html",
                           minhas_categorias=minhas_categorias,
                           categorias_disponiveis=categorias_disponiveis)


# Adiciona uma nova especialidade ao técnico
@technician_bp.route("/especialidades/adicionar", methods=["POST"])
@role_required("technician")
def adicionar_especialidade():
    user_id = session["user_id"]
    category_id = request.form.get("category_id")

    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    if not category_id:
        flash("Selecione uma categoria.", "danger")
        return redirect(url_for("technician.especialidades"))

    # ON CONFLICT evita erro caso o técnico tente adicionar uma categoria repetida
    query(
        """INSERT INTO technician_categories (technician_id, category_id)
           VALUES (%s, %s)
           ON CONFLICT (technician_id, category_id) DO NOTHING""",
        (tec["id"], category_id), commit=True)

    flash("✅ Especialidade adicionada!", "success")
    return redirect(url_for("technician.especialidades"))


# Remove uma especialidade do técnico
@technician_bp.route("/especialidades/remover/<int:vinculo_id>", methods=["POST"])
@role_required("technician")
def remover_especialidade(vinculo_id):
    user_id = session["user_id"]

    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # O "AND technician_id=%s" garante que um técnico só apague o PRÓPRIO vínculo,
    # nunca de outro técnico, mesmo que tente forjar o vinculo_id na URL
    query(
        "DELETE FROM technician_categories WHERE id=%s AND technician_id=%s",
        (vinculo_id, tec["id"]), commit=True)

    flash("✅ Especialidade removida.", "success")
    return redirect(url_for("technician.especialidades"))

# ============================================================
# UPLOAD DE FOTO DE PERFIL DO TÉCNICO
# ============================================================
UPLOAD_FOLDER = 'static/uploads/tecnicos'
EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg'}

def extensao_valida(filename):
    if not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS
@technician_bp.route("/upload-foto", methods=["POST"])
@role_required("technician")
def upload_foto():
    user_id = session["user_id"]

    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    if 'foto' not in request.files or request.files['foto'].filename == '':
        flash("Nenhum arquivo enviado.", "danger")
        return redirect(url_for("technician.dashboard"))

    arquivo = request.files['foto']

    if not extensao_valida(arquivo.filename):
        flash("Arquivo inválido. Use PNG ou JPG.", "danger")
        return redirect(url_for("technician.dashboard"))

    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    nome_arquivo = f"tecnico_{tec['id']}.{extensao}"
    caminho_completo = os.path.join(UPLOAD_FOLDER, nome_arquivo)
    arquivo.save(caminho_completo)

    caminho_relativo = f"uploads/tecnicos/{nome_arquivo}"
    query("UPDATE technicians SET foto_perfil=%s WHERE id=%s",
          (caminho_relativo, tec["id"]), commit=True)

    flash("✅ Foto atualizada com sucesso!", "success")
    return redirect(url_for("technician.dashboard"))

# ============================================================
# PERFIL DO TÉCNICO — ver e editar dados pessoais
# ============================================================

# Mostra a página de perfil já preenchida com os dados salvos no banco
@technician_bp.route("/perfil")
@role_required("technician")
def perfil():
    user_id = session["user_id"]

    # Busca todos os campos de perfil do técnico logado
    tec = query(
        """SELECT id, cpf, chave_pix, endereco, cidade, bairro, data_nascimento, foto_perfil
           FROM technicians WHERE user_id=%s""",
        (user_id,), fetchone=True)

    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # "tecnico=tec" é o que o template usa em {{ tecnico.cpf }}, {{ tecnico.chave_pix }} etc
    return render_template("tecnico_perfil.html", tecnico=tec)


# Recebe o formulário preenchido e atualiza os dados no banco
@technician_bp.route("/perfil/atualizar", methods=["POST"])
@role_required("technician")
def atualizar_perfil():
    user_id = session["user_id"]

    # request.form.get(...) pega cada campo enviado pelo formulário.
    # Se o campo vier vazio, salva como string vazia (não quebra nada,
    # já que as colunas aceitam isso)
    cpf = request.form.get("cpf", "").strip()
    data_nascimento = request.form.get("data_nascimento", "").strip() or None
    chave_pix = request.form.get("chave_pix", "").strip()
    cidade = request.form.get("cidade", "").strip()
    bairro = request.form.get("bairro", "").strip()
    endereco = request.form.get("endereco", "").strip()

    query(
        """UPDATE technicians
           SET cpf=%s, data_nascimento=%s, chave_pix=%s,
               cidade=%s, bairro=%s, endereco=%s
           WHERE user_id=%s""",
        (cpf, data_nascimento, chave_pix, cidade, bairro, endereco, user_id),
        commit=True)

    flash("✅ Perfil atualizado com sucesso!", "success")
    return redirect(url_for("technician.perfil"))

# ============================================================
# DISPONIBILIDADE DO TÉCNICO — dias da semana + horários
# ============================================================

# Lista fixa dos 7 dias aceitos pelo banco (respeitando o CHECK constraint
# da tabela technician_availability). O segundo valor de cada tupla é só
# o texto bonito mostrado na tela
DIAS_SEMANA = [
    ("segunda", "Segunda-feira"),
    ("terca", "Terça-feira"),
    ("quarta", "Quarta-feira"),
    ("quinta", "Quinta-feira"),
    ("sexta", "Sexta-feira"),
    ("sabado", "Sábado"),
    ("domingo", "Domingo"),
]


# Mostra a página com os dias já cadastrados marcados e preenchidos
@technician_bp.route("/disponibilidade")
@role_required("technician")
def disponibilidade():
    user_id = session["user_id"]

    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # Busca todos os dias já cadastrados pra esse técnico
    linhas = query(
        "SELECT dia_semana, hora_inicio, hora_fim FROM technician_availability WHERE technician_id=%s",
        (tec["id"],), fetchall=True)

    # Transforma a lista em um dicionário {dia: {hora_inicio, hora_fim}},
    # pra o template conseguir checar rapidamente "esse dia existe?"
    # com "chave in disponibilidade"
    disponibilidade_dict = {linha["dia_semana"]: linha for linha in linhas}

    return render_template("tecnico_disponibilidade.html",
                           dias_semana=DIAS_SEMANA,
                           disponibilidade=disponibilidade_dict)


# Recebe o formulário e salva/atualiza/remove cada dia conforme o que
# o técnico marcou ou desmarcou
@technician_bp.route("/disponibilidade/atualizar", methods=["POST"])
@role_required("technician")
def atualizar_disponibilidade():
    user_id = session["user_id"]

    tec = query("SELECT id FROM technicians WHERE user_id=%s", (user_id,), fetchone=True)
    if not tec:
        flash("Perfil de técnico não encontrado.", "danger")
        return redirect(url_for("login"))

    # Percorre os 7 dias fixos, checando o que veio marcado no formulário
    for chave, _ in DIAS_SEMANA:
        ativo = request.form.get(f"ativo_{chave}")  # vem "on" se marcado, None se não
        hora_inicio = request.form.get(f"inicio_{chave}", "").strip()
        hora_fim = request.form.get(f"fim_{chave}", "").strip()

        if ativo and hora_inicio and hora_fim:
            # Dia marcado com horários preenchidos: insere ou atualiza
            # (ON CONFLICT usa a UNIQUE constraint technician_id+dia_semana
            # que já existe na tabela, evitando duplicar linha do mesmo dia)
            query(
                """INSERT INTO technician_availability (technician_id, dia_semana, hora_inicio, hora_fim)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (technician_id, dia_semana)
                   DO UPDATE SET hora_inicio=EXCLUDED.hora_inicio, hora_fim=EXCLUDED.hora_fim""",
                (tec["id"], chave, hora_inicio, hora_fim), commit=True)
        else:
            # Dia desmarcado (ou sem horário preenchido): remove, se existir
            query(
                "DELETE FROM technician_availability WHERE technician_id=%s AND dia_semana=%s",
                (tec["id"], chave), commit=True)

    flash("✅ Disponibilidade atualizada!", "success")
    return redirect(url_for("technician.disponibilidade"))