from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("project/<int:pk>/", views.project_detail, name="project_detail"),
    path("project/new/", views.project_create, name="project_create"),
    path("project/<int:pk>/chat/", views.chat, name="chat"),
    path('project/<int:project_id>/document/<int:document_id>/delete/', views.delete_document, name='delete_document'),
    path('project/<int:project_id>/document/<int:document_id>', views.read_document, name='read_document'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
