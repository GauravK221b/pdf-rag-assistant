
import os
import time
import numpy as np
import faiss

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from google import genai
from groq import Groq
from dotenv import load_dotenv


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")


client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

model = SentenceTransformer("all-MiniLM-L6-v2")


def chunking(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap

    return chunks


def process_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    store_chunk = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()

        if not text:
            continue

        chunks = chunking(text)

        for chunk in chunks:
            store_chunk.append({
                "page_no": i + 1,
                "text": chunk
            })

    if not store_chunk:
        raise ValueError("No extractable text found in this PDF.")

    return store_chunk


def create_embeddings(store_chunk):
    texts = [item["text"] for item in store_chunk]

    embeddings = model.encode(
        texts,
        convert_to_numpy=True
    ).astype(np.float32)

    return embeddings


def create_faiss_index(embeddings):
    embeddings = embeddings.copy()

    faiss.normalize_L2(embeddings)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    return index


def search(query, model, index, store_chunk, k=3):
    query_encode = model.encode(query)

    query_encode = np.array(
        query_encode,
        dtype=np.float32
    ).reshape(1, -1)

    faiss.normalize_L2(query_encode)

    k = min(k, len(store_chunk))

    scores, indices = index.search(query_encode, k)

    results = []

    for rank, i in enumerate(indices[0]):
        if i == -1:
            continue

        results.append({
            "text": store_chunk[i]["text"],
            "page_no": store_chunk[i]["page_no"],
            "score": float(scores[0][rank])
        })

    return results



def generate_llm_response(prompt):

    # Primary provider: Gemini (one attempt)
    try:
        print("Trying Gemini...")

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        if response.text:
            print("Answer generated using Gemini.")
            return response.text, "Gemini"

        raise ValueError("Gemini returned an empty response.")

    except Exception as e:
        print(f"Gemini failed: {e}")
        print("Switching to Groq...")

    # Fallback provider: Groq
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a PDF question-answering assistant. "
                        "Answer only using the supplied PDF context. "
                        "Do not use outside knowledge. "
                        "If the answer is unavailable in the context, "
                        "say: I don't know based on the provided PDF."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        answer = response.choices[0].message.content

        if not answer:
            raise ValueError("Groq returned an empty response.")

        print("Answer generated using Groq.")
        return answer, "Groq"

    except Exception as e:
        print(f"Groq failed: {e}")

        raise RuntimeError(
            "Both Gemini and Groq are currently unavailable."
        )


def generate_answer(query, model, index, store_chunk):

    start = time.time()

    results = search(
        query,
        model,
        index,
        store_chunk,
        k=3
    )

    retrieval_time = time.time()
    print("Retrieval time:", retrieval_time - start)

    context = ""

    for result in results:
        context += f"""
Page: {result['page_no']}
Content: {result['text']}
"""

    prompt = f"""
You are a PDF question-answering assistant.

Answer using ONLY the provided context.
Do not use outside knowledge.

If the answer is unavailable, say:
"I don't know based on the provided PDF."

Context:
{context}

Question:
{query}

Answer:
"""

    answer, provider = generate_llm_response(prompt)

    end = time.time()

    print("Total time:", end - start)

    return answer, results, provider


def build_rag_pipeline(pdf_file):

    store_chunk = process_pdf(pdf_file)

    embeddings = create_embeddings(store_chunk)

    index = create_faiss_index(embeddings)

    return index, store_chunk
