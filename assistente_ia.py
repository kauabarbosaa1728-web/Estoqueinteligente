
import os
import re
from datetime import datetime, timezone
from decimal import Decimal

from openai import OpenAI


def criar_resposta(pergunta, db, Equipamento, Historico):
    pergunta = (pergunta or "").strip()

    if not pergunta:
        return "Digite uma pergunta para começar."

    if len(pergunta) > 2000:
        return "Sua pergunta é muito longa. Use até 2.000 caracteres."

    # Consultas somente de leitura.
    # A IA não pode alterar equipamentos nem movimentações.

    produtos = Equipamento.query.order_by(
        Equipamento.id.desc()
    ).limit(1000).all()

    registros = Historico.query.order_by(
        Historico.id.desc()
    ).limit(100).all()

    total = sum(
        int(p.quantidade_total or 0) for p in produtos
    )

    saldo = sum(
        int(p.quantidade or 0) for p in produtos
    )

    uso = total - saldo

    dados_produtos = []

    for p in produtos:
        dados_produtos.append({
            "nome": p.tipo,
            "marca": p.marca,
            "modelo": p.modelo,
            "mac": p.mac,
            "serial": p.serial,
            "codigo": p.codigo,
            "quantidade_disponivel": p.quantidade,
            "quantidade_total": p.quantidade_total,
            "unidade": p.unidade,
            "status": p.status,
            "data_chegada": str(p.chegada),
            "cadastrado_por": p.cadastrado_por
        })

    dados_historico = []

    for r in registros:
        dados_historico.append({
            "identificador": r.mac,
            "acao": r.acao,
            "usuario": r.usuario,
            "data": str(r.data)
        })

    # Respostas locais para perguntas gerais de saldo.
    texto = pergunta.lower()

    if texto in (
        "quantos equipamentos temos?",
        "quantos produtos temos?",
        "qual o total do estoque?"
    ):
        return (
            f"Existem {total} unidades cadastradas, "
            f"{saldo} disponíveis e {uso} em uso."
        )

    chave = os.environ.get("OPENAI_API_KEY")

    if not chave:
        return (
            f"Resumo do estoque: {total} unidades cadastradas, "
            f"{saldo} no saldo e {uso} em uso. "
            "Para responder perguntas mais complexas, "
            "configure OPENAI_API_KEY no Render."
        )

    cliente = OpenAI(api_key=chave)

    # Limita o tamanho do contexto enviado ao modelo.
    import json

    contexto = json.dumps({
        "resumo": {
            "total": total,
            "disponiveis": saldo,
            "em_uso": uso
        },
        "produtos": dados_produtos,
        "historico_recente": dados_historico
    }, ensure_ascii=False, default=str)

    resposta = cliente.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=(
            "Você é o Assistente IA do Estoque Inteligente, "
            "um sistema empresarial de controle de materiais "
            "e equipamentos de telecomunicações. "
            "Responda em português brasileiro, com clareza. "
            "Use os dados fornecidos para responder perguntas "
            "sobre estoque. Não invente equipamentos, MACs, "
            "seriais, quantidades, datas ou movimentações. "
            "Se os dados forem insuficientes, informe isso. "
            "O histórico enviado é parcial e a lista de "
            "produtos é limitada a 1000 registros. "
            "Não afirme que uma consulta parcial representa "
            "necessariamente todo o banco. "
            "Você não pode alterar dados do estoque. "
            "Para perguntas gerais de telecomunicações, "
            "explique de forma útil e objetiva."
        ),
        input=(
            "DADOS DO ESTOQUE:\n"
            + contexto
            + "\n\nPERGUNTA DO FUNCIONÁRIO:\n"
            + pergunta
        ),
        max_output_tokens=700
    )

    return resposta.output_text or "Não consegui gerar uma resposta."
