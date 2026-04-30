from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rigging', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='riggedmodel',
            name='detected_pose',
            field=models.CharField(
                blank=True,
                choices=[
                    ('t_pose', 'T-pose'),
                    ('a_pose', 'A-pose'),
                    ('arms_down', 'Arms down'),
                    ('unclear', 'Unclear'),
                ],
                default='unclear',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='riggedmodel',
            name='pose_angle_deg',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='riggedmodel',
            name='pose_confidence',
            field=models.FloatField(default=0.0),
        ),
    ]
