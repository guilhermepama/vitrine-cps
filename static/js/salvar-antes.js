// Tela de edição do grupo (spec 02; layout da spec 07). Opcional.
// Enviar ou remover imagem recarrega a página: antes disso, se o texto foi
// mexido, este script faz o mesmo "Salvar" do botão (POST com acao=salvar) e
// só então segue com a imagem. Também avisa ao sair da página com texto não
// salvo. Sem JavaScript, vale o aviso "Salve o texto antes de enviar imagens".
(function () {
  var texto = document.getElementById("form-projeto");
  var secao = document.getElementById("imagens");
  if (!texto || !secao || !window.fetch || !window.FormData) return;

  var mexido = false;
  var saindoPeloSalvar = false;
  texto.addEventListener("input", function () { mexido = true; });
  texto.addEventListener("submit", function () { saindoPeloSalvar = true; });
  window.addEventListener("beforeunload", function (evento) {
    if (mexido && !saindoPeloSalvar) { evento.preventDefault(); evento.returnValue = ""; }
  });

  var aviso = document.getElementById("aviso-salvar-texto");
  if (aviso) aviso.textContent = "O texto é salvo automaticamente antes de cada envio ou remoção de imagem.";

  function estadoDo(form) {
    var p = form.querySelector(".edicao-upload__estado");
    if (p) return p;
    p = document.createElement("p");
    p.className = "edicao-upload__estado";
    p.setAttribute("role", "status");
    form.appendChild(p);
    return p;
  }

  function salvarTexto() {
    var dados = new FormData(texto);
    dados.set("acao", "salvar");
    return fetch(texto.action, { method: "POST", body: dados, credentials: "same-origin" }).then(function (r) {
      // Salvo: a view redireciona para a própria tela (o fetch segue e chega com 200).
      if (r.ok && r.redirected) { mexido = false; return true; }
      return false;
    }, function () { return false; });
  }

  Array.prototype.forEach.call(secao.querySelectorAll("form"), function (form) {
    form.addEventListener("submit", function (evento) {
      if (!mexido) return;
      evento.preventDefault();
      var botao = form.querySelector('button[type="submit"]');
      var rotulo = botao ? botao.textContent : "";
      var estado = estadoDo(form);
      if (botao) { botao.disabled = true; botao.textContent = "Salvando o texto…"; }
      estado.classList.remove("edicao-upload__estado--erro");
      estado.textContent = "Salvando o texto antes de enviar…";
      estado.hidden = false;
      salvarTexto().then(function (salvou) {
        if (salvou) {
          if (botao) botao.textContent = "Enviando…";
          estado.textContent = "Texto salvo. Enviando…";
          saindoPeloSalvar = true;
          form.submit(); // envio nativo: não passa de novo por este handler
          return;
        }
        if (botao) { botao.disabled = false; botao.textContent = rotulo; }
        estado.classList.add("edicao-upload__estado--erro");
        estado.textContent = "O texto tem algum erro e não foi salvo, então a imagem não foi enviada. Clique em Salvar para ver o que corrigir.";
      });
    });
  });
})();
