from rag_engine import get_rag_response

query = "What is PMT Pro?"
response = get_rag_response(query)

print("\n📘 Final Response:")
print(response)
