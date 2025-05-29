# from langchain_community.document_loaders import UnstructuredWordDocumentLoader

# def test_doc_loading():
#     loader = UnstructuredWordDocumentLoader("documents/PMT_FAQ.docx")
#     docs = loader.load()

#     print(f"✅ Loaded {len(docs)} document(s).")
#     for i, doc in enumerate(docs):
#         print(f"\n--- Document {i+1} ---\n")
#         print(doc.page_content[:1000])  # show first 1000 characters

# if __name__ == "__main__":
#     test_doc_loading()


import os
from langchain_community.document_loaders import Docx2txtLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

# ✅ Make sure LangChain hits the correct Ollama endpoint
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

def build_vector_store():
    loader1 = Docx2txtLoader("documents/PMT_FAQ.docx")
    loader2 = Docx2txtLoader("documents/Status_15MAY.docx")
    docs = loader1.load() + loader2.load()

    embeddings = OllamaEmbeddings(model="all-minilm")

    vectordb = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory="vector_store"
    )

    print(f"✅ Loaded {len(docs)} documents into vector store.")

if __name__ == "__main__":
    build_vector_store()
    print("✅ Vector DB built and saved.")


