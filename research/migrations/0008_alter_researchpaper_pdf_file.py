
import research.validators
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('research', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='researchpaper',
            name='pdf_file',
            field=models.FileField(blank=True, null=True, upload_to='papers_pdf/', validators=[research.validators.validate_file_size]),
        ),
    ]
