import pandas as pd
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape, mark_safe
from llama_index.agent.openai import OpenAIAgentWorker
from llama_index.core import Settings
from llama_index.core.agent import AgentRunner
from llama_index.core.query_engine import PandasQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.llms.openai import OpenAI

from .forms import ChatForm, DocumentForm, DocumentSelectionForm, ProjectForm
from .models import Document, Project

Settings.chunk_size = 512
# Settings.llm = OpenAI(temperature=0, model="gpt-4-0125-preview", max_tokens=512)


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


def get_serializable_steps(tool_output):
    serializable_tools = []
    for tool in tool_output:
        # Assuming 'metadata' and 'node' are sub-objects we need to access
        serializable_tool = {
            "content": tool.content,
            "raw_input": tool.raw_input["input"],
            "raw_output": tool.raw_output.response,
            "metadata": {
                "pandas_instruction_str": tool.raw_output.metadata[
                    "pandas_instruction_str"
                ],
                "raw_pandas_output": tool.raw_output.metadata["raw_pandas_output"],
            },
        }
        serializable_tools.append(serializable_tool)
    return serializable_tools


def chat(request, pk):
    project = get_object_or_404(Project, pk=pk)

    #  Conversation key unique to each project
    conversation_key = f"conversation_{pk}"
    selected_documents_key = f"selected_docs_{pk}"

    if request.method == "POST" and request.POST.get("action") == "clear_context":
        request.session.pop(conversation_key, None)
        request.session.modified = True
        return redirect("chat", pk=pk)

    if request.method == "POST" and request.POST.get("action") == "clear_documents":
        request.session.pop(selected_documents_key, None)
        request.session.modified = True
        return redirect("chat", pk=pk)

    # If the document selection hasn't been made, show or process the selection form
    if selected_documents_key not in request.session:
        if request.method == "POST":
            doc_form = DocumentSelectionForm(request.POST, project_id=pk)
            if doc_form.is_valid():
                request.session[selected_documents_key] = [
                    doc_form.cleaned_data["document_1"].id,
                    doc_form.cleaned_data["document_2"].id,
                ]
                request.session.modified = True
                return redirect("chat", pk=pk)
        else:
            doc_form = DocumentSelectionForm(project_id=pk)

        return render(request, "projects/document_selection.html", {"form": doc_form})

    if request.method == "POST" and request.POST.get("action") == "chat":

        form = ChatForm(request.POST)
        if form.is_valid():
            message = form.cleaned_data["message"]

            # get all of the input docs for this project
            left_doc_id, right_doc_id = request.session[selected_documents_key]
            left_doc = project.documents.get(id=left_doc_id)
            right_doc = project.documents.get(id=right_doc_id)

            left_df = pd.read_csv(
                left_doc.file.path, skip_blank_lines=True, index_col=[0]
            ).astype(float)
            left_query_engine = PandasQueryEngine(df=left_df, verbose=True)

            right_df = pd.read_csv(
                right_doc.file.path, skip_blank_lines=True, index_col=[0]
            ).astype(float)
            right_query_engine = PandasQueryEngine(df=right_df, verbose=True)

            tools = [
                QueryEngineTool(
                    query_engine=left_query_engine,
                    metadata=ToolMetadata(
                        name="internal_model",
                        description="Provides information about our internal model for the target company. "
                        "Use a detailed plain text question as input to the tool.",
                    ),
                ),
                QueryEngineTool(
                    query_engine=right_query_engine,
                    metadata=ToolMetadata(
                        name="external_model",
                        description="Provides information about an external model for the target company. "
                        "Use a detailed plain text question as input to the tool.",
                    ),
                ),
            ]

            # initialize ReAct agent
            openai_step_engine = OpenAIAgentWorker.from_tools(tools, verbose=True)
            agent = AgentRunner(openai_step_engine)
            # agent = ReActAgent.from_tools(query_engine_tools, verbose=True)

            task = agent.create_task(message)

            # execute step
            response = None
            while response is None:
                step_output = agent.run_step(task.task_id)

                # if step_output is done, finalize response
                if step_output.is_last:
                    response = agent.finalize_response(task.task_id)

            # list tasks
            # task.list_tasks()

            # get completed steps
            # task.get_completed_steps(task.task_id)

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
                        "source_tools": get_serializable_steps(
                            step_output.output.sources
                        ),
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
