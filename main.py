from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, AnyUrl, validator
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# -----------------------------
# DB
# -----------------------------
DATABASE_URL = "sqlite:///./links.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # section color token
    color = Column(String, default="slate", nullable=False)

    links = relationship("Link", cascade="all, delete", passive_deletes=True)


class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Base.metadata.create_all(engine)

# -----------------------------
# FastAPI
# -----------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down later for cloud
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Schemas
# -----------------------------
class SectionCreate(BaseModel):
    name: str


class SectionUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class LinkCreate(BaseModel):
    title: str
    url: AnyUrl


class LinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[AnyUrl] = None


class ReorderPayload(BaseModel):
    # keep as List[int], but we will CLEAN it before validation finishes
    ordered_ids: List[int]

    @validator("ordered_ids", pre=True)
    def normalize_ids(cls, v):
        """
        Frontend sometimes sends garbage like: ["7","undefined","color",9]
        This makes reorder crash with 422. We sanitize it.
        """
        if v is None:
            return []

        cleaned = []
        # v should be a list; but handle any weird cases
        if not isinstance(v, list):
            v = [v]

        for x in v:
            try:
                i = int(str(x).strip())
                if i > 0:
                    cleaned.append(i)
            except Exception:
                # ignore junk: "undefined", "color", "", None, etc.
                continue

        if not cleaned:
            # you can also choose to return [] and just do nothing
            raise ValueError("ordered_ids must contain at least one valid integer id")

        return cleaned


ALLOWED_COLORS = {"slate", "blue", "green", "amber", "red", "purple", "pink", "teal"}

# -----------------------------
# Routes
# -----------------------------
@app.get("/sections")
def list_sections():
    db = SessionLocal()
    sections = db.query(Section).order_by(Section.sort_order).all()

    result = []
    for s in sections:
        links = (
            db.query(Link)
            .filter(Link.section_id == s.id)
            .order_by(Link.sort_order)
            .all()
        )
        result.append(
            {
                "id": s.id,
                "name": s.name,
                "color": s.color,
                "links": [{"id": l.id, "title": l.title, "url": l.url} for l in links],
            }
        )

    db.close()
    return result


@app.post("/sections")
def create_section(data: SectionCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Section name cannot be empty")

    db = SessionLocal()

    exists = db.query(Section).filter(Section.name == name).first()
    if exists:
        db.close()
        raise HTTPException(409, "Section name already exists")

    # put new sections at bottom
    max_sort = db.query(Section).order_by(Section.sort_order.desc()).first()
    next_sort = (max_sort.sort_order + 1) if max_sort else 0

    s = Section(name=name, sort_order=next_sort)
    db.add(s)
    db.commit()
    db.refresh(s)
    db.close()
    return {"id": s.id, "name": s.name, "color": s.color}


@app.put("/sections/{section_id}")
def update_section(section_id: int, data: SectionUpdate):
    db = SessionLocal()
    s = db.query(Section).get(section_id)
    if not s:
        db.close()
        raise HTTPException(404, "Section not found")

    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            db.close()
            raise HTTPException(400, "Section name cannot be empty")

        exists = (
            db.query(Section)
            .filter(Section.name == new_name, Section.id != section_id)
            .first()
        )
        if exists:
            db.close()
            raise HTTPException(409, "Section name already exists")

        s.name = new_name

    if data.color is not None:
        c = data.color.strip().lower()
        if c not in ALLOWED_COLORS:
            db.close()
            raise HTTPException(400, f"Invalid color. Allowed: {sorted(ALLOWED_COLORS)}")
        s.color = c

    db.commit()
    db.close()
    return {"ok": True}


@app.delete("/sections/{section_id}")
def delete_section(section_id: int):
    db = SessionLocal()
    s = db.query(Section).get(section_id)
    if not s:
        db.close()
        raise HTTPException(404, "Section not found")

    db.delete(s)
    db.commit()
    db.close()
    return {"ok": True}


@app.post("/sections/{section_id}/links")
def add_link(section_id: int, data: LinkCreate):
    title = data.title.strip()
    url = str(data.url).strip()
    if not title:
        raise HTTPException(400, "Title cannot be empty")

    db = SessionLocal()

    s = db.query(Section).get(section_id)
    if not s:
        db.close()
        raise HTTPException(404, "Section not found")

    # put new links at bottom (within section)
    max_sort = (
        db.query(Link)
        .filter(Link.section_id == section_id)
        .order_by(Link.sort_order.desc())
        .first()
    )
    next_sort = (max_sort.sort_order + 1) if max_sort else 0

    l = Link(section_id=section_id, title=title, url=url, sort_order=next_sort)
    db.add(l)
    db.commit()
    db.refresh(l)
    db.close()
    return {"id": l.id, "title": l.title, "url": l.url}


@app.put("/links/{link_id}")
def update_link(link_id: int, data: LinkUpdate):
    db = SessionLocal()
    l = db.query(Link).get(link_id)
    if not l:
        db.close()
        raise HTTPException(404, "Link not found")

    if data.title is not None:
        t = data.title.strip()
        if not t:
            db.close()
            raise HTTPException(400, "Title cannot be empty")
        l.title = t

    if data.url is not None:
        l.url = str(data.url).strip()

    db.commit()
    db.close()
    return {"ok": True}


@app.delete("/links/{link_id}")
def delete_link(link_id: int):
    db = SessionLocal()
    l = db.query(Link).get(link_id)
    if not l:
        db.close()
        raise HTTPException(404, "Link not found")

    db.delete(l)
    db.commit()
    db.close()
    return {"ok": True}


@app.put("/sections/reorder")
def reorder_sections(data: ReorderPayload):
    db = SessionLocal()

    # only update IDs that exist
    existing_ids = {x[0] for x in db.query(Section.id).all()}
    ordered = [sid for sid in data.ordered_ids if sid in existing_ids]

    for idx, sid in enumerate(ordered):
        db.query(Section).filter(Section.id == sid).update({"sort_order": idx})

    db.commit()
    db.close()
    return {"ok": True, "count": len(ordered)}


@app.put("/sections/{section_id}/links/reorder")
def reorder_links(section_id: int, data: ReorderPayload):
    db = SessionLocal()

    # only update links in that section
    existing_ids = {x[0] for x in db.query(Link.id).filter(Link.section_id == section_id).all()}
    ordered = [lid for lid in data.ordered_ids if lid in existing_ids]

    for idx, lid in enumerate(ordered):
        db.query(Link).filter(Link.id == lid, Link.section_id == section_id).update({"sort_order": idx})

    db.commit()
    db.close()
    return {"ok": True, "count": len(ordered)}


# -----------------------------
# Static frontend
# -----------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
