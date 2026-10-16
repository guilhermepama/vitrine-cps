// Tela de edição do grupo (spec 02; layout da spec 07). Opcional.
// Ao escolher um arquivo, mostra a prévia no próprio espaço da imagem. Nos
// formulários com `data-envio-automatico` (capa e card "+" da galeria) a
// imagem sobe na hora: o botão de enviar some (na capa ele passa a abrir o
// seletor). Recusa na hora formato e tamanho que o servidor recusaria
// (cadastro/imagens.py: JPG, PNG ou WebP, até 3 MB). Sem JavaScript, escolhe e
// clica no botão, e o servidor faz a mesma checagem.
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
    var automatico = form.hasAttribute("data-envio-automatico");
    var textoDoBotao = botao.textContent;
    var originais = Array.prototype.slice.call(alvo.children);
    var previa = null;
    var etiqueta = null;
    var endereco = null;

    if (automatico) {
      form.classList.add("edicao-upload--auto");
      if (form.querySelector(".adicionar")) {
        botao.hidden = true; // o card inteiro é o seletor (label do campo)
      } else {
        // capa: o botão abre o seletor e o campo de arquivo fica escondido
        botao.type = "button";
        campo.classList.add("campo-arquivo--oculto");
        botao.addEventListener("click", function () { campo.click(); });
      }
    }

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
      etiqueta = document.createElement("span");
      etiqueta.className = "previa__etiqueta";
      etiqueta.textContent = automatico ? "Enviando…" : "Prévia · ainda não enviada";
      previa.appendChild(img);
      previa.appendChild(etiqueta);
      originais.forEach(function (el) { el.hidden = true; });
      alvo.appendChild(previa);
      alvo.hidden = false;
      form.classList.add("edicao-upload--pronta");
      if (!automatico) botao.classList.add("botao--vermelho");
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
      if (automatico) {
        // passa pelo evento submit: salvar-antes.js salva o texto mexido antes
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
        return;
      }
      avisa("Imagem escolhida, ainda não enviada. Clique em “" + textoDoBotao + "” para enviar.");
    });

    form.addEventListener("submit", function (evento) {
      // salvar-antes.js segurou o envio para salvar o texto primeiro: ele cuida do aviso.
      if (evento.defaultPrevented || !campo.files || !campo.files[0]) return;
      // Só depois que o envio começou: o botão não tem name, então desabilitar não muda o POST.
      setTimeout(function () {
        botao.disabled = true;
        if (!automatico) botao.textContent = "Enviando…";
      }, 0);
      avisa("Enviando a imagem…");
    });
  });
})();
