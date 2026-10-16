// Tela de edição do grupo (spec 02; layout da spec 07). Opcional: ao escolher
// um arquivo, mostra a prévia no próprio espaço da imagem e avisa que ainda
// falta enviar. Recusa na hora formato e tamanho que o servidor recusaria
// (cadastro/imagens.py: JPG, PNG ou WebP, até 3 MB). Sem JavaScript, o
// formulário funciona igual e o servidor faz a mesma checagem.
(function () {
  var TAMANHO_MAXIMO = 3 * 1024 * 1024;
  var FORMATOS = ["image/jpeg", "image/png", "image/webp"];
  var formularios = document.querySelectorAll("form[data-previa]");

  Array.prototype.forEach.call(formularios, function (form) {
    var campo = form.querySelector('input[type="file"]');
    var botao = form.querySelector('button[type="submit"]');
    var estado = form.querySelector(".edicao-upload__estado");
    var alvo = document.getElementById(form.getAttribute("data-previa"));
    if (!campo || !botao || !estado || !alvo || !window.URL) return;
    var textoDoBotao = botao.textContent;
    var originais = Array.prototype.slice.call(alvo.children);
    var previa = null;
    var endereco = null;

    function avisa(texto, erro) {
      estado.textContent = texto;
      estado.hidden = !texto;
      estado.classList.toggle("edicao-upload__estado--erro", !!erro);
    }

    function limpa() {
      if (endereco) URL.revokeObjectURL(endereco);
      endereco = null;
      if (previa) previa.remove();
      previa = null;
      originais.forEach(function (el) { el.hidden = false; });
      if (alvo.classList.contains("edicao-upload__slot")) alvo.hidden = true;
      form.classList.remove("edicao-upload--pronta");
      botao.classList.remove("botao--vermelho");
    }

    function mostra(arquivo) {
      endereco = URL.createObjectURL(arquivo);
      previa = document.createElement("div");
      previa.className = "previa";
      var img = document.createElement("img");
      img.className = "edicao-capa__img";
      img.src = endereco;
      img.alt = "Prévia da imagem escolhida";
      var etiqueta = document.createElement("span");
      etiqueta.className = "previa__etiqueta";
      etiqueta.textContent = "Prévia · ainda não enviada";
      previa.appendChild(img);
      previa.appendChild(etiqueta);
      originais.forEach(function (el) { el.hidden = true; });
      alvo.appendChild(previa);
      alvo.hidden = false;
      form.classList.add("edicao-upload--pronta");
      botao.classList.add("botao--vermelho");
    }

    campo.addEventListener("change", function () {
      limpa();
      var arquivo = campo.files && campo.files[0];
      if (!arquivo) { avisa(""); return; }
      if (FORMATOS.indexOf(arquivo.type) === -1) {
        campo.value = "";
        avisa("Esse arquivo não é JPG, PNG ou WebP. Escolha outra imagem.", true);
        return;
      }
      if (arquivo.size > TAMANHO_MAXIMO) {
        campo.value = "";
        var mb = (arquivo.size / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
        avisa("A imagem tem " + mb + " MB; o limite é 3 MB. Reduza e tente de novo.", true);
        return;
      }
      mostra(arquivo);
      avisa("Imagem escolhida, ainda não enviada. Clique em “" + textoDoBotao + "” para enviar.");
    });

    form.addEventListener("submit", function (evento) {
      // salvar-antes.js segurou o envio para salvar o texto primeiro: ele cuida do botão.
      if (evento.defaultPrevented || !campo.files || !campo.files[0]) return;
      // Só depois que o envio começou: o botão não tem name, então desabilitar não muda o POST.
      setTimeout(function () {
        botao.disabled = true;
        botao.textContent = "Enviando…";
      }, 0);
      avisa("Enviando a imagem…");
    });
  });
})();
