// Tela de edição do grupo (spec 02; layout da spec 07). Opcional: pede
// confirmação ao sair da página com o texto mexido e não salvo.
(function () {
  var texto = document.getElementById("form-projeto");
  if (!texto) return;
  var mexido = false;
  var salvando = false;
  texto.addEventListener("input", function () { mexido = true; });
  texto.addEventListener("submit", function () { salvando = true; });
  window.addEventListener("beforeunload", function (evento) {
    if (mexido && !salvando) { evento.preventDefault(); evento.returnValue = ""; }
  });
})();
