# Plan de integración progresiva de datos porcinos

**Estado:** propuesta; no se descargaron datos ni se entrenó V3.

## Principios de seguridad

- V2, sus pesos, SHA, parámetros y evidencia histórica permanecen inmutables.
- A/B siguen siendo desarrollo de V2; Video C no se selecciona ni inspecciona
  en este trabajo.
- Los tres vídeos originales reservados de Phase 10.3 siguen bajo su catálogo
  estricto y no se reutilizan para una mezcla externa.
- Todo dataset externo se mantiene local, ignorado y con acceso autorizado.
- El entrenamiento externo nunca sustituye la validación independiente local.
- El flujo operativo sigue siendo cuatro docks → un carril compartido → una
  cámara/fuente → un contador.

## Etapa A — Auditoría de datos

Antes de copiar una sola imagen:

1. Guardar URL oficial, DOI/revisión, autores, fecha de acceso y términos de
   licencia.
2. Confirmar que la licencia permite uso de investigación, obras derivadas,
   entrenamiento de modelos y, por separado, uso comercial futuro. Para
   **PigLife**, la licencia oficial es Non-Exclusive Research Use: limita el
   uso a investigación no lucrativa, excluye uso comercial, prohíbe
   modificaciones/mejoras de los datos y compartirlos, y termina a los cinco
   años; por eso labels o modelos derivados requieren autorización escrita
   compatible. Si una casilla es desconocida, estado `BLOCKED_LEGAL_REVIEW`.
3. Descargar únicamente metadatos o un paquete pequeño autorizado para
   inventario. No descargar el archivo completo por defecto.
4. Generar un inventario de clips, frames, dimensiones, FPS, modalidades,
   clases, IDs, masks, timestamps y tamaño de archivo.
5. Calcular checksums de los archivos adquiridos y conservar el checksum de la
   fuente; no sobrescribir los originales.
6. Detectar duplicados exactos y casi duplicados dentro de cada fuente y entre
   fuentes. Comparar también nombres de cámara/día para evitar fuga.
7. Mantener separados los días, corrales, cámaras, grupos y secuencias. La
   unidad de split es la fuente temporal, no un frame aleatorio.
8. Revisar visualmente solo una muestra pequeña autorizada. No convertir la
   inspección en una nueva selección de Video C.

### Orden recomendado de auditoría

1. PigDetect High-IoU (paquete YOLO pequeño o metadatos; licencia primero).
2. PigLife Sub-1 (términos de Illinois primero).
3. PigTracking o Edinburgh (solo si se abre una pista MOT aislada).
4. OinkTrack/PigTracker/IR únicamente tras justificar la necesidad.

## Etapa B — Normalización

La normalización debe ser reversible y conservar las anotaciones nativas.

### Vista detector

```text
fuente original → parser específico → validación → clase pig=0
               → imagen/label YOLO → AnnotationManifest
               → PreparedTrainingDataset
```

El manifest debe conservar `source_dataset`, `source_clip_id`, `source_frame`,
licencia, versión, checksum, dimensiones y una huella de transformación. Los
labels normalizados se validan con las reglas existentes: coordenadas válidas,
clase 0 únicamente, boxes dentro de imagen, pares imagen/label y negativos
intencionales.

### Vista tracking

```text
MOT / Edinburgh JSON / OinkTrack JSON → frame_id + target_id + box
                                     → TrackingReplay
                                     → ByteTrack/crossing offline
```

El `target_id` externo se usa para matching de ground truth y no se inyecta
como ID de ByteTrack. Edinburgh requiere expandir las entradas por cambios e
interpolación descrita por su página; PigTracking y OinkTrack ya publican
formatos MOT o convertibles.

### Vista de segmentación

Las máscaras no cambian V2 automáticamente. Se pueden conservar para medir
solapamiento/oclusiones o para un experimento posterior, pero el primer V3
debe seguir siendo una hipótesis de detector de cajas con clase única.

## Etapa C — Experimentos aislados

No ejecutar ahora. Cada experimento usa un manifest y fingerprint nuevos,
mantiene A/B solo como desarrollo histórico y reserva un holdout externo no
consultado. La matriz propuesta está en
[`v3-experiment-proposal.md`](v3-experiment-proposal.md).

Reglas:

- máximo cuatro entrenamientos controlados iniciales;
- una variable principal por experimento (fuente, mezcla o tamaño de modelo);
- seed y configuración congelados antes de mirar el holdout;
- no seleccionar hiperparámetros con C;
- comparar siempre contra V2 en el mismo conjunto nuevo cuando sea posible;
- mantener un baseline V2 sin datos externos.

## Etapa D — Evaluación independiente

Hace falta una fuente nueva, preferiblemente un vídeo `demo_video_c` o posterior,
con autorización explícita y 30–60 frames humanos etiquetados para detección.
No puede haber frames, vecinos temporales ni clips del holdout en el train o
calibración.

Para conteo se requieren totales humanos independientes por vídeo y la línea
normalizada documentada. Un total humano no permite calcular precision/recall
de detección; boxes por frame y conteo completo son evidencias distintas.

La evaluación debe ejecutarse una vez con:

- arquitectura y weights congelados;
- `imgsz`, confidence, IoU NMS, `max_det` y tracker congelados;
- reporte de detección, tracking y conteo por separado;
- latencia/FPS de detector y pipeline completo;
- advertencia explícita de domain shift.

## Etapa E — Decisión GO / NO-GO

### GO condicionado para un experimento V3

Solo si se cumplen todos estos gates:

1. licencia escrita y compatible con el uso de entrenamiento y los artefactos
   derivados;
2. inventario reproducible, checksums y split por fuente sin fugas;
3. labels validados por HogFlow con cero errores fatales;
4. una razón causal para incluir la fuente (densidad, iluminación, oclusión o
   tracking), no solo más imágenes;
5. holdout nuevo autorizado, no usado para decisiones;
6. comparación pre-registrada contra V2, no una métrica externa aislada;
7. almacenamiento y tiempo de cómputo disponibles sin guardar vídeo de
   producción.

### NO-GO

No iniciar V3 si la licencia está ambigua, los splits no pueden auditarse, los
frames son solo crops sin contexto, la fuente no aporta cajas/IDs verificables,
o el experimento exige cambiar el contador/lane operativo para “hacerlo
funcionar”.

## Estimación de almacenamiento

Hechos publicados:

- PigDetect: 22 GB en la ficha; el paquete YOLOv8 aislado ronda 260–283 MB y
  High-IoU completo 10,5 GB.
- PigLife: 16,2 GiB.
- PigTracking: 48,3 GB en los tres ZIP publicados.
- Edinburgh: `annotated.tar` 3,2 GB; los archivos RGB-D diarios publicados
  varían aproximadamente de 8,5 a 25,8 GB por archivo según la tabla oficial.
- FaroPigSeg: ~150 MB; FaroPigReID-33 ~12 GB.

Planificación (inferencia, no tamaño garantizado): reservar 2–3× el tamaño de
la fuente para copia original autorizada, vista normalizada, manifests,
checksums y un run temporal. Por ello el primer piloto PigDetect puede caber en
~1–3 GB si se usa solo el paquete YOLO; PigLife y PigTracking deben tratarse
como adquisiciones de decenas de GB, no como un `pip install`.

## Estimación de cómputo

Son rangos de planificación, no resultados medidos:

- inventario/normalización: horas de I/O en SSD, dependiendo del número de
  frames extraídos;
- fine-tune pequeño de YOLO11n/YOLO11s a 640 con un subconjunto acotado: horas
  en una GPU moderna; CPU puede tardar un orden de magnitud más;
- replay MOT y métricas: principalmente I/O/CPU, con memoria acotada si se
  procesa por secuencia;
- máscaras, vídeo RGB-D y secuencias largas: coste dominante de decodificación
  y almacenamiento, no una justificación automática para cambiar el detector.

El hardware y el tiempo reales deben registrarse en el run; no se autoriza
presupuestar un piloto comercial a partir de estas estimaciones.

## Cambios de arquitectura necesarios (futuro, no implementados)

Solo serían necesarios adaptadores offline, no una segunda arquitectura:

- `PigDetectAdapter` para YOLO/COCO;
- `PigLifeAdapter` para sus subdatasets y metadata;
- `MotReplayAdapter` para PigTracking/OinkTrack;
- `EdinburghJsonAdapter` para JSON e interpolación;
- validación de licencia/procedencia y fingerprint de dataset;
- reportes separados de detección/tracking/conteo.

No se debe añadir una cola de vídeo, persistencia, cámara multicam, ReID,
estimación de peso, clase por tipo de cerdo ni lógica de negocio.
