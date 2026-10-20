// Tela de edição do grupo (spec 02; layout da spec 07). Opcional: pede
// confirmação ao sair da página com o texto ou uma legenda mexidos e não salvos.
(function () {
  var texto = document.getElementById("form-projeto");
  if (!texto) return;
  var mexido = false;
  var salvando = false;
  texto.addEventListener("input", function () { mexido = true; });
  texto.addEventListener("submit", function () { salvando = true; });
  // As legendas são trocadas pelo imagens.js: confere na hora de sair.
  function legendaMexida() {
    return Array.prototype.some.call(document.querySelectorAll(".legenda__campo"), function (campo) {
      return campo.value !== campo.defaultValue;
    });
  }
  window.addEventListener("beforeunload", function (evento) {
    if ((mexido && !salvando) || legendaMexida()) { evento.preventDefault(); evento.returnValue = ""; }
  });
})();
