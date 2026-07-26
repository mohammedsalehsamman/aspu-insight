
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('research', '0008_alter_researchpaper_pdf_file'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='researchpaper',
            name='assigned_editor',
            field=models.ForeignKey(blank=True, limit_choices_to={'role': 'editor'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_papers', to=settings.AUTH_USER_MODEL),
        ),
    ]
