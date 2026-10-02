"""python manage.py importar_lista <edicao_id> <arquivo.csv> [--aplicar]

Simula por padrão. Grava só com --aplicar e só se nenhuma linha tiver erro.
A saída nunca mostra o RA.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cadastro.importacao import ErroDeArquivo, analisar, ler_csv
from cadastro.importacao import aplicar as gravar
from cadastro.models import Edicao


class Command(BaseCommand):
    help = "Importa a lista de projetos das coordenações (CSV da planilha modelo)."

    def add_arguments(self, parser):
        parser.add_argument("edicao_id", type=int)
        parser.add_argument("arquivo")
        parser.add_argument("--aplicar", action="store_true", help="Grava de verdade (sem isto, só simula).")

    def handle(self, *args, edicao_id, arquivo, aplicar: bool = False, **options):
        edicao = Edicao.objects.filter(pk=edicao_id).first()
        if edicao is None:
            raise CommandError(f"Edição {edicao_id} não existe.")
        caminho = Path(arquivo)
        try:
            conteudo = caminho.read_bytes()
        except OSError:
            raise CommandError(f"Não foi possível ler o arquivo {caminho.name}.")
        try:
            registros, _ = ler_csv(conteudo)
        except ErroDeArquivo as erro:
            raise CommandError(str(erro))

        relatorio = analisar(edicao, registros)
        for linha in relatorio.linhas:
            texto = f"linha {linha.numero}: {linha.resultado}"
            if linha.titulo:
                texto += f" — {linha.titulo}"
            if linha.motivo:
                texto += f" ({linha.motivo})"
            self.stdout.write(texto)

        totais = relatorio.totais()
        self.stdout.write(
            f"Total: {totais['criado']} criado(s), {totais['atualizado']} atualizado(s), "
            f"{totais['ignorado']} ignorado(s), {totais['erro']} erro(s)."
        )
        if relatorio.tem_erro:
            raise CommandError("Há linhas com erro: nada foi gravado. Corrija o arquivo e rode de novo.")
        if not aplicar:
            self.stdout.write("Simulação: nada foi gravado. Rode com --aplicar para gravar.")
            return
        gravar(relatorio)
        self.stdout.write(self.style.SUCCESS(f"Gravado na edição {edicao.nome}."))
