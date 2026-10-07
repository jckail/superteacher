"""A case-variant section race is one row and a 409, not two rows or a 500."""

import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from superteacher import db as database
from superteacher.accounts import CurrentUser, ensure_owner
from superteacher.models import Course, Section
from superteacher.routers import roster
from superteacher.schemas import SectionIn


def test_concurrent_case_variant_posts_yield_one_success(tmp_path, monkeypatch):
    engine = database.make_engine(f"sqlite:///{tmp_path / 'race.db'}")
    try:
        database.run_migrations(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as db:
            owner_id = ensure_owner(db)
            course = Course(name="Math", owner_id=owner_id)
            db.add(course)
            db.commit()
            course_id = course.id
        user = CurrentUser(id=owner_id, email="owner@superteacher.invalid")
        gate = threading.Barrier(2)
        original = roster._name_taken

        def paused(db, model, name, **scope):
            taken = original(db, model, name, **scope)
            if model is Section:
                gate.wait(timeout=5)
            return taken

        monkeypatch.setattr(roster, "_name_taken", paused)

        def post(name):
            db = factory()
            try:
                roster.create_section(SectionIn(name=name, course_id=course_id), db, user)
                return 201
            except HTTPException as exc:
                return exc.status_code
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(post, ["Period 1", "period 1"]))
        assert sorted(codes) == [201, 409]
        with factory() as db:
            stored = db.scalars(select(Section.name).where(Section.course_id == course_id)).all()
            assert len(stored) == 1
    finally:
        engine.dispose()
