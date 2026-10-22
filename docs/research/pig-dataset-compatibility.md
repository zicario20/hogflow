# Compatibilidad de datasets porcinos con HogFlow

**Estado:** análisis de integración; no se modificaron contratos ni se
ejecutaron experimentos.

## Punto de partida HogFlow

La arquitectura existente mantiene estas fronteras:

`video → Detector → Detection → ByteTrack → track_id → línea dirigida → LifecycleDirectionalCounter → lane compartido → HMI`

El detector es un puerto framework-neutral (`Detector.predict(frame)`), y el
entrenamiento recibe un `PreparedTrainingDataset` validado. El cargador local
reutiliza manifest, status `annotated`/`verified_empty`, validación YOLO,
checksums, dimensiones y aislamiento por `clip_id`. La evaluación de detección
convierte boxes a coordenadas píxel y hace matching IoU; no evalúa tracking ni
conteo.

El V2 activo debe permanecer intacto: `hogflow_pig_demo_v2`, clase única
`pig`/0, `imgsz=640`, confianza `0.25`, IoU `0.5`, `max_det=300`, sin half,
SHA-256 `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c`.

## Mapa de compatibilidad

| Fuente | Conversión de datos necesaria | YOLO11 / Ultralytics | ByteTrack | Evaluación de detección | Evaluación de conteo | Riesgo principal |
|---|---|---|---|---|---|---|
| PigDetect | Casi ninguna para el paquete YOLO; validar `class_id`, dimensiones, hashes y split por día. | **Directa** para el experimento de cajas. Máscaras no entran en V2. | No aporta IDs temporales; usar solo detecciones en vídeo/replay si existe secuencia, no inventar IDs. | `PreparedTrainingDataset` puede consumir labels normalizadas tras manifest HogFlow. | Requiere trayectorias y una línea artificial; no es ground truth de cruce. | Licencia no visible; posible shift de granja/cámara. |
| PigLife | Parser por subdataset; conservar identificación, boxes, máscaras, postura, oclusión y nombre de origen. | Compatible después de normalizar a YOLO clase 0 `pig`; no descartar la metadata auxiliar. | Depende de si el clip entrega frame IDs/track IDs; auditar antes de usar. | Buen candidato para medir variabilidad de caja/oclusión. | No tiene por defecto la semántica HogFlow de “cruzó hacia pesaje”. | Términos propietarios y diversidad no equivalente a pasillo. |
| PigTracking | Adaptador MOT (`gt.txt`) a manifest/replay; `frame_id` y `target_id` deben conservarse. | Solo útil si se extraen imágenes y boxes para un experimento separado; no mezclar automáticamente. | **Directa para evaluación offline**; mapear MOT GT a `TrackingReplay`, nunca al ID runtime. | Boxes pueden alimentar una evaluación, pero el benchmark es temporal. | Replay con línea sintética sí; no implica conteo operacional. | Volumen, licencia pendiente y FPS subsampleado. |
| Edinburgh | Parser `output.json`, expansión de anotaciones por cambios e interpolación al frame RGB; opción de depth separada. | Compatible para RGB tras normalizar boxes; depth fuera del contrato actual. | **Alta**: IDs persistentes y frames temporales explícitos. | Útil para cajas y oclusión en un plano cenital. | Solo prueba la mecánica de cruce si se define una línea artificial; no representa corredor. | Un solo corral, casi cenital y solo día. |
| OinkTrack | Consumir `annotation.json` o su conversión MOT; mantener escenas, cámara y condiciones día/noche como fuentes separadas. | No es el primer adaptador de entrenamiento de V2; puede aportar un subconjunto de cajas. | **Alta** para MOT/TrackEval y estrés de iluminación. | Secundaria: su valor es temporal. | Replay de línea posible, pero sin verdad de cruce del proceso. | Licencia de datos no declarada y acceso externo. |
| AIFARMS Multi-Camera | Leer JSON/homografías y distinguir identidad global de track local. | No es necesario para el detector V2. | Útil para handover multicámara, fuera de la arquitectura de una cámara. | No hay inventario resumido suficiente para un primer fine-tune. | No compatible con un único pasillo/cámara sin introducir arquitectura prohibida. | Se tentaría a crear segunda cámara/worker. |
| FaroPigSeg | Verificar si “YOLO” son boxes o polígonos; adaptar solo boxes si la tarea sigue siendo detección. | Compatible como detección/segmentación no comercial tras auditoría. | No es benchmark temporal principal. | Puede aportar siluetas y oclusiones. | No aporta cruce. | Uso comercial prohibido. |
| PigTracker | Convertir SV-OBB a AABB solo como experimento de pérdida de información; conservar OBB original. | No es caja YOLO axis-aligned equivalente. | Alta para orientación/MOT si se obtiene permiso. | Secundaria. | Baja para el contador actual. | Acceso por acuerdo y formato orientado. |
| INPC IR | Convertir máscaras a boxes, conservar modalidad IR y separar de RGB. | No compatible directamente con V2 RGB; requiere experimento multimodal/IR. | Baja. | Solo prueba un dominio de sensor distinto. | Baja. | Licencia y descarga no verificadas; objetivo no es el cuerpo RGB. |

## Implicación para el fallo A→B

El informe de Phase 10.3B atribuyó la caída de V1 a una mezcla de shift de
escena/iluminación/composición, sesgo de cobertura y más crowding en B; la
resolución y `max_det` no explicaron el fallo. Por tanto:

- **PigDetect High-IoU** es la prueba más limpia para la hipótesis
  “faltan ejemplos densos/solapados”.
- **PigLife** prueba la hipótesis “falta variabilidad de fase, postura,
  ambiente y oclusión”, pero puede añadir demasiado shift si se mezcla sin
  ponderación.
- **PigTracking/OinkTrack/Edinburgh** prueban la hipótesis temporal
  (fragmentación, pérdida, ID switch), no la suficiencia del detector por sí
  solos.

Los resultados externos deben medirse además en una fuente local nueva. Un
mejor mAP en PigDetect no demuestra una mejora en la cámara de JBS.

## Compatibilidad con el contador y el carril único

`LiveDirectionalCounter` consume tracks y una línea dirigida; no sabe de
datasets. Para estudiar conteo sin tocar producción se necesita un adaptador de
replay que:

1. lea frames y boxes/IDs de una fuente;
2. convierta cada box a `TrackAnchor` con dimensiones nativas;
3. ejecute el tracker/crossing en un lifecycle explícito;
4. registre crossings positivos, reversos, duplicados y pérdidas;
5. compare el total solo con un conteo humano independiente del mismo vídeo.

No se debe pasar un `target_id` externo como identidad biológica de HogFlow ni
mutar el `SharedCountingLane`, docks, sesiones o totales operativos. La fuente
externa es una evidencia offline y el lane sigue siendo único.

## Requisitos mínimos de un adaptador futuro

- `source_id`, versión, licencia y checksum sin paths absolutos.
- Dimensiones, FPS, orientación, frame numbering y timestamps.
- Anotaciones originales inmutables y una vista normalizada HogFlow.
- `clip_id` opaco y split por vídeo/día/grupo, nunca por frames vecinos.
- Mapa explícito a clase `pig=0`; rechazar clases auxiliares silenciosamente no.
- Reporte de frames sin pigs como `verified_empty` cuando exista evidencia.
- Detección de duplicados por checksum de imagen y por perceptual hash
  únicamente como diagnóstico, no para borrar sin revisión.
- Registro de transformación: COCO/MOT/JSON/mascara → YOLO o replay.
- Prohibición de enviar datos a SaaS o de copiar media privada al repositorio.

## Decisión de arquitectura

No hace falta cambiar el runtime de producción para empezar un V3. Las únicas
capas justificables serían:

1. un adaptador offline de importación/validación;
2. un manifest de procedencia y licencia;
3. un normalizador a `PreparedTrainingDataset` y, por separado, un lector MOT
   para `TrackingReplay`;
4. métricas de tracking/conteo en un reporte offline.

No se autoriza una segunda cámara, un segundo detector, otro tracker, otra cola,
persistencia de vídeo o una nueva lógica de conteo.

## Métricas por capa

### Detección

Precision, recall, F1, TP/FP/FN por vídeo y por bin de tamaño/densidad; mAP50 y
mAP50–95 del framework, siempre separados de las métricas HogFlow. Reportar
falsos positivos y negativos por vídeo y no solo el promedio agregado.

### Tracking

IDF1/HOTA/MOTA cuando el formato y la licencia permitan una evaluación MOT,
además de fragmentación, ID switches, tracks perdidos, duración de track,
latencia y pérdida cercana a la línea. Los IDs del dataset son ground truth de
tracking, no IDs de operación.

### Conteo

Cruces positivos, reversos, duplicados, omitidos y error absoluto frente al
conteo humano. El sistema no puede generar su propia verdad terreno. Reportar
también FPS y latencia del pipeline completo.
