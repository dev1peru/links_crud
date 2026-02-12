from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, AnyUrl
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

    # Keep it (doesn't affect reorder). If your DB doesn't have it yet, delete links.db once.
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
    color: Optional[str] = None  # harmless even if you don’t use it in UI


class LinkCreate(BaseModel):
    title: str
    url: AnyUrl


class LinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[AnyUrl] = None


class ReorderPayload(BaseModel):
    ordered_ids: List[int]


ALLOWED_COLORS = {
    "slate", "gray",
    "blue", "navy", "indigo", "sky", "cyan",
    "teal", "mint",
    "green", "lime",
    "amber", "gold", "orange",
    "red",
    "pink",
    "purple",
    "coffee",
}



# -----------------------------
# Helpers
# -----------------------------
def get_db():
    return SessionLocal()


# -----------------------------
# Routes
# -----------------------------
@app.get("/sections")
def list_sections():
    db = get_db()
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

    db = get_db()

    exists = db.query(Section).filter(Section.name == name).first()
    if exists:
        db.close()
        raise HTTPException(409, "Section name already exists")

    s = Section(name=name)
    db.add(s)
    db.commit()
    db.refresh(s)
    db.close()
    return {"id": s.id, "name": s.name, "color": s.color}


@app.put("/sections/{section_id}")
def update_section(section_id: int, data: SectionUpdate):
    db = get_db()
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
    db = get_db()
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

    db = get_db()

    s = db.query(Section).get(section_id)
    if not s:
        db.close()
        raise HTTPException(404, "Section not found")

    l = Link(section_id=section_id, title=title, url=url)
    db.add(l)
    db.commit()
    db.refresh(l)
    db.close()
    return {"id": l.id, "title": l.title, "url": l.url}


@app.put("/links/{link_id}")
def update_link(link_id: int, data: LinkUpdate):
    db = get_db()
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
    db = get_db()
    l = db.query(Link).get(link_id)
    if not l:
        db.close()
        raise HTTPException(404, "Link not found")

    db.delete(l)
    db.commit()
    db.close()
    return {"ok": True}


# ✅ IMPORTANT FIX:
# These routes do NOT collide with /sections/{section_id}
@app.put("/sections-reorder")
def reorder_sections(data: ReorderPayload):
    db = get_db()
    for idx, sid in enumerate(data.ordered_ids):
        db.query(Section).filter(Section.id == sid).update({"sort_order": idx})
    db.commit()
    db.close()
    return {"ok": True}


@app.put("/sections/{section_id}/links-reorder")
def reorder_links(section_id: int, data: ReorderPayload):
    db = get_db()
    for idx, lid in enumerate(data.ordered_ids):
        db.query(Link).filter(Link.id == lid, Link.section_id == section_id).update({"sort_order": idx})
    db.commit()
    db.close()
    return {"ok": True}


# -----------------------------
# Static frontend
# -----------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
