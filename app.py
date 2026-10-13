
import os
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from assistente_ia import criar_resposta


# ==========================================
# CONFIGURACAO DO SISTEMA
# ==========================================

app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]

database_url = os.environ["DATABASE_URL"]

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

db = SQLAlchemy(app)

FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def agora():
    return datetime.now(timezone.utc)


def converter_data_brasilia(data):
    """
    Converte uma data UTC para o horario de Brasilia.
    Datas antigas sem timezone sao tratadas como UTC.
    """

    if data is None:
        return None

    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)

    return data.astimezone(FUSO_BRASILIA)


def formatar_data_brasilia(data):
    data_local = converter_data_brasilia(data)

    if data_local is None:
        return "-"

    return data_local.strftime("%d/%m/%Y %H:%M")


# ==========================================
# BANCO DE DADOS
# ==========================================

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(
        db.String(120),
        nullable=False
    )

    usuario = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    senha = db.Column(
        db.String(255),
        nullable=False
    )


class Equipamento(db.Model):
    __tablename__ = "equipamento"

    id = db.Column(db.Integer, primary_key=True)

    tipo = db.Column(
        db.String(100),
        nullable=False
    )

    marca = db.Column(
        db.String(100),
        nullable=True,
        default=""
    )

    modelo = db.Column(
        db.String(100),
        nullable=True,
        default=""
    )

    mac = db.Column(
        db.String(120),
        unique=True,
        nullable=True
    )

    serial = db.Column(
        db.String(120),
        nullable=True
    )

    codigo = db.Column(
        db.String(120),
        nullable=True
    )

    unidade = db.Column(
        db.String(30),
        default="un"
    )

    quantidade = db.Column(
        db.Integer,
        default=1,
        nullable=False
    )

    quantidade_total = db.Column(
        db.Integer,
        default=1,
        nullable=False
    )

    chegada = db.Column(
        db.Date,
        nullable=False
    )

    cadastro = db.Column(
        db.DateTime(timezone=True),
        default=agora
    )

    cadastrado_por = db.Column(
        db.String(120),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="saldo",
        nullable=False
    )


class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    equipamento_id = db.Column(
        db.Integer,
        nullable=False
    )

    mac = db.Column(
        db.String(120),
        nullable=False
    )

    acao = db.Column(
        db.String(200),
        nullable=False
    )

    usuario = db.Column(
        db.String(120),
        nullable=False
    )

    data = db.Column(
        db.DateTime(timezone=True),
        default=agora
    )


# ==========================================
# ATUALIZACAO DO BANCO
# ==========================================

def migrar_banco():
    db.create_all()

    colunas = {
        "codigo": "VARCHAR(120)",
        "unidade": "VARCHAR(30) DEFAULT 'un'",
        "quantidade": "INTEGER DEFAULT 1",
        "quantidade_total": "INTEGER DEFAULT 1"
    }

    with db.engine.begin() as conexao:

        for nome, definicao in colunas.items():
            conexao.execute(text(
                f"ALTER TABLE equipamento "
                f"ADD COLUMN IF NOT EXISTS "
                f"{nome} {definicao}"
            ))

        conexao.execute(text(
            "ALTER TABLE equipamento "
            "ALTER COLUMN mac DROP NOT NULL"
        ))

        conexao.execute(text(
            "ALTER TABLE equipamento "
            "ALTER COLUMN mac TYPE VARCHAR(120)"
        ))

        conexao.execute(text(
            "ALTER TABLE equipamento "
            "ALTER COLUMN marca DROP NOT NULL"
        ))

        conexao.execute(text(
            "ALTER TABLE equipamento "
            "ALTER COLUMN modelo DROP NOT NULL"
        ))

        conexao.execute(text(
            "UPDATE equipamento "
            "SET quantidade = 1 "
            "WHERE quantidade IS NULL"
        ))

        conexao.execute(text(
            "UPDATE equipamento "
            "SET quantidade_total = 1 "
            "WHERE quantidade_total IS NULL"
        ))

        conexao.execute(text(
            "UPDATE equipamento "
            "SET unidade = 'un' "
            "WHERE unidade IS NULL"
        ))


# ==========================================
# FUNCOES AUXILIARES
# ==========================================

def login_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):

        if "usuario_id" not in session:
            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return verificar


def normalizar_mac(valor):
    """
    Aceita identificadores personalizados.
    Nao exige formato hexadecimal.
    """

    if not valor:
        return None

    identificador = valor.strip().upper()

    if not identificador:
        return None

    if len(identificador) > 120:
        return None

    return identificador


def identificador(item):
    return (
        item.mac
        or item.serial
        or item.codigo
        or f"ID-{item.id}"
    )


def serializar_equipamento(item):
    """
    Prepara os dados do equipamento para
    a tabela atualizar automaticamente.
    """

    quantidade = int(item.quantidade or 0)

    quantidade_total = int(
        item.quantidade_total or 0
    )

    em_uso = quantidade_total - quantidade

    if quantidade == 0:
        situacao = "Em uso"

    elif em_uso > 0:
        situacao = "Saldo parcial"

    else:
        situacao = "No saldo"

    return {
        "id": item.id,
        "tipo": item.tipo,
        "marca": item.marca or "",
        "modelo": item.modelo or "",
        "mac": item.mac,
        "serial": item.serial,
        "codigo": item.codigo,
        "identificador": identificador(item),
        "unidade": item.unidade or "un",
        "quantidade": quantidade,
        "quantidade_total": quantidade_total,
        "em_uso": em_uso,
        "situacao": situacao,
        "chegada": (
            item.chegada.strftime("%d/%m/%Y")
            if item.chegada
            else "-"
        ),
        "cadastro": formatar_data_brasilia(
            item.cadastro
        ),
        "cadastrado_por": item.cadastrado_por
    }


def consultar_equipamentos(busca=""):
    """
    Consulta os equipamentos utilizando
    o mesmo filtro do Dashboard original.
    """

    consulta = Equipamento.query

    if busca:
        termo = f"%{busca}%"

        consulta = consulta.filter(or_(
            Equipamento.tipo.ilike(termo),
            Equipamento.marca.ilike(termo),
            Equipamento.modelo.ilike(termo),
            Equipamento.mac.ilike(termo),
            Equipamento.serial.ilike(termo),
            Equipamento.codigo.ilike(termo)
        ))

    return consulta.order_by(
        Equipamento.id.desc()
    ).limit(2000).all()


def consultar_indicadores():
    """
    Calcula os indicadores diretamente
    do banco PostgreSQL.
    """

    resultado = db.session.query(
        func.coalesce(
            func.sum(Equipamento.quantidade_total),
            0
        ),
        func.coalesce(
            func.sum(Equipamento.quantidade),
            0
        ),
        func.count(Equipamento.id)
    ).one()

    total = int(resultado[0])
    saldo = int(resultado[1])
    produtos = int(resultado[2])

    uso = total - saldo

    percentual_saldo = (
        round((saldo / total) * 100, 1)
        if total > 0
        else 0
    )

    percentual_uso = (
        round((uso / total) * 100, 1)
        if total > 0
        else 0
    )

    return {
        "total": total,
        "saldo": saldo,
        "uso": uso,
        "produtos": produtos,
        "percentual_saldo": percentual_saldo,
        "percentual_uso": percentual_uso
    }


def consultar_movimentacoes(limite=6):
    """
    Retorna as movimentacoes mais recentes.
    """

    registros = Historico.query.order_by(
        Historico.data.desc(),
        Historico.id.desc()
    ).limit(limite).all()

    movimentacoes = []

    for registro in registros:
        data_local = converter_data_brasilia(
            registro.data
        )

        movimentacoes.append({
            "id": registro.id,
            "equipamento_id": registro.equipamento_id,
            "identificador": registro.mac,
            "mac": registro.mac,
            "acao": registro.acao,
            "usuario": registro.usuario,
            "data": (
                data_local.strftime("%d/%m/%Y %H:%M")
                if data_local
                else "-"
            ),
            "data_iso": (
                data_local.isoformat()
                if data_local
                else None
            )
        })

    return movimentacoes


def consultar_calendario(ano, mes):
    """
    Conta as movimentacoes de cada dia
    do mes selecionado no calendario.

    Utiliza o horario de Brasilia.
    """

    inicio_local = datetime(
        ano,
        mes,
        1,
        tzinfo=FUSO_BRASILIA
    )

    if mes == 12:
        fim_local = datetime(
            ano + 1,
            1,
            1,
            tzinfo=FUSO_BRASILIA
        )
    else:
        fim_local = datetime(
            ano,
            mes + 1,
            1,
            tzinfo=FUSO_BRASILIA
        )

    inicio_utc = inicio_local.astimezone(
        timezone.utc
    )

    fim_utc = fim_local.astimezone(
        timezone.utc
    )

    registros = Historico.query.filter(
        Historico.data >= inicio_utc,
        Historico.data < fim_utc
    ).with_entities(
        Historico.data
    ).all()

    calendario = {}

    for registro in registros:
        data_local = converter_data_brasilia(
            registro.data
        )

        if not data_local:
            continue

        chave = data_local.strftime("%Y-%m-%d")

        calendario[chave] = (
            calendario.get(chave, 0) + 1
        )

    return calendario


@app.context_processor
def contexto():
    return {
        "nome_usuario": session.get("nome", "")
    }


# ==========================================
# VERIFICACAO DO SERVIDOR
# ==========================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "sistema": "Estoque Inteligente"
    })


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        nome = request.form.get(
            "usuario", ""
        ).strip()

        senha = request.form.get(
            "senha", ""
        )

        usuario = Usuario.query.filter_by(
            usuario=nome
        ).first()

        if usuario and check_password_hash(
            usuario.senha,
            senha
        ):

            session.clear()

            session["usuario_id"] = usuario.id
            session["nome"] = usuario.nome

            return redirect(url_for("index"))

        flash(
            "Usuario ou senha incorretos.",
            "erro"
        )

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_obrigatorio
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==========================================
# DASHBOARD PRINCIPAL
# ==========================================

@app.route("/")
@login_obrigatorio
def index():

    busca = request.args.get(
        "busca", ""
    ).strip()

    equipamentos = consultar_equipamentos(
        busca
    )

    indicadores = consultar_indicadores()

    return render_template(
        "index.html",
        equipamentos=equipamentos,
        total=indicadores["total"],
        saldo=indicadores["saldo"],
        uso=indicadores["uso"],
        busca=busca
    )


# ==========================================
# DASHBOARD INTELIGENTE AO VIVO
# ==========================================

@app.route("/api/dashboard")
@login_obrigatorio
def api_dashboard():
    """
    API utilizada pelo JavaScript para
    atualizar os indicadores automaticamente.
    """

    indicadores = consultar_indicadores()

    agora_local = datetime.now(
        FUSO_BRASILIA
    )

    movimentacoes = consultar_movimentacoes(
        limite=6
    )

    return jsonify({
        **indicadores,
        "data_atual": agora_local.strftime(
            "%d/%m/%Y"
        ),
        "hora_atual": agora_local.strftime(
            "%H:%M:%S"
        ),
        "atualizado_em": agora_local.isoformat(),
        "movimentacoes": movimentacoes
    })


# ==========================================
# API DA TABELA DE ESTOQUE
# ==========================================

@app.route("/api/estoque")
@login_obrigatorio
def api_estoque():
    """
    Permite atualizar a tabela do estoque
    sem recarregar a pagina inteira.
    """

    busca = request.args.get(
        "busca", ""
    ).strip()[:120]

    equipamentos = consultar_equipamentos(
        busca
    )

    itens = [
        serializar_equipamento(item)
        for item in equipamentos
    ]

    return jsonify({
        "itens": itens,
        "quantidade_registros": len(itens),
        "atualizado_em": datetime.now(
            FUSO_BRASILIA
        ).isoformat()
    })


# ==========================================
# API DO CALENDARIO INTELIGENTE
# ==========================================

@app.route("/api/calendario")
@login_obrigatorio
def api_calendario():
    """
    Retorna a quantidade de movimentacoes
    em cada dia do mes selecionado.
    """

    agora_local = datetime.now(
        FUSO_BRASILIA
    )

    try:
        ano = int(request.args.get(
            "ano",
            agora_local.year
        ))

        mes = int(request.args.get(
            "mes",
            agora_local.month
        ))

    except (ValueError, TypeError):
        return jsonify({
            "erro": "Ano ou mes invalido."
        }), 400

    if not (2000 <= ano <= 2100):
        return jsonify({
            "erro": "Ano invalido."
        }), 400

    if not (1 <= mes <= 12):
        return jsonify({
            "erro": "Mes invalido."
        }), 400

    calendario = consultar_calendario(
        ano,
        mes
    )

    return jsonify({
        "ano": ano,
        "mes": mes,
        "movimentacoes_por_dia": calendario,
        "total_movimentacoes": sum(
            calendario.values()
        )
    })


# ==========================================
# CADASTRO UNIVERSAL
# ==========================================

@app.route("/cadastrar", methods=["POST"])
@login_obrigatorio
def cadastrar():

    tipo = request.form.get(
        "tipo", ""
    ).strip()

    marca = request.form.get(
        "marca", ""
    ).strip()

    modelo = request.form.get(
        "modelo", ""
    ).strip()

    modo = request.form.get(
        "modo", "material"
    )

    codigo = request.form.get(
        "codigo", ""
    ).strip()

    unidade = request.form.get(
        "unidade", "un"
    )

    entrada = request.form.get(
        "identificadores", ""
    ).strip()

    if not tipo:
        flash(
            "Informe o nome do produto.",
            "erro"
        )
        return redirect(url_for("index"))

    if (
        len(tipo) > 100
        or len(marca) > 100
        or len(modelo) > 100
        or len(codigo) > 120
    ):
        flash(
            "Um dos campos ultrapassou o tamanho permitido.",
            "erro"
        )
        return redirect(url_for("index"))

    try:
        chegada = datetime.strptime(
            request.form.get("chegada", ""),
            "%Y-%m-%d"
        ).date()

    except (ValueError, TypeError):
        flash(
            "Data de chegada invalida.",
            "erro"
        )
        return redirect(url_for("index"))

    if modo not in ("material", "mac", "serial"):
        flash(
            "Tipo de cadastro invalido.",
            "erro"
        )
        return redirect(url_for("index"))

    try:
        if modo == "material":

            try:
                quantidade = int(
                    request.form.get(
                        "quantidade", "1"
                    )
                )
            except (ValueError, TypeError):
                quantidade = 0

            if quantidade < 1 or quantidade > 1000000:
                flash(
                    "Quantidade invalida.",
                    "erro"
                )
                return redirect(url_for("index"))

            if unidade not in (
                "un",
                "m",
                "kg",
                "cx",
                "pct",
                "rolo"
            ):
                flash(
                    "Unidade de medida invalida.",
                    "erro"
                )
                return redirect(url_for("index"))

            produto = Equipamento(
                tipo=tipo,
                marca=marca,
                modelo=modelo,
                mac=None,
                serial=None,
                codigo=codigo or (
                    "MAT-" + uuid4().hex[:10].upper()
                ),
                unidade=unidade,
                quantidade=quantidade,
                quantidade_total=quantidade,
                chegada=chegada,
                cadastrado_por=session["nome"],
                status="saldo"
            )

            db.session.add(produto)
            db.session.flush()

            db.session.add(Historico(
                equipamento_id=produto.id,
                mac=identificador(produto),
                acao=(
                    f"Cadastro de {quantidade} "
                    f"{unidade}"
                ),
                usuario=session["nome"]
            ))

        else:

            linhas = [
                linha.strip()
                for linha in entrada.replace(
                    ",", "\n"
                ).splitlines()
                if linha.strip()
            ]

            if not linhas or len(linhas) > 500:
                flash(
                    "Informe de 1 a 500 identificadores.",
                    "erro"
                )
                return redirect(url_for("index"))

            valores = [
                normalizar_mac(x)
                for x in linhas
            ]

            if None in valores:
                flash(
                    "Identificador invalido ou muito longo.",
                    "erro"
                )
                return redirect(url_for("index"))

            if len(set(valores)) != len(valores):
                flash(
                    "Existem identificadores repetidos no lote.",
                    "erro"
                )
                return redirect(url_for("index"))

            if modo == "mac":

                existentes = Equipamento.query.filter(
                    Equipamento.mac.in_(valores)
                ).first()

            else:

                existentes = Equipamento.query.filter(
                    Equipamento.serial.in_(valores)
                ).first()

            if existentes:
                flash(
                    "Um identificador ja esta cadastrado.",
                    "erro"
                )
                return redirect(url_for("index"))

            for valor in valores:

                produto = Equipamento(
                    tipo=tipo,
                    marca=marca,
                    modelo=modelo,
                    mac=(
                        valor if modo == "mac"
                        else None
                    ),
                    serial=(
                        valor if modo == "serial"
                        else None
                    ),
                    codigo=None,
                    unidade="un",
                    quantidade=1,
                    quantidade_total=1,
                    chegada=chegada,
                    cadastrado_por=session["nome"],
                    status="saldo"
                )

                db.session.add(produto)
                db.session.flush()

                db.session.add(Historico(
                    equipamento_id=produto.id,
                    mac=valor,
                    acao="Equipamento cadastrado",
                    usuario=session["nome"]
                ))

        db.session.commit()

        flash(
            "Cadastro realizado com sucesso!",
            "sucesso"
        )

    except IntegrityError:

        db.session.rollback()

        flash(
            "Identificador ja cadastrado.",
            "erro"
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro ao cadastrar produto"
        )

        flash(
            "Erro ao salvar o cadastro.",
            "erro"
        )

    return redirect(url_for("index"))


# ==========================================
# RETIRADA E DEVOLUCAO
# ==========================================

@app.route(
    "/status/<int:id>",
    methods=["POST"]
)
@login_obrigatorio
def alterar_status(id):

    try:
        quantidade = int(
            request.form.get(
                "quantidade", "1"
            )
        )
    except (ValueError, TypeError):
        quantidade = 0

    acao = request.form.get(
        "acao", "retirar"
    )

    if quantidade < 1 or quantidade > 1000000:
        flash(
            "Quantidade invalida.",
            "erro"
        )
        return redirect(url_for("index"))

    if acao not in ("retirar", "devolver"):
        flash(
            "Acao invalida.",
            "erro"
        )
        return redirect(url_for("index"))

    try:
        # Bloqueia o registro durante a movimentacao.
        # Evita retiradas simultaneas acima do saldo.
        produto = db.session.query(
            Equipamento
        ).filter_by(id=id).with_for_update().first()

        if produto is None:
            db.session.rollback()

            flash(
                "Produto nao encontrado.",
                "erro"
            )

            return redirect(url_for("index"))

        if acao == "retirar":

            if quantidade > produto.quantidade:
                db.session.rollback()

                flash(
                    "Saldo insuficiente.",
                    "erro"
                )

                return redirect(url_for("index"))

            produto.quantidade -= quantidade

            descricao = (
                f"Retirada de {quantidade} "
                f"{produto.unidade}"
            )

        else:

            em_uso = (
                produto.quantidade_total
                - produto.quantidade
            )

            if quantidade > em_uso:
                db.session.rollback()

                flash(
                    "Quantidade maior que o total em uso.",
                    "erro"
                )

                return redirect(url_for("index"))

            produto.quantidade += quantidade

            descricao = (
                f"Devolucao de {quantidade} "
                f"{produto.unidade}"
            )

        produto.status = (
            "saldo"
            if produto.quantidade > 0
            else "uso"
        )

        db.session.add(Historico(
            equipamento_id=produto.id,
            mac=identificador(produto),
            acao=descricao,
            usuario=session["nome"]
        ))

        db.session.commit()

        flash(
            "Estoque atualizado com sucesso!",
            "sucesso"
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro na movimentacao"
        )

        flash(
            "Erro ao atualizar o estoque.",
            "erro"
        )

    return redirect(url_for("index"))


# ==========================================
# HISTORICO
# ==========================================

@app.route("/historico")
@login_obrigatorio
def historico():

    registros = Historico.query.order_by(
        Historico.id.desc()
    ).limit(500).all()

    return render_template(
        "historico.html",
        registros=registros
    )


# ==========================================
# ASSISTENTE INTELIGENTE
# ==========================================

@app.route("/assistente")
@login_obrigatorio
def assistente():

    return render_template(
        "assistente.html"
    )


@app.route(
    "/api/assistente",
    methods=["POST"]
)
@login_obrigatorio
def api_assistente():

    dados = request.get_json(
        silent=True
    ) or {}

    pergunta = str(
        dados.get("pergunta", "")
    ).strip()

    if not pergunta:
        return jsonify({
            "erro": "Digite uma pergunta."
        }), 400

    if len(pergunta) > 2000:
        return jsonify({
            "erro": "Pergunta muito longa."
        }), 400

    try:

        resposta = criar_resposta(
            pergunta,
            db,
            Equipamento,
            Historico
        )

        return jsonify({
            "resposta": resposta
        })

    except Exception:

        app.logger.exception(
            "Erro no Assistente IA"
        )

        return jsonify({
            "erro": (
                "Nao foi possivel consultar "
                "o assistente agora."
            )
        }), 503


# ==========================================
# INICIALIZACAO DO SISTEMA
# ==========================================

with app.app_context():

    migrar_banco()

    admin_nome = (
        os.environ.get("ADMIN_USER")
        or os.environ.get("ADMIN_USERNAME")
        or ""
    ).strip()

    admin_senha = os.environ.get(
        "ADMIN_PASSWORD", ""
    )

    usuario_existente = db.session.query(
        Usuario.id
    ).first()

    if (
        not usuario_existente
        and admin_nome
        and len(admin_senha) >= 12
    ):

        administrador = Usuario(
            nome="Administrador",
            usuario=admin_nome,
            senha=generate_password_hash(
                admin_senha
            )
        )

        db.session.add(administrador)
        db.session.commit()


# ==========================================
# INICIAR SERVIDOR
# ==========================================

if __name__ == "__main__":
    app.run(debug=False)
