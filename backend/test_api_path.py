import asyncio
import traceback
import sys
sys.path.insert(0, '.')

async def test():
    try:
        # same path as route handler
        from app.api.routes.rag.knowledge_bases import CreateKBRequest
        from app.core.rag.knowledge_base import get_knowledge_base
        
        body = CreateKBRequest(name="test_diag", description="diag test")
        mgr = get_knowledge_base()
        kb = await mgr.create(
            name=body.name,
            description=body.description,
            dedup_method=body.dedup_method,
            embedding_model=body.embedding_model,
            segment_strategy=body.segment_strategy,
            metadata_schema=body.metadata_schema,
            default_retrieval_strategy=body.default_retrieval_strategy,
            storage_schema=body.storage_schema,
        )
        print("SUCCESS:", kb)
    except Exception:
        traceback.print_exc()

asyncio.run(test())
