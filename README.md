# Paneles Solares Familia — sitio web de ahorro

Sitio web privado (con PIN) que muestra el ahorro y la boleta estimada de
las dos instalaciones de paneles solares (tu casa y la de tus papás), a
partir de los datos de FusionSolar. Pensado para que tus papás solo tengan
que abrir un link y escribir un código — nada técnico de su parte.

## Cómo está armado

No hay ningún servidor que tengas que mantener corriendo. Todo funciona con
dos piezas gratuitas de GitHub:

1. **GitHub Actions** (`.github/workflows/actualizar-datos.yml`): todos los
   días, en la nube de GitHub, se conecta a FusionSolar con tus credenciales
   (guardadas como *secrets* cifrados, nunca visibles en el código ni en
   este chat), calcula el ahorro/boleta estimada y guarda el resultado en
   `docs/data/*.json`.
2. **GitHub Pages**: sirve la carpeta `docs/` como sitio web estático — el
   HTML/CSS/JS que ven tú y tus papás, con un PIN de entrada.

```
paneles-solares-web/
├── .github/workflows/actualizar-datos.yml   # el "cron" diario
├── config.yaml                                # tarifas (no es secreto)
├── scripts/
│   ├── fetch_daily.py                          # login FusionSolar + cálculo
│   ├── tariff.py                                # fórmula de ahorro/boleta
│   └── requirements.txt
└── docs/                                        # esto es lo que se publica como web
    ├── index.html / style.css / app.js
    └── data/
        ├── historial.json   (se genera solo)
        ├── resumen.json     (se genera solo)
        └── auth.json        (se genera solo, guarda el PIN ya "hasheado")
```

## Seguridad: qué es y qué NO es este PIN

Elegiste la opción simple (link + PIN compartido), así que sé transparente
sobre qué tan privado es esto:

- El PIN nunca se guarda en texto plano en el repo, solo su hash SHA-256
  (`auth.json`), y el sitio no lo deja pasar si no coincide.
- El sitio no aparece en buscadores (`robots: noindex`) y el link no es fácil
  de adivinar si le pones un nombre de repositorio poco obvio.
- PERO: es un sitio público servido por GitHub Pages. Si alguien tiene el
  link exacto, la pantalla de PIN lo detiene para ver el contenido, aunque
  técnicamente los archivos `docs/data/*.json` son accesibles directamente
  si alguien adivina esa URL. No es cifrado de verdad, es una barrera simple
  para visitas casuales — adecuado para datos de consumo eléctrico, no para
  información realmente sensible.
- Si más adelante quieres algo más serio (acceso solo con el email de cada
  uno, login de verdad), se puede migrar a Cloudflare Pages + Cloudflare
  Access (gratis hasta 50 usuarios) — mencionalo cuando quieras dar ese paso.

Tus contraseñas de FusionSolar SÍ están genuinamente protegidas: viven solo
como *GitHub Secrets* cifrados, nunca se escriben en ningún archivo del
repositorio ni pasan por este chat.

## Paso a paso para publicarlo

### 1. Crear el repositorio en GitHub

En [github.com/new](https://github.com/new), crea un repositorio **público**
(necesario para GitHub Pages gratis) llamado, por ejemplo,
`paneles-solares-familia`. No marques "Add a README".

### 2. Subir este proyecto

Descomprime el zip que te envié y, desde esa carpeta:

```bash
cd paneles-solares-web
git init
git add .
git commit -m "Primera versión del sitio de paneles solares"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/paneles-solares-familia.git
git push -u origin main
```

### 3. Configurar los secrets (credenciales)

En GitHub: **Settings → Secrets and variables → Actions → New repository
secret**. Crea uno por uno (nombre exacto a la izquierda, valor a la derecha):

| Nombre | Valor |
|---|---|
| `CASA_USUARIO` | tu usuario de FusionSolar |
| `CASA_PASSWORD` | tu contraseña de FusionSolar |
| `CASA_SUBDOMAIN` | `la5` (o el subdominio que uses para iniciar sesión) |
| `PADRES_USUARIO` | usuario de FusionSolar de tus papás |
| `PADRES_PASSWORD` | contraseña de FusionSolar de tus papás |
| `PADRES_SUBDOMAIN` | `la5` (ajusta si es distinto) |
| `SITE_PIN` | el código que van a usar tú y tus papás para entrar (ej. `2026`) |

### 4. Tarifas ya completadas

`config.yaml` ya viene con los datos reales de ambas boletas (misma
distribuidora Enel, tarifa BT1-T6 en las dos, ambas a nombre de tu papá):

- `casa` → tu casa en Ñuñoa (boleta a nombre de Ricardo San Martín).
- `padres` → la casa de tus papás en La Florida (boleta a nombre de
  Inmobiliaria Cumbre de Macul Ltda.).

No necesitas tocar nada aquí para partir. Si en algún momento cambia tu
tarifa (Enel las reajusta cada cierto tiempo) o quieres afinar los cargos
fijos, edita `cuentas.<casa|padres>.tarifa` en `config.yaml` y sube el
cambio:

```bash
git add config.yaml
git commit -m "Actualizar tarifa"
git push
```

### 5. Activar GitHub Pages

**Settings → Pages → Build and deployment → Source**: elige
`Deploy from a branch`, rama `main`, carpeta `/docs`. Guarda. GitHub te va a
mostrar la URL del sitio (algo como
`https://TU_USUARIO.github.io/paneles-solares-familia/`).

### 6. Primera ejecución manual

Ve a la pestaña **Actions** del repositorio → selecciona
"Actualizar datos de paneles solares" → **Run workflow**. Esto corre el
script por primera vez y genera los datos reales. Revisa el log: si alguna
cuenta falla (usuario/contraseña incorrectos, CAPTCHA, etc.), el mensaje de
error te va a decir cuál.

A partir de ahí, el workflow corre solo todos los días (20:30 hora de Chile
por defecto — lo puedes cambiar editando el `cron` en el archivo del
workflow).

### 7. Compartir con tus papás

Envíales el link de GitHub Pages y el PIN (`SITE_PIN` que elegiste) por
WhatsApp, por ejemplo. Solo tienen que abrir el link, escribir el código, y
ya ven el resumen — sin instalar nada.

## Nota sobre la precisión de los datos

FusionSolar no entrega un historial completo por API para cuentas
residenciales normales (por eso se usa `fusion_solar_py`, una librería no
oficial que automatiza el login web), y solo devuelve el total del día en
curso. Esto significa que:

- El historial se va construyendo día a día desde que actives el workflow —
  no hay forma de rellenar automáticamente los días anteriores.
- Los primeros días vas a ver el ciclo de facturación incompleto (con menos
  datos de los reales), y la estimación va a ser más precisa mientras más
  días lleve corriendo.
- La fórmula de ahorro/boleta fue calibrada contra la boleta real que
  subiste (diferencia de ~0,2% con el monto real de $70.951), pero sigue
  siendo una aproximación: no reproduce cargos ocasionales o promociones
  puntuales que a veces aparecen en la boleta real.

## Si algo deja de funcionar

Como el método de conexión a FusionSolar no es oficial (Huawei no da API
pública a clientes residenciales), si Huawei cambia su sitio web el login
automático puede romperse. La señal es que el workflow en la pestaña
"Actions" empieza a fallar — ahí me puedes pedir ayuda para revisarlo, o
revisar si hay una versión nueva de `fusion_solar_py` que lo arregle
(`pip install -U fusion_solar_py` en `scripts/requirements.txt`).
