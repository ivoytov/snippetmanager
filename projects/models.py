from django.db import models
from django.conf import settings
import os

def documents_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/documents/project_id_<id>/<filename>
    return f'documents/project_id_{instance.project.id}/{filename}'

class Project(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Document(models.Model):
    project = models.ForeignKey(Project, related_name='documents', on_delete=models.CASCADE)
    file = models.FileField(upload_to=documents_directory_path)  
    name = models.CharField(max_length=255) 
    content = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    

    def delete(self, using=None, keep_parents=False):
        """
        Override the delete method to remove the file from the filesystem
        on object deletion.
        """
        # construct file path
        this_file_path = self.file.path
        # delete the file from the filesystem
        if os.path.isfile(this_file_path):
            os.remove(this_file_path)

        # Now call the superclass method to delete the object
        super().delete(using=using, keep_parents=keep_parents)

    
    