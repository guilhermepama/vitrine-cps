// Menu do topo no celular (spec 07). Carregado no <head> sem defer: marca
// <html class="js"> antes da pintura, e só então o CSS esconde o menu atrás
// do botão. Sem JavaScript, os links ficam visíveis na linha do topo.
(function () {
  document.documentElement.classList.add("js");
  document.addEventListener("DOMContentLoaded", function () {
    var botao = document.querySelector(".nav-alterna");
    var nav = document.getElementById("menu");
    if (!botao || !nav) return;
    function fecha() {
      nav.classList.remove("aberto");
      botao.setAttribute("aria-expanded", "false");
      botao.setAttribute("aria-label", "Abrir menu");
    }
    botao.addEventListener("click", function () {
      var aberto = nav.classList.toggle("aberto");
      botao.setAttribute("aria-expanded", aberto ? "true" : "false");
      botao.setAttribute("aria-label", aberto ? "Fechar menu" : "Abrir menu");
    });
    // Link de âncora na mesma página: fecha o menu depois do clique.
    nav.addEventListener("click", function (evento) {
      if (evento.target.closest("a")) fecha();
    });
    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && nav.classList.contains("aberto")) { fecha(); botao.focus(); }
    });
  });
})();
