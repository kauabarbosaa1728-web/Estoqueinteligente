
import os
import re
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
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
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "true").lower() == "true"
)
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
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(100), nullable=False)
    marca = db.Column(db.String(100), nullable=False)
    modelo = db.Column(db.String(100), nullable=False)
    mac = db.Column(db.String(17), unique=True, nullable=False)
    serial = db.Column(db.String(120))
    chegada = db.Column(db.Date, nullable=False)
    cadastro = db.Column(db.DateTime(timezone=True), default=agora)
    cadastrado_por = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default="saldo", nullable=False)


class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, nullable=False)
    mac = db.Column(db.String(17), nullable=False)
    acao = db.Column(db.String(100), nullable=False)
    usuario = db.Column(db.String(120), nullable=False)
    data = db.Column(db.DateTime(timezone=True), default=agora)


def login_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return funcao(*args, **kwargs)
    return verificar


def normalizar_mac(valor):
    caracteres = re.sub(r"[^0-9A-Fa-f]", "", valor or "").upper()
    if not re.fullmatch(r"[0-9A-F]{12}", caracteres):
        return None
    return ":".join(
        caracteres[i:i + 2] for i in range(0, 12, 2)
    )


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
        consulta = consulta.filter(
            db.or_(
                Equipamento.mac.ilike(termo),
                Equipamento.tipo.ilike(termo),
                Equipamento.marca.ilike(termo),
                Equipamento.modelo.ilike(termo)
            )
        )

    equipamentos = consulta.order_by(
        Equipamento.id.desc()
    ).limit(500).all()

    total = db.session.query(func.count(Equipamento.id)).scalar()
    saldo = Equipamento.query.filter_by(status="saldo").count()
    uso = Equipamento.query.filter_by(status="uso").count()

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
    serial = request.form.get("serial", "").strip()

    try:
        chegada = datetime.strptime(
            request.form.get("chegada", ""), "%Y-%m-%d"
        ).date()
    except ValueError:
        flash("Data de chegada inválida.", "erro")
        return redirect(url_for("index"))

    if not all([tipo, marca, modelo]):
        flash("Preencha tipo, marca e modelo.", "erro")
        return redirect(url_for("index"))

    entrada = request.form.get("macs", "")
    linhas = [
        linha.strip()
        for linha in entrada.replace(",", "\n").splitlines()
        if linha.strip()
    ]

    if not linhas or len(linhas) > 500:
        flash("Informe entre 1 e 500 MACs.", "erro")
        return redirect(url_for("index"))

    macs = [normalizar_mac(linha) for linha in linhas]

    if None in macs or len(set(macs)) != len(macs):
        flash("Existem MACs inválidos ou repetidos no lote.", "erro")
        return redirect(url_for("index"))

    existentes = {
        item.mac for item in Equipamento.query.filter(
            Equipamento.mac.in_(macs)
        ).all()
    }

    if existentes:
        flash(
            "MAC já cadastrado: " + ", ".join(sorted(existentes)),
            "erro"
        )
        return redirect(url_for("index"))

    for mac in macs:
        equipamento = Equipamento(
            tipo=tipo,
            marca=marca,
            modelo=modelo,
            mac=mac,
            serial=serial if len(macs) == 1 else None,
            chegada=chegada,
            cadastrado_por=session["nome"],
            status="saldo"
        )
        db.session.add(equipamento)
        db.session.flush()

        db.session.add(Historico(
            equipamento_id=equipamento.id,
            mac=mac,
            acao="Equipamento cadastrado",
            usuario=session["nome"]
        ))

    try:
        db.session.commit()
        flash(f"{len(macs)} equipamento(s) cadastrado(s)!", "sucesso")
    except Exception:
        db.session.rollback()
        flash("Erro ao cadastrar. Verifique os MACs.", "erro")

    return redirect(url_for("index"))


@app.route("/status/<int:id>", methods=["POST"])
@login_obrigatorio
def alterar_status(id):
    equipamento = db.get_or_404(Equipamento, id)

    if equipamento.status == "saldo":
        equipamento.status = "uso"
        acao = "Equipamento marcado como em uso"
    else:
        equipamento.status = "saldo"
        acao = "Equipamento devolvido ao saldo"

    db.session.add(Historico(
        equipamento_id=equipamento.id,
        mac=equipamento.mac,
        acao=acao,
        usuario=session["nome"]
    ))
    db.session.commit()

    flash("Status atualizado com sucesso!", "sucesso")
    return redirect(url_for("index"))


@app.route("/historico")
@login_obrigatorio
def historico():
    registros = Historico.query.order_by(
        Historico.id.desc()
    ).limit(500).all()

    return render_template("historico.html", registros=registros)


with app.app_context():
    db.create_all()

    admin_nome = os.environ.get("ADMIN_USER", "").strip()
    admin_senha = os.environ.get("ADMIN_PASSWORD", "")
    admin_existe = db.session.query(Usuario.id).first()

    if not admin_existe and admin_nome and len(admin_senha) >= 12:
        db.session.add(Usuario(
            nome="Administrador",
            usuario=admin_nome,
            senha=generate_password_hash(admin_senha)
        ))
        db.session.commit()


if __name__ == "__main__":
    app.run(debug=False)
