from datetime import datetime
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, AnyUrl
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///./links.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    links = relationship("Link", cascade="all, delete")

class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("sections.id"))
    title = Column(String)
    url = Column(Text)
    sort_order = Column(Integer, default=0)

Base.metadata.create_all(engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SectionCreate(BaseModel):
    name: str

class LinkCreate(BaseModel):
    title: str
    url: AnyUrl

class ReorderPayload(BaseModel):
    ordered_ids: List[int]

@app.get("/sections")
def list_sections():
    db = SessionLocal()
    sections = db.query(Section).order_by(Section.sort_order).all()
    result = []
    for s in sections:
        links = db.query(Link).filter(Link.section_id == s.id).order_by(Link.sort_order).all()
        result.append({"id": s.id, "name": s.name, "links": [{"id": l.id, "title": l.title, "url": l.url} for l in links]})
    db.close()
    return result

@app.post("/sections")
def create_section(data: SectionCreate):
    db = SessionLocal()
    s = Section(name=data.name)
    db.add(s)
    db.commit()
    db.refresh(s)
    db.close()
    return s

@app.delete("/sections/{section_id}")
def delete_section(section_id: int):
    db = SessionLocal()
    s = db.query(Section).get(section_id)
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    db.close()
    return {"ok": True}

@app.post("/sections/{section_id}/links")
def add_link(section_id: int, data: LinkCreate):
    db = SessionLocal()
    l = Link(section_id=section_id, title=data.title, url=str(data.url))
    db.add(l)
    db.commit()
    db.refresh(l)
    db.close()
    return l

@app.delete("/links/{link_id}")
def delete_link(link_id: int):
    db = SessionLocal()
    l = db.query(Link).get(link_id)
    if not l:
        raise HTTPException(404)
    db.delete(l)
    db.commit()
    db.close()
    return {"ok": True}

@app.put("/sections/reorder")
def reorder_sections(data: ReorderPayload):
    db = SessionLocal()
    for idx, sid in enumerate(data.ordered_ids):
        db.query(Section).filter(Section.id == sid).update({"sort_order": idx})
    db.commit()
    db.close()
    return {"ok": True}

@app.put("/sections/{section_id}/links/reorder")
def reorder_links(section_id: int, data: ReorderPayload):
    db = SessionLocal()
    for idx, lid in enumerate(data.ordered_ids):
        db.query(Link).filter(Link.id == lid).update({"sort_order": idx})
    db.commit()
    db.close()
    return {"ok": True}

# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
