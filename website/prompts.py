from flask import Blueprint, request, render_template, flash, session, redirect, url_for, current_app
from werkzeug.utils import secure_filename
import os
from .extensions import db
from .models import Prompts, PromptMessages, UploadedFiles
from datetime import datetime
from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from config import ollama_llm
from PyPDF2 import PdfReader

prompts_bp = Blueprint('prompts', __name__, template_folder='templates')
ALLOWED_EXTENSIONS = {'txt', 'pdf'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

llm = LlamaCpp(model_path=ollama_llm, n_gpu_layers=60, n_batch=652, verbose=False)
prompt_template = PromptTemplate(template="Question: {question}\nAnswer:", input_variables=["question"])
llm_chain = LLMChain(prompt=prompt_template, llm=llm)


def process_text_input(text, prompt_id):
    response = llm_chain.run(question=text)
    save_prompt_message(text, response, prompt_id)


def process_file(path, filename, user_id, prompt_id):
    content = read_file(path)
    response = llm_chain.run(question=content)
    save_file_record(filename, path, user_id, prompt_id)
    save_prompt_message(content, response, prompt_id)


def read_file(path):
    if path.endswith('.pdf'):
        reader = PdfReader(path)
        return "".join(page.extract_text() or '' for page in reader.pages)
    elif path.endswith('.txt'):
        with open(path, 'r') as file:
            return file.read()
    return ""


def save_file_record(filename, path, user_id, prompt_id):
    file_record = UploadedFiles(FileName=filename, FilePath=path, UserID=user_id, PromptID=prompt_id,
                                UploadDate=datetime.utcnow())
    db.session.add(file_record)
    db.session.commit()


def save_prompt_message(text, response, prompt_id):
    db.session.add(PromptMessages(PromptID=prompt_id, MessageText=text, IsResponse=False))
    db.session.add(PromptMessages(PromptID=prompt_id, MessageText=response, IsResponse=True))
    db.session.commit()


@prompts_bp.route('/start-new-prompt')
def start_new_prompt():
    session.pop('prompt_id', None)
    return redirect(url_for('prompts.chat'))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@prompts_bp.route('/load-prompt/<int:prompt_id>')
def load_prompt(prompt_id):
    session['prompt_id'] = prompt_id
    return redirect(url_for('prompts.chat'))


@prompts_bp.route('/delete-prompt/<int:prompt_id>', methods=['POST'])
def delete_prompt(prompt_id):
    # Find the prompt
    prompt = Prompts.query.filter_by(PromptID=prompt_id).first()
    if prompt:
        # Delete associated uploaded files first
        UploadedFiles.query.filter_by(PromptID=prompt_id).delete()

        # Delete associated messages
        PromptMessages.query.filter_by(PromptID=prompt_id).delete()

        # Now delete the prompt
        db.session.delete(prompt)
        db.session.commit()
        flash('Prompt and all associated messages and files have been deleted.', 'success')

        # Clear session if the deleted prompt was the currently loaded one
        if session.get('prompt_id') == prompt_id:
            session.pop('prompt_id', None)
    else:
        flash('Prompt not found.', 'error')

    return redirect(url_for('prompts.chat'))
