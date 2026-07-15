"""Build the RAG crop-knowledge index.

Run once after editing knowledge/crops_seed.json or dropping PDFs into
knowledge/.  Needs VOYAGE_API_KEY in .env.

    python build_knowledge.py
"""

from dotenv import load_dotenv

from app.services import knowledge

if __name__ == "__main__":
    load_dotenv()
    count = knowledge.build_index()
    print(f"Indexed {count} knowledge chunks -> data/knowledge_index.npz")
