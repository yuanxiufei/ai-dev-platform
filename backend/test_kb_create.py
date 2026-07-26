import asyncio
import traceback
from app.core.rag.knowledge_base import get_knowledge_base

async def main():
    try:
        mgr = get_knowledge_base()
        print("mgr init ok")
        kb = await mgr.create(name='test_manual', description='test')
        print("created:", kb)
    except Exception as e:
        traceback.print_exc()
        print("ERROR:", e)

asyncio.run(main())
