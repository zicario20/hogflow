# Propuesta de experimento V3 para HogFlow

**Estado:** propuesta para autorización futura. No se entrenó V3 y no se
descargaron datasets completos.

## Objetivo

Determinar si datos externos autorizados reducen la caída de generalización
observada entre los vídeos locales A y B, sin cambiar el runtime de cuatro docks
con un único carril compartido.

La pregunta no es “qué dataset tiene el mAP más alto”, sino:

> ¿Una incorporación trazable de densidad, oclusión, iluminación o continuidad
> temporal mejora el detector/tracker de HogFlow en un vídeo nuevo y no visto,
> con el mismo contrato operativo?

## Baseline congelado

El baseline V2 no se retrena ni se sustituye:

| Elemento | Valor |
|---|---|
| Identidad | `hogflow_pig_demo_v2` |
| SHA-256 | `892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c` |
| Detector | YOLO11n / Ultralytics |
| Clase | `pig`, ID 0 |
| Resolución | 640 |
| Confianza | 0.25 |
| IoU NMS | 0.50 |
| `max_det` | 300 |
| Half precision | No |
| Estado | Demo; no validado para producción |

La comparación V2↔V3 debe ejecutar ambos modelos en el mismo holdout nuevo,
con el mismo preprocesado, matching IoU y protocolo de tracking.

## Fuentes candidatas y función experimental

| Fuente | Hipótesis que prueba | Uso inicial |
|---|---|---|
| PigDetect High-IoU | Más ejemplos densos y solapados reducen FN en crowding. | Fine-tune de detección acotado; no IDs. |
| PigLife | Variar fase productiva, postura, oclusión y ambientes mejora robustez. | Mezcla ponderada con muestra local; requiere licencia de Illinois. |
| PigTracking | Un detector mejor no basta si el track se fragmenta. | Benchmark MOT offline, no necesariamente train. |
| Edinburgh | IDs persistentes y temporalidad permiten medir continuidad. | Replay/track evaluation; no asumir transferencia geométrica. |
| OinkTrack | Día/noche, transiciones y alta densidad fuerzan asociaciones difíciles. | Experimento de tracking posterior; licencia pendiente. |

## Splits y gobernanza

### Desarrollo

- `local_a_b_dev`: solo A+B históricos ya consumidos por V2; no se presentan
  como holdout.
- `external_dev`: clips/días/grupos externos asignados por fuente temporal.
- `calibration`: bloques separados por vídeo/día, con buffer temporal; nunca
  frames vecinos de train.

### Holdout

- `demo_video_c` o una fuente posterior autorizada, nueva y no inspeccionada.
- Boxes humanos para 30–60 frames representativos y conteo humano completo si
  se desea evaluar crossing.
- C no entra en train, threshold, epochs, selección de modelo, NMS ni tuning de
  tracker.

### Reglas de exclusión

- No usar imágenes del mismo vídeo en train y holdout aunque tengan nombres
  diferentes.
- No mezclar frames extraídos de un mismo clip en splits distintos.
- No usar pesos publicados de PigDetect/PigTracking como “V3” sin declarar que
  son modelos externos y sin una auditoría de licencia/procedencia.
- No copiar media privada o archivos derivados al control de versiones.

## Matriz pequeña de experimentos

Máximo inicial: cuatro entrenamientos. Todos parten de un checkpoint oficial
compatible y de la abstracción HogFlow existente.

| ID | Datos de entrenamiento | Modelo / tamaño | Propósito | Selección |
|---|---|---|---|---|
| E0 | A+B local de desarrollo, exactamente el fingerprint V2 | V2 congelado | Baseline de referencia; no entrena. | Siempre. |
| E1 | Muestra autorizada PigDetect High-IoU + A local, pesos por fuente declarados | YOLO11n, 640 | Aislar si densidad/oclusiones mejoran recall sin matar precision. | F1/recall interno y diagnóstico de crowding. |
| E2 | A+B + PigDetect, split temporal por fuente | YOLO11n, 640 | Medir mezcla y transferencia sin aumentar capacidad. | V2 vs E2 en holdout C. |
| E3 | E2 + muestra PigLife aprobada, o PigLife-only como control de shift | YOLO11n o YOLO11s solo si E2 sigue limitado | Medir diversidad de iluminación/producción; no justificar modelo grande por intuición. | V2 vs E3 en C, coste y estabilidad. |

PigTracking, Edinburgh y OinkTrack deben iniciar como evaluación de tracking,
no como un quinto entrenamiento de detector. Si se autoriza una pista de MOT,
su resultado no decide por sí solo el modelo de cajas.

## Configuración a congelar antes de C

- arquitectura y checkpoint base;
- `imgsz`, batch, seed, workers, epochs y early stopping;
- augmentations;
- threshold de confianza, IoU NMS y `max_det`;
- tracker y sus parámetros;
- geometría de línea y anchor para el replay de conteo;
- versión de Ultralytics/Torch y dispositivo.

## Métricas y protocolo

### Detección

Por vídeo y agregado: TP, FP, FN, precision, recall, F1, mAP50 y mAP50–95
separados; además de FN por frame, FP por vídeo, bins de tamaño, densidad y
oclusiones anotadas cuando existan.

### Tracking

IDF1/HOTA/MOTA o el subconjunto permitido por el formato; fragmentación,
ID-switches, track loss, duración, continuidad cerca de la línea y latencia.
Los IDs externos son referencia de evaluación, no IDs de operación.

### Conteo

Sistema frente a conteo humano: diferencia firmada, error absoluto, porcentaje,
overcount, undercount, duplicados, omitidos y eventos por dirección. Sin ground
truth humano, el campo es `UNKNOWN`, nunca cero.

### Rendimiento

Latencia media/p95, FPS del detector, FPS de extremo a extremo, dispositivo,
memoria si está disponible y fallos de pipeline. No llamar “tiempo real” a un
resultado que no sostiene el throughput requerido.

## Criterio de aceptación pre-registrado

Estos son gates de decisión, no resultados ni promesas de producción:

1. **Legal/procedencia:** licencia compatible, checksums, versión y split
   reproducible.
2. **Detección:** en el holdout C, mejora de recall de al menos 10 puntos
   porcentuales frente a V2 y sin caída de precision mayor a 5 puntos; F1 no
   debe empeorar. Si el baseline es demasiado incierto, se reporta el intervalo
   y se aplaza la decisión, no se cambia el umbral post hoc.
3. **Tracking:** fragmentación e ID-switches no aumentan más de 10% relativos
   frente a V2 en los mismos clips, y no hay pérdida sistemática cerca de la
   línea.
4. **Conteo:** solo si existe ground truth humano; el error absoluto y el
   porcentaje deben estar por debajo de la tolerancia operativa acordada antes
   de ver C. Como objetivo de ingeniería inicial se puede pre-registrar ≤5%,
   pero no es una afirmación de exactitud ni un umbral normativo.
5. **Rendimiento:** la mejora no puede requerir una latencia que impida el
   throughput del despliegue; documentar el trade-off si se cambia a YOLO11s o
   mayor resolución.
6. **Arquitectura:** V3 sigue cargando por `PigDetectorConfiguration` y la
   cadena existente Detector → ByteTrack → Crossing → Counter; sin segundo
   contador, cámara, worker o persistencia.

Si falla cualquiera de los gates, la decisión es **NO-GO** o “datos
insuficientes”, no una oportunidad para redefinir el holdout.

## Qué resolvería cada dataset

- **PigDetect High-IoU:** recall de animales parcialmente solapados y densidad
  alta; limita: cámara/finca distinta y licencia no resuelta.
- **PigLife:** diversidad de etapas, postura, oclusión y ambiente; limita:
  licencia propietaria, metadatos por subdataset y shift productivo.
- **PigTracking:** fragmentación, ID switches y continuidad de tracks; limita:
  volumen, licencia y que boxes de MOT no son crossing truth.
- **Edinburgh:** evaluación temporal con IDs persistentes y RGB-D; limita:
  cámara cenital, un corral, día y solo ocho animales usuales.
- **OinkTrack:** día/noche, transiciones, oclusión prolongada y apariencia
  similar; limita: acceso externo, licencia no declarada y densidad superior a
  un pasillo.

## Requisitos para autorizar V3

Antes de cualquier descarga o entrenamiento, el usuario/proyecto debe aprobar:

1. dataset exacto y versión (no “cualquier PigLife/PigDetect”);
2. términos de uso y posibilidad de crear labels/weights derivados;
3. cantidad máxima de almacenamiento y ubicación local ignorada;
4. una fuente nueva de holdout y su autorización explícita;
5. número de frames adicionales a anotar y responsable de la revisión humana;
6. matriz E1–E3 y criterio de éxito anterior a mirar C;
7. política de retención y eliminación de los medios;
8. si el objetivo es solo investigación o también una futura revisión
   comercial.

## Decisión actual

**NO-GO para entrenar V3 ahora.** La investigación sí está lista para un
primer piloto documental con PigDetect High-IoU, pero faltan la autorización de
licencia, el inventario de una muestra, el holdout nuevo y el acuerdo de
criterios. El siguiente paso autorizado debe ser una auditoría de metadatos y
licencia de una fuente concreta; no una descarga masiva.
