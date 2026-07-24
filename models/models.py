from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    contacto = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)

    turnos = db.relationship("Turno", backref="cliente", lazy=True)

# ==============================
# PROFESIONALES
# ==============================

class Profesional(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    turnos = db.relationship("Turno", backref="profesional", lazy=True)
    bloqueos = db.relationship("Bloqueo", backref="profesional", lazy=True)


# ==============================
# TURNOS
# ==============================

class Turno(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    nombre_cliente = db.Column(db.String(150), nullable=False)
    contacto = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    servicio = db.Column(db.String(150))

    fecha = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    google_event_id = db.Column(db.String(200))
    recordatorio_enviado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profesional_id = db.Column(db.Integer, db.ForeignKey("profesional.id"), nullable=False)

    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"), nullable=True)


# ==============================
# BLOQUEOS / VACACIONES
# ==============================

class Bloqueo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(255))

    profesional_id = db.Column(db.Integer, db.ForeignKey("profesional.id"), nullable=False)

# ==============================
# CONFIG / TOKENS
# ==============================
class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.Text, nullable=False)
