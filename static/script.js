"use strict";

document.addEventListener("DOMContentLoaded", function () {
    // Abrir e fechar o menu lateral em telas menores
    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.getElementById("sidebar");

    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", function () {
            sidebar.classList.toggle("sidebar-open");
        });

        document.addEventListener("click", function (event) {
            const clicouNoMenu = sidebar.contains(event.target);
            const clicouNoBotao = menuToggle.contains(event.target);

            if (
                window.innerWidth <= 900 &&
                !clicouNoMenu &&
                !clicouNoBotao
            ) {
                sidebar.classList.remove("sidebar-open");
            }
        });

        sidebar.querySelectorAll("nav a").forEach(function (link) {
            link.addEventListener("click", function () {
                sidebar.classList.remove("sidebar-open");
            });
        });
    }

    // Confirmar operações importantes antes de enviar formulários
    document.querySelectorAll("[data-confirm]").forEach(function (element) {
        element.addEventListener("click", function (event) {
            const mensagem =
                element.getAttribute("data-confirm") ||
                "Deseja continuar?";

            if (!window.confirm(mensagem)) {
                event.preventDefault();
            }
        });
    });

    // Mostrar ou ocultar a senha
    document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
        button.addEventListener("click", function () {
            const inputId = button.getAttribute("data-password-toggle");
            const input = document.getElementById(inputId);

            if (!input) return;

            if (input.type === "password") {
                input.type = "text";
                button.setAttribute("aria-label", "Ocultar senha");
            } else {
                input.type = "password";
                button.setAttribute("aria-label", "Mostrar senha");
            }
        });
    });

    // Preencher o campo do assistente com uma pergunta sugerida
    const questionInput = document.getElementById("question");

    document.querySelectorAll("[data-question]").forEach(function (button) {
        button.addEventListener("click", function () {
            if (!questionInput) return;

            questionInput.value = button.getAttribute("data-question") || "";
            questionInput.focus();
        });
    });

    // Enviar a pergunta ao pressionar Ctrl + Enter
    if (questionInput) {
        questionInput.addEventListener("keydown", function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                const form = questionInput.closest("form");

                if (form && questionInput.value.trim()) {
                    form.requestSubmit();
                }
            }
        });
    }

    // Impedir quantidades menores que 1 nos formulários de movimentação
    document.querySelectorAll(".movement-form input[name='quantity']").forEach(function (input) {
        input.addEventListener("change", function () {
            const quantidade = Number.parseInt(input.value, 10);

            if (!Number.isInteger(quantidade) || quantidade < 1) {
                input.value = "1";
            }
        });
    });

    // Evitar envios repetidos por cliques consecutivos
    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                form.reportValidity();
                return;
            }

            const submitButton = event.submitter;

            if (!submitButton || submitButton.dataset.confirmedSubmit === "true") {
                return;
            }

            submitButton.dataset.confirmedSubmit = "true";
            submitButton.dataset.originalText = submitButton.textContent;
            submitButton.disabled = true;
            submitButton.textContent = "Processando...";

            // Reabilita se o navegador mantiver a página aberta após uma falha
            window.setTimeout(function () {
                if (submitButton.isConnected) {
                    submitButton.disabled = false;
                    submitButton.textContent = submitButton.dataset.originalText || "Enviar";
                    delete submitButton.dataset.confirmedSubmit;
                }
            }, 10000);
        });
    });
});
