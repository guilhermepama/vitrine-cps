// Tela do link de edição (spec 02). Opcional: sem JavaScript o link continua
// selecionável e o botão "Copiar" fica escondido.
(function () {
  var campo = document.getElementById("link");
  if (!campo) return;
  campo.addEventListener("focus", function () { campo.select(); });
  var botao = document.getElementById("copiar");
  if (!botao || !navigator.clipboard) return;
  botao.hidden = false;
  botao.addEventListener("click", function () {
    navigator.clipboard.writeText(campo.value).then(function () {
      botao.textContent = "Copiado!";
    });
  });
})();
