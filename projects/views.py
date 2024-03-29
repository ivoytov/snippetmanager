import pandas as pd
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape, mark_safe
from llama_index.core import Document as LlamaDocument
from llama_index.core import (Settings, StorageContext,
                              load_index_from_storage)
from llama_index.core.query_engine import PandasQueryEngine
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.index_store import SimpleIndexStore
from llama_index.core.vector_stores import SimpleVectorStore

from .forms import ChatForm, DocumentForm, ProjectForm
from .models import Document, Project

Settings.chunk_size = 512


def project_list(request):
    projects = Project.objects.all()
    return render(request, "projects/project_list.html", {"projects": projects})


def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    new_documents = project.documents.all()
    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():

            # Handle document file uploads
            new_documents = request.FILES.getlist("documents")
            
            for doc in new_documents:
                if doc.name.endswith(".csv"):
                    document = Document.objects.create(
                        project=project, file=doc, name=doc.name
                    )

            return redirect(
                "project_detail", pk=pk
            )  # Redirect to avoid re-post on refresh
    else:
        form = DocumentForm()

    context = {"project": project, "documents": new_documents, "form": form}
    return render(request, "projects/project_detail.html", context)


def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.save()
            return redirect("project_list")
    else:
        form = ProjectForm()

    return render(request, "projects/project_create.html", {"form": form})


def get_serializable_source_nodes(source_nodes):
    serializable_nodes = []
    for node in source_nodes:
        # Assuming 'metadata' and 'node' are sub-objects we need to access
        serializable_node = {
            "metadata": node.metadata,
            "node": {
                "start_char_idx": node.node.start_char_idx,
                "end_char_idx": node.node.end_char_idx,
            },
        }
        serializable_nodes.append(serializable_node)
    return serializable_nodes


def chat(request, pk):
    project = get_object_or_404(Project, pk=pk)

    #  Conversation key unique to each project
    conversation_key = f"conversation_{pk}"

    if request.method == 'POST' and request.POST.get('action') == 'clear_context':
        request.session.pop(conversation_key, None)
        request.session.modified = True
        return redirect("chat", pk=pk)

    if request.method == "POST" and request.POST.get('action') == 'chat':
        
        form = ChatForm(request.POST)
        if form.is_valid():
            message = form.cleaned_data["message"]

            # get all of the input docs for this project
            docs = project.documents.all()

            query_engine = None
            for doc in docs:
                df = pd.read_csv(doc.file.path, skip_blank_lines=True, index_col=[0])
                print(df)
                query_engine = PandasQueryEngine(df=df, verbose=True)

            if query_engine is None:
                assert False
            response = query_engine.query(
                message,
            )

            # Initialize conversation in session if not exist
            if conversation_key not in request.session:
                request.session[conversation_key] = []

            # Append user message and response to conversation history
            request.session[conversation_key].extend(
                [
                    {"role": "user", "text": message},
                    {
                        "role": "bot",
                        "text": str(response),
                        "source_nodes": None,
                    },
                ]
            )

            # Make session modification to save immediately
            request.session.modified = True

            # Redirect to clear POST data and avoid resubmitting form on refresh
            return redirect("chat", pk=pk)

    else:
        form = ChatForm()

    context = {
        "form": form,
        "project": project,
        "conversation": request.session.get(conversation_key, []),
    }
    return render(request, "projects/chat.html", context)


def delete_document(request, project_id, document_id):
    if request.method == "POST":  # Ensure the request to delete is via POST
        project = get_object_or_404(Project, pk=project_id)
        document = get_object_or_404(Document, pk=document_id, project=project)
        document.delete()  # This deletes the document object from the database
        
        return HttpResponseRedirect(
            reverse("project_detail", args=[project_id])
        )  # Redirect to project's detail view


def read_document(request, project_id, document_id):
    document = get_object_or_404(Document, pk=document_id)
    start_char_idx = request.GET.get("start_char_idx", None)
    end_char_idx = request.GET.get("end_char_idx", None)

    content = escape(document.content)

    # If both start and end indices are provided
    if start_char_idx and end_char_idx:
        start_char_idx = int(start_char_idx)
        end_char_idx = int(end_char_idx)

        # Validate indices
        if (
            start_char_idx < 0
            or end_char_idx > len(content)
            or start_char_idx > end_char_idx
        ):
            raise Http404("Invalid character indices provided.")

        # Insert <mark> tag for highlighting
        pre_highlight = content[:start_char_idx]
        highlighted_text = content[start_char_idx:end_char_idx]
        post_highlight = content[end_char_idx:]
        highlighted_text = (
            f'<span id="highlight"><mark>{highlighted_text}</mark></span>'
        )
        content = f"{pre_highlight}{highlighted_text}{post_highlight}"

    content = content.replace("\n", "<br>")
    return HttpResponse(mark_safe(content), content_type="text/html")
