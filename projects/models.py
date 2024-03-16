from django.db import models
from openai import OpenAI
from django.conf import settings

class Project(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Document(models.Model):
    project = models.ForeignKey(Project, related_name='documents', on_delete=models.CASCADE)
    file = models.FileField(upload_to='documents/')  
    name = models.CharField(max_length=255) 

    def __str__(self):
        return self.name

class Snippet(models.Model):
    document = models.ForeignKey(Document, related_name='snippets', on_delete=models.CASCADE)
    text = models.TextField()
    
    embeddings = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.text[:50]

    def save(self, *args, **kwargs):
        # Call the superclass save method
        super().save(*args, **kwargs)

        # Now that the snippet is saved, get embeddings if not already present
        if not self.embeddings:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)

            response = client.embeddings.create(
                input=self.text, model="text-embedding-3-small"
            )

            # Assuming response contains the embeddings in the desired format
            self.embeddings = response.data[0].embedding

            # Save the model again with embeddings
            super(Snippet, self).save()
