from django import forms
from .models import Project, Document

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name']

class ChatForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'cols': 40}), label='Your Prompt')

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class DocumentForm(forms.Form):
    documents = MultipleFileField(help_text="Upload up to 20 documents.", required=False)


class DocumentSelectionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        project_id = kwargs.pop('project_id', None)
        super(DocumentSelectionForm, self).__init__(*args, **kwargs)
        if project_id is not None:
            self.fields['document_1'].queryset = Document.objects.filter(project__id=project_id)
            self.fields['document_2'].queryset = Document.objects.filter(project__id=project_id)
    
    document_1 = forms.ModelChoiceField(queryset=Document.objects.none(), label="Select the internal model")
    document_2 = forms.ModelChoiceField(queryset=Document.objects.none(), label="Select the external model")