from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    locale = models.CharField(max_length=8, default="zh-CN")
    theme = models.CharField(max_length=8, default="dark")
