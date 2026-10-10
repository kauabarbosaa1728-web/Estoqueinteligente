import os
from functools import wraps
from datetime import date
from decimal import Decimal, InvalidOperation

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave-local-trocar-no-render")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def conectar():
    if not DATABASE_URL:
        raise RuntimeError(
            "Configure DATABASE_URL com a conexão do PostgreSQL."
        )
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


def inicializar_banco():
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    full_name VARCHAR(160) NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'funcionario',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(80) UNIQUE NOT NULL,
                    name VARCHAR(180) NOT NULL,
                    item_type VARCHAR(20) NOT NULL
                        CHECK (item_type IN ('equipamento','material')),
                    category VARCHAR(120) DEFAULT '',
                    supplier VARCHAR(180) DEFAULT '',
                    unit_value NUMERIC(12,2) NOT NULL DEFAULT 0,
                    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    quantity INTEGER NOT NULL DEFAULT 1
                        CHECK (quantity >= 0),
                    status VARCHAR(20) NOT NULL DEFAULT 'estoque'
                        CHECK (status IN ('estoque','uso','esgotado')),
                    notes TEXT DEFAULT '',
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS movements (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
                    item_name VARCHAR(180) NOT NULL,
                    movement_type VARCHAR(40) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    details TEXT DEFAULT '',
                    unit_value NUMERIC(12,2) NOT NULL DEFAULT 0,
                    supplier VARCHAR(180) DEFAULT '',
                    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    actor_name VARCHAR(160) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);
                CREATE INDEX IF NOT EXISTS idx_movements_date
                    ON movements(created_at DESC);
            """)

            cur.execute("SELECT id FROM users WHERE username = %s", (
                os.environ.get("ADMIN_USERNAME", "admin"),
            ))
            admin = cur.fetchone()

            if not admin:
                senha = os.environ.get("ADMIN_PASSWORD", "")
                if not senha:
                    raise RuntimeError(
                        "Configure ADMIN_PASSWORD antes de iniciar o sistema."
                    )

                cur.execute("""
                    INSERT INTO users
                    (username, full_name, password_hash, role)
                    VALUES (%s, %s, %s, 'admin')
                """, (
                    os.environ.get("ADMIN_USERNAME", "admin"),
                    "Administrador KBSISTEMAS",
                    generate_password_hash(senha)
                ))


def registrar_movimentacao(cur, item, tipo, quantidade, detalhes=""):
    cur.execute("""
        INSERT INTO movements
        (item_id, item_name, movement_type, quantity, details,
         unit_value, supplier, actor_id, actor_name)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        item["id"], item["name"], tipo, quantidade, detalhes,
        item["unit_value"], item.get("supplier", ""),
        session.get("user_id"), session.get("full_name", "Usuário")
    ))


def login_obrigatorio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def admin_obrigatorio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return func(*args, **kwargs)
    return wrapper


@app.errorhandler(403)
def proibido(_erro):
    return render_template(
        "error.html", code=403,
        message="Você não tem permissão para acessar esta área."
    ), 403


@app.route("/")
def inicio():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        usuario = request.form.get("username", "").strip()
        senha = request.form.get("password", "")

        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM users
                    WHERE username = %s AND active = TRUE
                """, (usuario,))
                pessoa = cur.fetchone()

        if pessoa and check_password_hash(pessoa["password_hash"], senha):
            session.clear()
            session["user_id"] = pessoa["id"]
            session["username"] = pessoa["username"]
            session["full_name"] = pessoa["full_name"]
            session["role"] = pessoa["role"]
            return redirect(url_for("dashboard"))

        flash("Usuário ou senha inválidos.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_obrigatorio
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_obrigatorio
def dashboard():
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE item_type='equipamento' AND status='estoque'
                    ) AS equipamentos_disponiveis,
                    COUNT(*) FILTER (
                        WHERE item_type='equipamento' AND status='uso'
                    ) AS equipamentos_em_uso,
                    COUNT(*) FILTER (
                        WHERE item_type='material'
                    ) AS materiais_cadastrados,
                    COALESCE(SUM(
                        CASE WHEN item_type='material' THEN quantity ELSE 0 END
                    ), 0) AS unidades_materiais
                FROM items
            """)
            stats = cur.fetchone()

            cur.execute("""
                SELECT * FROM items
                ORDER BY updated_at DESC, id DESC LIMIT 8
            """)
            itens = cur.fetchall()

            cur.execute("""
                SELECT * FROM movements
                ORDER BY created_at DESC, id DESC LIMIT 8
            """)
            movimentos = cur.fetchall()

    return render_template(
        "dashboard.html", stats=stats,
        recent_items=itens, recent_movements=movimentos
    )


@app.route("/estoque")
@login_obrigatorio
def estoque():
    busca = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    tipo = request.args.get("tipo", "")

    sql = "SELECT * FROM items WHERE 1=1"
    params = []

    if busca:
        sql += """
            AND (name ILIKE %s OR code ILIKE %s
            OR supplier ILIKE %s OR category ILIKE %s)
        """
        termo = f"%{busca}%"
        params.extend([termo, termo, termo, termo])

    if status in ("estoque", "uso", "esgotado"):
        sql += " AND status = %s"
        params.append(status)

    if tipo in ("equipamento", "material"):
        sql += " AND item_type = %s"
        params.append(tipo)

    sql += """
        ORDER BY
        CASE status WHEN 'estoque' THEN 1 WHEN 'uso' THEN 2 ELSE 3 END,
        name
    """

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            itens = cur.fetchall()

    return render_template(
        "estoque.html", items=itens,
        q=busca, status=status, tipo=tipo
    )


@app.route("/itens/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_item():
    if request.method == "POST":
        codigo = request.form.get("code", "").strip()
        nome = request.form.get("name", "").strip()
        tipo = request.form.get("item_type", "")
        categoria = request.form.get("category", "").strip()
        fornecedor = request.form.get("supplier", "").strip()
        data_entrada = request.form.get("entry_date") or str(date.today())
        observacoes = request.form.get("notes", "").strip()

        try:
            quantidade = int(request.form.get("quantity", "1"))
            valor = Decimal(
                request.form.get("unit_value", "0").replace(",", ".")
            )
            if quantidade < 1 or valor < 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            flash("Informe quantidade e valor válidos.", "error")
            return render_template("cadastro_item.html")

        if not codigo or not nome or tipo not in ("equipamento", "material"):
            flash("Preencha código, nome e tipo do item.", "error")
            return render_template("cadastro_item.html")

        if tipo == "equipamento":
            quantidade = 1

        try:
            with conectar() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO items
                        (code,name,item_type,category,supplier,unit_value,
                         entry_date,quantity,status,notes,created_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING *
                    """, (
                        codigo, nome, tipo, categoria, fornecedor, valor,
                        data_entrada, quantidade, "estoque",
                        observacoes, session["user_id"]
                    ))
                    item = cur.fetchone()
                    registrar_movimentacao(
                        cur, item, "entrada", quantidade,
                        "Cadastro inicial. Fornecedor: " +
                        (fornecedor or "não informado")
                    )

            flash("Item cadastrado com sucesso!", "success")
            return redirect(url_for("estoque"))

        except psycopg2.errors.UniqueViolation:
            flash("Esse código já existe. Informe um código diferente.", "error")
        except Exception:
            app.logger.exception("Erro ao cadastrar item")
            flash("Não foi possível cadastrar o item. Confira os dados.", "error")

    return render_template("cadastro_item.html")


@app.route("/itens/<int:item_id>/acao", methods=["POST"])
@login_obrigatorio
def acao_item(item_id):
    acao = request.form.get("action", "")
    detalhes = request.form.get("details", "").strip()

    try:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM items WHERE id=%s FOR UPDATE",
                    (item_id,)
                )
                item = cur.fetchone()

                if not item:
                    abort(404)

                if item["item_type"] == "equipamento":
                    if acao == "usar" and item["status"] == "estoque":
                        novo_status = "uso"
                        tipo_movimento = "retirada para uso"
                    elif acao == "devolver" and item["status"] == "uso":
                        novo_status = "estoque"
                        tipo_movimento = "devolução ao estoque"
                    else:
                        flash("Ação não permitida para este equipamento.", "error")
                        return redirect(url_for("estoque"))

                    cur.execute("""
                        UPDATE items SET status=%s,
                        updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s RETURNING *
                    """, (novo_status, item_id))
                    atualizado = cur.fetchone()
                    registrar_movimentacao(
                        cur, atualizado, tipo_movimento, 1, detalhes
                    )

                else:
                    try:
                        quantidade = int(request.form.get("quantity", "0"))
                        if quantidade <= 0:
                            raise ValueError
                    except ValueError:
                        flash("Informe uma quantidade maior que zero.", "error")
                        return redirect(url_for("estoque"))

                    if acao == "retirar":
                        if quantidade > item["quantity"]:
                            flash("Quantidade insuficiente em estoque.", "error")
                            return redirect(url_for("estoque"))
                        nova_quantidade = item["quantity"] - quantidade
                        tipo_movimento = "saída de material"
                    elif acao == "repor":
                        nova_quantidade = item["quantity"] + quantidade
                        tipo_movimento = "reposição de material"
                    else:
                        flash("Ação inválida.", "error")
                        return redirect(url_for("estoque"))

                    novo_status = "estoque" if nova_quantidade > 0 else "esgotado"
                    cur.execute("""
                        UPDATE items SET quantity=%s, status=%s,
                        updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s RETURNING *
                    """, (nova_quantidade, novo_status, item_id))
                    atualizado = cur.fetchone()
                    registrar_movimentacao(
                        cur, atualizado, tipo_movimento, quantidade, detalhes
                    )

        flash("Movimentação registrada com sucesso.", "success")

    except Exception:
        app.logger.exception("Erro ao registrar movimentação")
        flash("Não foi possível registrar a movimentação.", "error")

    return redirect(url_for("estoque"))


@app.route("/historico")
@login_obrigatorio
def historico():
    busca = request.args.get("q", "").strip()

    with conectar() as conn:
        with conn.cursor() as cur:
            if busca:
                termo = f"%{busca}%"
                cur.execute("""
                    SELECT * FROM movements
                    WHERE item_name ILIKE %s OR actor_name ILIKE %s
                    OR movement_type ILIKE %s OR details ILIKE %s
                    ORDER BY created_at DESC LIMIT 300
                """, (termo, termo, termo, termo))
            else:
                cur.execute("""
                    SELECT * FROM movements
                    ORDER BY created_at DESC LIMIT 300
                """)
            movimentos = cur.fetchall()

    return render_template("historico.html", movements=movimentos, q=busca)


@app.route("/usuarios", methods=["GET", "POST"])
@admin_obrigatorio
def usuarios():
    if request.method == "POST":
        nome = request.form.get("full_name", "").strip()
        usuario = request.form.get("username", "").strip()
        senha = request.form.get("password", "")
        perfil = request.form.get("role", "funcionario")

        if not nome or not usuario or len(senha) < 8:
            flash("Preencha todos os campos. A senha precisa ter 8 caracteres.", "error")
        elif perfil not in ("admin", "funcionario"):
            flash("Perfil inválido.", "error")
        else:
            try:
                with conectar() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO users
                            (username,full_name,password_hash,role)
                            VALUES (%s,%s,%s,%s)
                        """, (
                            usuario, nome, generate_password_hash(senha), perfil
                        ))
                flash("Usuário criado com sucesso.", "success")
                return redirect(url_for("usuarios"))
            except psycopg2.errors.UniqueViolation:
                flash("Esse nome de usuário já existe.", "error")
            except Exception:
                app.logger.exception("Erro ao criar usuário")
                flash("Não foi possível criar o usuário.", "error")

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,username,full_name,role,active,created_at
                FROM users ORDER BY full_name
            """)
            lista = cur.fetchall()

    return render_template("usuarios.html", users=lista)


@app.route("/usuarios/<int:user_id>/alternar", methods=["POST"])
@admin_obrigatorio
def alternar_usuario(user_id):
    if user_id == session.get("user_id"):
        flash("Você não pode desativar sua própria conta.", "error")
    else:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET active = NOT active
                    WHERE id=%s AND role <> 'admin' RETURNING id
                """, (user_id,))
                if cur.fetchone():
                    flash("Status do usuário atualizado.", "success")
                else:
                    flash("Usuário não encontrado ou conta protegida.", "error")

    return redirect(url_for("usuarios"))


def contexto_estoque():
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT item_type,status,COUNT(*) AS registros,
                COALESCE(SUM(quantity),0) AS quantidade
                FROM items GROUP BY item_type,status
            """)
            resumo = cur.fetchall()

            cur.execute("""
                SELECT code,name,item_type,category,supplier,unit_value,
                entry_date,quantity,status FROM items ORDER BY name LIMIT 100
            """)
            itens = cur.fetchall()

            cur.execute("""
                SELECT item_name,movement_type,quantity,actor_name,details,created_at
                FROM movements ORDER BY created_at DESC LIMIT 30
            """)
            movimentos = cur.fetchall()

    return resumo, itens, movimentos


def resposta_local(pergunta, resumo, itens, movimentos):
    texto = pergunta.lower()

    if any(p in texto for p in ("em uso", "usados", "em utilização")):
        encontrados = [
            i for i in itens
            if i["item_type"] == "equipamento" and i["status"] == "uso"
        ]
        if not encontrados:
            return "Não encontrei equipamentos marcados como em uso."
        return "Equipamentos em uso:\n" + "\n".join(
            f"- {i['name']} (código {i['code']})" for i in encontrados
        )

    if "fornecedor" in texto:
        fornecedores = sorted({
            i["supplier"] for i in itens if i["supplier"]
        })
        return "Fornecedores cadastrados:\n" + (
            "\n".join(f"- {f}" for f in fornecedores)
            if fornecedores else "Nenhum fornecedor cadastrado."
        )

    if any(p in texto for p in (
        "histórico", "historico", "movimentação", "movimentacao",
        "última", "ultima", "quem retirou"
    )):
        if not movimentos:
            return "Ainda não existem movimentações registradas."
        return "Movimentações recentes:\n" + "\n".join(
            f"- {m['created_at']:%d/%m/%Y %H:%M}: {m['movement_type']} — "
            f"{m['item_name']} (quantidade {m['quantity']}) por {m['actor_name']}"
            for m in movimentos[:10]
        )

    palavras = [p for p in texto.replace("?", " ").split() if len(p) > 2]
    encontrados = [
        i for i in itens
        if any(p in (
            i["name"] + " " + i["code"] + " " + (i["category"] or "")
        ).lower() for p in palavras)
    ]

    if encontrados:
        return "Itens encontrados:\n" + "\n".join(
            f"- {i['name']} | código {i['code']} | tipo {i['item_type']} | "
            f"status {i['status']} | quantidade {i['quantity']} | "
            f"fornecedor {i['supplier'] or 'não informado'}"
            for i in encontrados[:15]
        )

    linhas = ["Resumo do estoque:"]
    for item in resumo:
        linhas.append(
            f"- {item['item_type']} / {item['status']}: "
            f"{item['registros']} cadastro(s), quantidade {item['quantidade']}"
        )
    linhas.append(
        "Você também pode perguntar quais equipamentos estão em uso, "
        "quais fornecedores existem ou consultar movimentações."
    )
    return "\n".join(linhas)


@app.route("/chat", methods=["GET", "POST"])
@login_obrigatorio
def chat_ia():
    resposta = None
    pergunta = ""

    if request.method == "POST":
        pergunta = request.form.get("question", "").strip()

        if not pergunta:
            flash("Digite uma pergunta.", "error")
        else:
            try:
                resumo, itens, movimentos = contexto_estoque()
                resposta = resposta_local(pergunta, resumo, itens, movimentos)

                if OPENAI_API_KEY:
                    try:
                        from openai import OpenAI
                        cliente = OpenAI(api_key=OPENAI_API_KEY)
                        contexto = {
                            "resumo": [dict(x) for x in resumo],
                            "itens": [dict(x) for x in itens],
                            "movimentos_recentes": [dict(x) for x in movimentos]
                        }
                        resultado = cliente.chat.completions.create(
                            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                            messages=[
                                {
                                    "role": "system",
                                    "content":
                                    "Você é o assistente do Estoque Inteligente "
                                    "KBSISTEMAS. Responda em português. Use apenas "
                                    "os dados do contexto para informar fatos do "
                                    "estoque. Não invente quantidades. Contexto: "
                                    + str(contexto)
                                },
                                {"role": "user", "content": pergunta}
                            ],
                            temperature=0.2,
                            max_tokens=700
                        )
                        resposta = resultado.choices[0].message.content or resposta
                    except Exception:
                        app.logger.exception("IA indisponível; usando resposta local.")

            except Exception:
                app.logger.exception("Erro ao consultar estoque")
                resposta = "Não consegui consultar o banco. Confira a conexão e tente novamente."

    return render_template(
        "chat_ia.html", answer=resposta, question=pergunta
    )


@app.route("/health")
def health():
    try:
        with conectar() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception:
        return {"status": "error", "database": "unavailable"}, 503


if DATABASE_URL:
    try:
        inicializar_banco()
    except Exception:
        app.logger.exception("Não foi possível inicializar o banco de dados.")
else:
    app.logger.warning("DATABASE_URL não configurada.")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
