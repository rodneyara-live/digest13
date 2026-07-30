# 📰 Digest 13 — Daily News Digest & TTS Automation Pipeline

Digest 13 es un servicio de automatización local para la generación, síntesis de voz y entrega diaria de un informe periodístico curado. 

El sistema consulta modelos de lenguaje a través de API, genera un resumen maquetado en HTML y un archivo de audio MP3 de alta fidelidad utilizando síntesis de voz neuronal (`edge-tts`), enviando el paquete consolidado por correo electrónico para un consumo multisensorial (lectura + audio en paralelo) desde clientes como Thunderbird.

---

## 📐 Arquitectura del Sistema

```mermaid
flowchart TD
    %% Estilos de Nodos
    classDef systemd fill:#2b303a,stroke:#3b82f6,stroke-width:2px,color:#fff
    classDef script fill:#1e293b,stroke:#0ea5e9,stroke-width:2px,color:#fff
    classDef api fill:#0f172a,stroke:#8b5cf6,stroke-width:1.5px,color:#fff
    classDef process fill:#1e1b4b,stroke:#6366f1,stroke-width:1.5px,color:#fff
    classDef client fill:#022c22,stroke:#10b981,stroke-width:2px,color:#fff

    subgraph OS ["🖥️ EJECUCIÓN LOCAL (Ubuntu Linux)"]
        A["⏱️ systemd.timer<br/>(7:00 AM / Persistent=true)"]:::systemd --> B["🐍 script: main.py"]:::script

        subgraph Pipeline ["⚙️ Motor de Procesamiento"]
            B --> C["📡 RSS Feed Aggregator<br/>(Guardian, BBC, Al Jazeera,<br/>Delfino, Semanario, Ars)"]:::process
            C --> D["🤖 Groq API (LLaMA 3.3 70B)<br/>(Texto Curado LLM)"]:::api
            B --> E["🗣️ edge-tts Engine<br/>(Sintetiza MP3)"]:::api
            B --> F["🎨 HTML Generator<br/>(Ensambla Plantilla)"]:::api

            D --> G["📦 MIME Package Builder<br/>(HTML + Audio Incrustado)"]:::process
            E --> G
            F --> G
        end

        G --> H["📤 SMTP Transport Engine"]:::script
    end

    H --> I["🛡️ Servicio SMTP / Brevo"]:::client
    I --> J["📬 Cliente de Correo<br/>(Thunderbird Desktop / Mobile)"]:::client
```

---

## 📋 Requerimientos del Sistema

* **Sistema Operativo:** Linux (Probado y optimizado para Ubuntu 24.04 LTS / 26.04 LTS).
* **Lenguaje:** Python 3.10 o superior.
* **Dependencias de Python:**
* `groq` (Cliente oficial de la API de Groq).
* `edge-tts` (Síntesis de voz neuronal de Microsoft Edge).
* `python-dotenv` (Manejo de variables de entorno).
* `markdown` (Conversión Markdown → HTML).
* `feedparser` (Consumo de fuentes RSS).

* **Servicios Externos:**
* API Key de Groq (Gratuito / Sin prepago necesario).
* Cuenta SMTP para envío de correos (Brevo, etc.).

---

## 📦 Aislamiento y Estructura Autocontenida

Para garantizar que el proyecto no contamine el sistema de archivos global (`~/.cache/`, `~/.local/`), **Digest 13** exige las siguientes directrices de arquitectura:

1. **Directorio de Cache Local:** Todas las librerías que generen caché temporal o descarguen recursos deben redirigir sus salidas a `digest-13/.cache/`.
   
   ```python
   import os
   from pathlib import Path
   ```

PROJECT_ROOT = Path(__file__).parent.resolve()
os.environ["HF_HOME"] = str(PROJECT_ROOT / ".cache" / "huggingface")
os.environ["XDG_CACHE_HOME"] = str(PROJECT_ROOT / ".cache")
os.environ["TORCH_HOME"] = str(PROJECT_ROOT / ".cache" / "torch")

```
2. **Aceleración por GPU (NVIDIA Quadro T2000 / Turing 4GB VRAM):** En caso de integrar módulos locales opcionales de procesamiento futuro (vía PyTorch u ONNX), el código debe detectar la GPU mediante CUDA (`device = 'cuda'`) utilizando precisión `float16` o cuantización de 4 bits (`INT4`) para operar dentro del límite de memoria de la tarjeta.
3. **Limpieza en Git:** El archivo `.gitignore` debe excluir todo archivo o caché local generado.

---

## 🛠️ Configuración e Instalación

### 1. Clonar el repositorio y preparar el entorno

```bash
git clone [https://github.com/tu-usuario/digest-13.git](https://github.com/tu-usuario/digest-13.git)
cd digest-13

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar Variables de Entorno (`.env`)

Crea un archivo `.env` en la raíz del proyecto. **Nunca subas este archivo al repositorio Git**.

```ini
# Configuración de Groq API
GROQ_API_KEY="gsk_tu_api_key_aqui..."
LLM_MODEL="llama-3.3-70b-versatile"

# Configuración de la Voz (TTS)
TTS_VOICE="es-CR-MariaNeural"

# Configuración SMTP
SMTP_SERVER="smtp-relay.brevo.com"
SMTP_PORT=587
SMTP_USERNAME="tu_usuario_smtp"
SMTP_PASSWORD="tu_password_smtp"

# Remitente y Destinatario
EMAIL_FROM="remitente@verified.com"
EMAIL_TO="destino@correo.com"
```

---

## 📡 Fuentes RSS Agregadas

El pipeline recolecta titulares y sumarios de las siguientes fuentes RSS antes de enviarlos al LLM como contexto:

| Sección | Fuentes RSS |
|---------|-------------|
| Geopolítica y América Latina | The Guardian (world + americas), BBC News, Al Jazeera |
| Política y Sociedad Costarricense | Delfino.cr, Semanario Universidad |
| Tecnología y Cultura Digital | The Guardian (technology), Ars Technica |

Cada entrada incluye su fuente (`[The Guardian]`), y el prompt exige citar `(Fuente: ...)` al final de cada noticia. El contexto RSS se inyecta antes del prompt con la instrucción de basarse únicamente en esos resultados.

---

## 🗣️ Limpieza de Texto para TTS

Antes de la síntesis de voz, el texto markdown generado por el LLM se limpia mediante `text_cleaner.strip_markdown()` para eliminar:
- Encabezados (`#` a `######`)
- Negritas (`**texto**`) y cursivas (`*texto*`)
- Enlaces markdown (`[texto](url)`)
- Código inline (`` `codigo` ``)
- Listas (`- `, `1. `)
- Citas (`> `)

Esto evita que el TTS lea en voz alta símbolos de formato.

---

## 🎯 Prompt de Calibración Integrado

El backend en Python debe enviar el siguiente prompt exacto al modelo de lenguaje para garantizar la maquetación en bloques independientes, evitando párrafos masivos o respuestas continuas:

```text
ROL Y PERSONALIDAD DEL AGENTE: Eres el Editor Senior y Analista de Inteligencia de un boletín privado de alto nivel ("Digest 13"). Tu personalidad es sobria, analítica, pragmática y tica en su contexto, con un ojo agudo para la ingeniería, la tecnología profunda, el software libre, la soberanía digital, la fotografía física y la macroeconomía. Desprecias la prensa amarillista, las efemérides baratas, los comunicados de prensa corporativos, el circo mediático/vulgaridades de la política, la "tecnología de vitrina" de consumo y el "moralismo pedagógico" en las noticias. Tu trabajo no es resumir el internet, sino separar el grano de la paja para un lector técnico y pragmático.

REGLAS ESTRUCTURALES Y DE FORMATO:
- CERO MORALISMO Y CERO CONCLUSIONES VACÍAS: Queda ESTRICTAMENTE PROHIBIDO terminar las notas con frases aleccionadoras, genéricas o éticas como "Esto demuestra la importancia de...", "Subraya la necesidad de...", "Refleja los desafíos de..." o "Nos invita a reflexionar...". Entrega únicamente el HECHO, el CONTEXTO y la IMPLICACIÓN real.
- Cada sección DEBE contener notas periodísticas 100% INDEPENDIENTES entre sí.
- Queda ESTRICTAMENTE PROHIBIDO redactar ensayos continuos, fusionar noticias dentro de un mismo párrafo o usar conectores como "Por otro lado", "En paralelo" o "En materia de...".
- Cada noticia DENTRO de una sección DEBE llevar obligatoriamente esta estructura:
  ### [Título descriptivo, técnico y directo]
  [Un único párrafo independiente de 3 a 5 oraciones que detalle: Hecho concreto + Marco/Antecedente + Impacto o Implicación operativa/económica.]
  *(Fuente: [Nombre del medio])*

CONTENIDO Y COBERTURA POR SECCIÓN:

1. GEOPOLÍTICA Y AMÉRICA LATINA (Fuentes: The Guardian, BBC, Al Jazeera)
   - Selecciona hasta 6 acontecimientos de alto impacto sistémico (relaciones bilaterales, conflictos, macroeconomía, crisis de sucesión gubernamental o control de recursos).
   - Proporción obligatoria: Incluye al menos 2 temas relevantes de América Latina o el Sur Global para evitar un sesgo puramente eurocéntrico.
   - EXCLUSIÓN ABSOLUTA: Pifias diplomáticas o desaciertos de protocolo de mandatarios (ej. mapas errados, declaraciones ridículas sin efecto legal/militar), noticias de color local o curiosidades sin impacto real.

2. POLÍTICA Y SOCIEDAD COSTARRICENSE (Fuentes: Delfino.cr, Semanario Universidad)
   - Selecciona hasta 6 temas sobre la realidad institucional costarricense.
   - Incluye al menos 1 o 2 noticias de Semanario Universidad por tirada.
   - Prioriza la fiscalización del poder público, proyectos de ley en debate, resoluciones judiciales/constitucionales, indicadores macroeconómicos (deuda, tipo de cambio, inflación, impuestos) y tensiones en infraestructura/seguridad pública.
   - VACUNA ANTI-CIRCO POLÍTICO: Descarta por completo ataques personales, exabruptos, insultos, apodos a medios o funcionarios, disputas de micrófono y show mediático. Si una polémica contiene una propuesta real (ej. cambios en IVA o choques de competencia OIJ-Seguridad), EXTRAE ÚNICAMENTE el proyecto, la ley o el impacto económico/operativo, ignorando la chabacanería.
   - EXCLUSIÓN ABSOLUTA: Efemérides, aniversarios históricos, boletines universitarios/corporativos, actos protocolarios, inauguraciones locales, deportes y sucesos.

3. TECNOLOGÍA, INGENIERÍA, FOTOGRAFÍA TÉCNICA Y SOFTWARE
   - Selecciona entre 2 y 4 temas de fondo con impacto real:
     * Ingeniería y Procesos: Avances en ingeniería mecánica, manufactura, procesos industriales, ciencia de materiales o eficiencia energética aplicada.
     * Fotografía Técnica y Óptica: Avances en sensores dedicados, trazabilidad/firmas criptográficas de imagen (C2PA), evolución de óptica física y tecnología fotográfica no sintética.
     * Infraestructura e IA: Cambios en la economía del cómputo (costos de API/tokens), modelos abiertos/locales, soberanía digital y Linux/Open Source.
     * Hardware y Componentes: Crisis de silicio, precios de almacenamiento/RAM y fallos estructurales de arquitectura de procesadores.
     * Alertas de Videojuegos: ÚNICAMENTE si un juego AAA o Indie aclamado está 100% GRATIS para reclamar (Epic, GOG o Steam) o tiene descuento de 75% o más. Si no, IGNORA la industria.
   - EXCLUSIÓN ABSOLUTA: Tecnología de consumo de vitrina (lanzamientos de teléfonos, pantallas, audífonos), parches menores de versión, reseñas de gadgets y noticias de videojuegos a precio completo.

TONO: Imparcial, denso en datos, técnico, directo y de nivel profesional.
```

---

## 🎨 Plantilla HTML de Salida

El script debe encapsular el texto generado e incrustar el audio en la siguiente plantilla HTML responsiva para garantizar que la barra de reproducción esté visible en la parte superior:

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Digest 13 - Informe Diario</title>
    <style>
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #24292e;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f6f8fa;
        }
        .container {
            background: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }
        .audio-player {
            position: sticky;
            top: 0;
            background: #f1f3f5;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 25px;
            border: 1px solid #e1e4e8;
            z-index: 100;
        }
        audio {
            width: 100%;
        }
        h1 { border-bottom: 2px solid #eaecef; padding-bottom: 10px; font-size: 1.5rem; color: #0366d6; }
        h2 { font-size: 1.2rem; margin-top: 30px; color: #24292e; border-bottom: 1px solid #eaecef; padding-bottom: 5px; }
        h3 { font-size: 1rem; color: #005cc5; margin-top: 20px; }
        p { text-align: justify; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="audio-player">
            <p style="margin:0 0 8px 0; font-weight:bold; font-size:0.85rem; color:#586069;">🎧 ESCUCHAR DIGEST 13:</p>
            <audio controls src="cid:audio_resumen_mp3"></audio>
        </div>
        <!-- TEXTO DEL BOLETÍN GENERADO POR EL LLM -->
        {{CONTENIDO_NOTICIAS_HTML}}
    </div>
</body>
</html>
```

---

## ⚙️ Automatización en Linux mediante `systemd`

Para ejecutar Digest 13 diariamente a primera hora sin importar si la computadora estuvo apagada, crea los siguientes dos archivos en `~/.config/systemd/user/`:

### 1. `digest13.service`

```ini
[Unit]
Description=Servicio Digest 13 - Generacion de Noticias y TTS Diario
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/ruta/a/tu/proyecto/digest-13
ExecStart=/ruta/a/tu/proyecto/digest-13/venv/bin/python src/main.py

[Install]
WantedBy=default.target
```

### 2. `digest13.timer`

```ini
[Unit]
Description=Timer Diario para Digest 13

[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### Habilitar el temporizador:

```bash
systemctl --user daemon-reload
systemctl --user enable --now digest13.timer
```

La directiva `Persistent=true` asegura que si la máquina estaba apagada a las 7:00 AM, el script detectará el evento pendiente y se ejecutará automáticamente unos segundos después de que enciendas el sistema.

---

## 🔒 Consideraciones de Seguridad

1. **Aislamiento de Credenciales:** La cuenta SMTP configurada para enviar los correos debe ser una cuenta secundaria (p. ej. Proton Mail con contraseña de aplicación o token aislado) sin privilegios sobre cuentas personales principales.
2. **Exclusión de Git:** Asegurarse de que `.env`, la carpeta `venv/`, el directorio `.cache/` y cualquier archivo `.mp3` o `.html` temporal generado estén especificados dentro de `.gitignore`:
   
   ```gitignore
   venv/
   .cache/
   .env
   __pycache__/
   *.mp3
   *.html
   ```

```

```

```
