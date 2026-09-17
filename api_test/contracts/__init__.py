"""OAS-2 contract checks shared by HTTP and CI."""
from .documents import ContractError, project_document, load_file
from .validation import lint, validate_response
from .comparison import compare
