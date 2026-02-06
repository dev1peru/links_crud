from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, AnyUrl
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///./links.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    links = relationship("Link", back_populates="section", cascade="all, delete-orphan")

class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    url = Column(Text, nullable=False)
    notes = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    section = relationship("Section", back_populates="links")
    __table_args__ = (UniqueConstraint("section_id", "url", name="uq_section_url"),)

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SectionCreate(BaseModel):
    name: str

class LinkCreate(BaseModel):
    title: str
    url: AnyUrl

class ReorderPayload(BaseModel):
    ordered_ids: List[int]

@app.get("/sections")
def list_sections():
    session = SessionLocal()
    sections = session.query(Section).order_by(Section.sort_order, Section.name).all()
    result = []
    for s in sections:
        links = session.query(Link)\
            .filter(Link.section_id == s.id)\
            .order_by(Link.sort_order, Link.created_at.desc())\
            .all()
        result.append({
            "id": s.id,
            "name": s.name,
            "links": [{"id": l.id, "title": l.title, "url": l.url} for l in links]
        })
    session.close()
    return result

@app.post("/sections")
def create_section(payload: SectionCreate):
    session = SessionLocal()
    s = Section(name=payload.name.strip())
    session.add(s)
    session.commit()
    session.refresh(s)
    session.close()
    return {"id": s.id, "name": s.name, "links": []}

@app.delete("/sections/{section_id}")
def delete_section(section_id: int):
    session = SessionLocal()
    s = session.query(Section).filter(Section.id == section_id).first()
    if not s:
        raise HTTPException(404, "Section not found")
    session.delete(s)
    session.commit()
    session.close()
    return {"deleted": True}

@app.post("/sections/{section_id}/links")
def add_link(section_id: int, payload: LinkCreate):
    session = SessionLocal()
    l = Link(section_id=section_id, title=payload.title.strip(), url=str(payload.url))
    session.add(l)
    session.commit()
    session.refresh(l)
    session.close()
    return {"id": l.id, "title": l.title, "url": l.url}

@app.delete("/links/{link_id}")
def delete_link(link_id: int):
    session = SessionLocal()
    l = session.query(Link).filter(Link.id == link_id).first()
    if not l:
        raise HTTPException(404, "Link not found")
    session.delete(l)
    session.commit()
    session.close()
    return {"deleted": True}

@app.put("/sections/{section_id}/links/reorder")
def reorder_links(section_id: int, payload: ReorderPayload):
    session = SessionLocal()
    links = session.query(Link).filter(Link.section_id == section_id).all()
    ids = {l.id for l in links}
    if set(payload.ordered_ids) != ids:
        raise HTTPException(400, "Invalid link IDs")
    for idx, lid in enumerate(payload.ordered_ids):
        session.query(Link).filter(Link.id == lid).update({"sort_order": idx})
    session.commit()
    session.close()
    return {"ok": True}
