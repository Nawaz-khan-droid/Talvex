"""
FastAPI router for FAISS vector search.
Endpoints:
  POST /api/search/similar  - Search for similar jobs/applications
  POST /api/search/index    - Add documents to FAISS index
  GET  /api/search/stats    - Get index statistics
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Application
from services.vector_search import vector_search_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


# ============================================================
# Request / Response Schemas
# ============================================================

class SimilarSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    app_id: Optional[str] = Field(None, alias="appId", description="Exclude this app from results")

    model_config = ConfigDict(populate_by_name=True)


class IndexDocumentRequest(BaseModel):
    doc_id: str = Field(..., alias="docId")
    text: str = Field(..., min_length=1)
    metadata: Optional[dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True)


class IndexBatchRequest(BaseModel):
    documents: list[IndexDocumentRequest] = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class SearchResultItem(BaseModel):
    id: str
    score: float
    text: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class SimilarSearchResponse(BaseModel):
    results: list[SearchResultItem]
    total_indexed: int


class IndexResponse(BaseModel):
    success: bool
    index_id: int = Field(alias="indexId")
    total_documents: int = Field(alias="totalDocuments")

    model_config = ConfigDict(populate_by_name=True)


class IndexBatchResponse(BaseModel):
    success: bool
    added_count: int = Field(alias="addedCount")
    total_documents: int = Field(alias="totalDocuments")

    model_config = ConfigDict(populate_by_name=True)


class IndexStatsResponse(BaseModel):
    total_documents: int = Field(alias="totalDocuments")
    dimension: int
    index_type: str = Field(alias="indexType")

    model_config = ConfigDict(populate_by_name=True)


# ============================================================
# Endpoints
# ============================================================

def _is_admin(current_user: dict) -> bool:
    return current_user.get("role") == "admin"


@router.post("/similar", response_model=SimilarSearchResponse)
def search_similar(request: SimilarSearchRequest, current_user: dict = Depends(get_current_user)):
    """Search for similar job descriptions/applications using FAISS vector search."""
    try:
        results = vector_search_service.search(
            query=request.query,
            top_k=request.top_k,
        )

        # Filter out the requesting app if specified
        if request.app_id:
            results = [r for r in results if r["id"] != request.app_id]

        formatted = [
            SearchResultItem(
                id=r["id"],
                score=r["score"],
                text=r.get("text"),
                metadata=r.get("metadata"),
            )
            for r in results
        ]

        stats = vector_search_service.get_index_stats()

        return SimilarSearchResponse(
            results=formatted,
            total_indexed=stats["totalDocuments"],
        )
    except Exception as e:
        logger.error(f"Similar search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(e)}")


@router.post("/index", response_model=IndexResponse)
def index_document(request: IndexDocumentRequest, current_user: dict = Depends(get_current_user)):
    """Add a single document to the FAISS search index."""
    try:
        metadata = request.metadata or {}
        metadata["text"] = request.text  # Store text for index rebuilding

        idx = vector_search_service.add_document(
            doc_id=request.doc_id,
            text=request.text,
            metadata=metadata,
        )

        if idx < 0:
            raise HTTPException(status_code=400, detail="Empty text content, document not indexed.")

        stats = vector_search_service.get_index_stats()

        return IndexResponse(
            success=True,
            index_id=idx,
            total_documents=stats["totalDocuments"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document indexing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Document indexing failed: {str(e)}")


@router.post("/index/batch", response_model=IndexBatchResponse)
def index_documents_batch(request: IndexBatchRequest, current_user: dict = Depends(get_current_user)):
    """Add multiple documents to the FAISS search index in batch."""
    try:
        documents = []
        for doc in request.documents:
            metadata = doc.metadata or {}
            metadata["text"] = doc.text
            documents.append({
                "id": doc.doc_id,
                "text": doc.text,
                "metadata": metadata,
            })

        added = vector_search_service.add_documents_batch(documents)
        stats = vector_search_service.get_index_stats()

        return IndexBatchResponse(
            success=True,
            added_count=added,
            total_documents=stats["totalDocuments"],
        )
    except Exception as e:
        logger.error(f"Batch indexing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch indexing failed: {str(e)}")


@router.get("/stats", response_model=IndexStatsResponse)
def get_search_stats(current_user: dict = Depends(get_current_user)):
    """Get FAISS index statistics."""
    try:
        stats = vector_search_service.get_index_stats()
        return IndexStatsResponse(
            total_documents=stats["totalDocuments"],
            dimension=stats["dimension"],
            index_type=stats["indexType"],
        )
    except Exception as e:
        logger.error(f"Get index stats failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get index stats: {str(e)}")


@router.post("/reindex")
async def reindex_all_applications(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Reindex all applications from the database into FAISS using semantic embeddings."""
    try:
        from services.vector_search import SemanticVectorSearch

        stmt = select(Application)
        if not _is_admin(current_user):
            stmt = stmt.filter(Application.userId == current_user["user_id"])
        result = await db.execute(stmt)
        applications = result.scalars().all()

        # Build plain dicts that SemanticVectorSearch.reindex_all() expects
        app_dicts = [
            {
                "id": app.id,
                "roleTitle": app.roleTitle,
                "company": app.company,
                "jobDescription": app.jobDescription,
                "extractedKeywords": app.extractedKeywords,
                "status": app.status,
                "platform": app.platform,
            }
            for app in applications
        ]

        # Use the singleton's reindex_all if it supports it, else create new
        if hasattr(vector_search_service, "reindex_all"):
            added = vector_search_service.reindex_all(app_dicts)
            stats = vector_search_service.get_index_stats()
        else:
            # Legacy fallback — rebuild the old way
            new_service = type(vector_search_service)(
                index_path="/home/z/my-project/db/faiss_index"
            )
            documents = []
            for app in applications:
                text = f"{app.roleTitle} {app.company} {app.jobDescription}"
                if app.location:
                    text += f" {app.location}"
                if app.workMode:
                    text += f" {app.workMode}"
                if app.extractedKeywords:
                    try:
                        keywords = json.loads(app.extractedKeywords)
                        if isinstance(keywords, list):
                            text += " " + " ".join(keywords)
                    except (json.JSONDecodeError, TypeError):
                        pass
                documents.append({
                    "id": app.id,
                    "text": text,
                    "metadata": {
                        "text": text,
                        "company": app.company,
                        "role": app.roleTitle,
                        "status": app.status,
                        "platform": app.platform,
                    },
                })
            # Clear and rebuild legacy index
            new_service.index = None
            new_service.id_map = {}
            new_service._doc_metadata = {}
            import faiss as _faiss
            new_service.index = _faiss.IndexFlatL2(new_service.dimension)
            added = new_service.add_documents_batch(documents)
            # Replace singleton state
            vector_search_service.index = new_service.index
            vector_search_service.id_map = new_service.id_map
            vector_search_service._doc_metadata = new_service._doc_metadata
            vector_search_service._save_index()
            stats = vector_search_service.get_index_stats()

        return {
            "success": True,
            "indexed": added,
            "total": len(applications),
            "backend": stats.get("backend", "unknown"),
        }
    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reindex failed: {str(e)}")
