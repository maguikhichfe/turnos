"""
Uso local: carga a Tania, Rocio y Pamela en la base si todavía no existen.

    $env:DATABASE_URL = "sqlite:///local.db"
    python seed_profesionales.py
"""
from app import app, db
from models.models import Profesional

with app.app_context():
    for nombre in ["tania", "rocio", "pamela"]:
        if not Profesional.query.filter_by(nombre=nombre).first():
            db.session.add(Profesional(nombre=nombre))
    db.session.commit()
    print("Profesionales en la base:", [p.nombre for p in Profesional.query.all()])
