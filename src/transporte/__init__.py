"""Canal de transporte hacia el robot (specs/002, US4).

Vive fuera de ``src/vision/`` a propósito: el pipeline de visión es puro
(interpreta imágenes, sin E/S) y el transporte es el único lugar del proyecto
que habla con hardware. La Constitución §II exige justificar la estructura por
el pipeline, y esta es la frontera real entre ambos.

La abstracción es delgada: el bucle de visión llama ``encolar`` —O(1), sin
E/S— y un hilo aparte drena la cola hacia el medio físico. El bucle nunca
escribe en el puerto, de modo que una desconexión no puede bloquear la
detección (FR-031, Principio IV).

Ningún módulo de aquí se importa desde ``src/vision/``; la inyección va del
CLI hacia adentro.
"""

from __future__ import annotations

from src.transporte.base import Transporte

__all__ = ["Transporte", "base"]
