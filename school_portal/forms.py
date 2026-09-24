from django import forms


class ADLoginForm(forms.Form):
    username = forms.CharField(
        label="Username",
        max_length=128,
        widget=forms.TextInput(attrs={"autofocus": "autofocus", "placeholder": "Username"}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Password"}),
    )


class ADAuthenticationTestForm(forms.Form):
    username = forms.CharField(
        label="اسم مستخدم Active Directory",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "اسم المستخدم"}),
    )
    password = forms.CharField(
        label="كلمة المرور",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "تُستخدم للتحقق فقط"}),
    )
