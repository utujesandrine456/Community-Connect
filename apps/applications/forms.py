import os
from django import forms
from django.core.exceptions import ValidationError
from .models import Application, AssistanceCategory

ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.docx', '.txt'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class CitizenApplicationForm(forms.ModelForm):
    document = forms.FileField(
        required=False,
        help_text="Optional supporting document (PDF, PNG, JPG, DOCX, TXT; max 10MB)",
        widget=forms.FileInput(attrs={'class': 'form-input'})
    )

    class Meta:
        model = Application
        fields = ['full_name', 'phone', 'email', 'location', 'category', 'description']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Jane Doe'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. (555) 123-4567'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'e.g. jane@example.com (optional)'}),
            'location': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. North District, Ward 4'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': 'Please describe what assistance you need and why...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = AssistanceCategory.objects.filter(is_active=True)
        self.fields['category'].empty_label = "-- Select Type of Assistance --"
        self.fields['email'].required = False

    def clean_document(self):
        doc = self.cleaned_data.get('document')
        if doc:
            if doc.size > MAX_UPLOAD_SIZE:
                raise ValidationError("File is too large. Maximum size is 10 MB.")
            ext = os.path.splitext(doc.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise ValidationError(
                    f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                )
        return doc


class StatusLookupForm(forms.Form):
    reference = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. APP-A1B2C3'})
    )
    access_token = forms.CharField(
        max_length=64,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Enter your secure access token'})
    )

    def clean_reference(self):
        return self.cleaned_data['reference'].strip().upper()

    def clean_access_token(self):
        return self.cleaned_data['access_token'].strip().lower()
