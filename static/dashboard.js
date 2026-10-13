
/* ==========================================
   ESTOQUE INTELIGENTE
   DASHBOARD + ESTOQUE PREMIUM
   PAGINACAO DE 50 EQUIPAMENTOS
========================================== */

"use strict";

(() => {

    const INTERVALO_ATUALIZACAO = 5000;
    const FUSO = "America/Sao_Paulo";
    const ITENS_POR_PAGINA = 50;

    const MESES = [
        "Janeiro", "Fevereiro", "Março",
        "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro",
        "Outubro", "Novembro", "Dezembro"
    ];

    const SEMANA = [
        "Dom", "Seg", "Ter", "Qua",
        "Qui", "Sex", "Sáb"
    ];

    const dataInicial = new Date();

    const partesData = new Intl.DateTimeFormat(
        "en-US",
        {
            timeZone: FUSO,
            year: "numeric",
            month: "numeric",
            day: "numeric"
        }
    ).formatToParts(dataInicial);

    const obterParte = nome => Number(
        partesData.find(parte => parte.type === nome)?.value || 0
    );

    const HOJE_ANO = obterParte("year");
    const HOJE_MES = obterParte("month");
    const HOJE_DIA = obterParte("day");

    let calendarioAno = HOJE_ANO;
    let calendarioMes = HOJE_MES;

    let atualizando = false;
    let carregandoCalendario = false;
    let calendarioVersao = 0;

    let paginaAtual = 1;
    let totalPaginas = 1;
    let totalRegistros = 0;
    let buscaAplicada = "";

    let estoquePendente = null;
    let atualizacaoSolicitada = false;
    let ultimaRequisicaoEstoque = 0;

    // ======================================
    // FUNCOES AUXILIARES
    // ======================================

    function elemento(id) {
        return document.getElementById(id);
    }

    function definirTexto(id, valor) {
        const alvo = elemento(id);

        if (alvo) {
            alvo.textContent = String(valor);
        }
    }

    function formatarNumero(numero) {
        return new Intl.NumberFormat("pt-BR").format(
            Number(numero) || 0
        );
    }

    function formatarHora() {
        return new Intl.DateTimeFormat(
            "pt-BR",
            {
                timeZone: FUSO,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        ).format(new Date());
    }

    function formatarDataAtual() {
        return new Intl.DateTimeFormat(
            "pt-BR",
            {
                timeZone: FUSO,
                weekday: "long",
                day: "2-digit",
                month: "long",
                year: "numeric"
            }
        ).format(new Date());
    }

    function normalizar(valor) {
        return String(valor || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase();
    }

    async function buscarJSON(url) {
        const resposta = await fetch(
            url,
            {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    "Accept": "application/json"
                }
            }
        );

        if (!resposta.ok) {
            throw new Error(
                "Erro HTTP: " + resposta.status
            );
        }

        const tipo = resposta.headers.get(
            "content-type"
        ) || "";

        if (!tipo.includes("application/json")) {
            throw new Error(
                "A resposta não é JSON. Verifique o login."
            );
        }

        return resposta.json();
    }

    function criarElemento(tag, classe = "", texto = null) {
        const novo = document.createElement(tag);

        if (classe) {
            novo.className = classe;
        }

        if (texto !== null && texto !== undefined) {
            novo.textContent = String(texto);
        }

        return novo;
    }

    // ======================================
    // CONEXAO
    // ======================================

    function definirConexao(conectado) {
        const status = elemento("dash-status");

        if (!status) {
            return;
        }

        status.textContent = conectado
            ? "● Ao vivo"
            : "● Sem conexão";

        status.classList.toggle(
            "offline",
            !conectado
        );
    }

    // ======================================
    // INDICADORES DO DASHBOARD
    // ======================================

    function atualizarIndicadores(dados) {
        const total = Number(dados.total) || 0;
        const saldo = Number(dados.saldo) || 0;
        const uso = Number(dados.uso) || 0;
        const produtos = Number(dados.produtos) || 0;

        definirTexto("dash-total", formatarNumero(total));
        definirTexto("dash-saldo", formatarNumero(saldo));
        definirTexto("dash-uso", formatarNumero(uso));
        definirTexto("dash-produtos", formatarNumero(produtos));

        definirTexto(
            "dash-legenda-saldo",
            formatarNumero(saldo)
        );

        definirTexto(
            "dash-legenda-uso",
            formatarNumero(uso)
        );

        const percentual = total > 0
            ? Math.max(
                0,
                Math.min(100, saldo / total * 100)
            )
            : 0;

        definirTexto(
            "dash-percentual",
            percentual.toLocaleString(
                "pt-BR",
                { maximumFractionDigits: 1 }
            ) + "%"
        );

        const grafico = elemento("dash-rosca");

        if (grafico) {
            grafico.style.background = total === 0
                ? "#e5eaf1"
                : `conic-gradient(
                    #15975c 0% ${percentual}%,
                    #df4545 ${percentual}% 100%
                )`;
        }
    }

    // ======================================
    // ULTIMAS MOVIMENTACOES
    // ======================================

    function iconeMovimentacao(acao) {
        const valor = normalizar(acao);

        if (
            valor.includes("retirada") ||
            valor.includes("retirado")
        ) {
            return "📤";
        }

        if (valor.includes("devolu")) {
            return "📥";
        }

        if (
            valor.includes("cadastro") ||
            valor.includes("cadastrado")
        ) {
            return "📦";
        }

        return "🔄";
    }

    function atualizarMovimentacoes(movimentacoes) {
        const lista = elemento("dash-movimentacoes");

        if (!lista) {
            return;
        }

        lista.replaceChildren();

        if (
            !Array.isArray(movimentacoes) ||
            movimentacoes.length === 0
        ) {
            lista.appendChild(
                criarElemento(
                    "p",
                    "",
                    "Nenhuma movimentação registrada ainda."
                )
            );

            return;
        }

        movimentacoes.forEach(movimento => {
            const linha = criarElemento(
                "div",
                "dash-movimento"
            );

            const icone = criarElemento(
                "div",
                "dash-movimento-icone",
                iconeMovimentacao(movimento.acao)
            );

            const conteudo = criarElemento(
                "div",
                "dash-movimento-conteudo"
            );

            const titulo = criarElemento(
                "strong",
                "",
                movimento.acao || "Movimentação"
            );

            const descricao = criarElemento(
                "span",
                "",
                (
                    movimento.identificador || "-"
                ) + " • " + (
                    movimento.usuario || "-"
                )
            );

            const data = criarElemento(
                "span",
                "dash-movimento-data",
                movimento.data || "-"
            );

            conteudo.append(titulo, descricao);

            linha.append(icone, conteudo, data);

            lista.appendChild(linha);
        });
    }

    // ======================================
    // ESTOQUE PREMIUM
    // ======================================

    function criarCelula(linha, classe = "") {
        const celula = document.createElement("td");

        if (classe) {
            celula.className = classe;
        }

        linha.appendChild(celula);

        return celula;
    }

    function criarBotaoMovimentacao(
        acao,
        texto,
        classe
    ) {
        const botao = criarElemento(
            "button",
            classe,
            texto
        );

        botao.type = "submit";
        botao.name = "acao";
        botao.value = acao;

        return botao;
    }

    function criarLinhaEstoque(item) {
        const saldo = Math.max(
            0,
            Number(item.quantidade) || 0
        );

        const emUso = Math.max(
            0,
            Number(item.em_uso) || 0
        );

        const unidade = item.unidade || "un";

        const linha = document.createElement("tr");

        linha.dataset.estoqueId = String(item.id);

        linha.className = saldo === 0
            ? "linha-uso"
            : "linha-saldo";

        // PRODUTO

        const produto = criarCelula(linha);

        const caixaProduto = criarElemento(
            "div",
            "ep-product"
        );

        caixaProduto.appendChild(
            criarElemento(
                "span",
                "ep-product-icon",
                "📦"
            )
        );

        const informacoes = criarElemento("div");

        informacoes.appendChild(
            criarElemento(
                "strong",
                "",
                item.tipo || "-"
            )
        );

        const marcaModelo = [
            item.marca,
            item.modelo
        ].filter(Boolean).join(" ");

        informacoes.appendChild(
            criarElemento(
                "small",
                "",
                marcaModelo
            )
        );

        caixaProduto.appendChild(informacoes);
        produto.appendChild(caixaProduto);

        // IDENTIFICADOR COPIAVEL

        const identificador = criarCelula(linha);

        const botaoCopiar = criarElemento(
            "button",
            "ep-copy"
        );

        botaoCopiar.type = "button";
        botaoCopiar.title = "Copiar identificador";

        botaoCopiar.appendChild(
            criarElemento(
                "code",
                "",
                item.identificador ||
                item.mac ||
                item.serial ||
                item.codigo ||
                ("ID-" + item.id)
            )
        );

        botaoCopiar.appendChild(
            criarElemento(
                "span",
                "",
                "⧉"
            )
        );

        identificador.appendChild(botaoCopiar);

        // DATAS

        criarCelula(linha).textContent =
            item.chegada || "-";

        criarCelula(linha).textContent =
            item.cadastro || "-";

        criarCelula(linha).textContent =
            item.cadastrado_por || "-";

        // DISPONIVEL

        const celulaSaldo = criarCelula(
            linha,
            "verde-texto"
        );

        celulaSaldo.appendChild(
            criarElemento(
                "strong",
                "",
                `${formatarNumero(saldo)} ${unidade}`
            )
        );

        // EM USO

        const celulaUso = criarCelula(
            linha,
            "vermelho-texto"
        );

        celulaUso.appendChild(
            criarElemento(
                "strong",
                "",
                `${formatarNumero(emUso)} ${unidade}`
            )
        );

        // SITUACAO

        const celulaSituacao = criarCelula(linha);

        let situacao = "Disponível";
        let classeSituacao = "status saldo";

        if (saldo === 0) {
            situacao = "Sem saldo";
            classeSituacao = "status uso";
        } else if (emUso > 0) {
            situacao = "Saldo parcial";
        }

        celulaSituacao.appendChild(
            criarElemento(
                "span",
                classeSituacao,
                "● " + situacao
            )
        );

        // MOVIMENTACAO

        const celulaMovimento = criarCelula(linha);

        const formulario = document.createElement(
            "form"
        );

        formulario.method = "POST";
        formulario.action =
            `/status/${encodeURIComponent(item.id)}`;

        formulario.className = "movimentacao";

        const quantidade = document.createElement(
            "input"
        );

        quantidade.type = "number";
        quantidade.name = "quantidade";
        quantidade.min = "1";
        quantidade.step = "1";
        quantidade.value = "1";
        quantidade.required = true;
        quantidade.setAttribute(
            "aria-label",
            "Quantidade a movimentar"
        );

        formulario.appendChild(quantidade);

        if (saldo > 0) {
            formulario.appendChild(
                criarBotaoMovimentacao(
                    "retirar",
                    "↗ Retirar",
                    "btn-uso"
                )
            );
        }

        if (emUso > 0) {
            formulario.appendChild(
                criarBotaoMovimentacao(
                    "devolver",
                    "↙ Devolver",
                    "btn-saldo"
                )
            );
        }

        celulaMovimento.appendChild(formulario);

        return linha;
    }

    // ======================================
    // PROTEGER EDICAO E CONFIRMACAO
    // ======================================

    function estoqueEstaSendoEditado() {
        const corpo = elemento("estoque-corpo");
        const modal = elemento("ep-modal");

        if (!corpo) {
            return false;
        }

        if (modal && !modal.hidden) {
            return true;
        }

        if (
            document.activeElement &&
            corpo.contains(document.activeElement)
        ) {
            return true;
        }

        return false;
    }

    // ======================================
    // PAGINACAO DO ESTOQUE
    // ======================================

    function garantirControlesPaginacao() {
        let painel = elemento("ep-paginacao");

        if (painel) {
            return painel;
        }

        const corpo = elemento("estoque-corpo");

        if (!corpo) {
            return null;
        }

        const tabela = corpo.closest("table");

        if (!tabela) {
            return null;
        }

        painel = criarElemento(
            "div",
            "ep-paginacao",
        );

        painel.id = "ep-paginacao";

        painel.style.cssText = [
            "display:flex",
            "justify-content:space-between",
            "align-items:center",
            "gap:12px",
            "flex-wrap:wrap",
            "padding:16px 4px"
        ].join(";");

        const informacao = criarElemento(
            "span",
            "",
            "Carregando registros..."
        );

        informacao.id = "ep-paginacao-info";

        const acoes = criarElemento(
            "div",
            "ep-paginacao-acoes"
        );

        acoes.style.cssText = [
            "display:flex",
            "align-items:center",
            "gap:8px",
            "flex-wrap:wrap"
        ].join(";");

        const anterior = criarElemento(
            "button",
            "ep-paginacao-btn",
            "← Anterior"
        );

        anterior.id = "ep-pagina-anterior";
        anterior.type = "button";

        const numero = criarElemento(
            "span",
            "",
            "Página 1 de 1"
        );

        numero.id = "ep-paginacao-numero";

        const proxima = criarElemento(
            "button",
            "ep-paginacao-btn",
            "Próxima →"
        );

        proxima.id = "ep-pagina-proxima";
        proxima.type = "button";

        [anterior, proxima].forEach(botao => {
            botao.style.cssText = [
                "border:1px solid #dbe3ef",
                "background:white",
                "border-radius:10px",
                "padding:10px 14px",
                "font-weight:700",
                "cursor:pointer"
            ].join(";");
        });

        numero.style.cssText = [
            "font-size:13px",
            "font-weight:700",
            "color:#475569"
        ].join(";");

        acoes.append(anterior, numero, proxima);
        painel.append(informacao, acoes);

        const areaTabela = tabela.parentElement;

        if (areaTabela) {
            areaTabela.insertAdjacentElement(
                "afterend",
                painel
            );
        }

        return painel;
    }

    function atualizarControlesPaginacao() {
        garantirControlesPaginacao();

        const inicio = totalRegistros === 0
            ? 0
            : (paginaAtual - 1) * ITENS_POR_PAGINA + 1;

        const fim = Math.min(
            paginaAtual * ITENS_POR_PAGINA,
            totalRegistros
        );

        definirTexto(
            "ep-paginacao-info",
            `Exibindo ${formatarNumero(inicio)} a ` +
            `${formatarNumero(fim)} de ` +
            `${formatarNumero(totalRegistros)} equipamentos`
        );

        definirTexto(
            "ep-paginacao-numero",
            `Página ${formatarNumero(paginaAtual)} de ` +
            `${formatarNumero(Math.max(1, totalPaginas))}`
        );

        const anterior = elemento("ep-pagina-anterior");
        const proxima = elemento("ep-pagina-proxima");

        if (anterior) {
            anterior.disabled = paginaAtual <= 1;
            anterior.style.opacity = anterior.disabled
                ? "0.45"
                : "1";
            anterior.style.cursor = anterior.disabled
                ? "not-allowed"
                : "pointer";
        }

        if (proxima) {
            proxima.disabled = paginaAtual >= totalPaginas;
            proxima.style.opacity = proxima.disabled
                ? "0.45"
                : "1";
            proxima.style.cursor = proxima.disabled
                ? "not-allowed"
                : "pointer";
        }
    }

    function mudarPagina(novaPagina) {
        const destino = Number(novaPagina);

        if (
            !Number.isInteger(destino) ||
            destino < 1 ||
            destino > Math.max(1, totalPaginas) ||
            destino === paginaAtual
        ) {
            return;
        }

        paginaAtual = destino;
        atualizarControlesPaginacao();
        solicitarAtualizacao();
    }

    function configurarPaginacao() {
        garantirControlesPaginacao();

        document.addEventListener("click", evento => {
            const anterior = evento.target.closest(
                "#ep-pagina-anterior"
            );

            if (anterior) {
                mudarPagina(paginaAtual - 1);
                return;
            }

            const proxima = evento.target.closest(
                "#ep-pagina-proxima"
            );

            if (proxima) {
                mudarPagina(paginaAtual + 1);
            }
        });

        atualizarControlesPaginacao();
    }

    // ======================================
    // ATUALIZAR TABELA
    // ======================================

    function atualizarTabela(itens, metadados = {}) {
        const corpo = elemento("estoque-corpo");

        if (!corpo || !Array.isArray(itens)) {
            return;
        }

        if (estoqueEstaSendoEditado()) {
            estoquePendente = {
                itens,
                metadados
            };
            return;
        }

        estoquePendente = null;

        const fragmento = document.createDocumentFragment();

        if (itens.length === 0) {
            const linha = document.createElement("tr");

            const celula = criarCelula(
                linha,
                "vazio"
            );

            celula.textContent =
                "Nenhum produto encontrado.";

            celula.colSpan = 9;

            fragmento.appendChild(linha);
        } else {
            itens.forEach(item => {
                fragmento.appendChild(
                    criarLinhaEstoque(item)
                );
            });
        }

        corpo.replaceChildren(fragmento);

        paginaAtual = Number(
            metadados.pagina_atual ??
            metadados.pagina ??
            paginaAtual
        ) || 1;

        totalPaginas = Number(
            metadados.total_paginas
        ) || 0;

        totalRegistros = Number(
            metadados.total_registros
        ) || 0;

        atualizarControlesPaginacao();

        document.dispatchEvent(
            new CustomEvent("estoque:atualizado", {
                detail: {
                    quantidade: itens.length,
                    pagina: paginaAtual,
                    totalPaginas,
                    totalRegistros,
                    busca: buscaAplicada
                }
            })
        );
    }

    function aplicarEstoquePendente() {
        if (
            estoquePendente &&
            !estoqueEstaSendoEditado()
        ) {
            const pendente = estoquePendente;

            estoquePendente = null;

            atualizarTabela(
                pendente.itens,
                pendente.metadados
            );
        }
    }

    // ======================================
    // CALENDARIO
    // ======================================

    function chaveData(ano, mes, dia) {
        return (
            String(ano) + "-" +
            String(mes).padStart(2, "0") + "-" +
            String(dia).padStart(2, "0")
        );
    }

    function renderizarCalendario(movimentacoes) {
        const grade = elemento("dash-dias");

        if (!grade) {
            return;
        }

        definirTexto(
            "dash-mes",
            `${MESES[calendarioMes - 1]} ${calendarioAno}`
        );

        grade.replaceChildren();

        SEMANA.forEach(dia => {
            grade.appendChild(
                criarElemento(
                    "div",
                    "dash-dia-semana",
                    dia
                )
            );
        });

        const primeiroDia = new Date(
            Date.UTC(
                calendarioAno,
                calendarioMes - 1,
                1
            )
        ).getUTCDay();

        const quantidadeDias = new Date(
            Date.UTC(
                calendarioAno,
                calendarioMes,
                0
            )
        ).getUTCDate();

        for (let i = 0; i < primeiroDia; i++) {
            grade.appendChild(
                criarElemento(
                    "div",
                    "dash-dia vazio"
                )
            );
        }

        for (
            let dia = 1;
            dia <= quantidadeDias;
            dia++
        ) {
            const chave = chaveData(
                calendarioAno,
                calendarioMes,
                dia
            );

            const quantidade = Number(
                movimentacoes[chave]
            ) || 0;

            const ehHoje = (
                calendarioAno === HOJE_ANO &&
                calendarioMes === HOJE_MES &&
                dia === HOJE_DIA
            );

            const classes = ["dash-dia"];

            if (ehHoje) {
                classes.push("hoje");
            }

            if (quantidade > 0) {
                classes.push("com-movimento");
            }

            const caixa = criarElemento(
                "div",
                classes.join(" ")
            );

            caixa.appendChild(
                criarElemento(
                    "span",
                    "",
                    dia
                )
            );

            if (quantidade > 0) {
                caixa.appendChild(
                    criarElemento(
                        "small",
                        "",
                        quantidade + " mov."
                    )
                );

                caixa.title =
                    `${quantidade} movimentação(ões) em ` +
                    `${dia}/${calendarioMes}/${calendarioAno}`;
            }

            grade.appendChild(caixa);
        }
    }

    async function carregarCalendario() {
        if (carregandoCalendario) {
            return;
        }

        carregandoCalendario = true;

        const versao = ++calendarioVersao;
        const anoSolicitado = calendarioAno;
        const mesSolicitado = calendarioMes;

        try {
            const parametros = new URLSearchParams({
                ano: String(anoSolicitado),
                mes: String(mesSolicitado)
            });

            const dados = await buscarJSON(
                "/api/calendario?" + parametros.toString()
            );

            if (
                versao !== calendarioVersao ||
                anoSolicitado !== calendarioAno ||
                mesSolicitado !== calendarioMes
            ) {
                return;
            }

            renderizarCalendario(
                dados.movimentacoes_por_dia || {}
            );

            definirTexto(
                "dash-cal-info",
                `${formatarNumero(dados.total_movimentacoes)} ` +
                "movimentação(ões) neste mês."
            );

        } catch (erro) {
            console.error(
                "Erro ao carregar calendário:",
                erro
            );

            definirTexto(
                "dash-cal-info",
                "Não foi possível atualizar o calendário."
            );

        } finally {
            carregandoCalendario = false;
        }
    }

    function mudarMes(diferenca) {
        const data = new Date(
            Date.UTC(
                calendarioAno,
                calendarioMes - 1 + diferenca,
                1
            )
        );

        calendarioAno = data.getUTCFullYear();
        calendarioMes = data.getUTCMonth() + 1;

        calendarioVersao++;

        carregarCalendario();
    }

    function configurarCalendario() {
        const anterior = elemento("dash-anterior");
        const proximo = elemento("dash-proximo");
        const hoje = elemento("dash-hoje");

        anterior?.addEventListener(
            "click",
            () => mudarMes(-1)
        );

        proximo?.addEventListener(
            "click",
            () => mudarMes(1)
        );

        hoje?.addEventListener(
            "click",
            () => {
                calendarioAno = HOJE_ANO;
                calendarioMes = HOJE_MES;

                calendarioVersao++;
                carregarCalendario();
            }
        );
    }

    // ======================================
    // BUSCA
    // ======================================

    function configurarBusca() {
        const formulario = elemento("form-busca");

        if (!formulario) {
            return;
        }

        formulario.addEventListener(
            "submit",
            evento => {
                evento.preventDefault();

                const campo = elemento("busca");

                buscaAplicada = campo
                    ? campo.value.trim()
                    : "";

                paginaAtual = 1;
                estoquePendente = null;

                const url = new URL(
                    window.location.href
                );

                if (buscaAplicada) {
                    url.searchParams.set(
                        "busca",
                        buscaAplicada
                    );
                } else {
                    url.searchParams.delete(
                        "busca"
                    );
                }

                window.history.replaceState(
                    {},
                    "",
                    url
                );

                solicitarAtualizacao();
            }
        );
    }

    // ======================================
    // ATUALIZACAO GERAL
    // ======================================

    function solicitarAtualizacao() {
        if (atualizando) {
            atualizacaoSolicitada = true;
            return;
        }

        atualizarDashboard();
    }

    async function atualizarDashboard() {
        if (atualizando || document.hidden) {
            return;
        }

        atualizando = true;
        atualizacaoSolicitada = false;

        const buscaSolicitada = buscaAplicada;
        const paginaSolicitada = paginaAtual;
        const versaoSolicitada = ++ultimaRequisicaoEstoque;

        try {
            const parametros = new URLSearchParams({
                pagina: String(paginaSolicitada),
                por_pagina: String(ITENS_POR_PAGINA)
            });

            if (buscaSolicitada) {
                parametros.set(
                    "busca",
                    buscaSolicitada
                );
            }

            const urlEstoque =
                "/api/estoque?" + parametros.toString();

            const [dashboard, estoque] = await Promise.all([
                buscarJSON("/api/dashboard"),
                buscarJSON(urlEstoque)
            ]);

            atualizarIndicadores(dashboard);

            atualizarMovimentacoes(
                dashboard.movimentacoes || []
            );

            const requisicaoAindaAtual = (
                versaoSolicitada === ultimaRequisicaoEstoque &&
                buscaSolicitada === buscaAplicada &&
                paginaSolicitada === paginaAtual
            );

            if (requisicaoAindaAtual) {
                atualizarTabela(
                    estoque.itens || [],
                    estoque
                );
            }

            definirTexto(
                "dash-data",
                formatarDataAtual()
            );

            definirTexto(
                "dash-ultima",
                "Atualizado às " + formatarHora()
            );

            definirConexao(true);

            await carregarCalendario();

        } catch (erro) {
            console.error(
                "Erro ao atualizar Dashboard:",
                erro
            );

            definirConexao(false);

            definirTexto(
                "dash-ultima",
                "Falha na atualização automática."
            );

        } finally {
            atualizando = false;

            if (atualizacaoSolicitada && !document.hidden) {
                atualizacaoSolicitada = false;
                atualizarDashboard();
            }
        }
    }

    // ======================================
    // INICIALIZACAO
    // ======================================

    function iniciarDashboard() {
        if (!elemento("dashboard-vivo")) {
            return;
        }

        const campoBusca = elemento("busca");

        const parametrosIniciais = new URLSearchParams(
            window.location.search
        );

        buscaAplicada = parametrosIniciais.get("busca") || "";

        if (campoBusca && !campoBusca.value) {
            campoBusca.value = buscaAplicada;
        }

        configurarCalendario();
        configurarBusca();
        configurarPaginacao();

        definirTexto(
            "dash-data",
            formatarDataAtual()
        );

        atualizarDashboard();

        window.setInterval(
            () => {
                aplicarEstoquePendente();
                solicitarAtualizacao();
            },
            INTERVALO_ATUALIZACAO
        );

        document.addEventListener(
            "visibilitychange",
            () => {
                if (!document.hidden) {
                    aplicarEstoquePendente();
                    solicitarAtualizacao();
                }
            }
        );

        document.addEventListener(
            "focusout",
            () => {
                window.setTimeout(
                    aplicarEstoquePendente,
                    100
                );
            }
        );

        document.addEventListener(
            "estoque:atualizado",
            () => {
                console.debug(
                    "Estoque Premium atualizado."
                );
            }
        );
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            iniciarDashboard
        );
    } else {
        iniciarDashboard();
    }

})();


  
