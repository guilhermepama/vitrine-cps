"""Modelo base do Vitrine CPS (specs/01-cadastro.md)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.lookups import Exact
from django.utils import timezone
from django.utils.text import slugify

from cadastro.imagens import caminho_capa, caminho_imagem, validar_imagem
from cadastro.seguranca import gerar_token_edicao

somente_https = URLValidator(schemes=["https"])


class EdicaoQuerySet(models.QuerySet):
    def ativa(self):
        return self.filter(ativa=True).first()


class Edicao(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    data_evento = models.DateField()
    ativa = models.BooleanField(default=False)
    prazo_edicao = models.DateTimeField(help_text="Depois disso, o link do grupo só mostra o conteúdo.")
    peso_banca = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.70"))
    peso_publico = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.30"))
    banca_conferida_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    objects = EdicaoQuerySet.as_manager()

    class Meta:
        verbose_name = "edição"
        verbose_name_plural = "edições"
        ordering = ["-data_evento"]
        constraints = [
            models.UniqueConstraint(fields=["ativa"], condition=Q(ativa=True), name="uma_edicao_ativa"),
            models.CheckConstraint(
                condition=Exact(F("peso_banca") + F("peso_publico"), Decimal("1.00"))
                & Q(peso_banca__gte=0, peso_publico__gte=0),
                name="pesos_somam_um",
            ),
        ]

    def __str__(self):
        return self.nome

    def edicao_aberta(self):
        return timezone.now() <= self.prazo_edicao


class Curso(models.Model):
    class Unidade(models.TextChoices):
        FATEC = "fatec", "Fatec"
        ETEC = "etec", "Etec"

    sigla = models.CharField(max_length=10, unique=True)
    nome = models.CharField(max_length=120)
    unidade = models.CharField(max_length=5, choices=Unidade.choices)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["unidade", "sigla"]

    def __str__(self):
        return f"{self.sigla} — {self.nome}"


class Turma(models.Model):
    class TipoPeriodo(models.TextChoices):
        SEMESTRE = "semestre", "semestre"
        ANO = "ano", "ano"
        MODULO = "modulo", "módulo"

    class Turno(models.TextChoices):
        MANHA = "manha", "manhã"
        TARDE = "tarde", "tarde"
        NOITE = "noite", "noite"
        INTEGRAL = "integral", "integral"

    edicao = models.ForeignKey(Edicao, on_delete=models.PROTECT, related_name="turmas")
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name="turmas")
    numero_periodo = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    tipo_periodo = models.CharField(max_length=8, choices=TipoPeriodo.choices)
    turno = models.CharField(max_length=8, choices=Turno.choices, blank=True)

    class Meta:
        ordering = ["curso__sigla", "tipo_periodo", "numero_periodo"]
        constraints = [
            models.UniqueConstraint(
                fields=["edicao", "curso", "numero_periodo", "tipo_periodo", "turno"], name="turma_unica_na_edicao"
            ),
            models.CheckConstraint(condition=Q(numero_periodo__gte=1, numero_periodo__lte=12), name="periodo_1_a_12"),
        ]

    def __str__(self):
        return self.rotulo

    @property
    def rotulo(self):
        texto = f"{self.curso.sigla} — {self.numero_periodo}º {self.get_tipo_periodo_display()}"
        if self.turno:
            texto += f" ({self.get_turno_display()})"
        return texto


class Projeto(models.Model):
    class Status(models.TextChoices):
        PRE_CADASTRADO = "pre_cadastrado", "pré-cadastrado"
        EM_REVISAO = "em_revisao", "em revisão"
        PUBLICADO = "publicado", "publicado"
        AJUSTES = "ajustes", "ajustes pedidos"

    turma = models.ForeignKey(Turma, on_delete=models.PROTECT, related_name="projetos")
    titulo = models.CharField(max_length=120)
    slug = models.SlugField(max_length=70, unique=True, editable=False)
    resumo = models.CharField(max_length=280, blank=True)
    descricao = models.TextField(blank=True, validators=[MaxLengthValidator(3000)])
    componente_origem = models.CharField(max_length=120, blank=True)
    capa = models.ImageField(upload_to=caminho_capa, null=True, blank=True, validators=[validar_imagem])
    link_repositorio = models.URLField(blank=True, validators=[somente_https])
    link_demo = models.URLField(blank=True, validators=[somente_https])
    link_video = models.URLField(blank=True, validators=[somente_https])
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.PRE_CADASTRADO, db_index=True)
    motivo_ajustes = models.TextField(blank=True)
    representante_nome = models.CharField(max_length=120)
    ra_hmac = models.CharField(max_length=64, editable=False)
    reivindicado_em = models.DateTimeField(null=True, blank=True, editable=False)
    token_edicao_hash = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    token_edicao_gerado_em = models.DateTimeField(null=True, blank=True, editable=False)
    publicado_em = models.DateTimeField(null=True, blank=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["turma", "titulo"]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._slug_livre()
        super().save(*args, **kwargs)

    def _slug_livre(self):
        base = slugify(self.titulo)[:60].strip("-") or "projeto"
        candidato, n = base, 2
        while Projeto.objects.filter(slug=candidato).exists():
            candidato, n = f"{base}-{n}", n + 1
        return candidato

    # --- Moderação ----------------------------------------------------------

    def pendencias_para_publicar(self):
        faltando = []
        if not self.capa:
            faltando.append("capa")
        if not self.resumo.strip():
            faltando.append("resumo")
        if not self.descricao.strip():
            faltando.append("descrição")
        if not self.integrantes.exists():
            faltando.append("integrantes")
        return faltando

    def publicar(self):
        """Publica se estiver completo. Devolve a lista de pendências (vazia = publicado)."""
        faltando = self.pendencias_para_publicar()
        if faltando:
            return faltando
        self.status = self.Status.PUBLICADO
        if self.publicado_em is None:
            self.publicado_em = timezone.now()
        self.save(update_fields=["status", "publicado_em", "atualizado_em"])
        return []

    def devolver_para_ajustes(self):
        """Volta ao grupo. Exige motivo preenchido; devolve True se devolveu."""
        if not self.motivo_ajustes.strip():
            return False
        self.status = self.Status.AJUSTES
        self.save(update_fields=["status", "atualizado_em"])
        return True

    # --- Link de edição (ADR-009) ---------------------------------------------

    def regerar_link(self):
        """Invalida o link anterior. Devolve o token em claro — mostrar uma vez, não gravar."""
        token, token_hash = gerar_token_edicao()
        self.token_edicao_hash = token_hash
        self.token_edicao_gerado_em = timezone.now()
        self.save(update_fields=["token_edicao_hash", "token_edicao_gerado_em", "atualizado_em"])
        return token

    def revogar_link(self):
        self.token_edicao_hash = None
        self.token_edicao_gerado_em = None
        self.save(update_fields=["token_edicao_hash", "token_edicao_gerado_em", "atualizado_em"])


class Integrante(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="integrantes")
    nome = models.CharField(max_length=60, help_text="Como aparece na página pública.")
    papel = models.CharField(max_length=60, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    MAXIMO_POR_PROJETO = 10

    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self):
        return self.nome

    def clean(self):
        # Regra provisória (ADR-009): Etec mostra só o primeiro nome.
        nome = self.nome.strip()
        if self.projeto_id and self.projeto.turma.curso.unidade == Curso.Unidade.ETEC and len(nome.split()) > 1:
            raise ValidationError({"nome": "Para cursos da Etec, informe só o primeiro nome."})


class ImagemProjeto(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="imagens")
    arquivo = models.ImageField(upload_to=caminho_imagem, validators=[validar_imagem])
    legenda = models.CharField(max_length=120, blank=True, help_text="Texto alternativo da imagem.")
    ordem = models.PositiveSmallIntegerField(default=0)

    MAXIMO_POR_PROJETO = 6

    class Meta:
        verbose_name = "imagem do projeto"
        verbose_name_plural = "imagens do projeto"
        ordering = ["ordem", "id"]

    def __str__(self):
        return self.legenda or f"Imagem {self.pk}"
