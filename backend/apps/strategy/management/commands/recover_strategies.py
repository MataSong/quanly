from django.core.management.base import BaseCommand

from apps.strategy.recover import recover_running_runs


class Command(BaseCommand):
    help = "扫描 RUNNING 策略,容器已死则自动重拉(部署/重启后手动恢复用)。"

    def handle(self, *args, **options):
        result = recover_running_runs()
        self.stdout.write(self.style.SUCCESS(f"恢复完成: {result}"))
