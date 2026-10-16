// Filtro por curso da página de projetos (spec 07). Melhoria progressiva: o
// grupo de chips vem com `hidden` e só aparece com JavaScript; sem ele,
// todas as turmas ficam visíveis.
(function () {
  var grupo = document.querySelector("[data-filtro-cursos]");
  if (!grupo) return;
  var chips = grupo.querySelectorAll(".chip");
  var turmas = document.querySelectorAll(".turma[data-curso]");
  grupo.hidden = false;
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var curso = chip.getAttribute("data-curso");
      chips.forEach(function (outro) {
        var ativo = outro === chip;
        outro.classList.toggle("chip--ativo", ativo);
        outro.setAttribute("aria-pressed", ativo ? "true" : "false");
      });
      turmas.forEach(function (turma) {
        turma.hidden = curso !== "todos" && turma.getAttribute("data-curso") !== curso;
      });
    });
  });
})();
