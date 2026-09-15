// --- Formato de moneda chilena ---
function clp(valor) {
  return "$" + Math.round(valor).toLocaleString("es-CL");
}

function fechaLegible(iso) {
  const [y, m, d] = iso.split("-");
  const meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  return `${parseInt(d)} ${meses[parseInt(m) - 1]}`;
}

// --- Validación de PIN (compara el hash SHA-256, nunca el PIN en texto plano) ---
async function sha256(texto) {
  const buffer = new TextEncoder().encode(texto);
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function verificarPin() {
  const input = document.getElementById("input-pin");
  const error = document.getElementById("error-pin");
  const pin = input.value.trim();

  if (!pin) return;

  try {
    const resp = await fetch("data/auth.json", { cache: "no-store" });
    if (!resp.ok) throw new Error("no auth.json");
    const auth = await resp.json();
    const hashIngresado = await sha256(pin);

    if (hashIngresado === auth.pin_hash) {
      sessionStorage.setItem("acceso_ok", "1");
      mostrarApp();
    } else {
      error.textContent = "Código incorrecto, inténtalo de nuevo.";
      input.value = "";
      input.focus();
    }
  } catch (e) {
    // Si no existe auth.json (sitio recién desplegado, aún no corre el primer
    // workflow), dejamos pasar para no bloquear la primera configuración.
    console.warn("No se pudo validar el PIN, se permite el acceso:", e);
    mostrarApp();
  }
}

function mostrarApp() {
  document.getElementById("pantalla-pin").classList.add("oculto");
  document.getElementById("app").classList.remove("oculto");
  cargarDatos();
}

// --- Carga y render de datos ---
async function cargarDatos() {
  const contenedor = document.getElementById("contenedor-casas");
  try {
    const [resumenResp, historialResp] = await Promise.all([
      fetch("data/resumen.json", { cache: "no-store" }),
      fetch("data/historial.json", { cache: "no-store" }),
    ]);
    const resumen = await resumenResp.json();
    const historial = await historialResp.json();

    document.getElementById("fecha-actualizacion").textContent =
      "Actualizado: " + fechaLegible(resumen.generado_en);

    const claves = Object.keys(resumen.casas || {});
    if (claves.length === 0) {
      contenedor.innerHTML = `<p class="aviso-sin-datos">Todavía no hay datos suficientes. Vuelve a revisar en un par de días.</p>`;
      return;
    }

    contenedor.innerHTML = "";
    claves.forEach((clave, i) => {
      const est = resumen.casas[clave];
      const dias = (historial[clave] || []).slice(-30);
      contenedor.appendChild(crearTarjetaCasa(clave, est, dias, i));
    });

    claves.forEach((clave) => {
      const dias = (historial[clave] || []).slice(-30);
      if (dias.length > 1) dibujarGrafico(clave, dias);
    });
  } catch (e) {
    contenedor.innerHTML = `<p class="aviso-sin-datos">No se pudieron cargar los datos. Intenta más tarde.</p>`;
    console.error(e);
  }
}

function crearTarjetaCasa(clave, est, dias, index) {
  const div = document.createElement("div");
  div.className = "tarjeta-casa";
  div.innerHTML = `
    <h2>${est.nombre}</h2>
    <p class="periodo">Ciclo actual: ${fechaLegible(est.fecha_inicio)} – ${fechaLegible(est.fecha_fin)}</p>

    <div class="metricas-clave">
      <div class="metrica ahorro">
        <div class="valor">${clp(est.ahorro_total_clp)}</div>
        <div class="etiqueta">Ahorro estimado del ciclo</div>
      </div>
      <div class="metrica boleta">
        <div class="valor">${clp(est.monto_estimado_clp)}</div>
        <div class="etiqueta">Boleta estimada</div>
      </div>
    </div>

    <div class="detalle-kwh">
      <div><div class="num">${est.produccion_kwh.toFixed(0)}</div><div class="lbl">kWh generados</div></div>
      <div><div class="num">${est.autoconsumo_kwh.toFixed(0)}</div><div class="lbl">kWh autoconsumo</div></div>
      <div><div class="num">${est.inyeccion_red_kwh.toFixed(0)}</div><div class="lbl">kWh inyectados</div></div>
      <div><div class="num">${est.compra_red_kwh.toFixed(0)}</div><div class="lbl">kWh comprados</div></div>
    </div>

    ${est.credito_no_usado_clp > 0
      ? `<p class="proxima-lectura">Crédito a favor para el próximo ciclo: ${clp(est.credito_no_usado_clp)}</p>`
      : ""}
    <p class="proxima-lectura">📅 Próxima lectura estimada: ${fechaLegible(est.proxima_lectura)}</p>

    <div class="grafico-contenedor">
      <canvas id="grafico-${clave}"></canvas>
    </div>
  `;
  return div;
}

function dibujarGrafico(clave, dias) {
  const ctx = document.getElementById(`grafico-${clave}`);
  if (!ctx) return;

  new Chart(ctx, {
    type: "line",
    data: {
      labels: dias.map(d => fechaLegible(d.fecha)),
      datasets: [
        {
          label: "Producción (kWh)",
          data: dias.map(d => d.produccion_kwh),
          borderColor: "#E8A23D",
          backgroundColor: "#E8A23D22",
          fill: true,
          tension: 0.3,
          pointRadius: 0,
        },
        {
          label: "Consumo (kWh)",
          data: dias.map(d => d.consumo_kwh),
          borderColor: "#3D6FE8",
          backgroundColor: "#3D6FE822",
          fill: true,
          tension: 0.3,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: { ticks: { maxTicksLimit: 6, font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { font: { size: 10 } } },
      },
    },
  });
}

// --- Inicio ---
document.getElementById("btn-entrar").addEventListener("click", verificarPin);
document.getElementById("input-pin").addEventListener("keydown", (e) => {
  if (e.key === "Enter") verificarPin();
});

if (sessionStorage.getItem("acceso_ok") === "1") {
  mostrarApp();
}
