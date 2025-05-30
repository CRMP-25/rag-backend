# rag_engine.py

import os
from langchain.prompts import PromptTemplate
import time

def get_rag_response(query: str):
    print(f"\n🔍 Incoming query: {query}")

    # ✅ Set Ollama server URL inside the function
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

    # ✅ Delay imports to avoid crashing before Ollama is up
    from langchain_ollama.embeddings import OllamaEmbeddings
    from langchain_ollama import OllamaLLM
    from langchain_chroma import Chroma

    vectordb = Chroma(
        persist_directory="vector_store",
        embedding_function=OllamaEmbeddings(model="all-minilm")
    )

    docs_and_scores = vectordb.similarity_search_with_score(query, k=3)

    if not docs_and_scores:
        print("⚠️ No documents returned from vector search.")
        return "⚠️ Sorry, I couldn't find anything relevant in the documents."

    for i, (doc, score) in enumerate(docs_and_scores):
        print(f"→ Doc {i+1} | Score: {score:.4f}\n{doc.page_content[:300]}...\n")

    relevant_docs = [doc.page_content for doc, score in docs_and_scores if score < 50]
    if not relevant_docs:
        return "⚠️ Sorry, I couldn't find anything relevant in the documents."

    context = "\n---\n".join(relevant_docs)

    prompt_template = PromptTemplate.from_template("""
        You are a helpful assistant for PMT Pro. Use ONLY the below documents to answer the question.

        --- DOCUMENTS ---
        {context}

        --- QUESTION ---
        {query}

        Only answer from the documents above. If you can't find the answer, say: "I'm sorry, I couldn't find that information in the reference documents."
    """)

    final_prompt = prompt_template.format(context=context, query=query)

    try:
        llm = OllamaLLM(model="llama3")
        start = time.time()
        result = llm.invoke(final_prompt)
        print("⏱️ LLM Response Time:", round(time.time() - start, 2), "seconds")
        return result
    except Exception as e:
        print("❌ LLM call failed:", str(e))
        return "⚠️ LLM failed to generate a response. Please check the backend."
