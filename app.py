import sys

# En Windows la consola puede no estar en UTF-8: si eso pasa, los print()
# con emojis de este archivo tiran UnicodeEncodeError y el server nunca
# llega a levantar (ningún endpoint responde, aunque el código esté bien).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, request, jsonify, send_from_directory,  render_template
from flask_cors import CORS
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
from supabase import create_client
import os
import json
import re
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import resend
from models.models import db, Turno, Bloqueo, Profesional, Config
from sqlalchemy import func
import traceback
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from sqlalchemy import and_, or_
DURACIONES = {
  "esmaltado común": 60,
  "semipermanente": 60,
  "kapping / dipping": 60,
  "soft gel": 90,
  "belleza de pies": 60,
  "pedicuría": 60,
  "retiro semipermanente": 30,
  "retiro kapping": 30,
  "retiro soft gel": 60,
  "arreglo por uña": 15,
  "decoracion":15,
}


COMBOS_DURACION = {
    tuple(sorted(["semipermanente", "decoracion"])): 75,
    tuple(sorted(["esmaltado común", "belleza de pies"])): 90,
    tuple(sorted(["semipermanente", "belleza de pies"])): 120,
    tuple(sorted(["semipermanente", "decoracion", "belleza de pies"])): 120,
    tuple(sorted(["semipermanente", "pedicuría"])): 120,
    tuple(sorted(["semipermanente", "decoracion", "pedicuría"])): 120,
    tuple(sorted(["kapping / dipping", "pedicuría"])): 120,
    tuple(sorted(["kapping / dipping", "decoracion"])): 90,
    tuple(sorted(["kapping / dipping", "decoracion", "pedicuría"])): 150,
    tuple(sorted(["soft gel", "belleza de pies"])): 120,
    tuple(sorted(["soft gel", "decoracion", "belleza de pies"])): 150,
    tuple(sorted(["soft gel", "decoracion", "pedicuría"])): 150,
}
    

app = Flask(__name__)
print("DEPLOY NUEVO")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
 
with app.app_context():
    db.create_all()

CORS(app)
print("🔥 CARGANDO app.py 🔥")

@app.route("/")
def home():
    return render_template("index.html")


CALENDARS_BY_PROFESSIONAL = {
    "tania": "29de771488bcf52ac7f9b1a7481928112def7e80f88eaa0349f73e5750885ace@group.calendar.google.com",
    "rocio": "62844d16468bb6871a070f8df0ba810e5d833bec0bc8e5a0bc34c466328cfc91@group.calendar.google.com",
    "pamela": "7a1a2bec152c006affc725523c02c64f973f9a5c46c94e06c478ec9617b98cc1@group.calendar.google.com"
}



SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "America/Argentina/Buenos_Aires"
CALENDAR_ID = "29de771488bcf52ac7f9b1a7481928112def7e80f88eaa0349f73e5750885ace@group.calendar.google.com"

from datetime import datetime, timedelta


def trabaja_en_horario(prof, fecha, hora):
    """
    fecha = date
    hora = time
    """

    dia_semana = fecha.weekday()  # lunes=0

    hora_num = hora.hour + hora.minute / 60

    nombre = prof.nombre.lower()

    # lunes
    if dia_semana == 0:

        if nombre in ["rocio", "pamela"]:
            return 14 <= hora_num < 19

        return 10 <= hora_num < 19

    # sábados
    if dia_semana == 5:
        return 10 <= hora_num < 17

    # martes a viernes
    return 10 <= hora_num < 19

def calcular_duracion_backend(servicio_str):
    if not servicio_str:
        return 30

    servicios = [s.strip().lower() for s in servicio_str.split(",")]

    base = []

    for s in servicios:
        # 🔥 PRIMERO retiros (si no, "retiro semipermanente" matchea "semi" y
        # se confunde con "semipermanente", perdiendo tiempo real de turno)
        if "retiro soft" in s:
            base.append("retiro soft gel")
        elif "retiro semi" in s:
            base.append("retiro semipermanente")
        elif "retiro kapping" in s:
            base.append("retiro kapping")
        elif "semi" in s:
            base.append("semipermanente")
        elif "común" in s or "comun" in s:
            base.append("esmaltado común")
        elif "kapping" in s:
            base.append("kapping / dipping")
        elif "soft" in s:
            base.append("soft gel")
        elif "belleza" in s:
            base.append("belleza de pies")
        elif "pedicur" in s:
            base.append("pedicuría")
        elif "arreglo" in s:
            base.append("arreglo por uña")

        if "decor" in s:
            base.append("decoracion")

    key = tuple(sorted(base))

    print("SERVICIOS:", servicios)
    print("BASE:", base)
    print("KEY:", key)

    if key in COMBOS_DURACION:
        print("✅ USANDO COMBO:", key)
        return COMBOS_DURACION[key]

    # fallback
    total = sum(DURACIONES.get(s, 0) for s in base)

    print("⚠️ USANDO SUMA:", total)

    return total if total > 0 else 30
@app.route("/mejor-profesional", methods=["POST"])
def mejor_profesional():

    data = request.get_json()
    duracion = int(data.get("duracion", 30))

    profesionales = Profesional.query.all()

    ahora = datetime.now()
    mejor_opcion = None

    for prof in profesionales:

        fecha = ahora.date()

        # buscamos hasta 7 días adelante
        for _ in range(7):

            turnos = Turno.query.filter(
                Turno.fecha == fecha,
                Turno.profesional_id == prof.id
            ).all()

            bloques_ocupados = []

            

            for t in turnos:
                inicio = datetime.combine(t.fecha, t.hora)
                fin = inicio + timedelta(minutes=calcular_duracion_backend(t.servicio))

                bloques_ocupados.append((inicio, fin))

            # horario laboral
            hora = datetime.combine(fecha, datetime.strptime("10:00", "%H:%M").time())
            fin_dia = datetime.combine(fecha, datetime.strptime("18:00", "%H:%M").time())

            while hora + timedelta(minutes=duracion) <= fin_dia:


                if not trabaja_en_horario(prof, fecha, hora.time()):
                  hora += timedelta(minutes=30)
                  continue

                fin_turno = hora + timedelta(minutes=duracion)

                conflicto = False

                for inicio_ocupado, fin_ocupado in bloques_ocupados:
                    if not (fin_turno <= inicio_ocupado or hora >= fin_ocupado):
                        conflicto = True
                        break

                if not conflicto:
                    # encontramos hueco libre
                    if not mejor_opcion or hora < mejor_opcion["inicio"]:
                        mejor_opcion = {
                            "profesional": prof.nombre,
                            "fecha": fecha.isoformat(),
                            "hora": hora.strftime("%H:%M"),
                            "inicio": hora
                        }

                    break  # pasamos al siguiente profesional

                hora += timedelta(minutes=30)

            fecha += timedelta(days=1)

    if not mejor_opcion:
        return jsonify({"error": "No hay disponibilidad"})

    return jsonify({
        "profesional": mejor_opcion["profesional"],
        "fecha": mejor_opcion["fecha"],
        "hora": mejor_opcion["hora"]
    })
    
# Cargar credenciales
def get_calendar_service():
    token_info = json.loads(os.environ["GOOGLE_OAUTH_TOKEN"])

    creds = Credentials(
        token=token_info["token"],
        refresh_token=token_info["refresh_token"],
        token_uri=token_info["token_uri"],
        client_id=token_info["client_id"],
        client_secret=token_info["client_secret"],
        scopes=token_info["scopes"]
    )
    

    return build("calendar", "v3", credentials=creds)

def _normalizar_telefono(s):
    return re.sub(r"\D", "", s or "")


def _normalizar_email(s):
    return (s or "").strip().lower()


@app.route("/api/turnos", methods=["GET"])
def get_turnos():
    busqueda = request.args.get("busqueda")  # 👈 debe decir "busqueda", no "contacto"
    if not busqueda:
        return jsonify({"error": "Falta dato de búsqueda"}), 400

    email_buscado = _normalizar_email(busqueda)
    telefono_buscado = _normalizar_telefono(busqueda)

    ahora = datetime.now()
    hoy = ahora.date()
    hora_actual = ahora.time()

    candidatos = (
        db.session.query(Turno)
        .join(Profesional)
        .filter(
            or_(
                Turno.fecha >= hoy,
                and_(
                    Turno.fecha == hoy,
                    Turno.hora >= hora_actual
                )
            )
        )
        .order_by(Turno.fecha, Turno.hora)
        .all()
    )

    # 🔥 Comparamos normalizando espacios/guiones/mayúsculas: así no importa
    # si la clienta reservó con "11 2233-4455" y después busca "1122334455"
    turnos = [
        t for t in candidatos
        if (email_buscado and _normalizar_email(t.email) == email_buscado)
        or (telefono_buscado and _normalizar_telefono(t.contacto) == telefono_buscado)
    ]

    result = []
    for t in turnos:
        result.append({
            "id": t.id,
            "servicio": t.servicio,
            "profesional": t.profesional.nombre,
            "fecha": t.fecha.strftime("%Y-%m-%d"),
            "hora": t.hora.strftime("%H:%M")
        })

    return jsonify(result)
@app.route("/reservar", methods=["POST"])
def reservar():
    print("🔥 /reservar fue llamado")
    try:
        data = request.get_json() or request.form
        nombre = data.get("nombre")
        contacto = data.get("contacto")
        email = data.get("email")
        servicio = data.get("servicio")
        profesional_nombre = data.get("profesional")
        fecha = data.get("fecha")
        hora = data.get("hora")
        
        duracion = calcular_duracion_backend(servicio) # ✅ ya lo tenés, verificá que sea int
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
        hora_dt = datetime.strptime(hora, "%H:%M").time()
        inicio_nuevo = datetime.combine(fecha_dt, hora_dt)
        fin_nuevo = inicio_nuevo + timedelta(minutes=duracion)
        
        print("🔍 Buscando para:", fecha_dt, hora_dt, "duración:", duracion, "min")
        print("   Ventana:", inicio_nuevo, "→", fin_nuevo)

        if profesional_nombre == "cualquiera":
            profesionales = Profesional.query.all()
            disponibles = []
        
            for p in profesionales:
                print("Evaluando:", p.nombre)

                if not trabaja_en_horario(p, fecha_dt, hora_dt):
                    print("  -> fuera de horario")
                    continue
        
                # 🔴 1. BLOQUEOS
                bloqueos = Bloqueo.query.filter(
                    Bloqueo.profesional_id == p.id,
                    Bloqueo.fecha_inicio <= fecha_dt,
                    Bloqueo.fecha_fin >= fecha_dt
                ).all()
        
                ocupado = False
        
                if bloqueos:
                    ocupado = True
        
                # 🔴 2. TURNOS
                if not ocupado:
                    turnos_prof = Turno.query.filter(
                        Turno.fecha == fecha_dt,
                        Turno.profesional_id == p.id
                    ).all()
        
                    for t in turnos_prof:
                        inicio_existente = datetime.combine(t.fecha, t.hora)
                        dur_existente = calcular_duracion_backend(t.servicio) or 30
                        fin_existente = inicio_existente + timedelta(minutes=dur_existente)
        
                        if not (fin_nuevo <= inicio_existente or inicio_nuevo >= fin_existente):
                            ocupado = True
                            break
        
                # 🔴 3. DISPONIBLE
                if not ocupado:
                    disponibles.append(p)
        
            # 🔥 ESTO VA FUERA DEL FOR
            print("Disponibles:", [p.nombre for p in disponibles])
            print("Fecha:", fecha_dt)
            print("Hora:", hora_dt)
            if not disponibles:
                print("Disponibles:", [p.nombre for p in disponibles])
                return jsonify({"error": "No hay profesionales disponibles en ese horario"}), 400
        
            import random
            prof = random.choice(disponibles)

        else:
            prof = Profesional.query.filter(
                func.lower(Profesional.nombre) == profesional_nombre.lower()
            ).first()

        if not prof:
            return jsonify({"error": "Profesional no encontrado"}), 400

        calendar_id = CALENDARS_BY_PROFESSIONAL.get(prof.nombre.lower())
        if not calendar_id:
            return jsonify({"error": "Calendar ID no encontrado"}), 400

        tz = pytz.timezone(TIMEZONE)
        inicio = tz.localize(datetime.combine(fecha_dt, hora_dt))
        fin = inicio + timedelta(minutes=duracion)

        event = {
            "summary": f"{servicio} - {nombre}",
            "description": f"Contacto: {contacto}",
            "location": "Almte. F.J. Seguí 746, C1406 Cdad. Autónoma de Buenos Aires",
            "start": {"dateTime": inicio.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": fin.isoformat(), "timeZone": TIMEZONE},
            "attendees": [{"email": email, "responseStatus": "accepted"}] if email else [],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 1440},
                    {"method": "popup", "minutes": 60}
                ]
            }
        }

        google_event_id = None
        try:
            print("1️⃣ Obteniendo servicio")
        
            service = get_calendar_service()
        
            print("2️⃣ Servicio OK")
        
            print("3️⃣ Insertando evento en:", calendar_id)
        
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendUpdates="all"
            ).execute()
        
            print("4️⃣ Evento creado")
        
            google_event_id = created_event["id"]
        
        except Exception as e:
            import traceback
            print("ERROR CALENDAR")
            traceback.print_exc()

        nuevo_turno = Turno(
            nombre_cliente=nombre,
            contacto=contacto,
            email=email,
            servicio=servicio,
            profesional_id=prof.id,
            fecha=fecha_dt,
            hora=hora_dt,
            google_event_id=google_event_id
        )

        db.session.add(nuevo_turno)
        db.session.commit()
        print("✅ Turno guardado:", nuevo_turno.id, "→ profesional:", prof.nombre)

        return jsonify({"ok": True, "profesional": prof.nombre})

    except Exception as e:
        db.session.rollback()
        print("❌ ERROR RESERVAR:", str(e))
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def hay_profesional_disponible(fecha, hora_str, duracion):

    inicio_nuevo = datetime.combine(
        fecha,
        datetime.strptime(hora_str, "%H:%M").time()
    )

    fin_nuevo = inicio_nuevo + timedelta(minutes=duracion)

    profesionales = Profesional.query.all()

    for p in profesionales:
    
        if not trabaja_en_horario(p, fecha, inicio_nuevo.time()):
            continue
    
        if fin_nuevo.date() != fecha:
            continue
    
        if not trabaja_en_horario(
            p,
            fecha,
            (fin_nuevo - timedelta(minutes=1)).time()
        ):
            continue
    
        bloqueo = Bloqueo.query.filter(
            Bloqueo.profesional_id == p.id,
            Bloqueo.fecha_inicio <= fecha,
            Bloqueo.fecha_fin >= fecha
        ).first()
    
        if bloqueo:
            continue
    
        conflicto = False
    
        turnos = Turno.query.filter(
            Turno.fecha == fecha,
            Turno.profesional_id == p.id
        ).all()
    
        for t in turnos:
    
            inicio_existente = datetime.combine(t.fecha, t.hora)
    
            fin_existente = (
                inicio_existente +
                timedelta(
                    minutes=calcular_duracion_backend(t.servicio)
                )
            )
    
            if not (
                fin_nuevo <= inicio_existente or
                inicio_nuevo >= fin_existente
            ):
                conflicto = True
                break
    
        if not conflicto:
            return True

    return False

@app.route("/ocupados", methods=["GET"])
def horarios_ocupados():
    try:
        print("EJECUTANDO OCUPADOS")
        duracion = int(request.args.get("duracion", 30))

        fecha_str = request.args.get("fecha")
        profesional = request.args.get("profesional")

        if not fecha_str or not profesional:
            return jsonify({"ocupados": []})

        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()

        # ===============================
        # 🔥 FUNCIÓN CLAVE
        # ===============================
        

        # ===============================
        # 🔥 BLOQUEOS
        # ===============================
        if profesional.lower() not in ["cualquiera", "todos"]:
            bloqueo = Bloqueo.query.join(Bloqueo.profesional).filter(
                func.lower(Profesional.nombre) == profesional.lower(),
                Bloqueo.fecha_inicio <= fecha,
                Bloqueo.fecha_fin >= fecha
            ).first()

            if bloqueo:
                return jsonify({"vacaciones": True})

        # ===============================
        # 🔥 CASO 1: CUALQUIERA
        # ===============================
        if profesional.lower() in ["cualquiera", "todos"]:
          ocupados = []
          
          for h in range(10, 19):
          
              for m in [0, 30]:
          
                  hora = f"{h:02d}:{m:02d}"
          
                  if not hay_profesional_disponible(
                      fecha,
                      hora,
                      duracion
                  ):
                      ocupados.append(hora)
          
          return jsonify({"ocupados": ocupados})

        # ===============================
        # 🔥 CASO 2: PROFESIONAL
        # ===============================
        else:

            prof = Profesional.query.filter(
                func.lower(Profesional.nombre) == profesional.lower()
            ).first()

            if not prof:
                return jsonify({"ocupados": []})

            turnos = Turno.query.filter(
                Turno.fecha == fecha,
                Turno.profesional_id == prof.id
            ).all()

            ocupados = []

            for t in turnos:
                inicio = datetime.combine(t.fecha, t.hora)
                duracion = calcular_duracion_backend(t.servicio)
                fin = inicio + timedelta(minutes=duracion)

                hora_actual = inicio
                while hora_actual < fin:
                    ocupados.append(hora_actual.strftime("%H:%M"))
                    hora_actual += timedelta(minutes=30)

            return jsonify({"ocupados": ocupados})

    except Exception as e:
        print("ERROR OCUPADOS:", e)
        return jsonify({"ocupados": []})

ADMIN_PASSWORD = "1234"  # cambiá esto


@app.route("/admin")
def admin():

    clave = request.args.get("clave")

    if clave != ADMIN_PASSWORD:
        return "No autorizado", 401

    return  """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
        <title>Panel Admin</title>
    
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #fdf6f9;
                margin: 0;
                padding: 20px;
            }
    
            .card {
                background: white;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 8px 20px rgba(0,0,0,0.08);
                max-width: 500px;
                margin: auto;
            }
    
            h2 {
                text-align: center;
                color: #d63384;
                margin-bottom: 20px;
                font-size: 22px;
            }
    
            label {
                font-weight: 600;
                display: block;
                margin-top: 15px;
                font-size: 14px;
            }
    
            input, select {
                width: 100%;
                padding: 12px;
                border-radius: 10px;
                border: 1px solid #ddd;
                margin-top: 5px;
                font-size: 16px;
                box-sizing: border-box;
            }
    
            button {
                margin-top: 25px;
                width: 100%;
                padding: 14px;
                border: none;
                border-radius: 12px;
                background-color: #d63384;
                color: white;
                font-weight: bold;
                font-size: 16px;
                cursor: pointer;
                transition: 0.3s;
            }
    
            button:hover {
                background-color: #c2186a;
            }
    
            @media (max-width: 480px) {
                .card {
                    padding: 18px;
                }
    
                h2 {
                    font-size: 20px;
                }
            }
        </style>
    </head>
    
    <body>
    
        <div class="card">
            <h2>Panel Admin - Vacaciones</h2>
    
            <form method="POST" action="/admin/bloquear?clave=1234">
    
                <label>Profesional</label>
                <select name="profesional" required>
                    <option value="">Seleccionar profesional</option>
                    <option value="tania">Tania</option>
                    <option value="rocio">Rocio</option>
                    <option value="pamela">Pamela</option>
                </select>
    
                <label>Fecha inicio</label>
                <input type="date" name="fecha_inicio" required>
    
                <label>Fecha fin</label>
                <input type="date" name="fecha_fin" required>
    
                <label>Motivo</label>
                <input type="text" name="motivo" required>
    
                <button type="submit">Guardar bloqueo</button>
    
            </form>
        </div>
    
    </body>
    </html>
    """


@app.route("/reservas")
def reservas():
    return render_template("reservas.html")  # Sistema actual

@app.route("/admin/bloquear", methods=["POST"])
def bloquear():
    clave = request.args.get("clave")
    if clave != ADMIN_PASSWORD:
        return "No autorizado", 401

    try:
        profesional_nombre = request.form.get("profesional")
        fecha_inicio_str = request.form.get("fecha_inicio")
        fecha_fin_str = request.form.get("fecha_fin")
        motivo = request.form.get("motivo")

        # Convertir strings a date
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()

        # Buscar profesional en la base
        profesional_obj = Profesional.query.filter_by(nombre=profesional_nombre.lower()).first()
        if not profesional_obj:
            return "Profesional no encontrado", 404

        # Crear bloqueo usando el id del profesional
        nuevo_bloqueo = Bloqueo(
            profesional_id=profesional_obj.id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            motivo=motivo
        )

        db.session.add(nuevo_bloqueo)
        db.session.commit()

        return """
        <script>
            alert("Turno bloqueado correctamente");
            window.location.href = "/admin?clave=1234";
        </script>
        """

    except Exception as e:
        db.session.rollback()
        print("ERROR BLOQUEAR:", e)
        return "Error interno", 500

@app.route("/manicurista")
def pagina_turnos():
    return render_template("turnos.html")

@app.route("/manicuristas/turnos/<profesional>")
def turnos_manicurista(profesional):
    try:
        tz = pytz.timezone(TIMEZONE)
        hoy = datetime.now(tz).date()  # 🔥 fecha de hoy en Argentina

        turnos_db = (
            db.session.query(Turno)
            .join(Turno.profesional)
            .filter(
                Profesional.nombre.ilike(profesional),
                Turno.fecha >= hoy  # 🔥 todos los turnos de hoy en adelante
            )
            .order_by(Turno.fecha, Turno.hora)
            .all()
        )

        turnos = []
        for t in turnos_db:
            turnos.append({
                "id": t.id,
                "nombre": t.nombre_cliente,
                "contacto": t.contacto,
                "servicio": t.servicio,
                "fecha": t.fecha.isoformat(),
                "hora": t.hora.strftime("%H:%M"),
                "google_event_id": t.google_event_id,
                "profesional": t.profesional.nombre
            })

        return jsonify(turnos)

    except Exception as e:
        print("ERROR TURNOS MANICURISTA:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/sobre-nosotras")
def sobre_nosotras():
    return render_template("sobre_nosotras.html")


@app.route("/precios")
def precios():
    return render_template("precios.html")


@app.route("/cancelar", methods=["POST"])
def cancelar():
    try:
        data = request.json
        turno_id = data.get("id")

        turno = Turno.query.get(turno_id)

        if not turno:
            return jsonify({"error": "Turno no encontrado"}), 404

        calendar_id = CALENDARS_BY_PROFESSIONAL.get(turno.profesional.nombre.lower())
        event_id = turno.google_event_id

        print("Calendar ID:", calendar_id)
        print("Google Event ID:", event_id)

        # 1️⃣ Borrar evento en Google
        if calendar_id and event_id:
            try:
                service = get_calendar_service()
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=event_id
                ).execute()
            except Exception as e:
                print("Error eliminando evento en Google:", e)

        # 2️⃣ Borrar turno en DB
        db.session.delete(turno)
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as e:
        db.session.rollback()
        print("ERROR CANCELAR:", e)
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
