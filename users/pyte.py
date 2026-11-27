from users.models import User
list(User.objects.filter(role__in=["MANAGER", "ADMIN"]).values("email", "role", "is_active"))
