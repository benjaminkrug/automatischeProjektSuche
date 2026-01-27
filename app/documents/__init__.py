"""Documents module - Application document generation."""

from app.documents.generator import generate_application_folder, list_application_folders
from app.documents.word_handler import fill_anschreiben, create_template_if_missing

__all__ = [
    "generate_application_folder",
    "list_application_folders",
    "fill_anschreiben",
    "create_template_if_missing",
]
