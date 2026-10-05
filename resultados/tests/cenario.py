"""Cenários com dados reais (cadastro + votação + banca) para os testes das
views do resultados. Só dados fictícios."""

from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.utils import timezone

from banca.models import Criterio
from banca.tests import fabricas as banca
from cadastro.models import Curso, Edicao, Projeto
from cadastro.tests import fabricas as cadastro
from votacao.servicos import abrir_votacao, encerrar_votacao
from votacao.tests import fabricas as votacao

PUBLICADO = Projeto.Status.PUBLICADO
SENHA = "senha-forte-123"


def usuario(nome="coordenacao", staff=True, perms=("ver_resultados",), **campos):
    u = User.objects.create_user(nome, password=SENHA, is_staff=staff, **campos)
    u.user_permissions.set(Permission.objects.filter(content_type__app_label="resultados", codename__in=perms))
    return u


def edicao(turmas, nome="2026/2", estado="encerrada", conferida=True):
    """Edição com uma turma por chave de `turmas` ({sigla: [(titulo, votos, nota)]}).

    `nota` None = projeto sem avaliação da banca. Cada voto de um projeto
    sai de um token diferente (um token vota uma vez por projeto).
    `estado`: "configurar" (votação nunca aberta), "aberta" ou "encerrada".
    Devolve (edicao, {titulo: projeto}).
    """
    for aberta in Edicao.objects.filter(votacao_aberta_em__isnull=False, votacao_encerrada_em__isnull=True):
        encerrar_votacao(aberta.pk)
    ed = cadastro.edicao(nome=nome)
    Criterio.objects.create(edicao=ed, nome="Critério 1", ordem=1)
    projetos, por_turma = {}, {}
    for sigla, linhas in turmas.items():
        curso, _ = Curso.objects.get_or_create(sigla=sigla, defaults={"nome": sigla, "unidade": "fatec"})
        turma = cadastro.turma(ed, curso)
        por_turma[turma] = []
        for titulo, votos, nota in linhas:
            projeto = cadastro.projeto(turma, titulo=titulo, status=PUBLICADO)
            projetos[titulo] = projeto
            por_turma[turma].append((projeto, votos, nota))
    if estado == "configurar":
        return ed, projetos
    assert abrir_votacao(ed.pk) is None
    estacao = votacao.estacao(ed, nome=f"Entrada {nome}")
    maximo = max((v for linhas in por_turma.values() for _, v, _ in linhas), default=0)
    tokens = [votacao.token(estacao) for _ in range(maximo)]
    for turma, linhas in por_turma.items():
        jurado = banca.jurado(ed, turma, nome=f"Jurado {turma.pk}")
        for projeto, votos, nota in linhas:
            for token in tokens[:votos]:
                votacao.voto(token, projeto)
            if nota is not None:
                banca.avaliar(jurado, projeto, [Decimal(str(nota))])
    if estado == "encerrada":
        assert encerrar_votacao(ed.pk) is None
    if conferida:
        # Depois das notas: gravar nota desfaz a conferência (spec 06).
        Edicao.objects.filter(pk=ed.pk).update(banca_conferida_em=timezone.now())
    ed.refresh_from_db()
    return ed, projetos
