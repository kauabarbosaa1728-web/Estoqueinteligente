
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_

FUSO = ZoneInfo("America/Sao_Paulo")
LIMITE_LISTA = 15
LIMITE_BAIXO = 3


# ============================================================
# CONFIGURACAO
# ============================================================

def configuracao_ia():
    return {
        "configurada": True,
        "modelo": "Estoque IA 3.0 - Gratuita"
    }


def normalizar(texto):
    texto = str(texto or "").lower().strip()
    texto = unicodedata.normalize("NFKD", texto)

    return "".join(
        letra for letra in texto
        if not unicodedata.combining(letra)
    )


def numero(valor):
    return int(valor or 0)


def contem(texto, *expressoes):
    return any(expressao in texto for expressao in expressoes)


def dinheiro_nao_aplicavel():
    return None


def formatar_data(valor):
    if not valor:
        return "Nao informada"

    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            # Datas antigas podem estar salvas sem fuso.
            # Nao presumimos UTC para evitar horarios incorretos.
            return valor.strftime("%d/%m/%Y %H:%M")

        return valor.astimezone(FUSO).strftime("%d/%m/%Y %H:%M")

    return str(valor)


def formatar_item(item):
    total = numero(item.quantidade_total)
    saldo = numero(item.quantidade)

    return (
        f"📦 {item.tipo or 'Equipamento'}\n"
        f"ID: {item.id}\n"
        f"Marca: {item.marca or '-'}\n"
        f"Modelo: {item.modelo or '-'}\n"
        f"MAC: {item.mac or '-'}\n"
        f"Serial: {item.serial or '-'}\n"
        f"Codigo: {item.codigo or '-'}\n"
        f"Disponiveis: {saldo}\n"
        f"Em uso: {total - saldo}\n"
        f"Total: {total}"
    )


# ============================================================
# CONSULTAS GERAIS AO BANCO
# ============================================================

def resumo_geral(db, Equipamento):
    resultado = db.session.query(
        func.count(Equipamento.id),
        func.coalesce(func.sum(Equipamento.quantidade_total), 0),
        func.coalesce(func.sum(Equipamento.quantidade), 0)
    ).one()

    registros = numero(resultado[0])
    total = numero(resultado[1])
    disponiveis = numero(resultado[2])

    return {
        "registros": registros,
        "total": total,
        "disponiveis": disponiveis,
        "em_uso": total - disponiveis
    }


def resposta_resumo(db, Equipamento):
    dados = resumo_geral(db, Equipamento)

    return (
        "📊 RESUMO GERAL DO ESTOQUE\n\n"
        f"📦 Unidades totais: {dados['total']}\n"
        f"🟢 Disponiveis: {dados['disponiveis']}\n"
        f"🔴 Em uso: {dados['em_uso']}\n"
        f"🗂️ Registros cadastrados: {dados['registros']}\n\n"
        "Informacoes consultadas diretamente no banco de dados."
    )


def resposta_disponiveis(db, Equipamento):
    dados = resumo_geral(db, Equipamento)

    return (
        "🟢 ESTOQUE DISPONIVEL\n\n"
        f"Temos {dados['disponiveis']} unidades disponiveis.\n\n"
        f"Total geral: {dados['total']} unidades."
    )


def resposta_em_uso(db, Equipamento):
    dados = resumo_geral(db, Equipamento)

    return (
        "🔴 EQUIPAMENTOS EM USO\n\n"
        f"Existem {dados['em_uso']} unidades em uso.\n\n"
        f"Unidades disponiveis: {dados['disponiveis']}."
    )


def resposta_registros(db, Equipamento):
    dados = resumo_geral(db, Equipamento)

    return (
        "🗂️ REGISTROS CADASTRADOS\n\n"
        f"O sistema possui {dados['registros']} "
        "registros de equipamentos.\n\n"
        "Um registro pode representar mais de uma unidade."
    )


def resposta_percentual(db, Equipamento):
    dados = resumo_geral(db, Equipamento)

    if dados["total"] == 0:
        return "Ainda nao existem unidades no estoque."

    percentual = (
        dados["disponiveis"] / dados["total"]
    ) * 100

    uso = (
        dados["em_uso"] / dados["total"]
    ) * 100

    return (
        "📈 INDICADORES DO ESTOQUE\n\n"
        f"🟢 Disponivel: {percentual:.1f}%\n"
        f"🔴 Em uso: {uso:.1f}%\n\n"
        f"Total: {dados['total']} unidades."
    )


# ============================================================
# LISTAGENS E ANALISES
# ============================================================

def resposta_por_tipo(db, Equipamento):
    grupos = db.session.query(
        Equipamento.tipo,
        func.count(Equipamento.id),
        func.coalesce(func.sum(Equipamento.quantidade_total), 0),
        func.coalesce(func.sum(Equipamento.quantidade), 0)
    ).group_by(
        Equipamento.tipo
    ).order_by(
        func.sum(Equipamento.quantidade_total).desc()
    ).limit(LIMITE_LISTA).all()

    if not grupos:
        return "Nenhum equipamento cadastrado."

    linhas = ["📊 ESTOQUE POR TIPO\n"]

    for tipo, registros, total, saldo in grupos:
        linhas.append(
            f"• {tipo or 'Sem tipo'}\n"
            f"  Total: {numero(total)}\n"
            f"  Disponiveis: {numero(saldo)}\n"
            f"  Registros: {numero(registros)}"
        )

    linhas.append(
        f"\nExibindo ate {LIMITE_LISTA} tipos."
    )

    return "\n\n".join(linhas)


def resposta_por_marca(db, Equipamento):
    grupos = db.session.query(
        Equipamento.marca,
        func.coalesce(func.sum(Equipamento.quantidade_total), 0),
        func.coalesce(func.sum(Equipamento.quantidade), 0)
    ).group_by(
        Equipamento.marca
    ).order_by(
        func.sum(Equipamento.quantidade_total).desc()
    ).limit(LIMITE_LISTA).all()

    if not grupos:
        return "Nenhuma marca cadastrada."

    linhas = ["🏷️ ESTOQUE POR MARCA\n"]

    for marca, total, saldo in grupos:
        linhas.append(
            f"• {marca or 'Sem marca'}: "
            f"{numero(total)} unidades "
            f"({numero(saldo)} disponiveis)"
        )

    return "\n".join(linhas)


def resposta_zerados(Equipamento):
    consulta = Equipamento.query.filter(
        Equipamento.quantidade <= 0
    )

    total = consulta.count()
    itens = consulta.order_by(
        Equipamento.id.desc()
    ).limit(LIMITE_LISTA).all()

    if not itens:
        return "✅ Nenhum registro esta com saldo zerado."

    linhas = [f"⚠️ {total} REGISTRO(S) SEM SALDO\n"]

    for item in itens:
        linhas.append(
            f"• {item.tipo} | "
            f"{item.marca or '-'} "
            f"{item.modelo or '-'} | "
            f"MAC: {item.mac or '-'}"
        )

    if total > LIMITE_LISTA:
        linhas.append("\nLista parcial.")

    return "\n".join(linhas)


def resposta_estoque_baixo(Equipamento):
    consulta = Equipamento.query.filter(
        Equipamento.quantidade > 0,
        Equipamento.quantidade <= LIMITE_BAIXO
    )

    total = consulta.count()
    itens = consulta.order_by(
        Equipamento.quantidade.asc(),
        Equipamento.id.desc()
    ).limit(LIMITE_LISTA).all()

    if not itens:
        return (
            "✅ Nenhum registro esta com saldo entre "
            f"1 e {LIMITE_BAIXO} unidades."
        )

    linhas = [
        "⚠️ ESTOQUE BAIXO\n",
        f"Criterio: de 1 a {LIMITE_BAIXO} "
        "unidades disponiveis por registro.\n"
    ]

    for item in itens:
        linhas.append(
            f"• {item.tipo} | "
            f"{item.marca or '-'} "
            f"{item.modelo or '-'}: "
            f"{numero(item.quantidade)} disponivel(is)"
        )

    if total > LIMITE_LISTA:
        linhas.append("\nLista parcial.")

    return "\n".join(linhas)


def resposta_parcialmente_em_uso(Equipamento):
    consulta = Equipamento.query.filter(
        Equipamento.quantidade > 0,
        Equipamento.quantidade_total > Equipamento.quantidade
    )

    total = consulta.count()
    itens = consulta.order_by(
        Equipamento.id.desc()
    ).limit(LIMITE_LISTA).all()

    if not itens:
        return "Nenhum registro esta parcialmente em uso."

    linhas = [
        f"🟡 {total} REGISTRO(S) PARCIALMENTE EM USO\n"
    ]

    for item in itens:
        linhas.append(
            f"• {item.tipo} | "
            f"{item.marca or '-'} "
            f"{item.modelo or '-'}\n"
            f"  Disponiveis: {numero(item.quantidade)}\n"
            f"  Em uso: "
            f"{numero(item.quantidade_total) - numero(item.quantidade)}"
        )

    if total > LIMITE_LISTA:
        linhas.append("\nLista parcial.")

    return "\n\n".join(linhas)


def resposta_maior_estoque(Equipamento):
    item = Equipamento.query.order_by(
        Equipamento.quantidade_total.desc(),
        Equipamento.id.desc()
    ).first()

    if not item:
        return "Ainda nao existem equipamentos cadastrados."

    return (
        "🏆 REGISTRO COM MAIS UNIDADES\n\n"
        + formatar_item(item)
    )


def resposta_cadastros_recentes(Equipamento):
    itens = Equipamento.query.order_by(
        Equipamento.id.desc()
    ).limit(10).all()

    if not itens:
        return "Ainda nao existem cadastros."

    linhas = ["📅 ULTIMOS EQUIPAMENTOS CADASTRADOS\n"]

    for item in itens:
        linhas.append(
            f"• ID {item.id}: "
            f"{item.tipo} | "
            f"{item.marca or '-'} "
            f"{item.modelo or '-'}\n"
            f"  Cadastro: {formatar_data(item.cadastro)}"
        )

    return "\n\n".join(linhas)


# ============================================================
# BUSCA POR IDENTIFICADORES
# ============================================================

def resposta_busca(pergunta, Equipamento):
    texto = normalizar(pergunta)

    palavras_ignorar = {
        "buscar", "busca", "pesquisar", "pesquisa",
        "procure", "procurar", "encontre", "encontrar",
        "localizar", "localize", "mostre", "mostrar",
        "equipamento", "equipamentos", "produto",
        "produtos", "roteador", "roteadores",
        "mac", "serial", "codigo", "modelo", "marca",
        "qual", "quais", "onde", "esta", "estao",
        "tem", "tenho", "temos", "me", "um", "uma",
        "o", "a", "os", "as", "de", "do", "da",
        "dos", "das", "no", "na", "por", "com",
        "pelo", "pela"
    }

    palavras = re.findall(
        r"[a-z0-9:_./-]+", texto
    )

    termos = [
        palavra for palavra in palavras
        if palavra not in palavras_ignorar
        and len(palavra) >= 2
    ][:5]

    if not termos:
        return (
            "🔎 Informe um MAC, serial, codigo, "
            "marca ou modelo.\n\n"
            "Exemplo: Buscar equipamento ABC123"
        )

    filtros = []

    for termo in termos:
        padrao = f"%{termo}%"

        filtros.extend([
            Equipamento.tipo.ilike(padrao),
            Equipamento.marca.ilike(padrao),
            Equipamento.modelo.ilike(padrao),
            Equipamento.mac.ilike(padrao),
            Equipamento.serial.ilike(padrao),
            Equipamento.codigo.ilike(padrao)
        ])

    consulta = Equipamento.query.filter(or_(*filtros))

    total = consulta.count()
    itens = consulta.order_by(
        Equipamento.id.desc()
    ).limit(10).all()

    if not itens:
        return (
            "🔎 Nao encontrei registros com "
            "esse identificador."
        )

    linhas = [
        f"🔎 ENCONTREI {total} REGISTRO(S)\n"
    ]

    for item in itens:
        linhas.append(formatar_item(item))

    if total > 10:
        linhas.append(
            "\nExibindo somente os 10 primeiros resultados."
        )

    return "\n\n".join(linhas)


# ============================================================
# HISTORICO DE MOVIMENTACOES
# ============================================================

def buscar_movimentacoes(Historico, filtro=None):
    consulta = Historico.query

    if filtro == "retiradas":
        consulta = consulta.filter(
            or_(
                Historico.acao.ilike("%retirad%"),
                Historico.acao.ilike("%saida%"),
                Historico.acao.ilike("%saída%")
            )
        )

    elif filtro == "devolucoes":
        consulta = consulta.filter(
            or_(
                Historico.acao.ilike("%devol%"),
                Historico.acao.ilike("%retorno%")
            )
        )

    elif filtro == "hoje":
        agora = datetime.now(FUSO)
        inicio_local = agora.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fim_local = inicio_local.replace(
            hour=23, minute=59, second=59,
            microsecond=999999
        )

        # Esta consulta pressupoe que Historico.data
        # usa timestamps UTC no banco.
        inicio_utc = inicio_local.astimezone(timezone.utc)
        fim_utc = fim_local.astimezone(timezone.utc)

        consulta = consulta.filter(
            Historico.data >= inicio_utc,
            Historico.data <= fim_utc
        )

    total = consulta.count()

    itens = consulta.order_by(
        Historico.data.desc(),
        Historico.id.desc()
    ).limit(LIMITE_LISTA).all()

    return total, itens


def resposta_movimentacoes(Historico, filtro=None):
    total, itens = buscar_movimentacoes(
        Historico, filtro
    )

    titulos = {
        None: "ULTIMAS MOVIMENTACOES",
        "retiradas": "ULTIMAS RETIRADAS",
        "devolucoes": "ULTIMAS DEVOLUCOES",
        "hoje": "MOVIMENTACOES DE HOJE"
    }

    titulo = titulos.get(filtro, "MOVIMENTACOES")

    if not itens:
        return f"📋 {titulo}\n\nNenhum registro encontrado."

    linhas = [
        f"📋 {titulo}\n",
        f"Registros encontrados: {total}\n"
    ]

    for item in itens:
        linhas.append(
            f"• {item.acao}\n"
            f"  Identificador: {item.mac or '-'}\n"
            f"  Usuario: {item.usuario or '-'}\n"
            f"  Data: {formatar_data(item.data)}"
        )

    if total > LIMITE_LISTA:
        linhas.append("\nExibindo lista parcial.")

    return "\n\n".join(linhas)


def resposta_usuario(pergunta, Historico):
    padrao = re.search(
        r"(?:usuario|funcionario|colaborador)\s+"
        r"([a-zA-Z0-9_.-]+)",
        normalizar(pergunta)
    )

    if not padrao:
        return (
            "👤 Informe o nome do funcionario.\n\n"
            "Exemplo: Movimentacoes do usuario Carlos"
        )

    nome = padrao.group(1)

    consulta = Historico.query.filter(
        Historico.usuario.ilike(f"%{nome}%")
    )

    total = consulta.count()

    itens = consulta.order_by(
        Historico.data.desc(),
        Historico.id.desc()
    ).limit(LIMITE_LISTA).all()

    if not itens:
        return (
            f"Nao encontrei movimentacoes do usuario {nome}."
        )

    linhas = [
        f"👤 MOVIMENTACOES DE {nome.upper()}\n",
        f"Total de registros: {total}\n"
    ]

    for item in itens:
        linhas.append(
            f"• {item.acao} | {item.mac or '-'}\n"
            f"  {formatar_data(item.data)}"
        )

    if total > LIMITE_LISTA:
        linhas.append("\nLista parcial.")

    return "\n\n".join(linhas)


# ============================================================
# CONHECIMENTOS BASICOS DE TELECOM
# ============================================================

CONHECIMENTOS = [
    (
        ("o que e um roteador", "para que serve roteador"),
        "🌐 Um roteador encaminha dados entre redes. "
        "Em residencias e empresas, ele costuma distribuir "
        "a conexao de internet para os dispositivos."
    ),
    (
        ("o que e um switch", "para que serve switch"),
        "🔌 Um switch conecta dispositivos dentro de "
        "uma rede local, permitindo a comunicacao entre eles."
    ),
    (
        ("o que e mac", "endereco mac", "mac address"),
        "🔎 MAC e um identificador de interface de rede. "
        "Ele e muito usado para identificar equipamentos."
    ),
    (
        ("o que e ip", "endereco ip"),
        "🌐 IP e o endereco logico utilizado para "
        "identificar e comunicar dispositivos em uma rede."
    ),
    (
        ("o que e dns", "para que serve dns"),
        "🌍 DNS traduz nomes de dominio, como exemplo.com, "
        "para enderecos IP utilizados na comunicacao."
    ),
    (
        ("o que e dhcp", "para que serve dhcp"),
        "⚙️ DHCP distribui automaticamente configuracoes "
        "de rede, como endereco IP, gateway e DNS."
    ),
    (
        ("o que e gateway", "gateway padrao"),
        "🚪 Gateway e o equipamento ou endereco utilizado "
        "como saida para outras redes, geralmente a internet."
    ),
    (
        ("o que e onu", "o que e ont", "onu e ont",
         "diferenca entre onu e ont"),
        "📡 ONU e ONT sao equipamentos terminais "
        "de redes opticas. Em muitos contextos, ONT "
        "designa o terminal instalado no cliente."
    ),
    (
        ("o que e fibra optica", "como funciona fibra"),
        "💡 Fibra optica transmite informacoes por sinais "
        "luminosos, oferecendo alta capacidade de transmissao."
    ),
    (
        ("cat5e", "cat6", "cabo de rede"),
        "🔌 Cat5e e Cat6 sao categorias de cabeamento "
        "de rede. O Cat6 tem especificacoes superiores "
        "de desempenho e interferencia, dependendo "
        "da instalacao e da distancia."
    ),
    (
        ("o que e lan", "rede lan"),
        "🏢 LAN e uma rede local, como a rede "
        "de uma casa, escritorio ou empresa."
    ),
    (
        ("o que e wan", "rede wan"),
        "🌎 WAN e uma rede de longa distancia, "
        "que interliga redes em diferentes locais."
    ),
    (
        ("o que e wifi", "o que e wi-fi"),
        "📶 Wi-Fi e uma tecnologia de rede sem fio "
        "que conecta dispositivos a uma rede local."
    ),
    (
        ("2.4 ghz", "5 ghz", "2,4 ghz"),
        "📶 Wi-Fi de 2,4 GHz geralmente oferece "
        "maior alcance, enquanto 5 GHz costuma "
        "permitir maiores velocidades em distancias "
        "menores, dependendo do ambiente."
    ),
    (
        ("o que e ping", "teste de ping"),
        "🏓 Ping e um teste que ajuda a verificar "
        "se um destino responde na rede e qual "
        "a latencia aproximada da comunicacao."
    ),
    (
        ("sem internet", "internet nao funciona",
         "roteador sem internet"),
        "🛠️ VERIFICACAO BASICA\n\n"
        "1. Confira energia e cabos.\n"
        "2. Verifique as luzes do equipamento.\n"
        "3. Teste outro dispositivo.\n"
        "4. Confira o status da conexao WAN.\n"
        "5. Verifique se existe falha no provedor.\n\n"
        "Evite restaurar o equipamento para o padrao "
        "de fabrica sem autorizacao."
    ),
    (
        ("luz los", "los vermelha", "los piscando"),
        "🔴 A luz LOS geralmente indica perda "
        "de sinal optico. Verifique o conector "
        "e a integridade da fibra, sem olhar "
        "diretamente para a extremidade optica."
    ),
    (
        ("luz pon", "pon piscando"),
        "🟢 PON e um indicador relacionado "
        "a conexao do equipamento com a rede optica. "
        "O significado exato depende do modelo."
    ),
    (
        ("o que e serial", "numero de serie"),
        "🏷️ O numero de serie identifica uma unidade "
        "especifica de um produto e ajuda no controle "
        "patrimonial e rastreamento."
    ),
    (
        ("o que e almoxarifado", "gestao de estoque"),
        "📦 Almoxarifado e a area responsavel "
        "por receber, armazenar, controlar "
        "e distribuir materiais e equipamentos."
    )
]


def resposta_conhecimento(texto):
    for gatilhos, resposta in CONHECIMENTOS:
        if contem(texto, *gatilhos):
            return resposta

    return None


# ============================================================
# CONVERSAS E RESPOSTAS
# ============================================================

def criar_resposta(
    pergunta,
    db,
    Equipamento,
    Historico,
    conversa=None
):
    original = str(pergunta or "").strip()
    texto = normalizar(original)

    if not texto:
        return "Digite uma pergunta para comecar."

    if len(original) > 2000:
        return "Sua pergunta ultrapassou 2.000 caracteres."

    # Saudacoes
    saudacoes = {
        "bom dia": "Bom dia! ☀️",
        "boa tarde": "Boa tarde! 🌤️",
        "boa noite": "Boa noite! 🌙",
        "ola": "Ola! 😄",
        "oi": "Opa! Tudo certo? 😄",
        "opa": "Opa, meu parceiro! 😄",
        "salve": "Salve! Tamo junto! 😎"
    }

    for gatilho, resposta in saudacoes.items():
        if re.search(
            rf"\b{re.escape(gatilho)}\b",
            texto
        ):
            return (
                f"{resposta}\n\n"
                "Sou a Estoque IA 3.0! "
                "Posso ajudar com o estoque e telecomunicacoes. "
                "O que vamos consultar hoje?"
            )

    if contem(
        texto,
        "tudo bem", "como voce esta", "como vai",
        "tudo certo"
    ):
        return (
            "Tudo certo por aqui! 😄\n\n"
            "Estou pronta para ajudar. "
            "Como esta o movimento no almoxarifado?"
        )

    if contem(
        texto,
        "obrigado", "obrigada", "valeu", "tmj"
    ):
        return (
            "Tamo junto! 😎📦\n\n"
            "Sempre que precisar, e so chamar."
        )

    if contem(
        texto,
        "quem e voce", "seu nome", "o que voce faz",
        "como pode ajudar", "ajuda", "comandos",
        "o que sabe fazer"
    ):
        return (
            "🤖 ESTOQUE IA 3.0\n\n"
            "Sou o assistente gratuito do Estoque Inteligente.\n\n"
            "Posso consultar:\n"
            "📦 Resumo do estoque\n"
            "🟢 Quantidades disponiveis\n"
            "🔴 Quantidades em uso\n"
            "📊 Produtos por tipo e marca\n"
            "⚠️ Estoque zerado ou baixo\n"
            "🔎 MAC, serial, modelo e codigo\n"
            "📋 Historico e movimentacoes\n"
            "👤 Movimentacoes por usuario\n"
            "📈 Percentuais de disponibilidade\n"
            "🌐 Duvidas basicas de telecom\n\n"
            "Funciono sem creditos da OpenAI."
        )

    # Conhecimentos tecnicos
    resposta_tecnica = resposta_conhecimento(texto)

    if resposta_tecnica:
        return resposta_tecnica

    # Historico especifico
    if contem(
        texto,
        "movimentacoes do usuario",
        "movimentacao do usuario",
        "movimentacoes do funcionario",
        "historico do usuario"
    ):
        return resposta_usuario(original, Historico)

    if contem(
        texto,
        "movimentacoes de hoje",
        "movimentacao de hoje",
        "o que aconteceu hoje",
        "historico de hoje"
    ):
        return resposta_movimentacoes(Historico, "hoje")

    if contem(
        texto,
        "ultimas retiradas",
        "retiradas recentes",
        "historico de retiradas"
    ):
        return resposta_movimentacoes(Historico, "retiradas")

    if contem(
        texto,
        "ultimas devolucoes",
        "devolucoes recentes",
        "historico de devolucoes"
    ):
        return resposta_movimentacoes(Historico, "devolucoes")

    if contem(
        texto,
        "movimentacoes", "movimentacao",
        "historico", "ultimas acoes"
    ):
        return resposta_movimentacoes(Historico)

    # Analises
    if contem(
        texto,
        "estoque zerado", "sem saldo",
        "produtos zerados", "esgotados",
        "quantidade zero"
    ):
        return resposta_zerados(Equipamento)

    if contem(
        texto,
        "estoque baixo", "poucas unidades",
        "acabando", "saldo baixo"
    ):
        return resposta_estoque_baixo(Equipamento)

    if contem(
        texto,
        "parcialmente em uso", "uso parcial"
    ):
        return resposta_parcialmente_em_uso(Equipamento)

    if contem(
        texto,
        "maior estoque", "mais unidades",
        "maior quantidade", "mais quantidade"
    ):
        return resposta_maior_estoque(Equipamento)

    if contem(
        texto,
        "ultimos cadastros", "cadastros recentes",
        "cadastrados recentemente",
        "ultimos equipamentos cadastrados"
    ):
        return resposta_cadastros_recentes(Equipamento)

    if contem(
        texto,
        "por marca", "estoque por marca",
        "marcas cadastradas"
    ):
        return resposta_por_marca(db, Equipamento)

    if contem(
        texto,
        "por tipo", "por categoria",
        "tipos de produtos", "tipos cadastrados",
        "quais produtos", "quais equipamentos"
    ):
        return resposta_por_tipo(db, Equipamento)

    if contem(
        texto,
        "porcentagem", "percentual",
        "percentagem", "por cento"
    ):
        return resposta_percentual(db, Equipamento)

    if contem(
        texto,
        "quantos registros",
        "registros cadastrados",
        "produtos diferentes",
        "quantos cadastros"
    ):
        return resposta_registros(db, Equipamento)

    # Busca por identificador
    if contem(
        texto,
        "buscar", "pesquisar", "procure",
        "procurar", "encontre", "localizar",
        "localize"
    ):
        return resposta_busca(original, Equipamento)

    # Consultas de saldo
    if contem(
        texto,
        "em uso", "em utilizacao",
        "quantos usados", "quantos retirados"
    ):
        return resposta_em_uso(db, Equipamento)

    if contem(
        texto,
        "disponiveis", "disponivel",
        "no saldo", "quantos sobraram",
        "quantidade em estoque"
    ):
        return resposta_disponiveis(db, Equipamento)

    if contem(
        texto,
        "total", "estoque", "inventario",
        "resumo", "quantos produtos",
        "quantos equipamentos"
    ):
        return resposta_resumo(db, Equipamento)

    return (
        "🤖 Ainda nao tenho uma resposta programada "
        "para essa pergunta.\n\n"
        "Mas posso ajudar com consultas de estoque, "
        "movimentacoes, equipamentos e duvidas "
        "basicas de telecomunicacoes.\n\n"
        "Digite 'ajuda' para conhecer minhas funcoes."
    )
