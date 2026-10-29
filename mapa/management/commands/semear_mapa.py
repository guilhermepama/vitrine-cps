"""Cria os `Local` da planta para uma edição (spec 08). Idempotente: o que já existe não muda."""

from django.core.management.base import BaseCommand, CommandError

from cadastro.models import Edicao
from mapa import planta
from mapa.models import Local


class Command(BaseCommand):
    help = "Semeia os pontos do mapa do evento (estandes, salas, serviços, estações) para a edição ativa."

    def add_arguments(self, parser):
        parser.add_argument("--edicao", help="Nome da edição (padrão: a ativa).")
        parser.add_argument("--fileiras", default="A,B", help="Letras das fileiras de estandes, lado A e lado B. Ex.: A,B ou D,E.")

    def handle(self, *args, **opts):
        fileiras = tuple(f.strip().upper() for f in opts["fileiras"].split(","))
        if len(fileiras) != 2 or not all(len(f) == 1 and f.isalpha() for f in fileiras) or fileiras[0] == fileiras[1]:
            raise CommandError("--fileiras precisa de duas letras diferentes, ex.: A,B")
        if opts["edicao"]:
            edicao = Edicao.objects.filter(nome=opts["edicao"]).first()
        else:
            edicao = Edicao.objects.filter(ativa=True).first()
        if edicao is None:
            raise CommandError("Nenhuma edição encontrada.")

        existentes = set(Local.objects.filter(edicao=edicao).values_list("codigo", flat=True))
        novos = [
            Local(
                edicao=edicao,
                codigo=p.codigo,
                tipo=p.tipo,
                fileira=p.fileira,
                ordem=p.ordem,
                rotulo=p.rotulo,
                nome=p.nome,
            )
            for p in planta.pontos(fileiras)
            if p.codigo not in existentes
        ]
        Local.objects.bulk_create(novos)
        self.stdout.write(f"{edicao.nome}: {len(novos)} pontos criados, {len(existentes)} já existiam.")
