
/* ==========================================
   ESTOQUE INTELIGENTE
   DASHBOARD AO VIVO
========================================== */

"use strict";

(() => {

    // ======================================
    // CONFIGURACOES
    // ======================================

    const INTERVALO_ATUALIZACAO = 5000;

    const FUSO = "America/Sao_Paulo";

    const MESES = [
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro"
    ];

    const SEMANA = [
        "Dom",
        "Seg",
        "Ter",
        "Qua",
        "Qui",
        "Sex",
        "Sáb"
    ];

    const agora = new Date();

    const partesData = new Intl.DateTimeFormat(
        "en-US",
        {
            timeZone: FUSO,
            year: "numeric",
            month: "numeric",
            day: "numeric"
        }
    ).formatToParts(agora);

    const obterParte = (nome) => {
        return Number(
            partesData.find(
                (parte) => parte.type === nome
            )?.value || 0
        );
    };

    const HOJE_ANO = obterParte("year");
    const HOJE_MES = obterParte("month");
    const HOJE_DIA = obterParte("day");

    let calendarioAno = HOJE_ANO;
    let calendarioMes = HOJE_MES;

    let atualizando = false;
    let carregandoCalendario = false;
    let calendarioVersao = 0;


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
        return new Intl.NumberFormat(
            "pt-BR"
        ).format(Number(numero) || 0);
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

    function criarElemento(tag, classe, texto) {
        const novo = document.createElement(tag);

        if (classe) {
            novo.className = classe;
        }

        if (
            texto !== undefined &&
            texto !== null
        ) {
            novo.textContent = String(texto);
        }

        return novo;
    }


    // ======================================
    // STATUS DA CONEXAO
    // ======================================

    function definirConexao(conectado) {
        const status = elemento("dash-status");

        if (!status) {
            return;
        }

        if (conectado) {
            status.textContent = "● Ao vivo";
            status.classList.remove("offline");
        } else {
            status.textContent = "● Sem conexão";
            status.classList.add("offline");
        }
    }


    // ======================================
    // ATUALIZAR INDICADORES
    // ======================================

    function atualizarIndicadores(dados) {
        const total = Number(dados.total) || 0;
        const saldo = Number(dados.saldo) || 0;
        const uso = Number(dados.uso) || 0;
        const produtos = Number(dados.produtos) || 0;

        definirTexto(
            "dash-total",
            formatarNumero(total)
        );

        definirTexto(
            "dash-saldo",
            formatarNumero(saldo)
        );

        definirTexto(
            "dash-uso",
            formatarNumero(uso)
        );

        definirTexto(
            "dash-produtos",
            formatarNumero(produtos)
        );

        definirTexto(
            "dash-legenda-saldo",
            formatarNumero(saldo)
        );

        definirTexto(
            "dash-legenda-uso",
            formatarNumero(uso)
        );

        let percentual = 0;

        if (total > 0) {
            percentual = (saldo / total) * 100;
        }

        percentual = Math.max(
            0,
            Math.min(100, percentual)
        );

        definirTexto(
            "dash-percentual",
            percentual.toLocaleString(
                "pt-BR",
                {
                    maximumFractionDigits: 1
                }
            ) + "%"
        );

        const grafico = elemento("dash-rosca");

        if (grafico) {
            if (total === 0) {
                grafico.style.background = "#e5eaf1";
            } else {
                grafico.style.background =
                    `conic-gradient(
                        #15975c 0% ${percentual}%,
                        #df4545 ${percentual}% 100%
                    )`;
            }
        }
    }


    // ======================================
    // ULTIMAS MOVIMENTACOES
    // ======================================

    function iconeMovimentacao(acao) {
        const texto = String(
            acao || ""
        ).toLowerCase();

        if (texto.includes("retirada")) {
            return "📤";
        }

        if (texto.includes("devolu")) {
            return "📥";
        }

        if (texto.includes("cadastro") ||
            texto.includes("cadastrado")) {
            return "📦";
        }

        return "🔄";
    }

    function atualizarMovimentacoes(movimentacoes) {
        const lista = elemento(
            "dash-movimentacoes"
        );

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

        movimentacoes.forEach((movimento) => {

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

            conteudo.appendChild(titulo);
            conteudo.appendChild(descricao);

            linha.appendChild(icone);
            linha.appendChild(conteudo);
            linha.appendChild(data);

            lista.appendChild(linha);
        });
    }


    // ======================================
    // ATUALIZAR TABELA DE ESTOQUE
    // ======================================

    function criarCelula(linha, texto, classe) {
        const celula = document.createElement("td");

        if (classe) {
            celula.className = classe;
        }

        if (
            texto !== undefined &&
            texto !== null
        ) {
            celula.textContent = String(texto);
        }

        linha.appendChild(celula);

        return celula;
    }

    function criarBotaoMovimentacao(
        acao,
        texto,
        classe
    ) {
        const botao = document.createElement(
            "button"
        );

        botao.type = "submit";
        botao.name = "acao";
        botao.value = acao;
        botao.className = classe;
        botao.textContent = texto;

        return botao;
    }

    function criarLinhaEstoque(item) {
        const saldo = Number(
            item.quantidade
        ) || 0;

        const emUso = Number(
            item.em_uso
        ) || 0;

        const unidade = item.unidade || "un";

        const linha = document.createElement("tr");

        linha.className = saldo === 0
            ? "linha-uso"
            : "linha-saldo";

        // PRODUTO

        const produto = criarCelula(
            linha,
            ""
        );

        produto.appendChild(
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

        produto.appendChild(
            criarElemento(
                "small",
                "",
                marcaModelo
            )
        );

        // IDENTIFICADOR

        const identificador = criarCelula(
            linha,
            ""
        );

        identificador.appendChild(
            criarElemento(
                "code",
                "",
                item.identificador || "-"
            )
        );

        // DATAS E RESPONSAVEL

        criarCelula(
            linha,
            item.chegada || "-"
        );

        criarCelula(
            linha,
            item.cadastro || "-"
        );

        criarCelula(
            linha,
            item.cadastrado_por || "-"
        );

        // SALDO

        const celulaSaldo = criarCelula(
            linha,
            "",
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
            "",
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

        const celulaSituacao = criarCelula(
            linha,
            ""
        );

        let situacaoTexto = "No saldo";
        let situacaoClasse = "status saldo";

        if (saldo === 0) {
            situacaoTexto = "Em uso";
            situacaoClasse = "status uso";
        } else if (emUso > 0) {
            situacaoTexto = "Saldo parcial";
        }

        celulaSituacao.appendChild(
            criarElemento(
                "span",
                situacaoClasse,
                "● " + situacaoTexto
            )
        );

        // MOVIMENTACAO

        const celulaMovimento = criarCelula(
            linha,
            ""
        );

        const formulario = document.createElement(
            "form"
        );

        formulario.method = "POST";
        formulario.action = `/status/${encodeURIComponent(item.id)}`;
        formulario.className = "movimentacao";

        const quantidade = document.createElement(
            "input"
        );

        quantidade.type = "number";
        quantidade.name = "quantidade";
        quantidade.min = "1";
        quantidade.value = "1";
        quantidade.required = true;

        formulario.appendChild(quantidade);

        if (saldo > 0) {
            formulario.appendChild(
                criarBotaoMovimentacao(
                    "retirar",
                    "Retirar",
                    "btn-uso"
                )
            );
        }

        if (emUso > 0) {
            formulario.appendChild(
                criarBotaoMovimentacao(
                    "devolver",
                    "Devolver",
                    "btn-saldo"
                )
            );
        }

        celulaMovimento.appendChild(
            formulario
        );

        return linha;
    }

    function atualizarTabela(itens) {
        const corpo = elemento("estoque-corpo");

        if (!corpo) {
            return;
        }

        // Nao substitui os campos enquanto
        // o usuario estiver digitando uma quantidade.

        if (
            document.activeElement &&
            corpo.contains(document.activeElement)
        ) {
            return;
        }

        const fragmento = document.createDocumentFragment();

        if (
            !Array.isArray(itens) ||
            itens.length === 0
        ) {
            const linha = document.createElement(
                "tr"
            );

            const celula = criarCelula(
                linha,
                "Nenhum produto encontrado.",
                "vazio"
            );

            celula.colSpan = 9;

            fragmento.appendChild(linha);

        } else {

            itens.forEach((item) => {
                fragmento.appendChild(
                    criarLinhaEstoque(item)
                );
            });

        }

        corpo.replaceChildren(fragmento);
    }


    // ======================================
    // CALENDARIO INTELIGENTE
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

        SEMANA.forEach((dia) => {
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

                caixa.title = (
                    `${quantidade} movimentação(ões) em ${dia}/${calendarioMes}/${calendarioAno}`
                );
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
                `${formatarNumero(dados.total_movimentacoes)} movimentação(ões) neste mês.`
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

        // Invalida uma consulta anterior.
        calendarioVersao++;

        carregarCalendario();
    }

    function configurarCalendario() {
        const anterior = elemento("dash-anterior");
        const proximo = elemento("dash-proximo");
        const hoje = elemento("dash-hoje");

        if (anterior) {
            anterior.addEventListener(
                "click",
                () => mudarMes(-1)
            );
        }

        if (proximo) {
            proximo.addEventListener(
                "click",
                () => mudarMes(1)
            );
        }

        if (hoje) {
            hoje.addEventListener(
                "click",
                () => {
                    calendarioAno = HOJE_ANO;
                    calendarioMes = HOJE_MES;

                    calendarioVersao++;
                    carregarCalendario();
                }
            );
        }
    }


    // ======================================
    // BUSCA AUTOMATICA DO ESTOQUE
    // ======================================

    function configurarBusca() {
        const formulario = elemento("form-busca");

        if (!formulario) {
            return;
        }

        formulario.addEventListener(
            "submit",
            (evento) => {
                evento.preventDefault();

                const campo = elemento("busca");

                const busca = campo
                    ? campo.value.trim()
                    : "";

                const url = new URL(
                    window.location.href
                );

                if (busca) {
                    url.searchParams.set(
                        "busca",
                        busca
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

                atualizarDashboard();
            }
        );
    }


    // ======================================
    // ATUALIZACAO GERAL
    // ======================================

    async function atualizarDashboard() {
        if (atualizando) {
            return;
        }

        if (document.hidden) {
            return;
        }

        atualizando = true;

        try {
            const campoBusca = elemento("busca");

            const busca = campoBusca
                ? campoBusca.value.trim()
                : "";

            const parametros = new URLSearchParams();

            if (busca) {
                parametros.set("busca", busca);
            }

            const urlEstoque = parametros.toString()
                ? "/api/estoque?" + parametros.toString()
                : "/api/estoque";

            const [dashboard, estoque] = await Promise.all([
                buscarJSON("/api/dashboard"),
                buscarJSON(urlEstoque)
            ]);

            atualizarIndicadores(dashboard);

            atualizarMovimentacoes(
                dashboard.movimentacoes || []
            );

            atualizarTabela(
                estoque.itens || []
            );

            definirTexto(
                "dash-data",
                formatarDataAtual()
            );

            definirTexto(
                "dash-ultima",
                "Atualizado às " + formatarHora()
            );

            definirConexao(true);

            // Recarrega os dados do calendario.
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
        }
    }


    // ======================================
    // INICIALIZACAO
    // ======================================

    function iniciarDashboard() {
        if (!elemento("dashboard-vivo")) {
            return;
        }

        configurarCalendario();

        configurarBusca();

        definirTexto(
            "dash-data",
            formatarDataAtual()
        );

        atualizarDashboard();

        window.setInterval(
            atualizarDashboard,
            INTERVALO_ATUALIZACAO
        );

        document.addEventListener(
            "visibilitychange",
            () => {
                if (!document.hidden) {
                    atualizarDashboard();
                }
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
