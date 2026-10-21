from django.db import migrations, models


def exige_votos_vazia(apps, schema_editor):
    """Voto sem nota não existe (ADR-012): com votos gravados, não há nota a inventar."""
    Voto = apps.get_model("votacao", "Voto")
    if Voto.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError("votos existentes sem notas: esvazie ou migre antes de aplicar a 0004.")


class Migration(migrations.Migration):

    dependencies = [
        ("votacao", "0003_permissao_operar_estacao"),
    ]

    operations = [
        migrations.RunPython(exige_votos_vazia, migrations.RunPython.noop),
        migrations.AddField(
            model_name="voto",
            name="impacto_social",
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AddField(
            model_name="voto",
            name="inovacao",
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AddField(
            model_name="voto",
            name="impacto_ambiental",
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AddConstraint(
            model_name="voto",
            constraint=models.CheckConstraint(
                condition=models.Q(("impacto_social__gte", 0), ("impacto_social__lte", 5)),
                name="voto_impacto_social_0_a_5",
            ),
        ),
        migrations.AddConstraint(
            model_name="voto",
            constraint=models.CheckConstraint(
                condition=models.Q(("inovacao__gte", 0), ("inovacao__lte", 5)),
                name="voto_inovacao_0_a_5",
            ),
        ),
        migrations.AddConstraint(
            model_name="voto",
            constraint=models.CheckConstraint(
                condition=models.Q(("impacto_ambiental__gte", 0), ("impacto_ambiental__lte", 5)),
                name="voto_impacto_ambiental_0_a_5",
            ),
        ),
    ]
