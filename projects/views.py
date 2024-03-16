from django.shortcuts import render, redirect, get_object_or_404
from .models import Project, Snippet, Document
from .forms import ProjectForm, ChatForm, DocumentForm
from django.http import HttpResponse
from urllib.parse import unquote
from openai import OpenAI
from django.conf import settings
from scipy.spatial.distance import cosine
import pdb
import heapq
import logging
import os.path
from llama_index.core import (
    VectorStoreIndex,
    Document as LlamaDocument,
    StorageContext,
    load_index_from_storage,
    Settings,
)
from llama_index.core import load_index_from_storage
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.index_store import SimpleIndexStore
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import VectorStoreIndex, get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine



# Get an instance of a logger
logger = logging.getLogger("file_chunking")
Settings.chunk_size = 1000


def create_snippets_from_content(content, document):
    chunk_size = 1000
    overlap = int(chunk_size * 0.2)
    position = 0
    while position < len(content):
        chunk_end = position + chunk_size
        snippet_text = content[position : chunk_end + overlap]
        Snippet.objects.create(text=snippet_text, document=document)
        position += chunk_size - overlap


def project_list(request):
    projects = Project.objects.all()
    return render(request, "projects/project_list.html", {"projects": projects})


def project_detail(request, pk):
    global vector_index
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
                        text=content, metadata={"filename": doc.file, "name": doc.name}
                    )
                )
                create_snippets_from_content(content, document)

            # create parser and parse document into nodes
            parser = SentenceSplitter()
            nodes = parser.get_nodes_from_documents(llama_docs)

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
            chat_gpt_response, used_snippets = (
                "",
                [],
            )  # Placeholder for the ChatGPT response and used snippets

            # Convert text to embeddings using OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)

            response = client.embeddings.create(
                input=message, model="text-embedding-3-small"
            )

            # Assuming response contains the embeddings in the desired format
            user_embedding = response.data[0].embedding

            # Find up to 10 most similar snippets
            snippets = []
            for snippet in Snippet.objects.filter(document__project_id=project.pk):
                if snippet.embeddings:  # Ensure the snippet has embeddings
                    similarity = 1 - cosine(snippet.embeddings, user_embedding)
                    if similarity > 0.3:
                        # Using a min heap to keep top 3 most similar snippets
                        heapq.heappush(snippets, (similarity, snippet))
                        if len(snippets) > 10:
                            heapq.heappop(
                                snippets
                            )  # Remove snippet with lowest similarity if more than 3

            # If we found similar snippets, prepare prompt for ChatGPT
            if snippets:
                combined_prompt = "Based on the following snippets: \n"
                snippets.sort(reverse=True)  # Get snippets sorted by similarity
                for _, snippet in snippets:
                    combined_prompt += f"\n- {snippet.text}"
                    used_snippets.append(snippet)

                snippets.sort(reverse=True)
                combined_prompt += f"\n\n{message}"

                # Now, generate a response from ChatGPT
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": combined_prompt},
                    ],
                )

                chat_gpt_response = response.choices[0].message.content

            else:
                chat_gpt_response = (
                    "I couldn't find similar snippets. How can I assist you?"
                )

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
                response_mode="refine",
            )

            # assemble query engine
            query_engine = RetrieverQueryEngine(
                retriever=retriever,
                response_synthesizer=response_synthesizer,
            )

            # query
            llama_response = query_engine.query(message)
            pdb.set_trace()
            return render(
                request,
                "chat_results.html",
                {
                    "form": form,
                    "response": chat_gpt_response,
                    "llama_response": llama_response,
                    "used_snippets": used_snippets,
                },
            )

    else:
        form = ChatForm()

    context = {"form": form, "project": project}
    return render(request, "projects/chat.html", context)
