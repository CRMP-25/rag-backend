from typing import List, Dict
import os
import time
import requests
from langchain.prompts import PromptTemplate

def wait_for_ollama(timeout=30):
    print("⏳ Waiting for Ollama to be ready...")
    for _ in range(timeout):
        try:
            r = requests.get("http://localhost:11434")
            if r.status_code == 200:
                print("✅ Ollama is ready.")
                return True
        except:
            pass
        time.sleep(1)
    print("❌ Ollama did not start in time.")
    return False

def get_rag_response(query: str, user_context: str = ""):

    print("🚨 USING UPDATED CODE VERSION")
    print(f"\n🔍 Incoming query: {query}")

    if not wait_for_ollama():
        return "⚠️ Ollama is not responding. Please try again later."

    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

    from langchain_ollama.embeddings import OllamaEmbeddings
    from langchain_ollama import OllamaLLM
    from langchain_chroma import Chroma

    vectordb = Chroma(
        persist_directory="vector_store",
        embedding_function=OllamaEmbeddings(model="all-minilm")
    )

    docs = vectordb.similarity_search(query, k=3)

    if not docs:
        print("⚠️ No documents returned from vector search.")
        return "⚠️ Sorry, I couldn't find anything relevant in the documents."

    for i, doc in enumerate(docs):
        print(f"→ Doc {i+1}:\n{doc.page_content[:300]}...\n")


    print("🔍 Type of docs[0]:", type(docs[0]))
    print("🔍 docs[0]:", docs[0])
    relevant_docs = [doc.page_content for doc in docs]

    if not relevant_docs:
        return "⚠️ Sorry, I couldn't find anything relevant in the documents."

    doc_context = "\n---\n".join(relevant_docs)
    context = f"{user_context}\n\n--- DOCUMENT CONTEXT ---\n{doc_context}"


    prompt_template = PromptTemplate.from_template("""
            You are a helpful assistant for PMT Pro. Use the context below to answer the user's question.
            You may refer to either the USER CONTEXT or the DOCUMENT CONTEXT.

            --- USER CONTEXT ---
            {context}

            --- QUESTION ---
            {query}

            Only answer based on the context above. Do not make up information.
            If the answer isn't found, say: "I'm sorry, I couldn't find that information in the context provided."
            """)

    print("🧠 Combined Context Sent to LLM:\n", context[:500], "...\n")

    final_prompt = prompt_template.format(context=context, query=query)

    try:
        llm = OllamaLLM(model="llama3")
        start = time.time()
        result = llm.invoke(final_prompt)
        print("⏱️ LLM Response Time:", round(time.time() - start, 2), "seconds")
        return result
    except Exception as e:
        print("❌ LLM call failed:", str(e))
        return "⚠️ LLM failed to generate a response. Please check the backend"