// Tela de edição do grupo (spec 02; layout da spec 07). Opcional.
// Imagens sem recarregar a página: enviar, trocar a capa, salvar legenda e
// remover vão por fetch para as mesmas rotas; a view responde como sempre
// (redireciona para a tela de edição) e o script troca só a seção de Imagens
// e o painel "O que falta". A rolagem fica onde está e o texto que está sendo
// digitado nos campos não se perde.
// Na capa e no card "+" (`data-envio-automatico`) a imagem sobe assim que o
// arquivo é escolhido, com a prévia no próprio espaço. Formato e tamanho que o
// servidor recusaria (cadastro/imagens.py: JPG, PNG ou WebP, até 3 MB) são
// recusados na hora. Sem JavaScript, os formulários funcionam normalmente
// (escolhe, clica no botão e a página recarrega).
(function () {
  if (!window.fetch || !window.FormData || !window.DOMParser || !window.URL) return;
  var TAMANHO_MAXIMO = 3 * 1024 * 1024;
  var FORMATOS = ["image/jpeg", "image/png", "image/webp"];
  var ocupado = false;

  function estadoDo(form) {
    var p = form.querySelector(".edicao-upload__estado");
    if (p) return p;
    p = document.createElement("p");
    p.className = "edicao-upload__estado";
    p.setAttribute("role", "status");
    p.hidden = true;
    form.appendChild(p);
    return p;
  }

  function avisa(form, texto, erro) {
    var estado = estadoDo(form);
    estado.textContent = texto;
    estado.hidden = !texto;
    estado.classList.toggle("edicao-upload__estado--erro", !!erro);
  }

  // Aviso no rodapé da tela: aparece onde a pessoa estiver rolando e some sozinho.
  var caixa = null;
  var relogio = null;
  function flutuante(texto, erro) {
    if (!caixa) {
      caixa = document.createElement("p");
      caixa.className = "aviso-flutuante";
      caixa.setAttribute("role", "status");
      document.body.appendChild(caixa);
    }
    caixa.textContent = texto;
    caixa.classList.toggle("aviso-flutuante--erro", !!erro);
    caixa.classList.add("aviso-flutuante--visivel");
    clearTimeout(relogio);
    relogio = setTimeout(function () { caixa.classList.remove("aviso-flutuante--visivel"); }, erro ? 7000 : 4000);
  }

  // Troca a seção de Imagens e o painel lateral pelos da página que voltou.
  function aplicar(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var nova = doc.getElementById("imagens");
    var atual = document.getElementById("imagens");
    if (!nova || !atual) return false; // virou somente leitura ou link inválido
    var envioNovo = doc.querySelector(".envio");
    var envioAtual = document.querySelector(".envio");
    if (envioNovo && envioAtual) envioAtual.replaceWith(document.adoptNode(envioNovo));
    var ok = doc.querySelector(".edicao__avisos .alerta--ok");
    nova = document.adoptNode(nova);
    atual.replaceWith(nova);
    var erro = nova.querySelector(".alerta[role=alert]");
    if (erro) flutuante(erro.textContent.trim(), true);
    else if (ok) flutuante(ok.textContent.trim(), false);
    iniciar(nova);
    return true;
  }

  function enviar(form, botao) {
    if (ocupado) return;
    ocupado = true;
    if (botao) botao.disabled = true;
    fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin" })
      .then(function (r) { return r.text().then(function (html) { return { r: r, html: html }; }); })
      .then(function (res) {
        ocupado = false;
        if (!aplicar(res.html)) window.location.reload();
      }, function () {
        ocupado = false;
        if (botao) botao.disabled = false;
        avisa(form, "Não foi possível falar com o servidor. Confira a conexão e tente de novo.", true);
      });
  }

  function prepararUpload(form) {
    var campo = form.querySelector('input[type="file"]');
    var botao = form.querySelector('button[type="submit"]');
    var alvo = document.getElementById(form.getAttribute("data-previa"));
    if (!campo || !botao || !alvo) return;
    var automatico = form.hasAttribute("data-envio-automatico");
    var originais = Array.prototype.slice.call(alvo.children);
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

    function limpa() {
      if (endereco) URL.revokeObjectURL(endereco);
      endereco = null;
      var velha = alvo.querySelector(".previa");
      if (velha) velha.remove();
      originais.forEach(function (el) { el.hidden = false; });
      if (alvo.classList.contains("edicao-upload__slot")) alvo.hidden = true;
      form.classList.remove("edicao-upload--pronta");
      botao.classList.remove("botao--vermelho");
    }

    function mostra(arquivo) {
      endereco = URL.createObjectURL(arquivo);
      var previa = document.createElement("div");
      previa.className = "previa";
      var img = document.createElement("img");
      img.className = "edicao-capa__img";
      img.src = endereco;
      img.alt = "Prévia da imagem escolhida";
      var etiqueta = document.createElement("span");
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
      if (!arquivo) { avisa(form, ""); return; }
      if (FORMATOS.indexOf(arquivo.type) === -1) {
        campo.value = "";
        avisa(form, "Esse arquivo não é JPG, PNG ou WebP. Escolha outra imagem.", true);
        return;
      }
      if (arquivo.size > TAMANHO_MAXIMO) {
        campo.value = "";
        var mb = (arquivo.size / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
        avisa(form, "A imagem tem " + mb + " MB; o limite é 3 MB. Reduza e tente de novo.", true);
        return;
      }
      mostra(arquivo);
      if (automatico) {
        avisa(form, "Enviando a imagem…");
        enviar(form, botao);
        return;
      }
      avisa(form, "Imagem escolhida, ainda não enviada. Clique em “" + botao.textContent + "” para enviar.");
    });
  }

  function iniciar(raiz) {
    var aviso = raiz.querySelector("#aviso-salvar-texto");
    if (aviso) aviso.textContent = "As imagens são enviadas sem recarregar a página: o texto que você está digitando não se perde. Lembre de salvar o texto no fim.";
    Array.prototype.forEach.call(raiz.querySelectorAll("form[data-previa]"), prepararUpload);
    Array.prototype.forEach.call(raiz.querySelectorAll("form"), function (form) {
      form.addEventListener("submit", function (evento) {
        evento.preventDefault();
        var botao = evento.submitter || form.querySelector('button[type="submit"]');
        var campo = form.querySelector('input[type="file"]');
        if (campo && !(campo.files && campo.files[0])) return;
        if (campo) avisa(form, "Enviando a imagem…");
        if (botao && botao.type === "submit" && !botao.hidden) botao.textContent = campo ? "Enviando…" : "Salvando…";
        enviar(form, botao);
      });
    });
  }

  var secao = document.getElementById("imagens");
  if (secao) iniciar(secao);
})();
