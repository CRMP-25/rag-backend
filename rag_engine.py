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

def get_rag_response(query: str):
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

    prompt_template = PromptTemplate.from_template("""...""")

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
