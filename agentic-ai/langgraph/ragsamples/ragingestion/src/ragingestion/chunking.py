"""Step 2 - CHUNK. Pick a strategy per upload; compare their retrieval quality in the UI."""

from langchain_core.documents import Document
from langchain_text_splitters import (
    CharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)

STRATEGIES = {
    "recursive": "Split on paragraphs, then sentences, then words (best general default)",
    "markdown": "Split on # headings first, then recursively; heading path kept in metadata",
    "token": "Fixed token windows (exact embedding-model budgets)",
    "fixed": "Fixed character windows on blank lines (simplest baseline)",
}


def chunk(docs: list[Document], strategy: str = "recursive", size: int = 800, overlap: int = 100) -> list[Document]:
    if strategy == "recursive":
        splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
        out = splitter.split_documents(docs)
    elif strategy == "token":
        out = TokenTextSplitter(chunk_size=size, chunk_overlap=overlap).split_documents(docs)
    elif strategy == "fixed":
        out = CharacterTextSplitter(separator="\n\n", chunk_size=size, chunk_overlap=overlap).split_documents(docs)
    elif strategy == "markdown":
        md = MarkdownHeaderTextSplitter([("#", "h1"), ("##", "h2"), ("###", "h3")], strip_headers=False)
        sections: list[Document] = []
        for d in docs:
            for s in md.split_text(d.page_content):
                s.metadata = {**d.metadata, **s.metadata}
                sections.append(s)
        out = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap).split_documents(sections)
    else:
        raise ValueError(f"Unknown strategy {strategy!r}; choose from {list(STRATEGIES)}")

    for i, d in enumerate(out):
        d.metadata["chunk_index"] = i
        d.metadata["chunk_strategy"] = strategy
    return out
