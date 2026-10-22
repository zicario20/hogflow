# Panorama de datasets porcinos para HogFlow

**Fecha de revisión:** 2026-10-22
**Alcance:** investigación documental; no se descargaron datasets, no se
inspeccionó Video C y no se modificó el detector V2.

## Lectura correcta de esta investigación

Esta revisión separa tres niveles:

- **Hecho verificado:** aparece en la página institucional, publicación,
  repositorio oficial o metadato del registro enlazado.
- **Inferencia técnica:** conclusión de compatibilidad con HogFlow derivada del
  formato, la cámara o las anotaciones publicadas; debe comprobarse con una
  muestra autorizada.
- **Pendiente de autorización:** licencia, acceso o detalle técnico que no debe
  suponerse por el hecho de que un enlace sea público.

El V2 congelado sigue siendo `hogflow_pig_demo_v2`, clase `pig`/ID `0`,
YOLO11n, `imgsz=640`, confianza `0.25`, IoU NMS `0.50`, `max_det=300`, sin
half precision, SHA-256
`892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c`.
Su estado continúa siendo **DEMO MODEL — NOT PRODUCTION VALIDATED**.

## Resumen ejecutivo

Los tres candidatos prioritarios son:

1. **PigDetect High-IoU** para el primer experimento de detección. Publica
   etiquetas YOLO/COCO y máscaras, separa días de adquisición y construye una
   variante dirigida a alta densidad. Es el menor cambio de integración, aunque
   su licencia no está declarada en la ficha de Zenodo y su cámara no es el
   pasillo HogFlow.
2. **PigLife** para ampliar variabilidad de fases productivas, postura,
   oclusión, ambiente y cámara. Es conceptualmente valioso para la caída de
   generalización A→B, pero el portal y la datasheet describen datos
   propietarios de University of Illinois y exigen aceptar términos; no se
   puede tratar como dataset comercialmente reutilizable sin revisión legal.
3. **PigTracking** (complementado por Edinburgh u OinkTrack) para evaluar la
   continuidad temporal, fragmentación e ID switches. No debe mezclarse
   automáticamente en el entrenamiento de un detector: su valor principal es
   el benchmark MOT y la evaluación del seguimiento.

## Matriz comparativa

| Dataset / fuente oficial | Institución / autores | Tamaño y contenido verificado | Anotaciones | Cámara, densidad e iluminación | Compatibilidad con HogFlow | Detección | Tracking | Conteo direccional | Licencia / acceso | Recomendación |
|---|---|---|---|---|---|---|---|---|---|---|
| [PigDetect](https://zenodo.org/records/18155376) | UWE Bristol y Scotland's Rural College; Bernotas, Hansen, Smith, Jack, Baxter y D'Eath | Dos subconjuntos de **4.320 imágenes etiquetadas**. El test usa 280 frames de 14 días; train/val 4.040 frames de 202 días. La ficha lista 22 GB de archivos; los ZIP Random/High-IoU son ~10,4/10,5 GB y los paquetes YOLOv8 ~260/283 MB. | YOLO (`class_id x_center y_center width height`), COCO y máscaras de instancia por split. High-IoU selecciona escenas densas mediante IoU medio y elimina vecinos `N=5`. | RGB; múltiples días, grupos, edades y tamaños de corral. La alta densidad es explícita; no es una cámara de pasillo ni se publica una matriz de iluminación JBS. | YOLO directo después de verificar clase, nombres y checksums. Requiere manifest HogFlow y split por día; máscaras son opcionales. | **Alta** para un experimento de cajas y oclusión; útil para contrastar `imgsz`/densidad. | Baja directa: no es una secuencia MOT; usar solo para detector. | Baja: no hay una línea compartida ni eventos de cruce. | Zenodo muestra el registro abierto pero deja el campo **License** vacío; la licencia efectiva debe verificarse con los autores antes de uso derivado o comercial. | **Alta** como primer piloto técnico, condicionada a licencia. |
| [PigLife](https://data.aifarms.org/view/piglife) / [ODSR Illinois](https://odsr.illinois.edu/piglife/) | AIFARMS / University of Illinois; Jiangong Li y Angela Green-Miller | Portal: **38 clips, 2.000 frames y 22.000 instancias**, 16,2 GiB. Cubre breeding, gestation, farrow, wean, nursery, growth y finish. | El portal anuncia identificación de objetos, bounding boxes, segmentación, postura/comportamiento, oclusión, variación animal, diversidad ambiental, vídeo e imágenes. | Varias fases y sistemas productivos; densidad y cámara dependen del subdataset. No equivale a la vista fija de los vídeos A/B. | Requiere parser/normalizador propio y conservar procedencia. Boxes pueden alimentar YOLO; máscaras/posturas/oclusión deben permanecer como metadata auxiliar. | **Alta** para diversidad y oclusión, si la licencia permite el uso previsto. | Media: el portal anuncia vídeo y seguimiento como objetivo, pero el formato temporal exacto debe auditarse. | Baja/media: hace falta derivar trayectorias y una línea artificial; no aporta ground truth de cruce HogFlow. | La datasheet indica que los datos son propietarios de Illinois, sujetos a licencia, confidencialidad y posibles controles de exportación. | **Alta** para una segunda fuente, no para descargar sin autorización. |
| [PigTracking](https://zenodo.org/records/18155637) | UWE Bristol y Scotland's Rural College, mismo ecosistema PigDetect | **Más de 740.000 frames etiquetados**, 216 días, 22 grupos, resoluciones 1/2/5 FPS; archivos publicados ~48,3 GB. | MOT `frame_id, target_id, bb_left, bb_top, bb_width, bb_height`; `gt.txt`, COCO, `mot_labels`, máscaras y baselines. | Vídeo RGB longitudinal; media publicada 7,62 cerdos/frame. Densidad temporal y continuidad son el foco. | Requiere adaptador MOT→`DetectionFrame`/replay; IDs se usan para evaluar tracking, no como identidad biológica de producción. | Media: hay cajas, pero el conjunto está organizado para MOT y sus splits/labels deben auditarse antes de fine-tune. | **Alta** para ByteTrack, fragmentación, ID switches y pérdidas. | Media para un replay sintético con línea; no contiene el pasillo compartido de HogFlow. | La ficha de Zenodo no expone una licencia legible; revisión legal previa obligatoria. | **Alta** para validación de tracking aislada. |
| [Edinburgh Pig Behavior Video Dataset](https://homepages.inf.ed.ac.uk/rbf/PIGDATA/) | University of Edinburgh / SRUC; Bergamini, Pini, Simoni, Vezzani, Calderara, D'Eath y Fisher | 23 días, ~3.429.000 frames, 8 cerdos usuales por frame, 1280×720, 6 FPS, RGB+depth. 12 secuencias con 600 frames cada una: 7.200 frames anotados. `annotated.tar` 3,2 GB; los archivos de vídeo diarios son multi-GB. | Boxes axis-aligned, ID persistente, etiqueta de comportamiento; anotación cada tercer frame con interpolación y JSON por pig. | Cámara casi cenital, un corral de 5,8×1,9 m, solo de día; no es vista lateral de pasillo. | Parser JSON e interpolación temporal; RGB puede alimentar detector, depth no debe entrar en el contrato V2 sin diseño explícito. | Media: excelente control temporal, pero fuerte domain shift geométrico. | **Alta** para continuidad, IDs persistentes, pérdidas y evaluación de asociaciones. | Media/baja: permite crear líneas de replay, pero no representa entradas/salidas de un corredor. | Página institucional pública; las condiciones de redistribución deben confirmarse antes de incorporar datos derivados. | **Alta** para benchmark de tracking, no primer dataset de fine-tune. |
| [OinkTrack](https://github.com/LeoHuang0511/OinkTrack) / [página del proyecto](https://leohuang0511.github.io/oinktrack-page/) | National Taiwan University, NYCU y NTNU; Huang et al. | >5 h anotadas, 16 secuencias, ~36 cerdos/frame, 573.700 boxes y 574 IDs consistentes. Incluye día, noche y transiciones. | `annotation.json`, conversión MOT, cajas por frame e ID; evaluación con TrackEval (MOTA, HOTA, IDF1, etc.). | Granjas comerciales, alta densidad, oclusiones, apariencia similar y cambios día/noche. | MOT→replay y evaluación TrackEval; no sustituye el detector YOLO ni el contador. | Media: útil como fuente auxiliar, pero el dominio puede ser demasiado diferente. | **Alta** para robustez temporal y oclusión persistente. | Media en replay; no hay línea de cruce común. | El README no declara licencia del dataset; la licencia CC BY-SA de la página web no debe interpretarse como licencia de los vídeos. Acceso por Google Drive. | **Media/alta** para tracking después de PigTracking. |
| [AIFARMS Multi-Camera Pig Tracking](https://github.com/AIFARMS/multi-camera-pig-tracking) | AIFARMS / UIUC; implementación oficial CVPR 2021 | El repositorio enlaza un dataset de vídeos de ISRL y un vídeo de despliegue; no publica tamaño total en README. | Bounding boxes, identidades globales, JSON de resultados y homografías. | Múltiples cámaras y corrales grandes; más cercano a transferencia entre cámaras que a un pasillo único. | Solo como benchmark de asociación/homografía; no debe ampliar el runtime de una cámara. | Media/baja para YOLO por falta de inventario público resumido. | Alta para identidad entre cámaras, pero fuera de alcance de HogFlow actual. | Baja: cuatro docks comparten una cámara/carril, no handover multicámara. | El README no declara una licencia de datos; acceso por enlace externo requiere autorización. | Media, investigación futura, no V3 inicial. |
| [FaroPigSeg / FaroPigReID-33](https://github.com/yudong888/FaroPig-Datasets) | University of Barcelona y AGCO; datos de granja comercial | FaroPigSeg: 1.518 imágenes, >16.000 instancias, ~150 MB; FaroPigReID-33 ~12 GB. | El README indica etiquetas YOLO y tareas de segmentación/ReID; el formato exacto de cada split debe auditarse. | Granja de acabado comercial, múltiples corrales; el README no garantiza una vista de corredor. | Boxes/masks requieren comprobar orientación de campos y clase única. ReID está fuera del objetivo de HogFlow. | Media/alta para segmentación y oclusión si se usa solo FaroPigSeg. | Baja/media: ReID no es ByteTrack ground truth. | Baja: no hay cruce direccional. | **Investigación solamente; uso comercial prohibido** según el README. | Media para un experimento no comercial, no para producto. |
| [PigTracker Dataset](https://github.com/linwjscau/PigTracker_MOT-Framework-For-Pig-Farming) | Lin et al.; repositorio oficial del artículo 2026 | Tamaño total no publicado en README. | SV-OBB, orientación cabeza-cola e IDs persistentes; escenarios de densidad, luz y oclusión severa. | Escenas densas; la cámara y número de secuencias requieren acuerdo de acceso. | No es caja YOLO axis-aligned directa; convertir OBB a AABB perdería orientación. | Media para detector, con pérdida de información si se aplana. | Alta como investigación de MOT orientado. | Media/baja para HogFlow actual. | Acuerdo firmado y correo institucional; contraseña. No asumir licencia comercial. | Media, solo si una hipótesis orientada lo justifica. |
| [INPC infrared pig segmentation](https://github.com/HUBUwg96/INPC) | Hubei University; Wang et al., *Infrared Physics & Technology* 2024 | El artículo describe el primer dataset público IR de segmentación de cerdo; no publica en la página un tamaño descargable resumido. | Máscaras de instancia y cajas/segmentación; enlace de datos externo. | Infrarrojo en granja; iluminación y apariencia no son RGB de HogFlow. | Requeriría una rama/modalidad IR y conversión de máscaras; no es compatible con el detector V2 RGB sin experimento separado. | Baja para el objetivo inmediato de cajas RGB. | Baja. | Baja. | Repositorio no declara licencia de datos en su README; enlace Baidu requiere revisión. | Baja para V3 inicial; útil solo para estudiar IR. |

## Fuentes que no deben confundirse con una solución de conteo

Un dataset con boxes, IDs o segmentación no contiene automáticamente ground truth
de cruce por la línea HogFlow. Los conteos del propio detector, tracker o
dataset no sustituyen el conteo humano de cada vídeo. La línea y la dirección
deben definirse en el replay y el error de conteo debe contrastarse con un
worksheet humano independiente.

## Prioridad recomendada

- **Primero:** una muestra pequeña y autorizada de PigDetect High-IoU, porque el
  formato YOLO ya está descrito y la selección de alta densidad ataca el fallo
  de oclusión/crowding observado en B. No implica que PigDetect sea similar a
  JBS.
- **Segundo:** PigLife, después de aceptar y archivar sus términos, para medir
  si diversidad de fases, oclusiones y ambientes mejora la generalización sin
  borrar el peso del dominio local.
- **Tercero:** PigTracking o Edinburgh para una pista de evaluación de tracking;
  OinkTrack es una extensión posterior si se necesita estrés día/noche y largo
  plazo.

## Fuentes y estados legales

Una página pública, un DOI o un repositorio GitHub no equivale a una licencia
comercial. En particular, PigLife declara propiedad/licencia de Illinois; las
fichas Zenodo de PigDetect y PigTracking dejan el campo de licencia sin una
declaración utilizable en la revisión; OinkTrack, AIFARMS Multi-Camera y
PigTracker requieren confirmar términos con sus autores. Ningún dataset debe
entrar a un entrenamiento de HogFlow hasta guardar una copia de los términos,
la versión, el checksum y el permiso para obras derivadas.

## Fuentes oficiales consultadas

- [PigLife portal](https://data.aifarms.org/view/piglife), [datasheet](https://data.aifarms.org/datasheet/piglife) y [ODSR Illinois](https://odsr.illinois.edu/piglife/).
- [PigDetect Zenodo](https://zenodo.org/records/18155376) y su [README de formato](https://zenodo.org/records/18155376/preview/ReadMe-PigDetect.txt).
- [PigTracking Zenodo](https://zenodo.org/records/18155637).
- [Edinburgh Pig Behavior Dataset](https://homepages.inf.ed.ac.uk/rbf/PIGDATA/).
- [OinkTrack](https://github.com/LeoHuang0511/OinkTrack) y [página del proyecto](https://leohuang0511.github.io/oinktrack-page/).
- [AIFARMS Multi-Camera Pig Tracking](https://github.com/AIFARMS/multi-camera-pig-tracking).
- [FaroPig-Datasets](https://github.com/yudong888/FaroPig-Datasets).
- [PigTracker](https://github.com/linwjscau/PigTracker_MOT-Framework-For-Pig-Farming).
- [INPC](https://github.com/HUBUwg96/INPC) y [artículo IR](https://doi.org/10.1016/j.infrared.2024.105491).
