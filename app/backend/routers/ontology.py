"""画面とMCPが同じ意味・クエリ・制約を使用する。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from services import ontology, capa_service
from services.ontology_contract import definition

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


def _call(fn):
    try:
        return fn()
    except (ontology.OntologyError, capa_service.CapaError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/definition")
def get_definition():
    return definition()


@router.get("/resolve")
def resolve(object_type: ontology.ObjectType, query: str = Query(min_length=1, max_length=300),
            limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return _call(lambda: ontology.resolve(db, object_type, query, limit))


@router.get("/objects/{object_type}/{object_id}")
def get_object(object_type: ontology.ObjectType, object_id: str, db: Session = Depends(get_db)):
    return _call(lambda: ontology.get_object(db, object_type, object_id))


@router.get("/objects/{object_type}/{object_id}/relations/{relation}")
def traverse(object_type: ontology.ObjectType, object_id: str, relation: str,
             limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000),
             db: Session = Depends(get_db)):
    return _call(lambda: ontology.traverse(db, object_type, object_id, relation, limit, offset))


@router.post("/query")
def query(body: ontology.QualityQuery, db: Session = Depends(get_db)):
    return _call(lambda: ontology.query_quality(db, body))


@router.get("/graph/{defect_id}")
def graph(defect_id: str, capa_limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    return _call(lambda: ontology.report_graph(db, defect_id, capa_limit))


class CapaPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capa_id: str = Field(min_length=1, max_length=100)
    status: str | None = None
    effect_note: str | None = None
    owner: str | None = None
    due_date: str | None = None


@router.post("/actions/capa/preview")
def preview(body: CapaPreview, db: Session = Depends(get_db)):
    return _call(lambda: capa_service.preview_update(db, body.capa_id,
                 body.model_dump(exclude={"capa_id"}, exclude_none=True)))
