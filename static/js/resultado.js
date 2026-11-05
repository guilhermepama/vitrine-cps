// Resultado público (spec 09): liga/desliga as colunas de pontos e abre
// "Como calculamos" quando o link aponta para #calculo. Sem JS, tudo fica visível
// e a explicação abre pelo próprio <details>.
(function () {
  var raiz = document.querySelector(".rp");
  var caixa = document.getElementById("calculo-caixa");
  var conta = document.getElementById("mostrar-conta");
  if (raiz && conta) {
    var aplica = function () { raiz.classList.toggle("rp-sem-conta", !conta.checked); };
    conta.addEventListener("change", aplica);
    aplica();
  }
  if (caixa) {
    var abre = function () { if (location.hash === "#calculo") caixa.open = true; };
    window.addEventListener("hashchange", abre);
    abre();
  }
})();
