# mcp_server.py  (drop this into your repo)
import os
from typing import Annotated
from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
import markdownify
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, TextContent
from openai import BaseModel
from pydantic import AnyUrl, Field
import readabilipy
from pathlib import Path

# New imports for resume parsing
from pypdf import PdfReader
import docx

# Read secrets from environment (set these in Render)
TOKEN = os.environ.get("TOKEN", "<replace_with_env_TOKEN>")
MY_NUMBER = os.environ.get("MY_NUMBER", "91XXXXXXXXXX")  # {country}{number}, no '+'
RESUME_PATH = os.environ.get("RESUME_PATH", "")  # optional: relative path to resume file

class RichToolDescription(BaseModel):
    description: str
    use_when: str
    side_effects: str | None

class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(token=token, client_id="unknown", scopes=[], expires_at=None)
        return None

# ... (keep Fetch class and fetch() as in your original file) ...
# I assume you keep the Fetch class and fetch tool unchanged - omit here for brevity.

mcp = FastMCP("My MCP Server", auth=SimpleBearerAuthProvider(TOKEN))

ResumeToolDescription = RichToolDescription(
    description="Serve your resume in plain markdown.",
    use_when="Puch (or anyone) asks for your resume; this must return raw markdown, no extra formatting.",
    side_effects=None,
)

# Implemented resume tool:
@mcp.tool(description=ResumeToolDescription.model_dump_json())
async def resume() -> str:
    """
    Return your resume exactly as markdown text.
    Looks for RESUME_PATH env var first, otherwise checks common filenames in repo root.
    Supports: .md, .markdown, .txt, .pdf, .docx
    On failure raises McpError with INTERNAL_ERROR.
    """
    def find_candidate() -> Path | None:
        if RESUME_PATH:
            p = Path(RESUME_PATH)
            if p.exists(): return p
        # common fallback names
        candidates = ["resume.md", "Resume.md", "resume.markdown", "resume.txt", "resume.pdf", "resume.docx"]
        for name in candidates:
            p = Path(name)
            if p.exists(): return p
        # fallback to any file that starts with "resume"
        for p in Path(".").iterdir():
            if p.is_file() and p.name.lower().startswith("resume"):
                return p
        return None

    p = find_candidate()
    if not p:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Resume file not found. Add resume.md/pdf/docx to project root or set RESUME_PATH env var."))

    try:
        suffix = p.suffix.lower()
        if suffix in (".md", ".markdown", ".txt"):
            return p.read_text(encoding="utf-8")
        if suffix == ".pdf":
            reader = PdfReader(str(p))
            pages = [page.extract_text() or "" for page in reader.pages]
            # Basic cleanup: join pages with blank line
            return "\n\n".join(pages).strip()
        if suffix == ".docx":
            doc = docx.Document(str(p))
            paragraphs = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
            return "\n\n".join(paragraphs).strip()
        # fallback to raw text
        return p.read_text(errors="ignore")
    except Exception as e:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to read resume: {e}"))

@mcp.tool
async def validate() -> str:
    return MY_NUMBER

# (Keep your Fetch tool here — unchanged.)

async def main():
    # Render will provide $PORT; default to 8085 locally
    port = int(os.environ.get("PORT", "8085"))
    await mcp.run_async("streamable-http", host="0.0.0.0", port=port)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
