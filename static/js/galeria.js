// Galeria da página pública do projeto (spec 02; layout da spec 07). Opcional.
// Clique na imagem abre a mesma imagem ampliada num <dialog>, com a legenda,
// anterior/próxima (botões ou setas do teclado) e fechar (Esc, botão ou clique
// no fundo). Sem JavaScript, o link da imagem abre o arquivo original em outra aba.
(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll(".galeria__ampliar"));
  if (!links.length || typeof HTMLDialogElement === "undefined") return;

  var visor = document.createElement("dialog");
  visor.className = "visor";
  visor.setAttribute("aria-label", "Imagem ampliada");
  visor.innerHTML =
    '<figure class="visor__figura"><img class="visor__img" alt=""><figcaption class="visor__legenda"></figcaption></figure>' +
    '<p class="visor__contador mono"></p>' +
    '<button type="button" class="visor__botao visor__fechar" aria-label="Fechar">×</button>' +
    '<button type="button" class="visor__botao visor__ant" aria-label="Imagem anterior">←</button>' +
    '<button type="button" class="visor__botao visor__prox" aria-label="Próxima imagem">→</button>';
  document.body.appendChild(visor);

  var img = visor.querySelector(".visor__img");
  var legenda = visor.querySelector(".visor__legenda");
  var contador = visor.querySelector(".visor__contador");
  var fechar = visor.querySelector(".visor__fechar");
  var ant = visor.querySelector(".visor__ant");
  var prox = visor.querySelector(".visor__prox");
  var atual = 0;

  function mostra(i) {
    atual = (i + links.length) % links.length;
    var link = links[atual];
    var miniatura = link.querySelector("img");
    var figura = link.closest("figure");
    var texto = figura && figura.querySelector("figcaption") ? figura.querySelector("figcaption").textContent : "";
    img.src = link.href;
    img.alt = miniatura ? miniatura.alt : "";
    legenda.textContent = texto;
    legenda.hidden = !texto;
    contador.textContent = (atual + 1) + " / " + links.length;
    ant.hidden = prox.hidden = links.length < 2;
  }

  links.forEach(function (link, i) {
    link.addEventListener("click", function (e) {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return; // abrir em outra aba continua valendo
      e.preventDefault();
      mostra(i);
      if (!visor.open) visor.showModal();
      fechar.focus();
    });
  });
  ant.addEventListener("click", function () { mostra(atual - 1); });
  prox.addEventListener("click", function () { mostra(atual + 1); });
  fechar.addEventListener("click", function () { visor.close(); });
  visor.addEventListener("click", function (e) { if (e.target === visor) visor.close(); });
  visor.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") mostra(atual - 1);
    else if (e.key === "ArrowRight") mostra(atual + 1);
  });
  visor.addEventListener("close", function () {
    img.removeAttribute("src");
    links[atual].focus();
  });
})();
