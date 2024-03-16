from django.db import models
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
    
    