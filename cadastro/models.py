"""Modelo base do Vitrine CPS (specs/01-cadastro.md)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator, URLValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.lookups import Exact
from django.utils import timezone
from django.utils.text import slugify

from cadastro.imagens import caminho_capa, caminho_imagem, remover_metadados, validar_imagem
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
    # Preenchidos pela votação (spec 03). Depois de aberta, a edição trava.
    votacao_aberta_em = models.DateTimeField(null=True, blank=True, editable=False)
    votacao_encerrada_em = models.DateTimeField(null=True, blank=True, editable=False)
    # Escrito só pela conferência da banca e pelas correções (spec 06).
    banca_conferida_em = models.DateTimeField(null=True, blank=True, editable=False)
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
            models.CheckConstraint(
                condition=Q(votacao_encerrada_em__isnull=True)
                | Q(votacao_aberta_em__isnull=False, votacao_encerrada_em__gte=F("votacao_aberta_em")),
                name="encerramento_apos_abertura",
            ),
        ]

    def __str__(self):
        return self.nome

    def edicao_aberta(self):
        return timezone.now() <= self.prazo_edicao

    def votacao_foi_aberta(self):
        return self.votacao_aberta_em is not None and self.votacao_aberta_em <= timezone.now()

    def clean(self):
        super().clean()
        if self.peso_banca is not None and self.peso_publico is not None and self.peso_banca <= self.peso_publico:
            raise ValidationError({"peso_banca": "O peso da banca deve ser maior que o do público (ADR-007)."})
        self._verificar_travas()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self._verificar_travas(travar_linha=True)
            super().save(*args, **kwargs)

    def _verificar_travas(self, travar_linha=False):
        """Depois de aberta a votação, pesos e abertura não mudam (sem snapshot — PR #14);
        depois de encerrada, o encerramento também não muda nem é apagado (spec 03).

        No save(), a linha da edição fica travada (select_for_update) até o fim
        da transação. Quem abre a votação (spec 03) trava a mesma linha.
        """
        if not self.pk:
            return
        consulta = Edicao.objects.select_for_update() if travar_linha else Edicao.objects
        antes = consulta.filter(pk=self.pk).values(
            "peso_banca", "peso_publico", "votacao_aberta_em", "votacao_encerrada_em"
        ).first()
        if not antes or antes["votacao_aberta_em"] is None:
            return
        erros = {}
        if self.votacao_aberta_em != antes["votacao_aberta_em"]:
            erros["votacao_aberta_em"] = "A abertura da votação não pode ser alterada nem apagada."
        encerrada = antes["votacao_encerrada_em"]
        if encerrada is not None and self.votacao_encerrada_em != encerrada:
            erros["votacao_encerrada_em"] = "O encerramento da votação não pode ser alterado nem apagado."
        pesos = (Decimal(str(self.peso_banca)), Decimal(str(self.peso_publico)))
        if pesos != (antes["peso_banca"], antes["peso_publico"]):
            erros["peso_banca"] = "Os pesos não mudam depois de aberta a votação (ADR-007)."
        if erros:
            raise ValidationError(erros)


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

    def clean(self):
        super().clean()
        self._verificar_travas()

    def save(self, *args, **kwargs):
        self._verificar_travas()
        super().save(*args, **kwargs)

    def _verificar_travas(self):
        """Turma com projeto não muda de edição nem de curso: os votos iriam junto."""
        if not self.pk:
            return
        antes = Turma.objects.filter(pk=self.pk).values("edicao_id", "curso_id").first()
        mudou = antes and (antes["edicao_id"], antes["curso_id"]) != (self.edicao_id, self.curso_id)
        if mudou and self.projetos.exists():
            raise ValidationError("Turma com projetos não muda de edição nem de curso.")

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
    # Não editável: muda só por publicar(), devolver_para_ajustes() e pelo fluxo do grupo (spec 02).
    status = models.CharField(
        max_length=14, choices=Status.choices, default=Status.PRE_CADASTRADO, db_index=True, editable=False
    )
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

    def clean(self):
        super().clean()
        self._verificar_travas()
        self._verificar_ra_unico_na_edicao()

    def _verificar_ra_unico_na_edicao(self):
        """Um RA representa no máximo um projeto por edição (spec 01). A mensagem não mostra o RA."""
        if not self.ra_hmac or not self.turma_id:
            return
        outros = Projeto.objects.filter(ra_hmac=self.ra_hmac, turma__edicao_id=self.turma.edicao_id)
        if outros.exclude(pk=self.pk).exists():
            raise ValidationError("Este RA já representa outro projeto nesta edição.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self._verificar_travas(travar_edicao=True)
            if not self.slug:
                self.slug = self._slug_livre()
            remover_metadados(self.capa)
            super().save(*args, **kwargs)

    def _verificar_travas(self, travar_edicao=False):
        """Slug nunca muda; status e turma fixos depois de aberta a votação; nunca muda de edição.

        Sem snapshot do resultado (PR #14), mudar status ou turma de um projeto
        com votos alteraria o ranking em silêncio. `QuerySet.update()` passa por
        cima disto — mude status e turma só pelos métodos do model.
        """
        if not self.pk:
            return
        antes = Projeto.objects.filter(pk=self.pk).values("slug", "status", "turma_id", "turma__edicao_id").first()
        if not antes:
            return
        if self.slug != antes["slug"]:
            raise ValidationError({"slug": "O slug não muda: o link público do projeto não pode quebrar."})
        # Trava a linha da edição: abrir a votação ao mesmo tempo espera esta gravação.
        edicoes = Edicao.objects.select_for_update() if travar_edicao else Edicao.objects
        aberta_em = edicoes.filter(pk=antes["turma__edicao_id"]).values_list("votacao_aberta_em", flat=True).first()
        if self.turma_id != antes["turma_id"]:
            nova_edicao = Turma.objects.filter(pk=self.turma_id).values_list("edicao_id", flat=True).first()
            if nova_edicao != antes["turma__edicao_id"]:
                raise ValidationError({"turma": "O projeto não pode mudar de edição."})
        mudou = (self.status, self.turma_id) != (antes["status"], antes["turma_id"])
        if mudou and aberta_em is not None:
            raise ValidationError("A votação desta edição já foi aberta: status e turma do projeto não mudam.")

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
        """Publica se estiver completo. Devolve a lista de pendências (vazia = publicado).

        Com a votação da edição aberta, levanta ValidationError (trava)."""
        if self.status != self.Status.EM_REVISAO:
            return ["status (só se publica um projeto em revisão)"]
        faltando = self.pendencias_para_publicar()
        if faltando:
            return faltando
        anterior = (self.status, self.publicado_em)
        self.status = self.Status.PUBLICADO
        if self.publicado_em is None:
            self.publicado_em = timezone.now()
        try:
            self.save(update_fields=["status", "publicado_em", "atualizado_em"])
        except ValidationError:
            self.status, self.publicado_em = anterior  # objeto volta a refletir o banco
            raise
        return []

    def devolver_para_ajustes(self):
        """Volta ao grupo. Só de em_revisao ou publicado, com motivo; devolve True se devolveu.

        Com a votação da edição aberta, levanta ValidationError (trava)."""
        if self.status not in (self.Status.EM_REVISAO, self.Status.PUBLICADO):
            return False
        if not self.motivo_ajustes.strip():
            return False
        anterior = self.status
        self.status = self.Status.AJUSTES
        try:
            self.save(update_fields=["status", "atualizado_em"])
        except ValidationError:
            self.status = anterior
            raise
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

    def save(self, *args, **kwargs):
        remover_metadados(self.arquivo)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.legenda or f"Imagem {self.pk}"
