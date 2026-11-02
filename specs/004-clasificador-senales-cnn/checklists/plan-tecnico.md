# Checklist: Plan técnico — Clasificador CNN de Señales

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

## Autorización y alcance

- [ ] CHK001 El docente autorizó explícitamente el uso de CNN en esta fase.
- [ ] CHK002 La feature está separada del Reto 1 original y no se presenta como parte de él.
- [ ] CHK003 El alcance excluye reentrenamiento con footage del robot y comandos nuevos de velocidad.

## Arquitectura

- [ ] CHK004 `src/vision/` no importa `onnxruntime`, `tensorflow` ni `keras`.
- [ ] CHK005 `src/clasificacion/` es la única frontera de E/S del modelo.
- [ ] CHK006 `src/transporte/` sigue siendo el único paquete con sockets.
- [ ] CHK007 `PipelineVision(params)` sin clasificador mantiene el comportamiento actual.
- [ ] CHK008 El modelo se carga una sola vez por corrida.

## Modelo y exportación

- [ ] CHK009 El artefacto ONNX y la metadata existen en `assets/modelos/`.
- [ ] CHK010 La metadata incluye clases, tamaño, canal, preproceso, escala, hash y paridad.
- [ ] CHK011 La paridad Keras/ONNX es `max|Δ| < 1e-4` y top-1 100 %.
- [ ] CHK012 El runtime rechaza un modelo con hash o tamaño incorrecto.

## Localización y clasificación

- [ ] CHK013 El localizador usa solo HSV, umbralización, morfología y contornos.
- [ ] CHK014 `roi_senales` limita las propuestas.
- [ ] CHK015 Hay supresión por IoU para regiones solapadas.
- [ ] CHK016 La CNN solo se ejecuta si el localizador propone una región; el contexto del fotograma es la entrada, nunca un frame sin compuerta.
- [ ] CHK017 El preproceso coincide con `mobilenet.preprocess_input`.
- [ ] CHK018 Las predicciones bajo el umbral se descartan y no confirman.

## FSM y cadencia

- [ ] CHK019 PARE/SIGA usan el `Detector` y la FSM existentes sin cambiar su semántica.
- [ ] CHK020 PARE envía `x`, mantiene 3.0 s y reanuda en SIGA.
- [ ] CHK021 SIGA espacia `w` 1.0 s; ZONA 2.0 s; VELOCIDAD 0.5 s.
- [ ] CHK022 El primer `w` tras corrección, pérdida o reanudación es inmediato.
- [ ] CHK023 Las correcciones `a`/`d` conservan `fotogramas_por_orden`.
- [ ] CHK024 `DETENER` tiene prioridad absoluta y no se retrasa.
- [ ] CHK025 El modo de marcha persiste hasta otra confirmación.

## Pruebas y rendimiento

- [ ] CHK026 Tests unitarios del localizador con las 4 señales sintéticas.
- [ ] CHK027 Tests unitarios del clasificador con sesión falsa.
- [ ] CHK028 Tests de integración con clasificador falso para las 4 clases.
- [ ] CHK029 Tests de cadencia con `t_s` inyectado.
- [ ] CHK030 La suite existente pasa completa con `--clasificador off`.
- [ ] CHK031 La inferencia ONNX mide ≤ 15 ms por fotograma en el portátil de desarrollo.
- [ ] CHK032 0 PARE falsos sobre los 9 videos sin señales.

## Datos y riesgos

- [ ] CHK033 El riesgo de dominio se registra: dataset de teléfono, sin footage del robot.
- [ ] CHK034 El supuesto de que `w` espaciado modula la velocidad se valida en pista o se documenta como abierto.
- [ ] CHK035 Las métricas nuevas son aditivas y no rompen `metricas.json` existente.
- [ ] CHK036 El visor muestra clase, confianza y modo de marcha.
- [ ] CHK037 AGENTS.md y quickstart reflejan el estado real.
