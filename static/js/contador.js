// Tela de edição do grupo (spec 02; layout da spec 07). Opcional: mostra
// "N de 280" embaixo dos campos com limite. Sem JavaScript, o maxlength do
// campo continua barrando o excesso.
(function () {
  var campos = document.querySelectorAll(".edicao__campo textarea[maxlength]");
  Array.prototype.forEach.call(campos, function (campo) {
    var limite = parseInt(campo.getAttribute("maxlength"), 10);
    if (!limite) return;
    var saida = document.createElement("p");
    saida.className = "ajuda contador";
    campo.insertAdjacentElement("afterend", saida);
    function atualiza() {
      var usados = campo.value.length;
      saida.textContent = usados.toLocaleString("pt-BR") + " de " + limite.toLocaleString("pt-BR") + " caracteres";
      saida.classList.toggle("contador--perto", usados >= limite * 0.9);
    }
    campo.addEventListener("input", atualiza);
    atualiza();
  });
})();
