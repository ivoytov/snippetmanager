import logging

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from llama_index.core import Document as LlamaDocument
from llama_index.core import (Settings, StorageContext, VectorStoreIndex,
                              get_response_synthesizer,
                              load_index_from_storage)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.index_store import SimpleIndexStore
from llama_index.core.vector_stores import SimpleVectorStore

from .forms import ChatForm, DocumentForm, ProjectForm
from .models import Document, Project


Settings.chunk_size = 512


# Get an instance of a logger
logger = logging.getLogger("file_chunking")


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
            llama_docs = []
            for doc in new_documents:
                logger.debug(f"Processing document: {doc.name}, size: {doc.size}")

                document = Document.objects.create(
                    project=project, file=doc, name=doc.name
                )
                doc.seek(0)
                content = doc.read().decode("utf-8")
                llama_docs.append(
                    LlamaDocument(
                        text=content, doc_id=document.pk, metadata={"name": doc.name}
                    )
                )

            # create parser and parse document into nodes
            parser = SentenceSplitter(chunk_size=512)
            nodes = parser.get_nodes_from_documents(llama_docs)

            try:
                storage_context = StorageContext.from_defaults(
                    docstore=SimpleDocumentStore(),
                    vector_store=SimpleVectorStore(),
                    index_store=SimpleIndexStore(),
                    persist_dir="./storage")
            except FileNotFoundError:
                # create storage context using default stores
                storage_context = StorageContext.from_defaults(
                    docstore=SimpleDocumentStore(),
                    vector_store=SimpleVectorStore(),
                    index_store=SimpleIndexStore(),
                )

            # create (or load) docstore and add nodes
            storage_context.docstore.add_documents(nodes)

            # build index
            index = VectorStoreIndex(nodes, storage_context=storage_context)

            # can also set index_id to save multiple indexes to the same folder
            index.set_index_id(pk)
            index.storage_context.persist(persist_dir="./storage")

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


def chat(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        form = ChatForm(request.POST)
        if form.is_valid():
            message = form.cleaned_data["message"]

            # to load index later, make sure you setup the storage context
            # this will loaded the persisted stores from persist_dir
            storage_context = StorageContext.from_defaults(persist_dir="./storage")

            # then load the index object
            # if loading an index from a persist_dir containing multiple indexes
            index = load_index_from_storage(storage_context, index_id=f"{pk}")

            # configure retriever
            retriever = VectorIndexRetriever(
                index=index,
                similarity_top_k=10,
            )

            # configure response synthesizer
            response_synthesizer = get_response_synthesizer(
                response_mode="compact",
            )

            # assemble query engine
            query_engine = RetrieverQueryEngine(
                retriever=retriever,
                response_synthesizer=response_synthesizer,
            )

            # query
            response = query_engine.query(message)
            return render(
                request,
                "chat_results.html",
                {
                    "form": form,
                    "response": response,
                    "used_snippets": response.source_nodes,
                    "project_id": project.pk
                },
            )

    else:
        form = ChatForm()

    context = {"form": form, "project": project}
    return render(request, "projects/chat.html", context)




def delete_document(request, project_id, document_id):
    if request.method == "POST":  # Ensure the request to delete is via POST
        project = get_object_or_404(Project, pk=project_id)
        document = get_object_or_404(Document, pk=document_id, project=project)
        document.delete()  # This deletes the document object from the database
        # update index
        storage_context = StorageContext.from_defaults(persist_dir="./storage")
        index = load_index_from_storage(storage_context, index_id=f"{project_id}")
        index.delete_ref_doc(f"{document_id}")

        return HttpResponseRedirect(
            reverse("project_detail", args=[project_id])
        )  # Redirect to project's detail view
