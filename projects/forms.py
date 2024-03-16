from django import forms
from .models import Project

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name']

class ChatForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'cols': 40}), label='Your Prompt')

class DocumentForm(forms.Form):
    documents = forms.FileField(widget=forms.ClearableFileInput(attrs={'multiple': True}), help_text="Upload up to 20 documents.")
