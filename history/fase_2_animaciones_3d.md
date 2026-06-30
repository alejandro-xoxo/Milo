# Historia: Fase 2 — Mejora de Animaciones 3D (Agujero Negro Realista)

## ¿Qué queríamos hacer?
Transformar el avatar 3D del agujero negro interactivo de MILO en una simulación astrofísica realista,
implementando todas las mejoras especificadas en la guía de desarrollo V2.

## ¿Por qué lo hicimos?
El sistema previo usaba geometrías simples (esferas, anillos de partículas básicos) sin base física real.
La nueva versión mejora dramáticamente el realismo visual, la interactividad y el rendimiento adaptativo.

## ¿Cómo lo hicimos?

### 1. Accretion Disk Realista
- Reemplazamos la esfera aproximada por un `TorusGeometry` toroidal (r=2.8, tube=0.85)
- Textura procedural basada en valor-noise: gradiente radial de densidad (exponencial desde borde interno),
  turbulencia MHD (sin(theta)×cos(r)×noise para simular remolinos), opacidad por intensidad
- Rotación Kepleriana: velocidad ∝ 1/sqrt(r)
- `MeshStandardMaterial` con `emissiveMap` = la textura procedural generada en canvas 512x512

### 2. Photon Ring
- `TorusGeometry(1.5, 0.065, 24, 128)` — radio en 1.5× radio de Schwarzschild
- Material emisivo blanco, opacidad variable según estado
- Flicker rápido (18 Hz) en estado `processing` para simular radiación Hawking
- Reactivo al volumen de audio en estado `speaking`

### 3. Relativistic Jets
- 600 partículas en dos streams helicoidales (norte/sur) usando `cos(helixAngle+theta)*coneRadius`
- Twist helicoidal parametrizado: `twistAmp = 0.22 (processing) vs 0.04 (idle)`
- Flujo de partículas continuo — respawn al salir de límites
- Visibles solo en `processing` (opacity=0.85), hidden en otros estados

### 4. Event Horizon Shader
- `ShaderMaterial` custom con vertex shader de rotación leve y Hawking-expand
- Fragment shader de absorción: negro puro con glow sutil en bordes (frame-dragging visual)
- Uniform `hawkingExpand` escala la esfera levemente cuando MILO habla

### 5. Lensing Post-Processing
- `ShaderPass` adicional en el `EffectComposer`
- UV displacement basado en distancia al centro de pantalla: `displacement / (1 + dist²×8)`
- Animado con `sin(time*0.4)` para ondulación sutil
- Audio-reactivo: `uAudioStrength` se actualiza con `avgVol/256*0.05` en estado speaking
- FPS monitor lo desactiva automáticamente si FPS < 45

### 6. Interactividad Mejorada
- **Raycasting clickeable**: horizon (easter egg burst), disk (tooltip velocidad orbital), jets (toggle visibility)
- **Tooltip animado** con glassmorphism (HTML div overlay)
- **Drag & Rotate** con `PointerEvent` API e inercia decaying (decay=0.91)
- **Zoom reactivo por estado**: idle=12, processing=8, speaking=10, listening=11
- **Pinch-to-zoom táctil** para tablets/móviles
- **Cursor feedback**: `pointer` sobre objetos clickeables

### 7. Performance
- `THREE.DynamicDrawUsage` en buffers de partículas
- FPS monitor adaptativo: reduce bloom y desactiva lensing si FPS < 45
- Partículas: 3000 ring + 800 halo + 600 jets = 4400 total (manejable)
- `Math.min(clock.getDelta(), 0.05)` para cap de delta-time

## ¿Para qué sirve?
El resultado es un avatar 3D cinematográfico que reacciona de forma diferente en cada estado:
- **Idle**: órbita Kepleriana suave, lensing sutil, mouse dodge
- **Processing**: vórtice agresivo, jets helicoidales, zoom in, lensing fuerte
- **Speaking**: ondas de audio en disco y halo, shockwaves, Hawking expand
- **Listening**: pulsación reactiva a voz, zoom medio
- **Error**: caos/jitter de partículas, shake de posición

## Archivos modificados
- `src/frontend/index.html` — reescritura completa del bloque Three.js (líneas 590-1374)

## Fecha
2026-06-30
