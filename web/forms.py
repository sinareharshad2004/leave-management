from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from users.enums import Role
User = get_user_model()


class EmployeeRegisterForm(forms.Form):
    """Public sign-up. The role is never a form field; it is fixed by the form class."""

    role = "EMPLOYEE"

    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(
        label="Confirm password", strip=False, widget=forms.PasswordInput
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                try:
                    validate_password(
                        p1, User(name=cleaned.get("name", ""), email=cleaned.get("email", ""))
                    )
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            name=self.cleaned_data["name"],
            password=self.cleaned_data["password1"],
            role=self.role,
        )

class ManagerRegisterForm(EmployeeRegisterForm):
     """Used only by the admin-only 'Register Manager' page."""
     role=Role.MANAGER

 

