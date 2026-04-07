from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from course_search_api.dependencies import get_db
from shared.models import Program, Requirement

router = APIRouter(prefix="/api/programs", tags=["programs"])


@router.get("")
def list_programs(db: Session = Depends(get_db)) -> list[dict]:
    programs = db.query(Program).order_by(Program.name).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "type": p.type,
            "total_credits": p.total_credits,
        }
        for p in programs
    ]


@router.get("/{program_id}/requirements")
def get_program_requirements(program_id: int, db: Session = Depends(get_db)) -> dict:
    program = db.query(Program).filter(Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    requirements = (
        db.query(Requirement)
        .filter(Requirement.program_id == program_id)
        .order_by(Requirement.sort_order)
        .all()
    )
    return {
        "program": {"id": program.id, "name": program.name, "type": program.type},
        "requirements": [
            {
                "id": r.id,
                "sort_order": r.sort_order,
                "requirement_type": r.requirement_type,
                "course_code": r.course_code,
                "description": r.name,
            }
            for r in requirements
        ],
    }
