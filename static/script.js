document.addEventListener("DOMContentLoaded", function () {

/* VARIABLES */

let currentStep = 0;
let booking = { services: [] };

const steps = document.querySelectorAll(".step");
const progressSteps = document.querySelectorAll(".progress-step");

const calendarTitle = document.getElementById("calendarTitle");
const calendarGrid = document.getElementById("calendarGrid");
const selectedDateText = document.getElementById("selectedDateText");
const timeGrid = document.getElementById("timeGrid");

const DURACIONES = {
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
  "decoracion": 15 
};
const COMBOS_DURACION = {
  ["semipermanente|decoracion"]: 75,

  ["esmaltado común|belleza de pies"]: 90,

  ["semipermanente|belleza de pies"]: 120,
  ["semipermanente|decoracion|belleza de pies"]: 120,

  ["semipermanente|pedicuría"]: 120,
  ["semipermanente|decoracion|pedicuría"]: 120,

  ["kapping / dipping|pedicuría"]: 120,
  ["kapping / dipping|decoracion"]: 90,
  ["kapping / dipping|decoracion|pedicuría"]: 150,

  ["soft gel|belleza de pies"]: 120,
  ["soft gel|decoracion|belleza de pies"]: 150,
  ["soft gel|decoracion|pedicuría"]: 150
};

const SLOT_MINUTES = 30;

/* HELPERS */

function getSlotsNecesarios() {
  const duracion = booking.services.reduce((total, s) => total + (DURACIONES[s] || 0), 0);
  return Math.ceil(duracion / SLOT_MINUTES);
}

document.addEventListener("click", function (e) {
  const menu = document.getElementById("navLinks");
  const toggle = document.querySelector(".menu-toggle");

  // si el menú NO está abierto → no hacer nada
  if (!menu.classList.contains("active")) return;

  // si el click NO fue dentro del menú ni en el botón
  if (!menu.contains(e.target) && !toggle.contains(e.target)) {
    menu.classList.remove("active");
  }
});


function horaAMinutos(horaStr) {
  const [h, m] = horaStr.split(":").map(Number);
  return h * 60 + m;
}

function esHorarioValido(hora, ocupados, duracionServicio) {
  const start = horaAMinutos(hora);

  const slotsNecesarios = duracionServicio / SLOT_MINUTES;

  for (let i = 0; i < slotsNecesarios; i++) {
    const slotMin = start + i * SLOT_MINUTES;

    const h = String(Math.floor(slotMin / 60)).padStart(2, "0");
    const m = String(slotMin % 60).padStart(2, "0");
    const slotStr = `${h}:${m}`;

    if (ocupados.includes(slotStr)) {
      return false;
    }
  }

  return true;
}

function calcularDuracionTotal() {
  if (!booking.services || booking.services.length === 0) return 0;

  // normalizar a minúsculas
  const servicios = booking.services.map(s => s.toLowerCase().trim());

  // detectar decoración
  const tieneDeco = servicios.some(s => s.includes("decor"));

  // mapear servicios base
  const base = [];

  servicios.forEach(s => {
      // 🔥 PRIMERO retiros
      if (s.includes("retiro soft")) base.push("retiro soft gel");
      else if (s.includes("retiro semi")) base.push("retiro semipermanente");
      else if (s.includes("retiro kapping")) base.push("retiro kapping");
    
      // 🔽 después servicios normales
      else if (s.includes("semi")) base.push("semipermanente");
      else if (s.includes("común")) base.push("esmaltado común");
      else if (s.includes("kapping")) base.push("kapping / dipping");
      else if (s.includes("soft")) base.push("soft gel");
      else if (s.includes("belleza")) base.push("belleza de pies");
      else if (s.includes("pedicur")) base.push("pedicuría");
  });

  if (tieneDeco) base.push("decoracion");

  // clave ordenada
  const key = base.sort().join("|");
  console.log("SERVICIOS:", servicios);
  console.log("BASE:", base);
  console.log("KEY:", key);
  console.log("COMBO:", COMBOS_DURACION[key]);

  // 🔥 buscar combo
  if (COMBOS_DURACION[key]) {
    return COMBOS_DURACION[key];
  }

  // 🔁 fallback suma normal
  return servicios.reduce((total, s) => {
    return total + (DURACIONES[s] || 0);
  }, 0);
}

/* NAVEGACION */

window.showSection = function(sectionId) {
  document.querySelectorAll("#reservas section").forEach(sec => sec.classList.remove("active"));
  document.getElementById(sectionId).classList.add("active");
};

window.openBooking = function() { showSection("booking"); };
window.openMyTurns = function() { showSection("myAppointments"); };

window.toggleMenu = function() {
  document.getElementById("navLinks").classList.toggle("active");
};

window.scrollToSection = function(id) {
  const section = document.getElementById(id);
  if (section) section.scrollIntoView({ behavior: "smooth" });
};

/* HASH AL CARGAR */
if (window.location.hash === "#mis-turnos") {
  showSection("myAppointments");
}

/* CANCELAR TURNO */

window.cancelarTurno = async function(id) {
  if (!confirm("¿Querés cancelar este turno?")) return;

  try {
    const res = await fetch("/cancelar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });

    if (!res.ok) { alert("❌ No se pudo cancelar el turno"); return; }

    alert("✅ Turno cancelado correctamente");
    document.getElementById("checkAppointments").click();

  } catch (err) {
    console.error(err);
    alert("❌ Error de conexión");
  }
};

/* MIS TURNOS */

const checkBtn = document.getElementById("checkAppointments");

if (checkBtn) {
  checkBtn.addEventListener("click", async () => {
    const contactoIngresado = document.getElementById("contactInput").value.trim();
    const contenedor = document.getElementById("appointmentsList");
    contenedor.innerHTML = "";

    if (!contactoIngresado) {
      contenedor.innerHTML = "<p>Ingresá tu correo o teléfono.</p>";
      return;
    }

    try {
      const response = await fetch("/api/turnos?busqueda=" + encodeURIComponent(contactoIngresado));
      const data = await response.json();

      if (!response.ok) {
        contenedor.innerHTML = "<p>Error: " + (data.error || response.status) + "</p>";
        return;
      }

      if (!Array.isArray(data) || data.length === 0) {
        contenedor.innerHTML = "<p>No tenés turnos agendados.</p>";
        return;
      }

      const hoy = new Date().toISOString().split("T")[0];
      const turnosFuturos = data.filter(t => t.fecha >= hoy);
      if (turnosFuturos.length === 0) {
        contenedor.innerHTML = "<p>No tenés turnos agendados.</p>";
        return;
      }

      turnosFuturos.forEach(t => {
        const div = document.createElement("div");
        div.className = "turno-card";
        div.innerHTML =
          "<strong>" + t.servicio + "</strong><br>" +
          "Profesional: " + t.profesional + "<br>" +
          "Fecha: " + t.fecha + " " + t.hora + "<br><br>" +
          "<button onclick=\"cancelarTurno(" + t.id + ")\">Cancelar Turno</button>";
        contenedor.appendChild(div);
      });

    } catch (error) {
      console.error(error);
      contenedor.innerHTML = "<p>Error al cargar los turnos.</p>";
    }
  });
}

/* STEPS */

function resetSteps() {
  currentStep = 0;
  steps.forEach(s => s.classList.remove("active"));
  progressSteps.forEach(p => p.classList.remove("active"));
  steps[0].classList.add("active");
  progressSteps[0].classList.add("active");
}

function nextStep() {
  if (currentStep < steps.length - 1) {
    steps[currentStep].classList.remove("active");
    progressSteps[currentStep].classList.remove("active");
    currentStep++;
    steps[currentStep].classList.add("active");
    progressSteps[currentStep].classList.add("active");
  }
}

function prevStep() {
  if (currentStep > 0) {
    steps[currentStep].classList.remove("active");
    progressSteps[currentStep].classList.remove("active");
    currentStep--;
    steps[currentStep].classList.add("active");
    progressSteps[currentStep].classList.add("active");
  } else {
    showSection("home");
  }
}

async function continueStep() {

  if (currentStep === 0) {
    if (!booking.services || booking.services.length === 0) {
      alert("Seleccioná al menos un servicio");
      return;
    }
  }

  if (currentStep === 1) {
    if (!booking.professional) {
      alert("Seleccioná un profesional");
      return;
    }
  }

  if (currentStep === 2) {
    if (!booking.date || !booking.time) {
      alert("Seleccioná fecha y horario");
      return;
    }
  }

  nextStep();
}

/* SERVICIOS */

document.querySelectorAll("[data-service]").forEach(card => {
  card.addEventListener("click", () => {
    if (!booking.services) booking.services = [];

    const servicio = card.dataset.service;

    if (card.classList.contains("selected")) {
      card.classList.remove("selected");
      booking.services = booking.services.filter(s => s !== servicio);
    } else {
      card.classList.add("selected");
      booking.services.push(servicio);
    }

    console.log("Servicios:", booking.services);
  });
});

/* PROFESIONAL */

document.querySelectorAll("[data-professional]").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll("[data-professional]").forEach(b => b.classList.remove("selected"));
    btn.classList.add("selected");
    booking.professional = btn.dataset.professional;
    booking.date = null;
    booking.time = null;
    timeGrid.innerHTML = "";
    selectedDateText.innerText = "Seleccioná un día";
  };
});

/* CALENDARIO */

let currentDate = new Date();

const monthNames = [
  "enero","febrero","marzo","abril","mayo","junio",
  "julio","agosto","septiembre","octubre","noviembre","diciembre"
];

function renderCalendar() {
  if (!calendarGrid) return;

  calendarGrid.innerHTML =
    "<span>lu</span><span>ma</span><span>mi</span><span>ju</span>" +
    "<span>vi</span><span>sá</span><span>do</span>";

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  calendarTitle.innerText = monthNames[month] + " " + year;

  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const offset = firstDay === 0 ? 6 : firstDay - 1;

  for (let i = 0; i < offset; i++) {
    calendarGrid.innerHTML += "<span></span>";
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const fecha = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
    const esDomingo = fecha.getDay() === 0;
  
    const btn = document.createElement("button");
    btn.className = "day";
    btn.innerText = day;
  
    if (esDomingo) {
      btn.classList.add("disabled");
      btn.disabled = true;
    } else {
      btn.onclick = () => selectDay(day);
    }
  
    calendarGrid.appendChild(btn);
  }
}

function selectDay(day) {
  document.querySelectorAll(".day").forEach(d => d.classList.remove("selected"));
  document.querySelectorAll(".day").forEach(btn => {
    if (parseInt(btn.innerText) === day) btn.classList.add("selected");
  });

  const dd = String(day).padStart(2, "0");
  const mm = String(currentDate.getMonth() + 1).padStart(2, "0");
  booking.date = dd + "/" + mm;
  selectedDateText.innerText = booking.date;

  loadTimes();
}

function changeMonth(direction) {
  currentDate.setMonth(currentDate.getMonth() + direction);
  renderCalendar();
  timeGrid.innerHTML = "";
  selectedDateText.innerText = "Seleccioná un día";
  booking.date = null;
  booking.time = null;
}

/* HORARIOS */

async function loadTimes() {
  booking.time = null;

  if (!booking.date) {
    timeGrid.innerHTML = "<p>Seleccioná un día primero</p>";
    return;
  }

  timeGrid.innerHTML = "Cargando horarios...";

  const parts = booking.date.split("/");
  const fechaISO = new Date().getFullYear() + "-" + parts[1] + "-" + parts[0];
  const duracionTotal = calcularDuracionTotal();

  const profesionalQuery = booking.professional === "cualquiera" ? "todos" : booking.professional;

  try {
    const res = await fetch(
      "/ocupados?fecha=" + fechaISO +
      "&profesional=" + profesionalQuery +
      "&duracion=" + duracionTotal
    );

    if (!res.ok) throw new Error("Error en backend");

    const data = await res.json();
    const ocupados = (data.ocupados || []).map(h => h.slice(0, 5));

    console.log("Ocupados recibidos:", ocupados);

    if (data.vacaciones) {
      timeGrid.innerHTML = "<p>Profesional de vacaciones</p>";
      return;
    }


  const horarios = [];

  // detectar día
  const fechaObj = new Date(new Date().getFullYear(), parts[1] - 1, parts[0]);
  const dia = fechaObj.getDay();
  
  const esSabado = dia === 6;
  const esLunes = dia === 1;
  
 
  
  // 🔥 horarios de cierre
  const cierre = esSabado ? 17 : 19; // sábado corta antes
  
  // 🔥 último inicio permitido según duración
  const ultimoInicio = (cierre * 60) - duracionTotal;
  
  // 🔥 hora mínima dinámica
  let horaMin = 10;
  const profesional = booking.professional?.toLowerCase().trim();
  
  if (
      esLunes &&
      (
          profesional === "rocio" ||
          profesional === "pamela"
      )
  ) {
      horaMin = 14;
  }
  
  // generar horarios
  for (let h = horaMin; h < cierre; h++) {
    const horaEnPunto = String(h).padStart(2, "0") + ":00";
    const horaYMedia = String(h).padStart(2, "0") + ":30";
  
    [horaEnPunto, horaYMedia].forEach(hora => {
  
      // ❌ excluir 10:30
      if (hora === "10:30") return;
  
      const minutos = horaAMinutos(hora);
  
      // 🔥 CLAVE: validar contra duración
      if (minutos <= ultimoInicio) {
        horarios.push(hora);
      }
  
    });
  }

    timeGrid.innerHTML = "";





    horarios.forEach(hora => {
      const btn = document.createElement("button");
      btn.className = "time-slot";
      btn.innerText = hora;

      if (booking.professional === "cualquiera") {
      
        // 👉 solo bloquear si TODOS ocupados
        if (ocupados.includes(hora)) {
          btn.classList.add("occupied");
          btn.disabled = true;
        }
      
      } else {
      
        // 👉 lógica normal con duración
        if (!esHorarioValido(hora, ocupados, duracionTotal)) {
          btn.classList.add("occupied");
          btn.disabled = true;
        }
      
      }

      btn.onclick = () => {
        document.querySelectorAll(".time-slot").forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        booking.time = hora;
      };

      timeGrid.appendChild(btn);
    });

  } catch (error) {
    console.error("ERROR FETCH:", error);
    timeGrid.innerHTML = "<p>Error cargando horarios</p>";
  }
}

/* CONFIRMAR RESERVA */

const confirmBtn = document.getElementById("confirmBtn");

if (confirmBtn) {
  confirmBtn.addEventListener("click", async () => {
    const nombre = document.getElementById("Name").value;
    const contacto = document.getElementById("Contact").value;
    const email = document.getElementById("Email").value;

    if (booking.services.length === 0 || !booking.date || !booking.time || !nombre || !contacto || !email) {
      alert("Completá todos los datos, incluyendo el correo");
      return;
    }

    const [dd, mm] = booking.date.split("/");
    const fechaISO = new Date().getFullYear() + "-" + mm + "-" + dd;
    const duracionTotal = calcularDuracionTotal();

    try {
      const res = await fetch("/reservar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre,
          contacto,
          email,
          servicio: booking.services.join(", "),
          profesional: booking.professional.toLowerCase(),
          fecha: fechaISO,
          hora: booking.time,
          duracion: duracionTotal
        })
      });

      const data = await res.json();

      if (!res.ok) {
        alert("❌ " + (data.error || "Error al reservar"));
        return;
      }

      const profesionalNombre = data.profesional
        ? data.profesional.charAt(0).toUpperCase() + data.profesional.slice(1)
        : "";

      const mensaje = profesionalNombre
        ? "Turno reservado con " + profesionalNombre
        : "Turno reservado";

      alert("✅ " + mensaje);

      showSection("home");
      resetSteps();

    } catch (err) {
      console.error(err);
      alert("Error de conexión");
    }
  });
}

/* INICIO */

if (calendarGrid) renderCalendar();

window.continueStep = continueStep;
window.prevStep = prevStep;
window.nextStep = nextStep;
window.changeMonth = changeMonth;

showSection("home");

});

/* =========================
   CAROUSEL GLOBAL
========================= */

let index = 0;

window.moveSlide = function(direction) {
  const track = document.getElementById("carouselTrack");
  if (!track) return;

  const slides = track.children;
  index += direction;

  if (index < 0) index = slides.length - 1;
  if (index >= slides.length) index = 0;

  track.style.transform = "translateX(-" + (index * 100) + "%)";
};

setInterval(() => { window.moveSlide(1); }, 4000);

document.addEventListener("DOMContentLoaded", function () {
  const track = document.getElementById("carouselTrack");
  if (!track) return;

  let startX = 0;

  track.addEventListener("touchstart", (e) => { startX = e.touches[0].clientX; });
  track.addEventListener("touchend", (e) => {
    const endX = e.changedTouches[0].clientX;
    if (startX - endX > 50) window.moveSlide(1);
    if (endX - startX > 50) window.moveSlide(-1);
  });
});
