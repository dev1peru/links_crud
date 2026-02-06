from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, AnyUrl
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# --- DB ---
DATABASE_URL = "sqlite:///./links.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # required for SQLite + FastAPI
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    links = relationship("Link", back_populates="section", cascade="all, delete-orphan")

class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(200), nullable=False)
    url = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    section = relationship("Section", back_populates="links")

    __table_args__ = (
        # optional: avoid duplicate URLs inside same section
        UniqueConstraint("section_id", "url", name="uq_section_url"),
    )

Base.metadata.create_all(bind=engine)

# --- API ---
app = FastAPI(title="Links CRUD")

# Allow local HTML/JS to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---
class SectionCreate(BaseModel):
    name: str
    sort_order: int = 0

class LinkCreate(BaseModel):
    title: str
    url: AnyUrl
    notes: Optional[str] = None
    sort_order: int = 0

class LinkOut(BaseModel):
    id: int
    title: str
    url: str
    notes: Optional[str]
    sort_order: int

class SectionOut(BaseModel):
    id: int
    name: str
    sort_order: int
    links: List[LinkOut] = []

# --- Helpers ---
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# --- Endpoints ---
@app.get("/sections", response_model=List[SectionOut])
def list_sections():
    session = SessionLocal()
    try:
        sections = session.query(Section).order_by(Section.sort_order, Section.name).all()
        result = []
        for s in sections:
            links = (
                session.query(Link)
                .filter(Link.section_id == s.id)
                .order_by(Link.sort_order, Link.created_at.desc())
                .all()
            )
            result.append(
                SectionOut(
                    id=s.id,
                    name=s.name,
                    sort_order=s.sort_order,
                    links=[
                        LinkOut(
                            id=l.id, title=l.title, url=l.url,
                            notes=l.notes, sort_order=l.sort_order
                        )
                        for l in links
                    ],
                )
            )
        return result
    finally:
        session.close()

@app.post("/sections", response_model=SectionOut)
def create_section(payload: SectionCreate):
    session = SessionLocal()
    try:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "Section name cannot be empty")

        exists = session.query(Section).filter(Section.name == name).first()
        if exists:
            raise HTTPException(409, "Section already exists")

        s = Section(name=name, sort_order=payload.sort_order)
        session.add(s)
        session.commit()
        session.refresh(s)
        return SectionOut(id=s.id, name=s.name, sort_order=s.sort_order, links=[])
    finally:
        session.close()

@app.delete("/sections/{section_id}")
def delete_section(section_id: int):
    session = SessionLocal()
    try:
        s = session.query(Section).filter(Section.id == section_id).first()
        if not s:
            raise HTTPException(404, "Section not found")
        session.delete(s)
        session.commit()
        return {"deleted": True}
    finally:
        session.close()

@app.post("/sections/{section_id}/links", response_model=LinkOut)
def add_link(section_id: int, payload: LinkCreate):
    session = SessionLocal()
    try:
        s = session.query(Section).filter(Section.id == section_id).first()
        if not s:
            raise HTTPException(404, "Section not found")

        l = Link(
            section_id=section_id,
            title=payload.title.strip(),
            url=str(payload.url),
            notes=payload.notes,
            sort_order=payload.sort_order,
        )
        session.add(l)
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(409, "This URL already exists in that section")
        session.refresh(l)
        return LinkOut(id=l.id, title=l.title, url=l.url, notes=l.notes, sort_order=l.sort_order)
    finally:
        session.close()

@app.delete("/links/{link_id}")
def delete_link(link_id: int):
    session = SessionLocal()
    try:
        l = session.query(Link).filter(Link.id == link_id).first()
        if not l:
            raise HTTPException(404, "Link not found")
        session.delete(l)
        session.commit()
        return {"deleted": True}
    finally:
        session.close()
