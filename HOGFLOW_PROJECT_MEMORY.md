# Memoria oficial del proyecto HogFlow

> Documento vivo de contexto técnico y operativo. Debe leerse junto con
> `AGENTS.md`, no en sustitución de sus reglas normativas.

Última reconstrucción integral: 25 de julio de 2026.
Última actualización incremental: Phase 7, 25 de julio de 2026.

Línea base técnica de Phase 7:
`ee40b6529aa833b9ab701da06347defccfd3fb52`
(`Implement Phase 6 line position evaluation`). Phase 7 se publica mediante el
commit `Implement Phase 7 reverse and duplicate counting`; su SHA final debe
consultarse con Git porque un documento no puede incluir de forma
autorreferencial el SHA del mismo commit que lo contiene.

## Cómo interpretar esta memoria

Esta memoria reconstruye el proyecto a partir del repositorio, su historial de
Git y las decisiones conservadas en la conversación de desarrollo. Usa estas
etiquetas:

- **HECHO VERIFICADO**: respaldado por código, pruebas, documentación o Git.
- **DECISIÓN HISTÓRICA**: intención o decisión explícita conservada en la
  conversación y compatible con el repositorio.
- **INFERENCIA**: conclusión razonable derivada de evidencia, pero no medida
  directamente como resultado empírico.
- **PROPUESTA PENDIENTE**: idea que requiere aprobación o especificación futura.
- **LIMITACIÓN**: frontera de evidencia o capacidad conocida.

Cuando la conversación y el repositorio difieren, el repositorio es la fuente
de verdad sobre el comportamiento técnico actual. La conversación explica la
intención y el contexto histórico, pero no convierte una idea en funcionalidad.
`AGENTS.md` conserva precedencia normativa para reglas de trabajo y roadmap.

---

## 1. Identidad del proyecto

### 1.1 Nombre, propósito y problema

- **Nombre:** HogFlow.
- **Estado:** prototipo de investigación / MVP; no es un sistema de producción,
  un piloto completado ni un producto comercialmente validado.
- **Propósito:** evaluar si visión por computadora puede ayudar a reconciliar el
  conteo de cerdos que atraviesan un pasaje físico restringido.
- **Problema de negocio bajo investigación:** el conteo continuo de animales en
  movimiento puede requerir esfuerzo manual y reconciliación. HogFlow no afirma
  que una empresa concreta tenga errores, pérdidas o necesidad de compra.
- **Hipótesis central:** una combinación de detección de cerdos, seguimiento
  multiobjeto y cruce direccional de una línea virtual podría estimar con error
  suficientemente bajo el número de cerdos que se desplazan por un callejón
  restringido hacia un área de pesaje.

La hipótesis exige datos representativos, autorización, anotaciones y ground
truth verificado por humanos. Implementar infraestructura no la valida.

### 1.2 Visión y resultado final esperado

**DECISIÓN HISTÓRICA.** La visión es un sistema local, semi-automático y
auditable que reciba una cámara en vivo, detecte y siga cerdos, evalúe cruces
direccionales, mantenga conteos por sesión, preserve eventos y permita revisión
operativa. El resultado final previsto incluye continuidad del proceso manual,
evidencia de error de conteo y gates explícitos antes de cualquier piloto.

El resultado final no existe todavía. En el estado actual hay adquisición en
vivo, integración de detector, tracking temporal y eventos geométricos live de
cruce. Faltan el detector de cerdos validado, conteo acumulado/deduplicado,
sesiones, almacenamiento, interfaz y evaluación contra ground truth.

### 1.3 Usuarios previstos

- propietario del producto e investigador del proyecto;
- desarrolladores y auditores técnicos;
- futuros anotadores y revisores de datos autorizados;
- futuros operadores de un MVP semi-automático;
- responsables de un posible piloto autorizado, solo después de superar gates.

No hay actualmente un usuario operativo en producción.

### 1.4 Prioridades

La prioridad oficial de diseño es:

```text
CALIDAD > ARQUITECTURA > MANTENIBILIDAD > ESCALABILIDAD > VELOCIDAD
```

Esto implica preferir comportamiento medible, contratos pequeños, evidencia
honesta y cambios auditables frente a entrega rápida, optimización prematura o
infraestructura especulativa.

### 1.5 Estado de la investigación de mercado

`MARKET_RESEARCH.md` conserva un screen preliminar de instalaciones de grandes
procesadores estadounidenses:

| Grupo investigado | Rango candidato de trabajo |
| --- | ---: |
| JBS USA Pork | 5 |
| Smithfield Foods | 4–8 |
| Tyson Foods | 3–6 |
| Seaboard / STF | 2 |
| Triumph Foods | 1 |
| Clemens Food Group | 2 |
| Indiana Packers | 1 |
| Hormel-related | 0–2 |
| **Total** | **18–27** |

**HECHO DOCUMENTAL, no validación comercial.** El rango no es un TAM o SAM
validado. TAM no está calculado; SAM exige verificación por instalación; SOM es
solo un escenario hipotético. Los revenue scenarios son modelos de hipótesis,
no forecasts, contratos ni valoración.

### 1.6 Integridad histórica e invención

`INVENTION_LOG.md` contiene una entrada fechada el 12 de julio de 2026. La
entrada está marcada explícitamente como reconstrucción de conceptos soportados
por material fuente preservado y **no** como transcripción verbatim. Conserva la
fecha histórica y el estado de concepto/hipótesis. No afirma patente,
patent-pending, ownership, inventorship, patentabilidad ni freedom to operate.

---

## 2. Reglas de trabajo

### 2.1 Modelo operativo

**DECISIÓN HISTÓRICA.** El proyecto ha trabajado con cuatro roles conceptuales:

| Rol | Responsabilidad |
| --- | --- |
| Usuario / product owner | Define el problema, autoriza alcance, acepta o rechaza decisiones, controla datos privados y aprueba el siguiente paso. |
| ChatGPT arquitecto | Convierte objetivos en especificaciones por fase, explicita límites y criterios de aceptación. |
| Codex implementador | Inspecciona el repositorio, implementa solo el alcance autorizado, prueba, documenta, audita artefactos y sincroniza Git cuando se solicita. |
| Auditor independiente | Revisa commit, CI, límites, evidencia y discrepancias sin asumir que la implementación es correcta. |

El “auditor independiente” es un rol de revisión; el repositorio no demuestra
que cada auditoría haya sido realizada por una persona distinta.

### 2.2 Ciclo de una fase

1. El product owner aprueba una fase o subfase concreta.
2. Se inspeccionan `AGENTS.md`, esta memoria, contexto, documentos, código,
   pruebas, branch, `HEAD`, remotos y estado de Git.
3. Se declara el cambio previsto antes de editar.
4. Se implementa únicamente el alcance aprobado.
5. Se agregan pruebas sintéticas o autorizadas; CI nunca depende de datos
   privados, webcam, GPU, internet o pesos.
6. Se ejecutan las quality gates configuradas.
7. Se revisan diff, privacidad, artefactos, límites de fase y documentación.
8. Se crea un commit pequeño y descriptivo; se hace push solo cuando fue
   solicitado y las validaciones pasan.
9. Se audita el commit y el resultado de CI.
10. Si cambió el conocimiento del proyecto, se actualiza esta memoria en el
    mismo commit.

### 2.3 Definición de fase completada

Una fase se considera completada solo cuando:

- su alcance implementable está entregado;
- las exclusiones siguen ausentes;
- los contratos y límites arquitectónicos se preservan;
- las pruebas anteriores y nuevas pasan;
- lint, formato, compilación, dependencias y diff pasan cuando están
  configurados;
- documentación y estado reflejan lo implementado, no lo deseado;
- la auditoría de privacidad y artefactos pasa;
- el commit está creado y, si era requisito, sincronizado y con CI exitoso;
- las limitaciones empíricas permanecen explícitas.

Una subfase de infraestructura puede estar **implementada** aunque la evidencia
real siga pendiente. Eso no autoriza a decir que el detector, tracker, conteo o
mercado están validados.

### 2.4 Cambios prohibidos sin aprobación

- implementar una fase futura o mezclar fases;
- renumerar o redefinir el roadmap;
- cambiar contratos públicos o arquitectura estable;
- modificar reglas de conteo para hacer pasar una integración;
- introducir sesiones, base de datos, UI o analytics antes de su fase;
- descargar modelos o medios silenciosamente;
- usar datos de empleadores o datos confidenciales;
- comprometer videos, frames, sidecars, anotaciones reales, pesos, ejecuciones,
  credenciales, URLs privadas o reportes locales;
- presentar dobles sintéticos como evidencia real;
- ocultar fallos, omitir warnings o debilitar pruebas;
- reescribir entradas históricas del `INVENTION_LOG.md`;
- convertir hipótesis de `MARKET_RESEARCH.md` en resultados técnicos;
- hacer conclusiones jurídicas de patentabilidad, inventorship, ownership o
  freedom to operate.

### 2.5 Política de mantenimiento de esta memoria

`HOGFLOW_PROJECT_MEMORY.md` es un documento vivo. No se debe regenerar completo
en cada fase. Después de esta reconstrucción inicial se actualizan solo los
deltas relevantes:

- estado y commit de la fase;
- contratos o pipeline nuevos o eliminados;
- ADRs y decisiones nuevas;
- defectos, riesgos y deuda técnica;
- pruebas, CI y evidencia empírica;
- roadmap y siguiente paso.

Antes de cada commit se debe preguntar: “¿Este cambio modifica el conocimiento
del proyecto?”. Si la respuesta es sí, esta memoria se actualiza en el mismo
commit. Ningún commit arquitectónicamente relevante se considera completo si
esta memoria no refleja el cambio.

---

## 3. Arquitectura oficial

### 3.1 Pipeline conceptual completo

```text
Camera
→ Frame Capture
→ Detector
→ Tracker
→ Virtual Line
→ Crossing Event
→ Counter
→ Session
→ Storage
→ Dashboard
```

| Etapa | Responsabilidad | Estado actual |
| --- | --- | --- |
| Camera | Fuente USB/RTSP; archivo solo para desarrollo. | **IMPLEMENTADO** como foundation; USB validada en un portátil, RTSP no certificado. |
| Frame Capture | Adquirir, ordenar, timestamp, convertir a RGB bytes, buffer limitado. | **IMPLEMENTADO** en Phase 5.1. |
| Detector | Producir cajas y clases sin tracking ni conteo. | Contratos, adapters y pipeline **IMPLEMENTADOS**; detector real de cerdos no disponible/validado. |
| Tracker | Asociar detecciones con IDs temporales. | Tracking finito y `LiveTracker` **IMPLEMENTADOS**; tracking real de cerdos no validado. |
| Virtual Line | Definir segmento finito y lado/dirección. | **IMPLEMENTADO** en Phase 1/2 finita y Phase 5.4 live normalizada; no calibrada con cerdos. |
| Crossing Event | Emitir transiciones geométricas direccionales. | **IMPLEMENTADO** en Phase 1/2 y como evento live sin conteo en Phase 5.4. |
| Counter | Incrementar una vez por identidad temporal elegible. | **IMPLEMENTADO** en Phase 1 finita y Phase 7 live por lifecycle; no es identidad biológica ni total de sesión. |
| Session | Limitar IDs contados a una sección/sesión. | **PLANNED**, Phase 8. |
| Storage | Persistir sesiones y eventos. | **PLANNED**, Phase 10; paquete placeholder solamente. |
| Dashboard | Interfaz del operador y revisión. | **PLANNED**, Phase 9; no existe UI operativa. |

### 3.2 Responsabilidades y dependencias

Dirección general:

```text
infraestructura/adapters
        ↓
pipeline/orquestación
        ↓
contratos + modelos inmutables
        ↓
core/config
```

Reglas:

- `counting` no importa OpenCV, NumPy, Ultralytics ni Supervision.
- `streaming`, `detection` y `tracking` de dominio no importan adapters.
- frameworks se cargan de forma perezosa dentro de `hogflow.adapters`.
- detección no cuenta; tracking no detecta ni cuenta; preview no decide negocio.
- el pipeline compone, pero no duplica geometría ni incrementa conteos por su
  cuenta.
- `sessions` y `storage` son fronteras futuras y no deben contaminar visión.
- modelos públicos son inmutables cuando es práctico: dataclasses `frozen` y
  `slots`, tuples y bytes empaquetados.
- imports no deben abrir cámara, descargar modelos, crear bases de datos,
  configurar root logging ni iniciar loops.

### 3.3 Contratos públicos principales

| Contrato/modelo | Ruta | Semántica |
| --- | --- | --- |
| `Frame`, `BoundingBox`, `Detection`, `Track` | `src/hogflow/models.py` | Lenguaje canónico finito, framework-neutral. `Frame` contiene RGB bytes. |
| `VideoSource` | `src/hogflow/video/contracts.py` | Fuente finita: `read() -> Frame | None`, `close()`. |
| `Detector` | `src/hogflow/detection/contracts.py` | Detección finita: `predict(Frame) -> Sequence[Detection]`. |
| `Tracker` | `src/hogflow/tracking/contracts.py` | Tracking finito: `update(Frame, detections) -> Sequence[Track]`. |
| `CameraSource` | `src/hogflow/streaming/contracts.py` | Fuente viva con lifecycle, resultados explícitos, health y statistics. |
| `FramePacket` | `src/hogflow/streaming/models.py` | Payload RGB inmutable, identidad de stream, secuencia y tiempos. |
| `LiveDetector` | `src/hogflow/detection/ports.py` | `load`, `infer`, metadata, `close`; lifecycle explícito. |
| `FrameDetections` | `src/hogflow/detection/inference.py` | Resultado ligado exactamente a stream y frame. |
| `LiveTracker` | `src/hogflow/tracking/ports.py` | `start(stream_id)`, `update`, `reset`, `close`; una instancia por lifecycle. |
| `TrackingRequest`, `TrackingResult` | `src/hogflow/tracking/models.py` | Entrada/salida inmutable con IDs temporales y provenance. |
| `DirectionalLineCounter` | `src/hogflow/counting/line_crossing.py` | Única fuente de verdad para geometría finita, dirección y deduplicación positiva. |
| `LiveCrossingDetector` | `src/hogflow/counting/live_ports.py` | `start`, `update(TrackingResult)`, `reset`, `close`; eventos sin conteo. |
| `NormalizedLine`, `LiveCrossingEvent` | `src/hogflow/counting/live_models.py` | Geometría normalizada finita y evento ligado a frame/lifecycle. |

### 3.4 Pipeline finito frente a pipeline en vivo

**Pipeline finito pregrabado:**

```text
VideoSource → Frame → Detector → Detection → Tracker → Track
→ bottom-center Point → DirectionalLineCounter → JSONL/video anotado
```

`GenericCountingPipeline` es síncrono, procesa cada frame seleccionado y termina
por EOF o límite. El CLI compatible está en
`src/hogflow/video/generic_counter.py`.

**Pipeline en vivo:**

```text
CameraSource → LiveStreamRunner → BoundedFrameBuffer → FramePacket
→ LiveDetectionPipeline → FrameDetections
→ LiveTrackingPipeline → TrackingResult
→ LiveCrossingPipeline → LiveCrossingEvent → preview opcional
```

Es stream-first, usa secuencias monotónicas por lifecycle, buffer fijo y
prioriza el frame útil más reciente. Crossing es opcional y desactivado por
default; incluye eventos geométricos pero no conteo acumulado.

### 3.5 `Tracker` finito frente a `LiveTracker`

- `Tracker` no prescribe `start/reset/close`; sirve al video genérico finito.
- `LiveTracker` posee recursos y estado, se liga a un `stream_id`, exige frames
  crecientes, se resetea tras reconexión y se cierra explícitamente.
- ambos usan modelos HogFlow, no objetos Supervision.
- los IDs duran solamente el lifecycle del tracker. Pueden reutilizarse tras
  reset y nunca son identidad biológica ni conteo.

### 3.6 Buffer, scheduling y lifecycle

- buffer con capacidad fija y políticas `drop_oldest`/`drop_newest`;
  `drop_oldest` es el default de tiempo real;
- adquisición independiente del consumidor mediante un único producer thread
  opcional;
- detección drena frames disponibles y retiene el más reciente útil;
- every-N, target FPS y máximo frame age pueden omitir inferencias;
- tracking se ejecuta serialmente después de una detección exitosa y no agrega
  otra cola;
- source drops, inference skips y tracking failures se contabilizan por etapas;
- reconexión live usa backoff determinista; EOF de archivo no reconecta;
- cierre cooperativo libera cámara, detector, tracker y preview.

---

## 4. Estructura del repositorio

| Ruta | Responsabilidad actual |
| --- | --- |
| `AGENTS.md` | Reglas normativas de agentes, roadmap y límites. |
| `HOGFLOW_PROJECT_CONTEXT.md` | Contexto técnico y roadmap resumido. |
| `HOGFLOW_PROJECT_MEMORY.md` | Memoria operativa viva y razonamiento histórico. |
| `INVENTION_LOG.md` | Registro cronológico de conceptos; entrada 2026-07-12 reconstruida y no verbatim. |
| `MARKET_RESEARCH.md` | Investigación comercial separada de validación técnica. |
| `README.md` | Entrada de proyecto, estado y enlaces. |
| `.github/workflows/ci.yml` | CI source-only/synthetic en Ubuntu/Python 3.12. |
| `docs/phase_0/` | Problema, proceso, solución conceptual, supuestos y resumen. |
| `docs/phase_1/` | Diseño, uso y evidencia del contador genérico. |
| `docs/phase_2/` | Foundation, contratos, integración, reglas y ADR-001–048. |
| `docs/phase_3/` | Adquisición autorizada, inventario y uso local. |
| `docs/phase_4/` | Evaluación, anotación, splitting, extracción y training baseline. |
| `docs/phase_5/` | Streaming, hardware, detección live y tracking live. |
| `docs/phase_6/` | Evaluación offline de posiciones de línea. |
| `docs/phase_7/` | Política lifecycle de positivos, duplicates y reversos. |
| `src/hogflow/core/` | Excepciones, logging e identificadores comunes. |
| `src/hogflow/config/` | Configuración mínima inmutable. |
| `src/hogflow/models.py` | Modelos canónicos de frame/detección/track finitos. |
| `src/hogflow/adapters/` | OpenCV, Ultralytics, YOLO training y Supervision ByteTrack. |
| `src/hogflow/annotation/` | Política, YOLO serialization, manifest y validación. |
| `src/hogflow/data/` | Inventario, splits, selección y extracción local. |
| `src/hogflow/evaluation/` | Métricas de detección y evaluación offline Phase 6. |
| `src/hogflow/training/` | Contrato, configuración, dataset gates, resultados y reportes de training. |
| `src/hogflow/video/` | Contrato finito, CLI genérico/live, metadata y output OpenCV. |
| `src/hogflow/streaming/` | Fuente viva, packet, buffer, lifecycle, health y sintéticos. |
| `src/hogflow/detection/` | Contratos finito/live, resultados, errores, telemetry y fakes. |
| `src/hogflow/tracking/` | Contratos finito/live, modelos, config, telemetry y fakes. |
| `src/hogflow/counting/` | Geometría/eventos Phase 5.4 y política lifecycle Phase 7, además del contador genérico. |
| `src/hogflow/pipeline/` | Orquestación genérica y composición serial live detection/tracking/crossing/counting. |
| `src/hogflow/domain/` | Placeholder de dominio operativo; sin entidades. |
| `src/hogflow/sessions/` | Placeholder; Phase 8 no implementada. |
| `src/hogflow/storage/` | Placeholder; Phase 10 no implementada. |
| `tests/` | Suite sintética/unitaria/arquitectónica; ningún medio real. |
| `data/` | Workspace local protegido; Git conserva README, ejemplos seguros y `.gitkeep` aprobados. |

CLIs relevantes:

- `python -m hogflow.video.generic_counter`: video finito genérico con conteo;
- `python -m hogflow.data.inventory`: inventario local Phase 3;
- `python -m hogflow.evaluation.dataset_selection`: selección local Phase 4.1;
- módulos de splitting, selección de frames, extracción y validación de
  anotaciones en `hogflow.data`/`hogflow.annotation`;
- `python -m hogflow.adapters.camera_stream_cli`: diagnóstico de stream;
- `python -m hogflow.video.live_detection_cli`: detección, tracking, crossing y
  counting lifecycle opcionales; sin sesión ni persistencia.

No hay aplicación de operador, dashboard, implementación de sesiones ni base de
datos. Los nombres de esas fronteras no implican funcionalidad.

---

## 5. Historial por fases

Resumen de madurez:

| Bloque | Implementación | Evidencia empírica | Clasificación actual |
| --- | --- | --- | --- |
| Phase 0 | Documentación completada. | No aplica como prueba técnica. | Aprobada como problem framing. |
| Phase 1 | Contador genérico finito completado. | Sin evidencia pig-specific. | Aprobada con limitaciones explícitas. |
| Phase 2 | 2.1–2.3 completadas. | Smoke sintético de integración. | Arquitectura aprobada. |
| Phase 3 | Infraestructura de inventario completada. | Clips autorizados históricos, no publicados. | Infraestructura completa; colección/revisión abierta. |
| Phase 4 | 4.1–4.3 tooling completado. | Sin training ni checkpoint real de cerdo. | Infraestructura completa; validación empírica pendiente. |
| Phase 5.1 | Adquisición live completada. | Webcam USB real en un equipo. | Completa con observaciones; no RTSP production proof. |
| Phase 5.2 | Live detector integration completada. | Detector vacío en webcam; no pesos de cerdo. | Completa como integración; evidencia pig-specific bloqueada. |
| Phase 5.3 | Live tracking integration completada y observaciones técnicas cerradas. | ByteTrack real con boxes sintéticos en webcam. | Cerrada técnicamente; accuracy real no validada. |
| Phase 5.4 | Eventos live de cruce implementados. | Tracks sintéticos solamente. | Implementación completa; eventos reales no validados. |
| Phase 6 | Evaluador offline de líneas implementado. | Replays/ground truth sintéticos. | Infraestructura completa; calibración representativa pendiente. |
| Phase 7 | Política lifecycle de reversos y duplicates implementada. | Fixtures sintéticos solamente. | Infraestructura completa; deduplicación real no validada. |

### 5.1 Phase 0 — Define problem and map process

- **Objetivo:** delimitar problema, proceso conceptual, observación, riesgos,
  tres secciones y validación necesaria.
- **Entregado:** seis documentos en `docs/phase_0/`.
- **Fuera de alcance:** código de visión, exactitud, ground truth, piloto y
  validación comercial.
- **Decisión clave:** formular una hipótesis estrecha y no construir antes de
  documentar supuestos.
- **Commit:** `7ca6aa21ab4d5de83b8d533ddb27381a8458d412`.
- **Estado:** documentación completada; sus hipótesis no están validadas.

### 5.2 Phase 1 — Generic line-crossing counter

- **Objetivo:** probar con clases genéricas el flujo detección–tracking–línea sin
  afirmar capacidad con cerdos.
- **Entregado:** `DirectionalLineCounter`, CLI de video, JSONL, anotación,
  tracking genérico y pruebas sintéticas.
- **Corrección crítica:** la implementación inicial evaluaba la línea matemática
  infinita mientras el video mostraba un segmento. Se añadió intersección real
  entre el movimiento y el segmento finito, incluidos diagonales y endpoints.
- **Reglas preservadas:** epsilon/near-line, dirección configurable, reversos,
  un incremento positivo por tracker y TTL sin borrar el guard de IDs contados.
- **Commits:** implementación inicial dentro de `7ca6aa2…`; corrección geométrica
  `46574512cd0a55bb19711f87e458afcf5dea93c8`.
- **Evidencia:** lógica determinista sin modelo; integración genérica creada.
- **Limitación:** no validó video real en la tarea original ni cerdos.
- **Estado:** implementación genérica completada y luego preservada por Phase 2.

### 5.3 Phase 2.1 — Architecture foundation

- **Objetivo:** paquetes, errores, logging, settings, dependencias y tests de
  arquitectura sin cambiar Phase 1.
- **Entregado:** `core`, `config`, placeholders y ADR-001–007.
- **Decisiones:** logging stdlib, settings frozen/slotted, imports sin efectos,
  dominio operativo separado y no crear abstracciones especulativas.
- **Commit:** `db46ecb85947bc51c0c491c90677a81eadff5247`.
- **Estado:** completada.

### 5.4 Phase 2.2 — Interfaces & Contracts

- **Objetivo:** lenguaje canónico y contratos reemplazables, sin adapters.
- **Entregado:** `Frame`, `BoundingBox`, `Detection`, `Track`, más un Protocol
  `Detector`, `Tracker` y `VideoSource`.
- **Pruebas:** inmutabilidad, exports, type hints, docstrings, imports y ausencia
  de frameworks/side effects. La conversación registra 87 pruebas al cierre.
- **Fuera de alcance:** implementación, pipeline, sesiones, storage y UI.
- **Commit:** `0b9d5d3f8aec78698ce3a1bb1c85f3e9bd65b639`.
- **Estado:** completada.

### 5.5 Phase 2.3 — Generic pipeline integration

- **Objetivo:** adaptar el contador genérico a contratos sin doble inferencia.
- **Entregado:** adapters OpenCV/Ultralytics, `GenericCountingPipeline`, modelos
  de resultado, callbacks de video/JSONL y CLI compatible.
- **Decisiones:** `Frame` RGB bytes pese al coste, CLI como composition root,
  pipeline síncrono y counting como única fuente de verdad geométrica.
- **Evidencia:** smoke sintético de infraestructura y 130 pruebas.
- **Limitación:** no real-model smoke autorizado en esa tarea.
- **Commit:** `711282bf011e7944437922858daa1812308db1c9`.
- **Estado:** Phase 2 completada.

### 5.6 Phase 3 — Pig video data acquisition and inventory

- **Objetivo:** inventariar videos autorizados/locales sin entrenar ni contar.
- **Entregado:** discovery determinista, metadata OpenCV acotada, estimación
  conservadora de estabilidad, sidecars manuales, suitability, manifests y
  reportes JSON/CSV/Markdown.
- **Política:** originales en `data/raw/`; videos, sidecars e inventarios jamás
  entran a Git.
- **Evidencia:** 165 pruebas registradas al cierre; pruebas sintéticas no prueban
  calidad de videos de cerdos.
- **Commit:** `8cbbcf9ed1fbbdcd1b5b5398f29555b85133360a`.
- **Estado:** infraestructura implementada; adquisición/revisión real puede
  continuar localmente.

### 5.7 Phase 4.1 — CI and detection evaluation foundation

- **Objetivo:** CI source-only, evaluación de detección y selección metadata-only.
- **Entregado:** modelos de ground truth/predicción, IoU, matching uno-a-uno,
  TP/FP/FN, precision/recall/F1, selección por autorización y workspaces
  protegidos.
- **Decisión:** no implementar mAP incompleto; matching confidence-first
  determinista.
- **Evidencia:** 208 pruebas al cierre según la auditoría conversacional; CI no
  usa media ni pesos.
- **Commit:** `c84d72023621207936bea77eb2f22cdf57c6d740`.
- **Estado:** tooling completado; no detector entrenado/validado.

### 5.8 Phase 4.2 — Local annotation dataset preparation

- **Objetivo:** preparar dataset local reproducible sin entrenar.
- **Entregado:** política `0 = pig`, estados de frame, YOLO text, split por video
  fuente, planning temporal, extracción opcional, source map privado, manifest
  sanitizado y validación JSON/CSV/Markdown.
- **Decisiones:** nunca dividir frames del mismo source entre splits; con pocos
  sources usar plan `preparation` y warnings; un label vacío exige
  `verified_empty`.
- **Evidencia:** flujo sintético end-to-end; no extracción piloto real.
- **Commit:** `db46f397fbe335e771ac70980dd6257ebfc5d72a`.
- **Estado:** tooling completado; anotación real puede estar incompleta.

### 5.9 Phase 4.3 — Baseline detector training

- **Objetivo:** un trainer reemplazable, no máxima accuracy.
- **Entregado:** `DetectorTrainer`, configuración reproducible, dataset gates,
  `YOLOBaselineTrainer`, fingerprints, resume, métricas separadas y failure
  report local.
- **Decisión:** Ultralytics solo en adapter; métricas framework no se mezclan
  con métricas HogFlow.
- **Evidencia:** 300 pruebas en la línea base posterior; smoke sintético de
  orquestación, no optimización real.
- **Commit:** `6cb2638f4e1173b3bca148fd7d2582c303311680`.
- **Estado:** pipeline de training operacional; no checkpoint real de cerdo.

### 5.10 Phase 5.1 — Live camera stream foundation

- **Objetivo:** arquitectura stream-first de adquisición viva sin inferencia.
- **Entregado:** `CameraSource`, `FramePacket`, source identity segura, adapters
  USB/RTSP/file, fuente sintética, buffer acotado, runner, reconnect, health,
  statistics y CLI headless.
- **Decisión:** `drop_oldest` por defecto para latencia acotada; locator de
  cámara runtime-only; archivo es fuente de desarrollo, no producción.
- **Evidencia sintética:** 50 frames en capacidad 4, 46 drops, secuencias 46–49.
- **Evidencia hardware:** webcam de portátil 640×480 ~30 FPS; cinco ciclos de
  30 s, ejecución corregida de 10 min y 30 min; 53,997 frames en la de 30 min,
  sin read failures ni secuencias duplicadas y con liberación de cámara.
- **Commits:** `506ef8a6b02dcdaac9bf8c1e819a61ad295ed7fe` y validación
  `6a71a42848d900b1fe4f02a4dda0fbc9f0dd5e46`.
- **Estado:** foundation completada y validada en un solo backend/hardware;
  RTSP y producción no validados.

### 5.11 Phase 5.2 — Live pig detection integration

- **Objetivo:** conectar `FramePacket` a inferencia live sin tracking/conteo.
- **Entregado:** `LiveDetector`, `FrameDetections`, scheduling every-N/target
  FPS/max-age, telemetry, fakes, adapter Ultralytics con path local explícito,
  fingerprint/provenance, preview y CLI JSON.
- **Decisión:** ningún auto-download y el buffer de source es el único backlog.
- **Evidencia:** 401 pruebas; webcam con `EmptyDetector`: 1,381 frames en 60 s,
  1,353 inferidos, 27 skipped, sin drops/failures; reopen de 15 s exitoso.
- **Limitación:** el detector vacío solo valida lifecycle. No había pesos de
  cerdo válidos ni se ejecutó inferencia real de cerdo.
- **Commit:** `09cbb776fe44649d07b90fab7e09be4a711ef8f3`.
- **Estado:** implementación y CI completados; evidencia de cerdo bloqueada.

### 5.12 Phase 5.3 — Live multi-object tracking integration

- **Objetivo:** convertir resultados live en IDs temporales sin contar.
- **Entregado:** `LiveTracker`, modelos, ByteTrack config, adapter Supervision,
  fakes, pipeline, telemetry, preview y CLI con tracking desactivado por defecto.
- **Decisiones:** una instancia por stream lifecycle, reset tras reconnect,
  tracking serial sin segunda cola, API 0.29.1 aislada y `frame_rate` definido
  como frecuencia esperada de updates efectivos del tracker.
- **Evidencia sintética:** trayectorias uno/dos objetos, misses, expiración,
  gaps, resets, stream isolation y fallos.
- **Evidencia hardware:** webcam + detecciones sintéticas + ByteTrack real. Run
  largo: 2,636 frames a 30.00 FPS, 2,632 updates, 2,501 tracks emitidos, cero
  drops/failures, 2.89 ms promedio. Reopen: 1,146 frames a 30.02 FPS, 1,145
  updates, 1,088 tracks, cero drops/failures, 2.91 ms promedio. CPU promedio
  26.3%, peak 73.9%; RSS aproximada 52–180 MB. Preview no probado.
- **Cierre técnico:** IDs únicos por resultado, mapping `class_id → class_name`
  uno-a-uno, recuperación temporal con reset seguro del backend y política
  explícita para FPS, gaps y `lost_track_buffer`.
- **Pruebas/CI:** implementación original con 453 passed y GitHub Actions run
  `29681085740` exitoso; cierre local con 465 passed y un `FutureWarning` de
  deprecación ByteTrack. El CI remoto del cierre no se afirma antes de push.
- **Commit:** `f5cc77336423d5ed6c885d0504628e72232c2bd8`.
- **Commit de cierre:** `Close Phase 5.3 tracking observations`.
- **Estado:** cerrada técnicamente; no tracking real de cerdos ni accuracy.

### 5.13 Phase 5.4 — Live virtual-line crossing event integration

- **Objetivo:** consumir `TrackingResult` y emitir eventos direccionales
  geométricos sin conteo acumulado.
- **Entregado:** `LiveCrossingDetector`, puntos/línea normalizados, lados
  explícitos, anchors bottom-center/center, `VirtualLineCrossingDetector`,
  eventos ligados a frame y lifecycle, limpieza por ausencia, telemetry,
  pipeline serial opcional, preview OpenCV y CLI.
- **Decisiones:** segmento finito para evitar extensiones invisibles; epsilon
  como distancia perpendicular normalizada; ninguna interpolación de frames o
  tiempo; crossing desactivado por default; reset alineado con reconnect del
  tracker; errores de contrato/lifecycle fatales y preview aislada.
- **Evidencia:** pruebas sintéticas de geometría horizontal/vertical/diagonal,
  ambos sentidos, `ON_LINE`, gaps, múltiples tracks, expiración, reset,
  stream isolation, pipeline, preview, CLI y boundaries.
- **Commit:** `Implement Phase 5.4 live line crossing events` (consultar SHA
  final en Git por la autorreferencia del documento).
- **Estado:** implementación event-only completada; sin validación con cerdos,
  line calibration, event accuracy ni count accuracy.

### 5.14 Phase 6 — Virtual-line position evaluation

- **Objetivo:** comparar posiciones/configuraciones de línea sobre exactamente
  el mismo replay de tracking, sin convertir eventos en conteo operacional.
- **Entregado:** `LineCandidate`, `LineEvaluationPlan`, `TrackingReplay`,
  ground truth de eventos independiente de tracker IDs, matching greedy
  uno-a-uno, métricas descriptivas y con ground truth, ranking explícito,
  `VirtualLinePositionEvaluator`, JSON estricto path-free y CLI offline.
- **Decisiones:** replay serial; un lifecycle de Phase 5.4 por candidato;
  geometría reutilizada, no duplicada; gaps preservados sin interpolación;
  proximidad a extremos solo diagnóstica; sin ground truth, default
  `NO_AUTOMATIC_RECOMMENDATION`.
- **Evidencia:** fixtures sintéticos de paso limpio, extensión fuera del
  segmento y jitter/gaps, más pruebas de modelos, matching, ranking,
  serialización, privacidad, CLI, determinismo, lifecycle y boundaries.
- **Commit:** `Implement Phase 6 line position evaluation` (consultar SHA final
  en Git por la autorreferencia del documento).
- **Estado:** infraestructura de evaluación implementada; evaluación
  representativa con cerdos, ground truth humano y línea calibrada pendientes.

### 5.15 Phase 7 — Reverse movement and duplicate counting

- **Objetivo:** convertir eventos geométricos live en decisiones direccionales
  auditables y un total limitado al lifecycle actual.
- **Entregado:** `LiveCountingConfiguration`, `TemporaryTrackIdentity`,
  `LiveCountingDecision`, `LiveCountingResult`, snapshots/summaries,
  `LiveDirectionalCounter`, `LifecycleDirectionalCounter`, telemetry,
  `LiveCountingPipeline`, preview OpenCV opcional y CLI.
- **Decisiones:** dirección positiva geométrica explícita; identidad mínima
  `(source_id, crossing_lifecycle_id, tracker_id)`; primer positivo incrementa;
  positivos repetidos y reversos producen decisiones con incremento cero;
  ningún decremento; aplicación atómica por frame; counted IDs no expiran
  durante el lifecycle; capacidad excedida falla sin eviction; reconnect crea
  lifecycle y total nuevos.
- **Compatibilidad:** el campo histórico Phase 5.4
  `tracker_lifecycle_id` se preserva, con alias claro
  `crossing_lifecycle_id`; Phase 6 continúa evaluando eventos geométricos sin
  deduplicación.
- **Evidencia:** fixtures sintéticos de positivos, reversos, duplicados, dos
  tracks, gaps, stale, atomicidad, capacidad, reconnect, preview, CLI,
  boundaries y regresión.
- **Commit:** `Implement Phase 7 reverse and duplicate counting` (consultar SHA
  final en Git por la autorreferencia del documento).
- **Estado:** infraestructura lifecycle-aware implementada; validación
  representativa de cerdos, reversos, duplicates, ID switches y accuracy
  pendiente.

### 5.16 Estado de las fases 8–16

No iniciadas. Sus nombres normativos son:

| Fase | Alcance normativo | Estado |
| --- | --- | --- |
| 8 | Session manager de tres secciones. | NOT STARTED |
| 9 | Operator MVP UI. | NOT STARTED |
| 10 | SQLite para sesiones/eventos. | NOT STARTED |
| 11 | Evaluación contra ground truth humano. | NOT STARTED |
| 12 | Error analysis y analytics dashboard. | NOT STARTED |
| 13 | Failure review y review clips. | NOT STARTED |
| 14 | Consistencia de peso opcional. | NOT STARTED |
| 15 | Portfolio case study. | NOT STARTED |
| 16 | Pilot-readiness plan y validation gates. | NOT STARTED |

---

## 6. Registro de decisiones

Los detalles normativos están en `docs/phase_2/architecture_decisions.md`. Esta
tabla preserva su razonamiento operativo.

### 6.1 Foundation, contratos e integración genérica

| ADR | Fase | Contexto/alternativas | Decisión y motivo | Consecuencia / estado |
| --- | --- | --- | --- | --- |
| 001 | 2.1 | Mover Phase 1 o preservarla. | Preservar rutas, CLI y tests para evitar riesgo sin beneficio. | Adaptación diferida a 2.3. Aceptada. |
| 002 | 2.1 | Contador acoplado a CV o dominio puro. | Counting sin frameworks para pruebas deterministas. | Adapters convierten observaciones. Aceptada. |
| 003 | 2.1 | Logging externo/estructurado o stdlib. | `logging` stdlib, config solo en entrypoints. | Sin dependencia ni side effect. Aceptada. |
| 004 | 2.1 | Pydantic/loaders o dataclasses mínimas. | Settings frozen/slotted validados. | Config loaders pospuestos. Aceptada. |
| 005 | 2.1 | Crear contratos anticipados o esperar 2.2. | Esperar requisitos de 2.2. | Menos especulación. Aceptada. |
| 006 | 2.1 | Mezclar operación con CV o reservar dominio. | Dominio operativo separado, sin entidades todavía. | Evita contaminar counting. Aceptada. |
| 007 | 2.1 | Managers/factories/DI/event bus o mínima arquitectura. | Solo abstracciones con necesidad presente. | Código pequeño/auditable. Aceptada. |
| 008 | 2.2 | Modelos por componente o lenguaje canónico. | `hogflow.models` con RGB bytes inmutables. | Conversiones explícitas. Aceptada. |
| 009 | 2.2 | Protocols pequeños o framework/pipeline total. | Un Protocol por detector/tracker/source, sin ejecución. | Adapters/orquestación posteriores. Aceptada. |
| 010 | 2.3 | Frameworks en dominio o adapters. | OpenCV/Ultralytics/Supervision aislados; una inferencia. | Reemplazo localizado. Aceptada. |
| 011 | 2.3 | DI container o CLI composition root. | CLI construye collaborators. | Mantiene compatibilidad. Aceptada. |
| 012 | 2.3 | NumPy en `Frame` o RGB bytes. | Preservar bytes pese a copy/conversión. | Pureza a coste de rendimiento. Aceptada. |
| 013 | 2.3 | Async/queues o flujo síncrono. | `GenericCountingPipeline` síncrono. | Determinista, sin infraestructura prematura. Aceptada. |

### 6.2 Datos, evaluación y training

| ADR | Fase | Contexto/alternativas | Decisión y motivo | Consecuencia / estado |
| --- | --- | --- | --- | --- |
| 014 | 4.1 | CI con datos reales o source-only. | Ubuntu/Python 3.12, sintético, permisos read-only. | No valida media/modelos reales. Aceptada. |
| 015 | 4.1 | Duplicar bbox o reutilizarla. | Wrapper de evaluación con coordinate space explícito. | Evita dos geometrías canónicas. Aceptada. |
| 016 | 4.1 | Matching ambiguo o determinista. | Confidence-first, IoU y tie-break por IDs. | TP/FP/FN reproducibles; no mAP. Aceptada. |
| 017 | 4.1 | Selección decodificando media o metadata-only. | Autorización/readability/suitability, IDs opacos. | Paths/notas no salen. Aceptada. |
| 018 | 4.2 | Formato propietario o YOLO text neutral. | `0 = pig`, normalizado y validado; YOLO es serialization. | No acopla dominio a Ultralytics. Aceptada. |
| 019 | 4.2 | Split por frame o source video. | Split por clip; con diversidad insuficiente, `preparation`. | Previene leakage y falsa significancia. Aceptada. |
| 020 | 4.2 | Paths dentro de manifests o source map privado. | Separar mapa local ignorado de records sanitizados. | Reproducibilidad requiere conservar mapa local. Aceptada. |
| 021 | 4.2 | Extraer primero o planificar timestamps. | Plan metadata-only antes de extracción explícita. | Menos frames redundantes, rerun idempotente. Aceptada. |
| 022 | 4.3 | Trainer YOLO global o contrato reemplazable. | `DetectorTrainer` + adapter YOLO. | Otra familia puede sustituirlo. Aceptada. |
| 023 | 4.3 | Mezclar métricas framework/HogFlow o namespacing. | Evaluador HogFlow independiente; mAP framework separado. | No falsa equivalencia. Aceptada. |
| 024 | 4.3 | Publicar artefactos o provenance sanitizada local. | Fingerprints/IDs opacos; outputs ignorados. | Auditabilidad local sin dataset/pesos en Git. Aceptada. |

### 6.3 Streaming, live detection y live tracking

| ADR | Fase | Contexto/alternativas | Decisión y motivo | Consecuencia / estado |
| --- | --- | --- | --- | --- |
| 025 | 5.1 | Extender `VideoSource` con ambigüedad o nuevo contrato live. | `CameraSource` con estados explícitos; `VideoSource` intacto. | Finito/live separados. Aceptada. |
| 026 | 5.1 | Arrays mutables/wall clock o packets inmutables/monotonic. | RGB bytes y secuencia monotónica. | Orden seguro con copy. Aceptada. |
| 027 | 5.1 | Cola ilimitada o buffer fijo. | Capacidad fija, default `drop_oldest`. | Latencia/memoria acotadas, drops observables. Aceptada. |
| 028 | 5.1 | Framework async o runner síncrono. | Runner síncrono + un producer opcional + backoff inyectable. | Shutdown/reconnect testeables. Aceptada. |
| 029 | 5.1 | Locators en reports o identidad opaca. | Credentials runtime-only, repr sanitizada. | Sin secret manager incorporado. Aceptada. |
| 030 | 5.2 | Cambiar `Detector` o añadir `LiveDetector`. | Contrato live con lifecycle; finito intacto. | Dos contratos por lifecycles genuinos. Aceptada. |
| 031 | 5.2 | Segunda cola de inferencia o source buffer único. | Draining/latest useful frame, skips explícitos. | No backlog creciente. Aceptada. |
| 032 | 5.2 | Alias que auto-descarga o artefacto local explícito. | Path local, SHA-256, class map y provenance estructural. | Sin falsa evidencia de cerdo. Aceptada. |
| 033 | 5.2 | Preview obligatoria/acoplada o local opcional. | Port + adapter OpenCV, headless default, failure isolation. | No UI/recording. Aceptada. |
| 034 | 5.3 | Cambiar `Tracker` o añadir `LiveTracker`. | Lifecycle live separado con modelos canónicos. | IDs temporales y reset explícito. Aceptada. |
| 035 | 5.3 | Backend global multi-stream o uno por stream. | Una instancia por stream lifecycle. | Sin mezcla ni registry ilimitado. Aceptada. |
| 036 | 5.3 | Cola tracking propia o tracking serial. | Tracking en callback de detección exitosa. | Asociación exacta, no segunda cola. Aceptada. |
| 037 | 5.3 | API Supervision en dominio o adapter aislado. | Lazy adapter 0.29.1 con API verificada. | Migración por deprecación queda localizada. Aceptada. |
| 038 | 5.3 | Cámara, inferencia y tracker pueden avanzar a frecuencias distintas. | `frame_rate` representa updates efectivos esperados; gaps no fabrican updates y reconnect hace reset. | Retención depende de configuración por deployment; validación empírica sigue pendiente. Aceptada. |
| 039 | 5.4 | Reusar contador Phase 1 o separar eventos live. | Detector live event-only; no `counted_tracker_ids` ni total. | Phase 1 permanece compatible y Phase 7 no se adelanta. Aceptada. |
| 040 | 5.4 | Línea por píxeles/infinita o segmento normalizado. | Segmento finito normalizado, epsilon perpendicular y bottom-center default. | Independiente de resolución; gaps no estiman tiempo/trayectoria. Aceptada. |
| 041 | 5.4 | Cola propia o crossing serial; state persistente o reset alineado. | Callback serial, sin cola, crossing off por default y reset por reconnect. | Asociación exacta y sin herencia de lados entre lifecycles. Aceptada. |
| 042 | 6 | Evaluación paralela/compartida o replay serial aislado. | Una instancia Phase 5.4 por candidato y el mismo replay inmutable, en serie. | Orden de candidatos no contamina resultados; auditoría simple. Aceptada. |
| 043 | 6 | Pickle/manifests con paths o JSON estricto sanitizado. | Esquema JSON versionado y path-free, con IO atómico. | Replays/reports son inspeccionables sin media ni rutas privadas. Aceptada. |
| 044 | 6 | Elegir más eventos o condicionar recomendación a evidencia. | Sin ground truth no hay recomendación automática; con ground truth ranking explícito. | Evita presentar señal descriptiva como accuracy. Aceptada. |
| 045 | 6 | Cambiar emisión cerca de extremos o solo diagnosticar. | Reusar intersección finita y medir proximidad sin alterar eventos. | Permite comparar segmentos cortos/largos sin nueva regla de negocio. Aceptada. |
| 046 | 7 | ID numérico global o identidad calificada por lifecycle. | `(source, crossing lifecycle, tracker ID)` más lifecycle propio de counting. | Reconnect no hereda total/IDs; no implica identidad biológica. Aceptada. |
| 047 | 7 | Reverso decrementa/corrige o solo se registra. | Primer positivo incrementa; duplicate/reverse no incrementan ni decrementan. | Política conservadora y auditable; no existe net count. Aceptada. |
| 048 | 7 | Mutación evento-a-evento/eviction o frame atómico/capacidad fatal. | Validar y calcular lote completo antes de commit; capacidad falla sin expulsar IDs. | Sin estado parcial ni duplicados por eviction; pipeline serial sin cola. Aceptada. |

---

## 7. Decisiones rechazadas o pospuestas

| Idea | Estado | Motivo | Condición para reconsiderar |
| --- | --- | --- | --- |
| Aplicación completa en `main.py`/`app.py`. | Rechazada | Viola separación y testabilidad. | No reconsiderar; usar módulos y composition roots. |
| DI containers, service locators, plugin managers, event buses. | Pospuesta | No existe necesidad concreta. | Fase aprobada con más de un consumidor real y coste demostrado. |
| Exponer NumPy/OpenCV/Ultralytics/Supervision en contratos. | Rechazada | Acopla dominio y dificulta pruebas. | Solo nuevo adapter, no debilitar contratos. |
| Convertir `Frame.pixels`/`FramePacket` a arrays para optimizar. | Pospuesta | Inmutabilidad y neutralidad tienen prioridad. | Perfil de rendimiento real con diseño de contrato aprobado. |
| Async, multiprocessing o streaming distribuido. | Pospuesta | Complejidad sin requisito actual. | Evidencia de que runner/producer actual no satisface una fase. |
| Procesar todos los frames con cola ilimitada. | Rechazada | Latencia y memoria crecerían sin límite. | No reconsiderar para camino real-time; usar análisis batch separado. |
| Auto-descargar modelos o usar COCO como “pig detector”. | Rechazada | Riesgo de provenance y afirmación falsa. | Artefacto local autorizado, class map y evidencia explícita. |
| Implementar mAP parcial. | Rechazada | Sería métrica engañosa. | Implementación completa, revisada y claramente diferenciada. |
| Split de frames del mismo video entre train/val/test. | Rechazada | Leakage de source. | No reconsiderar; split siempre al nivel de source. |
| Forzar 70/20/10 con tres o pocos clips. | Rechazada | Estadística engañosa. | Suficientes sources independientes autorizados. |
| Otorgar counting candidacy solo por metadata automática. | Rechazada | Requiere confirmación visual/manual. | Mantener revisión explícita. |
| Extraer/guardar frames en imports, tests o CI. | Rechazada | Privacidad y side effects. | Extracción local explícita únicamente. |
| Una instancia global ByteTrack para múltiples cámaras. | Rechazada | Mezclaría estados/IDs. | Multi-camera debe componer instancias aisladas. |
| Tratar `active_tracks` o nuevos IDs como conteo. | Rechazada | IDs temporales cambian/fragmentan. | Solo eventos de cruce y reglas futuras validadas. |
| Añadir línea/conteo durante Phase 5.3. | Rechazada | Fuera de alcance; Phase 6/7 gobiernan esas reglas. | Fase explícitamente aprobada y reconciliada con roadmap. |
| Sesiones, SQLite, UI o analytics anticipados. | Pospuesta | Roadmap asigna Fases 8–12. | Implementar solo su fase aprobada. |
| Afirmar RTSP production readiness por tests USB/sintéticos. | Rechazada | No existe evidencia RTSP representativa. | Validación autorizada por backend/cámara/red. |
| Afirmar protección de patente desde invention log. | Rechazada | Un registro conceptual no otorga protección. | Solo evidencia jurídica externa documentada. |
| Definir Phase 5.4 por inferencia. | Resuelta | El owner aprobó el alcance event-only y sus exclusiones. | Cualquier ampliación hacia conteo pertenece a una fase posterior autorizada. |
| Decrementar el total al observar un reverso. | Rechazada en Phase 7 | Un reverso no demuestra salida definitiva ni corrige una identidad. | Solo con evidencia y una fase/regla futura explícitamente autorizada. |
| Expulsar IDs contados para liberar capacidad. | Rechazada en Phase 7 | Permitiría que un positivo repetido vuelva a incrementar silenciosamente. | Rediseño aprobado con semántica equivalente y evidencia; el default actual falla seguro. |
| Combinar totales de reconnect/lifecycles. | Pospuesta | No existe sesión ni re-identificación biológica. | Phase 8+ con reglas explícitas y riesgos medidos. |

---

## 8. Estado técnico actual

### 8.1 Repositorio y CI

| Elemento | Estado verificado al 25-07-2026 |
| --- | --- |
| Branch | `main` |
| Línea base técnica de Phase 7 | `ee40b6529aa833b9ab701da06347defccfd3fb52` |
| `origin/main` al iniciar Phase 7 | Mismo SHA que la línea base |
| Working tree al iniciar | Limpio |
| Remote | `https://github.com/zicario20/hogflow.git` |
| CI | GitHub Actions `CI`, run `29681085740`, conclusión `success` |
| Suite Phase 5.3 original | 453 passed; 1 warning de ByteTrack deprecated |
| Suite de cierre Phase 5.3 | 465 passed; 1 warning de ByteTrack deprecated |
| Suite Phase 5.4 | 524 passed; 1 warning de ByteTrack deprecated |
| Suite local Phase 6 | 570 passed; 1 warning de ByteTrack deprecated |
| Suite local Phase 7 | 625 passed; 1 warning de ByteTrack deprecated |
| Python local verificado | 3.12.13; proyecto declara `>=3.10` |
| Python CI | 3.12 en Ubuntu latest |

Versiones locales verificadas por metadata de paquetes:

| Dependencia | Versión local | Restricción del proyecto |
| --- | ---: | --- |
| `opencv-python` | 4.13.0.92 | `>=4.10,<5` |
| `supervision` | 0.29.1 | `>=0.29.1,<0.30` |
| `ultralytics` | 8.4.101 | `>=8.4.92,<9` |
| `lap` | 0.5.13 | `>=0.5.12` |
| `pytest` | 8.4.2 | `>=8,<9` |
| `ruff` | 0.15.22 | `>=0.12,<1` |

CI ejecuta checkout, instalación editable `.[dev]`, Ruff lint/format, pytest,
compileall y pip check con permisos `contents: read`. No sube artefactos.

### 8.2 Capacidades reales

**IMPLEMENTADO Y VERIFICADO:**

- línea finita y conteo genérico determinista sobre tracks;
- adapters/pipeline de video finito;
- inventario, selección, preparación, anotación y training tooling local;
- fuente USB/RTSP/file/sintética detrás de `CameraSource`;
- buffer acotado, reconnect, health y shutdown;
- live detection con fakes y adapter local Ultralytics;
- live tracking con fakes y adapter Supervision ByteTrack;
- eventos live de cruce sobre segmento finito normalizado, con lifecycle,
  limpieza acotada y pipeline serial opcional;
- evaluación offline determinista de candidatos de línea con replay idéntico,
  lifecycles aislados, métricas descriptivas/ground truth opcional, ranking
  explícito y reportes sanitizados;
- decisiones live lifecycle-aware para primer positivo, positivo duplicado y
  reverso, con actualización atómica, capacidad acotada y reset por reconnect;
- hardware USB para adquisición, lifecycle detector vacío y tracking de cajas
  sintéticas;
- CI source-only y boundaries automatizados.

**NO IMPLEMENTADO O NO VALIDADO:**

- checkpoint de detector de cerdos entrenado y validado;
- detección real de cerdos en el pipeline live;
- tracking de cerdos representativo y métricas de identidad;
- evaluación representativa de posiciones con ground truth humano;
- validación representativa del conteo lifecycle-aware, reversos y duplicados;
- sesiones de tres secciones;
- SQLite, UI, dashboard, analytics y review clips;
- evaluación contra ground truth y error de conteo;
- RTSP production validation, multi-camera orchestration y piloto.

---

## 9. Defectos conocidos y deuda técnica

El cierre técnico de Phase 5.3 resolvió HF-D001–HF-D003 y formalizó la decisión
arquitectónica de HF-D004–HF-D006. Phase 5.4 mitiga HF-D007 para estado
geométrico y Phase 7 lo mitiga para deduplicación dentro de un lifecycle, sin
resolver identidad física entre lifecycles. Phase 6 mitiga HF-D018 con tooling
reproducible, no con evidencia representativa. La calibración empírica y las
demás deudas permanecen explícitas.

| ID | Severidad | Evidencia | Archivo / símbolo | Descripción y riesgo | Solución recomendada | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| HF-D001 | Media | **HECHO VERIFICADO** | `tracking/models.py::TrackingResult.__post_init__` | Un resultado con IDs duplicados representaría dos cajas con la misma identidad visible. | El modelo rechaza IDs repetidos con `MalformedTrackerOutputError`; regresiones cubren vacío, uno, distintos y duplicados. | Resuelta en el cierre Phase 5.3. |
| HF-D002 | Media | **HECHO VERIFICADO** | `SupervisionByteTrackAdapter::_class_name_map` | Un mismo ID de clase no puede conservar dos nombres sin ambigüedad. | Validación uno-a-uno antes de mutar backend; conflicto produce `InputDataError` sin sobrescritura. | Resuelta en el cierre Phase 5.3. |
| HF-D003 | Media | **HECHO VERIFICADO** | `SupervisionByteTrackAdapter.update`; `LiveTrackingPipeline` | Un fallo ordinario de update puede ser recuperable, pero no debe continuar sobre estado parcial. | Reset inmediato; si funciona, `TemporaryTrackingError` y siguiente frame continúa. Fallo de reset, lifecycle, input y output malformado permanecen fatales/específicos. | Resuelta con posible fragmentación explícita tras recovery. |
| HF-D004 | Media | **HECHO VERIFICADO** | `tracking/config.py::ByteTrackConfiguration.frame_rate`; ADR-038 | ByteTrack recibe FPS estático y la cámara/inferencia pueden operar a frecuencias distintas. | `frame_rate` se define como frecuencia esperada de updates exitosos del tracker; no se adapta automáticamente. | Decisión cerrada; calibración por deployment pendiente. |
| HF-D005 | Alta para evidencia futura | **HECHO VERIFICADO** | ADR-036/038; `LiveTrackingPipeline` | Frames omitidos por scheduling no generan updates intermedios. | Preservar gaps y no fabricar detecciones/updates; test verifica una llamada por request real. | Política cerrada; efecto empírico pendiente. |
| HF-D006 | Alta para oclusión | **HECHO VERIFICADO EN API 0.29.1** | `ByteTrackConfiguration.lost_track_buffer`; ADR-038 | Supervision calcula `max_time_lost = int(frame_rate / 30 * lost_track_buffer)` y lo consume en pasos de update. | Tratar `lost_track_buffer` como referencia a 30 FPS y configurar `frame_rate` según updates efectivos esperados. | Semántica cerrada; tuning con oclusión real pendiente. |
| HF-D007 | Alta para conteo | **HECHO VERIFICADO** | ADR-034/035/041/046; `TemporaryTrackIdentity` | Reset/reconnect puede reutilizar IDs. Phase 7 califica por source/crossing lifecycle y resetea el total, pero no sabe si dos lifecycles observan el mismo animal físico. | Mantener lifecycles separados y medir el riesgo; no inventar identidad biológica. | Mitigada dentro del lifecycle; abierta entre lifecycles. |
| HF-D008 | Alta de mantenimiento | **HECHO VERIFICADO** | `adapters/supervision_bytetrack.py`; ADR-037 | Supervision 0.29.1 advierte que ByteTrack está deprecated desde 0.28 y se elimina en 0.30. | Migrar/reemplazar solo el adapter, manteniendo contratos. | Pin `<0.30`; warning visible. |
| HF-D009 | Baja/Media | **HECHO VERIFICADO** | ADR-012/026 | RGB bytes exige BGR↔RGB y reconstrucción/copy. Puede afectar CPU/latencia. | Perfilar con detector real antes de rediseñar contrato. | Aceptada conscientemente. |
| HF-D010 | Baja | **HECHO empírico** | hardware Phase 5.3 | Un intento de reopen de 15 s terminó sin frames porque el límite incluía apertura/warm-up; una ventana extendida funcionó. | Separar timeout de startup y duración de frame flow si una fase lo exige. | Limitación, no defecto confirmado. |
| HF-D011 | Media de evidencia | **HECHO VERIFICADO** | `.github/workflows/ci.yml` | CI no prueba webcam, RTSP, GPU, pesos, media real, GUI ni calidad de cerdo. | Mantener CI sintético y añadir validación local autorizada/documentada por gate. | Intencional. |
| HF-D012 | Bloqueante empírico | **HECHO VERIFICADO** | docs Phase 4/5 | No hay checkpoint pig-specific validado ni dataset/ground truth final en Git. | Completar localmente autorización, anotación, split, training y evaluación. | Abierta. |
| HF-D013 | Alta para deployment | **HECHO VERIFICADO** | docs Phase 5 | RTSP existe como adapter/config, pero no tiene certificación real de red/cámara. | Test autorizado de disconnect, credentials, latency y reconnect. | Pendiente. |
| HF-D014 | Media de gobernanza | **HECHO VERIFICADO** | `AGENTS.md`; ADR-039–041 | Phase 5.4 carecía de alcance normativo. | El owner aprobó integración event-only sin conteo y preservó Phase 6/7. | Resuelta en Phase 5.4. |
| HF-D015 | Media operativa | **INFERENCIA** | política de datos locales | Git no conserva source maps, media, labels, checkpoints ni reports; su pérdida impide reproducir runs. | Backup local autorizado, cifrado y con control de acceso fuera de Git. | Propuesta pendiente. |
| HF-D016 | Alta para eventos reales | **INFERENCIA respaldada por diseño** | `VirtualLineCrossingDetector`; ADR-040 | Jitter de cajas puede alternar lados y producir eventos aparentes pese a epsilon. | Calibrar epsilon/línea con tracks representativos y medir falsos eventos. | Pendiente empírica. |
| HF-D017 | Alta para trazabilidad | **HECHO VERIFICADO** | `LiveCrossingEvent.previous_frame_sequence`; ADR-040 | Con gaps grandes se observa cambio de lado pero no instante ni trayectoria exacta. | Conservar ambos frames, no interpolar y estratificar evaluación por gap. | Incertidumbre explícita. |
| HF-D018 | Bloqueante para accuracy | **HECHO VERIFICADO** | docs Phase 5.4 / Phase 6 | La línea normalizada es manual y no está calibrada con cerdos representativos. | Usar el evaluador Phase 6 con replay representativo y ground truth autorizado. | Tooling implementado; evidencia pendiente. |
| HF-D019 | Bloqueante empírico | **HECHO VERIFICADO** | `evaluation/line_models.py::EvidenceLevel`; docs Phase 6 | No existe replay representativo con ground truth humano de crossing en Git. | Crear evidencia local autorizada y preservar provenance; no inferir accuracy desde fixtures sintéticos. | Abierta. |
| HF-D020 | Media metodológica | **HECHO VERIFICADO** | `evaluation/line_matching.py` | El matching greedy uno-a-uno es determinista, pero puede no maximizar globalmente matches en casos ambiguos. | Auditar ventanas/ambigüedad con ground truth representativo antes de cambiar algoritmo. | Limitación explícita. |
| HF-D021 | Alta para calibración | **INFERENCIA respaldada por diseño** | `LineCandidate`; métricas near-endpoint | Anchor, epsilon y longitud/posición de segmento pueden sesgar eventos, especialmente con jitter, gaps y oclusión. | Comparar candidatos estratificados y revisar eventos near-endpoint/gap con datos representativos. | Pendiente empírica. |
| HF-D022 | Alta para count accuracy | **INFERENCIA respaldada por diseño** | `LifecycleDirectionalCounter`; ADR-047 | ID switch o fragmentación puede asignar varios IDs al mismo animal y permitir varios incrementos. | Medir con tracking/ground truth representativo antes de afirmar deduplicación real. | Abierta empírica. |
| HF-D023 | Alta para undercount | **INFERENCIA respaldada por diseño** | counted identity set Phase 7 | Reutilizar indebidamente un tracker ID dentro del mismo lifecycle puede bloquear un animal distinto. | Medir ID reuse y limitar lifecycles con reglas futuras explícitas. | Abierta empírica. |
| HF-D024 | Alta entre reconnects | **HECHO VERIFICADO EN DISEÑO** | ADR-046; `LiveCountingPipeline` | Reset evita state leakage pero permite que el mismo animal físico contribuya en otro lifecycle; los totales no se combinan. | Phase 8/11 deben definir y evaluar límites operativos sin re-ID inventada. | Abierta; fuera de Phase 7. |
| HF-D025 | Media de capacidad | **HECHO VERIFICADO** | `maximum_counted_identities` | Alcanzar el límite detiene el run para evitar eviction; una configuración insuficiente afecta disponibilidad. | Dimensionar por deployment y observar capacity errors; no expulsar IDs silenciosamente. | Riesgo explícito/fail-safe. |

---

## 10. Datos y validación empírica

### 10.1 Estado de datos

| Elemento | Qué existe | Qué falta |
| --- | --- | --- |
| Videos reales | **DECISIÓN HISTÓRICA:** se inventariaron localmente clips autorizados y se crearon sidecars; Git no los contiene. | Verificar existencia actual, ampliar diversidad y documentar autorización fuera de Git. |
| Revisión manual | Históricamente, dos clips se consideraron candidatos de conteo (uno más fuerte, uno más difícil) y otro solo detección/tracking por movimiento irregular. | Esa clasificación no prueba accuracy ni está disponible en el repo. |
| Inventario | Tooling y outputs locales JSON/CSV/Markdown. | Output actual es ignorado; no se auditó en esta reconstrucción. |
| Anotaciones | Política y tooling YOLO. | No hay confirmación de dataset real completamente anotado. |
| Splits | Planner por source video. | No hay split real final verificado; pocos sources pueden exigir `preparation`. |
| Ground truth | Modelos/evaluador y reglas. | No existe ground truth de detección/tracking/conteo representativo confirmado. |
| Training | Pipeline reemplazable. | No se ejecutó training real confirmado; no checkpoint pig-specific. |
| Checkpoints | Workspaces/protecciones. | Ningún checkpoint validado disponible al terminar Phase 5.3. |
| Métricas | IoU, matching, precision/recall/F1 implementados. | No métricas reales de cerdos, tracking o conteo. |

Los nombres privados de videos, source references y review notes no pertenecen
a esta memoria. Son datos locales y no deben publicarse.

### 10.2 Evidencia sintética

Prueba contratos, validaciones, geometría, buffers, scheduling, lifecycle,
privacy, adapters con backends falsos y control flow. No prueba:

- apariencia de cerdos;
- generalización del detector;
- oclusión y densidad reales;
- estabilidad de identidad;
- accuracy de cruce o conteo;
- valor económico.

### 10.3 Evidencia de hardware real

- Phase 5.1 validó una webcam USB de portátil mediante OpenCV MSMF, incluidos
  runs de 10 y 30 minutos y reopen repetido.
- Phase 5.2 validó webcam → buffer → detector vacío → shutdown/reopen.
- Phase 5.3 validó webcam → cajas sintéticas → Supervision ByteTrack → telemetry
  → cleanup/reopen.

Esto valida integración y lifecycle en ese hardware. No valida RTSP, detección
de cerdos, tracking real, conteo ni producción.

### 10.4 Autorización y privacidad

- solo datos públicos, sintéticos o explícitamente autorizados;
- media, sidecars, source maps, annotations, manifests reales, runs, weights y
  reports permanecen locales e ignorados;
- CI crea fixtures temporales sintéticos;
- no se publican credentials, URLs RTSP privadas, IPs de deployment ni rutas
  locales.

---

## 11. Métricas

### 11.1 Detección

Implementadas como infraestructura, pero sin resultado real de cerdos:

- `IoU = intersection_area / union_area`;
- `precision = TP / (TP + FP)`;
- `recall = TP / (TP + FN)`;
- `F1 = 2 * precision * recall / (precision + recall)`;
- falsos positivos y falsos negativos por frame/clase;
- latencia promedio, p50/p95 y FPS efectivo live.

El matching es uno-a-uno, por clase, ordenado por confidence y tie-break IDs.
No existe una implementación HogFlow de mAP; métricas mAP de framework deben
permanecer namespaced y no equivalen a accuracy de conteo.

### 11.2 Tracking

Métricas previstas para validación futura:

- ID switches;
- fragmentación de tracks;
- tracks perdidos;
- reasociaciones;
- estabilidad de ID bajo oclusión, densidad y gaps;
- tiempo hasta confirmación/expiración;
- latencia de update y tasa de updates;
- fallos, resets y comportamiento después de reconnect.

Telemetry actual (`tracks_emitted`, IDs nuevos, visibles actuales, latencia) es
operativa, no una métrica de accuracy ni un conteo de cerdos.

### 11.3 Conteo

Métricas objetivo del sistema completo:

- `Absolute Count Error = abs(AI Count - Ground Truth)`;
- `Count Error Rate = abs(AI Count - Ground Truth) / Ground Truth`;
- Exact Count Rate;
- error porcentual;
- overcount rate;
- undercount rate;
- exactitud por dirección;
- exactitud por sesión/sección;
- resultados estratificados por densidad, oclusión, iluminación y perspectiva.

El KPI primario es error de conteo, no precision de detección aislada. Ninguna
de estas métricas de conteo tiene todavía resultado empírico con cerdos.

---

## 12. Fase siguiente

### 12.1 Siguiente trabajo confirmado

**HECHO VERIFICADO:** el owner autorizó Phase 7 con política conservadora por
lifecycle: primer positivo incrementa, positivos repetidos y reversos no
incrementan, y un reverso no decrementa. La implementación no añade sesiones,
storage o UI.

**Recomendación actual:** auditar Phase 7 y su CI antes de comenzar Phase 8.
En paralelo, la evaluación representativa pendiente de Phase 6/7 debe
permanecer explícita y no bloquear la honestidad del estado técnico.

### 12.2 Siguiente fase normativa

Phase 8 conserva su propósito normativo: construir el session manager de tres
secciones. No está iniciada por Phase 7. Debe componer el contador existente,
no copiar sus reglas, y definir cuándo comienza/termina un lifecycle operativo
sin convertir IDs temporales en identidad biológica.

Fuera del siguiente trabajo salvo aprobación expresa:

- SQLite/storage de Phase 10;
- Operator MVP UI de Phase 9;
- re-identificación, net count o decremento por reverso;
- combinar cámaras o reconnects sin regla validada;
- afirmar count accuracy desde fixtures sintéticos.

### 12.3 Condiciones de inicio de Phase 8

- auditoría técnica y CI de Phase 7 verificados;
- límites entre crossing, counting lifecycle y session lifecycle revisados;
- reglas de una sola sesión activa y reset de IDs especificadas;
- riesgos de reconnect, ID switch, fragmentación y total parcial visibles;
- ninguna dependencia de storage/UI adelantada;
- actualización de esta memoria incluida en el commit autorizado.

### 12.4 Criterios mínimos del siguiente cierre

- ninguna regresión Phase 0–7;
- Phase 8 limitada al session manager autorizado;
- evento geométrico, decisión lifecycle y sesión separados;
- ID switches, fragmentación y reconnect tratados como riesgos observables;
- resultados pobres y fallos conservados;
- documentación, ADRs y memoria sincronizadas;
- quality gates, push y CI reportados con evidencia real.

---

## 13. Roadmap

### 13.1 Roadmap normativo Phase 0–16

- **CONFIRMADO / implementado:** Phase 0, Phase 1, Phase 2.1–2.3, tooling Phase
  3, tooling Phase 4.1–4.3, Phase 5.1–5.4, tooling Phase 6 y Phase 7 según sus
  alcances.
- **CONFIRMADO / no iniciado:** Phase 8–16 con nombres y límites definidos en
  `AGENTS.md`.

### 13.2 Cierre técnico inmediato

1. **COMPLETADO:** cierre de observaciones técnicas de Phase 5.3.
2. **COMPLETADO:** definición e implementación event-only de Phase 5.4.
3. **COMPLETADO:** infraestructura offline de evaluación Phase 6.
4. **COMPLETADO:** infraestructura lifecycle-aware de Phase 7.
5. **PENDIENTE:** auditar Phase 7 y ejecutar evaluación representativa Phase
   6/7.
6. **PENDIENTE:** triage de deuda del tracker y plan de migración Supervision.
7. **PENDIENTE:** asegurar backup privado/reproducible de datos locales.

### 13.3 Validación técnica

1. Completar dataset autorizado, anotación y split por source.
2. Entrenar/evaluar un detector pig-specific con provenance.
3. Medir tracking real: ID switches, fragmentación, oclusión y gaps.
4. Phase 6: aplicar el evaluador a posiciones con datos representativos.
5. Phase 7: medir reversos y duplicate-counting con eventos representativos.
6. Phase 11–12: ground truth, error y failure analytics.

Estas tareas son **TENTATIVAS en calendario**, aunque las fases 6–12 son parte
del roadmap confirmado.

### 13.4 Piloto

**FUTURO, no aprobado como ejecución:** Phase 16 define readiness, no realiza un
piloto. Requiere autorización, cámaras, ground truth, seguridad, continuidad de
conteo manual, criterios de éxito/fallo, rollback y revisión posterior.

### 13.5 Producto inicial

**ROADMAP CONFIRMADO, implementación futura:**

- Phase 8: session manager de tres secciones;
- Phase 9: Operator MVP UI;
- Phase 10: SQLite y eventos;
- Phase 13: review system/clips.

El orden de integración exacto debe respetar dependencias y una especificación
aprobada. No existe producto inicial operativo hoy.

### 13.6 Etapa comercial

**TENTATIVA:** validar necesidad recurrente, workflow, willingness to pay,
costes e impacto en instalaciones autorizadas. `MARKET_RESEARCH.md` conserva un
screen preliminar de 18–27 instalaciones candidatas entre procesadores grandes;
no es TAM/SAM validado, forecast ni pipeline comercial.

### 13.7 Escalabilidad futura

**IDEAS FUTURAS, no aprobadas:** multi-camera orchestration, adapter RTSP
certificado, procesamiento async/distribuido, reemplazo de ByteTrack, hardware
edge, observabilidad más amplia y deployments administrados. No deben
implementarse hasta que una necesidad medida justifique su coste.

---

## INSTRUCCIONES PARA CHATGPT, CODEX Y OTROS AGENTES

1. Leer completamente `AGENTS.md` y este archivo antes de modificar el proyecto.
2. Inspeccionar repositorio, documentos relevantes, tests y Git; no confiar
   ciegamente en esta memoria.
3. Verificar branch, `HEAD`, `origin/main` y working tree.
4. Comparar esta memoria con el estado actual y reportar discrepancias.
5. Usar código/Git como verdad técnica; usar conversación como contexto
   histórico; no inventar decisiones.
6. Distinguir siempre implementación, documentación, prueba sintética,
   hardware plumbing y evidencia empírica real.
7. No modificar arquitectura o contratos públicos sin aprobación explícita.
8. No implementar fases futuras ni redefinir el roadmap.
9. No usar ni exponer media privada, credentials, paths, source references,
   weights o datos de empleadores.
10. No descargar modelos/media ni añadir telemetry cloud de forma silenciosa.
11. Ejecutar pruebas y quality gates; no afirmar éxito si no se ejecutaron.
12. Entregar el SHA exacto y el estado de push/CI cuando el flujo incluya Git.
13. Antes del commit, decidir si cambió el conocimiento del proyecto.
14. Si cambió, actualizar esta memoria en el mismo commit; modificar solo las
    secciones afectadas, no regenerar el documento completo.
15. En el reporte final, confirmar si esta memoria cambió y por qué. Si no
    cambió, explicar por qué el cambio no alteró el conocimiento del proyecto.
16. Preservar el historial de invención y separar market research de resultados.
17. Nunca presentar IDs temporales, detecciones, tracks visibles o el total
    Phase 7 como identidad biológica, conteo de sesión o accuracy validada.
18. No convertir la evaluación Phase 6 en deduplicación/reversos ni contaminar
    sus métricas con Phase 7; cada contrato conserva su alcance.
19. Todo cambio aprobado debe terminar con tests, commit descriptivo, push a
    la rama autorizada y verificación `HEAD == origin/<rama>`, salvo que el
    usuario retire expresamente autorización de push.
20. No afirmar CI verde sin recuperar la conclusión remota real.

Checklist mínimo antes de commit:

```text
[ ] alcance actual solamente
[ ] tests anteriores y nuevos pasan
[ ] arquitectura y imports respetados
[ ] diff y archivos staged revisados
[ ] no datos/artefactos/secretos
[ ] documentación coincide con código
[ ] HOGFLOW_PROJECT_MEMORY.md actualizada si corresponde
[ ] commit descriptivo y push a rama autorizada
[ ] HEAD coincide con origin/<rama>
[ ] SHA, push y CI real reportables
```

---

## 15. Glosario

| Término | Definición en HogFlow |
| --- | --- |
| `Frame` | Frame finito canónico con RGB bytes, dimensiones, índice y timestamp. |
| `FramePacket` | Unidad viva inmutable con stream ID, secuencia monotónica, tiempos, dimensiones y payload. |
| `Detection` | Caja, confidence, class ID y class name sin identidad temporal. |
| `DetectionResult` | Nombre conceptual para salida estructurada; en live el tipo concreto es `FrameDetections`. |
| `FrameDetections` | Detecciones vinculadas exactamente a un `FramePacket`, modelo y latencia. |
| `Tracker` | Protocol finito que asocia `Frame + Detection` y devuelve `Track`. |
| `LiveTracker` | Protocol con lifecycle explícito, ligado a un stream, que devuelve `TrackingResult`. |
| `TrackingResult` | Resultado inmutable de tracks visibles para un frame exacto; no es conteo. |
| `track_id` | Identidad temporal asignada por un tracker dentro de un lifecycle. |
| `VirtualLine` | Segmento finito dirigido; Phase 5.4 usa `NormalizedLine` independiente de resolución. |
| `CrossingEvent` | Evento Phase 1 con `counted`; no debe confundirse con el evento live event-only. |
| `LiveCrossingEvent` | Transición geométrica live ligada a frame, línea y lifecycle; no contiene conteo acumulado. |
| `TemporaryTrackIdentity` | Clave Phase 7 `(source, crossing lifecycle, tracker ID)`; temporal, no biológica. |
| `LiveCountingDecision` | Resultado auditable por evento: positivo contado, positivo duplicado o reverso ignorado. |
| `LiveCountingResult` | Lote atómico de decisiones y total del lifecycle para un frame; no es resultado de sesión. |
| `LifecycleDirectionalCounter` | Contador Phase 7 que permite un incremento positivo por identidad temporal dentro de un crossing lifecycle. |
| Lifecycle directional count | Total Phase 7 limitado al lifecycle actual; se reinicia tras reconnect/reset y no prueba animales únicos. |
| `LineSide` | Lado explícito `NEGATIVE`, `ON_LINE` o `POSITIVE` respecto a línea orientada. |
| `TrackAnchor` | Política determinista para punto representativo; default live `BOTTOM_CENTER`. |
| `LineCandidate` | Configuración inmutable y fingerprinted de línea, anchor, epsilon y retención para evaluación offline. |
| `TrackingReplay` | Secuencia inmutable y ordenada de `TrackingResult` usada idénticamente por cada candidato. |
| `LineEvaluationReport` | Reporte sanitizado con resultados, evidencia, ranking explícito, warnings y limitaciones; no es count report. |
| Evidence level | Clasificación `SYNTHETIC`, `CONTROLLED_REPLAY`, `REPRESENTATIVE_WITHOUT_GROUND_TRUTH` o `REPRESENTATIVE_WITH_GROUND_TRUTH` que limita afirmaciones. |
| Counter | Regla que incrementa únicamente un cruce positivo elegible por tracker. |
| Session | Ventana operativa futura por sección con estado y conteo independiente. No implementada. |
| Stream | Secuencia potencialmente no acotada de una fuente USB/RTSP; file es desarrollo finito. |
| Adapter | Capa que convierte entre frameworks externos y modelos/contratos HogFlow. |
| Lifecycle | Periodo `start/open` a `close`, con estado y propiedad de recursos. |
| Frame gap | Diferencia de secuencia por drops o skips; no implica detecciones intermedias. |
| Reconnect | Reapertura de fuente viva tras interrupción; resetea el tracker live actual. |
| Ground truth | Etiqueta/conteo humano autorizado usado como referencia independiente. |
| ID switch | Cambio de identidad asignada a un mismo objeto o intercambio entre objetos. |
| Fragmentación | Un objeto real representado por varios tracks separados. |
| Bounded buffer | Cola de capacidad fija que limita memoria/latencia y registra drops. |
| Latest-useful-frame | Política que prioriza el frame elegible más reciente y omite backlog obsoleto. |
| `lost_track_buffer` | Parámetro ByteTrack de tolerancia a pérdida; su relación con gaps reales requiere validación. |
| Provenance | Metadata verificable de artefacto/config/dataset sin afirmar calidad ausente. |
| `verified_empty` | Estado humano explícito para un frame sin cerdos; habilita label YOLO vacío intencional. |
| Counting candidate | Clip con confirmaciones manuales mínimas para estudiar conteo; no prueba que contar funcione. |
| RTSP | Protocolo soportado arquitectónicamente por adapter; no validado para producción. |

---

## Regla final de integridad

Esta memoria no convierte intención en evidencia. HogFlow sigue siendo un
prototipo de investigación. El avance técnico debe medirse primero por
correctitud, aislamiento arquitectónico y reproducibilidad; la viabilidad se
decidirá únicamente con datos autorizados, ground truth y resultados honestos.
