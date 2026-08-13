"""
Management command: seed_admin

读取环境变量，创建/更新超管账号 + 内置 admin 系统角色（含全部权限点）。
幂等：可重复执行。
"""
import logging
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.accounts.models import Role, UserProfile, UserRole
from core.accounts.permissions_registry import ALL_PERMISSION_CODES

log = logging.getLogger("quanly.management.seed_admin")
User = get_user_model()


class Command(BaseCommand):
    help = "Seed superadmin user + built-in admin role (idempotent)"

    def handle(self, *args, **options):
        self._seed_admin_role()
        self._seed_admin_user()

    def _seed_admin_role(self):
        """确保 is_system=True 的 admin 角色存在并含全部权限点。"""
        all_perms = sorted(ALL_PERMISSION_CODES)
        role, created = Role.objects.update_or_create(
            name="admin",
            defaults={
                "permissions": all_perms,
                "is_system": True,
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} system role 'admin' with {len(all_perms)} permissions."
            )
        )
        return role

    def _seed_admin_user(self):
        username = os.environ.get("QUANLY_ADMIN_USER", "admin")
        password = os.environ.get("QUANLY_ADMIN_PASSWORD", "")
        email = os.environ.get("QUANLY_ADMIN_EMAIL", "admin@quanly.local")

        if not password:
            self.stdout.write(
                self.style.WARNING(
                    "QUANLY_ADMIN_PASSWORD not set; skipping user seed."
                )
            )
            return

        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "is_superuser": True,
                "is_staff": True,
                "is_active": True,
            },
        )
        # 只在首次创建时设密码,避免每次容器重启覆盖运维手动改过的密码。
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])

        # 确保 UserProfile 存在
        UserProfile.objects.get_or_create(
            user=user,
            defaults={"auth_source": "local"},
        )

        # 绑定 admin 系统角色
        admin_role = Role.objects.filter(name="admin", is_system=True).first()
        if admin_role:
            UserRole.objects.get_or_create(user=user, role=admin_role)

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} superadmin user '{username}'."
            )
        )
