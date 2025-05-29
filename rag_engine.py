import os
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate
import time

# ✅ Set Ollama server URL (required)
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

def get_rag_response(query: str):
    print(f"\n🔍 Incoming query: {query}")
    
    # ✅ Load Vector Store
    vectordb = Chroma(
        persist_directory="vector_store",
        embedding_function=OllamaEmbeddings(model="all-minilm")
    )

    # ✅ Search top 3 relevant documents
    docs_and_scores = vectordb.similarity_search_with_score(query, k=3)

    if not docs_and_scores:
        print("⚠️ No documents returned from vector search.")
        return "⚠️ Sorry, I couldn't find anything relevant in the documents."

    # ✅ Show debug info
    for i, (doc, score) in enumerate(docs_and_scores):
        print(f"→ Doc {i+1} | Score: {score:.4f}\n{doc.page_content[:300]}...\n")

    # ✅ Filter based on relevance threshold (adjust if needed)
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
        # ✅ Use latest OllamaLLM (safe with future versions)
        # llm = OllamaLLM(model="mistral")  # or "llama2" / "tinyllama"
        llm = OllamaLLM(model="llama3")
        start = time.time()
        print("llm:",llm);
        # llm = OllamaLLM(model="llama2:7b")
        result = llm.invoke(final_prompt)
        print("⏱️ LLM Response Time:", round(time.time() - start, 2), "seconds")
        return result
    except Exception as e:
        print("❌ LLM call failed:", str(e))
        return "⚠️ LLM failed to generate a response. Please check the backend."
    

    # if __name__ == "__main__":
    # # Run a basic LLM test
    #     import time

    #     test_prompt = "Summarize this: PMT is a smart assistant."
    #     print("🧪 Testing LLM with a simple prompt...\n")

    #     try:
    #         start = time.time()
    #         llm = OllamaLLM(model="llama3")  # You can switch to "mistral" or others here
    #         res = llm.invoke(test_prompt)
    #         print("📋 LLM Response:\n", res)
    #         print("⏱️ Response time:", round(time.time() - start, 2), "seconds")
    #     except Exception as e:
    #         print("❌ LLM test failed:", str(e))

