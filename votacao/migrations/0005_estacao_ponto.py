from django.db import migrations, models

import mapa.planta


class Migration(migrations.Migration):

    dependencies = [
        ("votacao", "0004_voto_tres_notas"),
    ]

    operations = [
        migrations.AddField(
            model_name="estacao",
            name="ponto",
            field=models.CharField(
                blank=True,
                choices=mapa.planta.estacoes(),
                help_text="Estação de QR correspondente na planta do evento.",
                max_length=20,
                verbose_name="ponto no mapa",
            ),
        ),
    ]
