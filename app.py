
import os
import re
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

database_url = os.environ["DATABASE_URL"]
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)


def agora():
    return datetime.now(timezone.utc)


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    usuario = db.Column(db.String(80), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)


class Equipamento(db.Model):
    __tablename__ = "equipamento"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(100), nullable=False)
    marca = db.Column(db.String(100), nullable=False, default="")
    modelo = db.Column(db.String(100), nullable=False, default="")
    mac = db.Column(db.String(17), unique=True, nullable=True)
    serial = db.Column(db.String(120), nullable=True)
    codigo = db.Column(db.String(120), nullable=True)
    unidade = db.Column(db.String(30), default="un")
    quantidade = db.Column(db.Integer, default=1, nullable=False)
    quantidade_total = db.Column(db.Integer, default=1, nullable=False)
    chegada = db.Column(db.Date, nullable=False)
    cadastro = db.Column(db.DateTime(timezone=True), default=agora)
    cadastrado_por = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default="saldo", nullable=False)


class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, nullable=False)
    mac = db.Column(db.String(120), nullable=False)
    acao = db.Column(db.String(200), nullable=False)
    usuario = db.Column(db.String(120), nullable=False)
    data = db.Column(db.DateTime(timezone=True), default=agora)


def migrar_banco():
    # Preserva as tabelas e os registros existentes.
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
                f"ADD COLUMN IF NOT EXISTS {nome} {definicao}"
            ))

        conexao.execute(text(
            "ALTER TABLE equipamento "
            "ALTER COLUMN mac DROP NOT NULL"
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
            "UPDATE equipamento SET quantidade = 1 "
            "WHERE quantidade IS NULL"
        ))

        conexao.execute(text(
            "UPDATE equipamento SET quantidade_total = 1 "
            "WHERE quantidade_total IS NULL"
        ))

        conexao.execute(text(
            "UPDATE equipamento SET unidade = 'un' "
            "WHERE unidade IS NULL"
        ))


def login_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return funcao(*args, **kwargs)
    return verificar


def normalizar_mac(valor):
    if not valor or not valor.strip():
        return None

    caracteres = re.sub(
        r"[^0-9A-Fa-f]", "", valor
    ).upper()

    if not re.fullmatch(r"[0-9A-F]{12}", caracteres):
        return None

    return ":".join(
        caracteres[i:i + 2] for i in range(0, 12, 2)
    )


def identificador(item):
    return item.mac or item.serial or item.codigo or f"ID-{item.id}"


@app.context_processor
def contexto():
    return {"nome_usuario": session.get("nome", "")}


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")

        usuario = Usuario.query.filter_by(usuario=nome).first()

        if usuario and check_password_hash(usuario.senha, senha):
            session.clear()
            session["usuario_id"] = usuario.id
            session["nome"] = usuario.nome
            return redirect(url_for("index"))

        flash("Usuário ou senha incorretos.", "erro")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_obrigatorio
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_obrigatorio
def index():
    busca = request.args.get("busca", "").strip()

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

    equipamentos = consulta.order_by(
        Equipamento.id.desc()
    ).limit(500).all()

    total = db.session.query(
        func.coalesce(func.sum(Equipamento.quantidade_total), 0)
    ).scalar()

    saldo = db.session.query(
        func.coalesce(func.sum(Equipamento.quantidade), 0)
    ).scalar()

    uso = total - saldo

    return render_template(
        "index.html",
        equipamentos=equipamentos,
        total=total,
        saldo=saldo,
        uso=uso,
        busca=busca
    )


@app.route("/cadastrar", methods=["POST"])
@login_obrigatorio
def cadastrar():
    tipo = request.form.get("tipo", "").strip()
    marca = request.form.get("marca", "").strip()
    modelo = request.form.get("modelo", "").strip()
    modo = request.form.get("modo", "material")
    codigo = request.form.get("codigo", "").strip()
    unidade = request.form.get("unidade", "un")
    entrada = request.form.get("identificadores", "").strip()

    if not tipo:
        flash("Informe o nome do produto ou equipamento.", "erro")
        return redirect(url_for("index"))

    try:
        chegada = datetime.strptime(
            request.form.get("chegada", ""), "%Y-%m-%d"
        ).date()
    except ValueError:
        flash("Informe uma data de chegada válida.", "erro")
        return redirect(url_for("index"))

    if modo == "material":
        try:
            quantidade = int(request.form.get("quantidade", "1"))
        except ValueError:
            quantidade = 0

        if quantidade < 1 or quantidade > 1000000:
            flash("Informe uma quantidade válida.", "erro")
            return redirect(url_for("index"))

        produto = Equipamento(
            tipo=tipo,
            marca=marca,
            modelo=modelo,
            mac=None,
            serial=None,
            codigo=codigo or f"MAT-{uuid4().hex[:10].upper()}",
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
            acao=f"Cadastro de {quantidade} {unidade}",
            usuario=session["nome"]
        ))

    else:
        linhas = [
            linha.strip()
            for linha in entrada.replace(",", "\n").splitlines()
            if linha.strip()
        ]

        if not linhas or len(linhas) > 500:
            flash("Informe de 1 a 500 identificadores.", "erro")
            return redirect(url_for("index"))

        if modo == "mac":
            valores = [normalizar_mac(x) for x in linhas]

            if None in valores:
                flash("Um ou mais MACs são inválidos.", "erro")
                return redirect(url_for("index"))

            existentes = {
                e.mac for e in Equipamento.query.filter(
                    Equipamento.mac.in_(valores)
                ).all()
            }
        elif modo == "serial":
            valores = linhas

            existentes = {
                e.serial for e in Equipamento.query.filter(
                    Equipamento.serial.in_(valores)
                ).all()
            }
        else:
            flash("Tipo de cadastro inválido.", "erro")
            return redirect(url_for("index"))

        if len(set(valores)) != len(valores) or existentes:
            flash("Existem identificadores repetidos.", "erro")
            return redirect(url_for("index"))

        for valor in valores:
            produto = Equipamento(
                tipo=tipo,
                marca=marca,
                modelo=modelo,
                mac=valor if modo == "mac" else None,
                serial=valor if modo == "serial" else None,
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

    try:
        db.session.commit()
        flash("Cadastro realizado com sucesso!", "sucesso")
    except IntegrityError:
        db.session.rollback()
        flash("Identificador já cadastrado.", "erro")
    except Exception:
        db.session.rollback()
        app.logger.exception("Erro no cadastro")
        flash("Erro ao salvar o cadastro.", "erro")

    return redirect(url_for("index"))


@app.route("/status/<int:id>", methods=["POST"])
@login_obrigatorio
def alterar_status(id):
    produto = db.get_or_404(Equipamento, id)

    try:
        quantidade = int(request.form.get("quantidade", "1"))
    except ValueError:
        quantidade = 0

    acao = request.form.get("acao", "retirar")

    if quantidade < 1:
        flash("Quantidade inválida.", "erro")
        return redirect(url_for("index"))

    if acao == "retirar":
        if quantidade > produto.quantidade:
            flash("Saldo insuficiente.", "erro")
            return redirect(url_for("index"))

        produto.quantidade -= quantidade
        descricao = f"Retirada de {quantidade} {produto.unidade}"

    elif acao == "devolver":
        em_uso = produto.quantidade_total - produto.quantidade

        if quantidade > em_uso:
            flash("Quantidade maior que o total em uso.", "erro")
            return redirect(url_for("index"))

        produto.quantidade += quantidade
        descricao = f"Devolução de {quantidade} {produto.unidade}"

    else:
        flash("Ação inválida.", "erro")
        return redirect(url_for("index"))

    produto.status = (
        "saldo" if produto.quantidade > 0 else "uso"
    )

    db.session.add(Historico(
        equipamento_id=produto.id,
        mac=identificador(produto),
        acao=descricao,
        usuario=session["nome"]
    ))

    db.session.commit()

    flash("Estoque atualizado!", "sucesso")
    return redirect(url_for("index"))


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


with app.app_context():
    migrar_banco()

    admin_nome = os.environ.get("ADMIN_USER", "").strip()
    admin_senha = os.environ.get("ADMIN_PASSWORD", "")

    if (
        not db.session.query(Usuario.id).first()
        and admin_nome
        and len(admin_senha) >= 12
    ):
        db.session.add(Usuario(
            nome="Administrador",
            usuario=admin_nome,
            senha=generate_password_hash(admin_senha)
        ))
        db.session.commit()


if __name__ == "__main__":
    app.run(debug=False)
