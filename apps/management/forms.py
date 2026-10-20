from django import forms
from django.contrib.auth.forms import AuthenticationForm
from apps.applications.models import Application


class AdminLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Administrator Username',
            'autofocus': True,
            'id': 'admin_username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Administrator Password',
            'id': 'admin_password'
        })
    )


class ApplicationReviewForm(forms.ModelForm):
    status = forms.ChoiceField(
        choices=Application.Status.choices,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'application_status'
        })
    )
    citizen_response = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 4,
            'placeholder': 'Write message or instructions for the citizen (visible when checking status)...',
            'id': 'citizen_response'
        }),
        help_text="Visible to the citizen on the secure status portal."
    )
    internal_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Private administrator notes (internal staff only)...',
            'id': 'internal_notes'
        }),
        help_text="For internal organization records only. Never shown to citizens."
    )

    class Meta:
        model = Application
        fields = ['status', 'citizen_response', 'internal_notes']

    def clean(self):
        cleaned_data = super().clean()
        new_status = cleaned_data.get('status')
        citizen_response = cleaned_data.get('citizen_response', '').strip()

        if self.instance and self.instance.pk:
            current_status = self.instance.status
            if new_status != current_status:
                if not self.instance.can_transition_to(new_status):
                    self.add_error(
                        'status',
                        f"Cannot transition status from '{self.instance.get_status_display()}' to '{dict(Application.Status.choices).get(new_status)}'."
                    )

        if new_status == Application.Status.NEEDS_INFORMATION and not citizen_response:
            self.add_error(
                'citizen_response',
                "Please provide a response explaining what additional information is needed from the citizen."
            )

        if new_status == Application.Status.REJECTED and not citizen_response:
            self.add_error(
                'citizen_response',
                "Please provide a citizen-facing response explaining the reason for rejection."
            )

        return cleaned_data
