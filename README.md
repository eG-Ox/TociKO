# Aprende de mis partidas

Prototipo local para Windows: registra demostraciones de teclado y mouse de Roblox, entrena una red pequeña por imitación y muestra sus predicciones sobre una imagen. Todavía no juega automáticamente ni garantiza supervivencia. No necesita tu contraseña de Roblox.

## Instalación

Instala Python 3.11 o 3.12 de https://www.python.org/downloads/windows/ y abre PowerShell en esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Grabar

```powershell
.\.venv\Scripts\python.exe bot.py record
```

Abre Roblox y pulsa **F8** para iniciar o pausar; **F9** termina. Empieza pausado y solo captura mientras el título de la ventana activa contiene Roblox. Guarda imágenes del monitor principal completo a 10 FPS y únicamente las acciones W/A/S/D, espacio, Shift, E, R, 1/2/3 y botones izquierdo/derecho. También registra desplazamiento del cursor y rueda; la rueda se conserva para futuras versiones, no se entrena todavía. Selecciona otro monitor con `--monitor 2`.

El monitor puede incluir otras ventanas o notificaciones: ciérralas antes de grabar. No se graban texto libre, audio ni contraseñas. No hay subidas automáticas. `data/` y `models/` están excluidos de Git. La captura comienza solo al ejecutar el comando y activar F8; no hay servicio en segundo plano.

Haz al menos dos sesiones distintas y termina cada una con F9. Mantén la misma resolución, sensibilidad, cámara y distribución de controles. Incluye movimiento, combate, recarga y escapes. El espacio en disco crece con la duración; comprueba tus capturas antes de grabar mucho tiempo.

## Entrenar y probar

```powershell
.\.venv\Scripts\python.exe bot.py train --epochs 10
.\.venv\Scripts\python.exe bot.py predict data\SESION\00000000.jpg
```

Sustituye SESION por una carpeta creada al grabar. Se reserva al menos una sesión completa para validación, sin mezclar fotogramas vecinos entre entrenamiento y validación. Usa GPU CUDA si PyTorch la detecta y CPU en caso contrario. Guarda el modelo con menor pérdida de validación en `models/policy.pt`.

## Límites y siguiente etapa

Es una base experimental, no un bot ya entrenado. El modelo usa una imagen por decisión y puede imitar errores o quedarse sin actuar si hay muchas muestras inactivas. Las coordenadas del cursor de Windows no equivalen siempre al movimiento relativo de cámara con el cursor bloqueado: hay que comprobar y mejorar esa captura antes de implementar control autónomo. Las teclas o acciones no listadas no se aprenden. La pérdida de validación no demuestra habilidad ni tiempo de supervivencia.

La ejecución automática dentro de Roblox queda para una siguiente etapa, tras verificar la captura, las predicciones y las reglas aplicables al juego. No incluye inyección, lectura de memoria, modificación del cliente ni evasión de sistemas antitrampas.

Referencias: [pynput](https://pynput.readthedocs.io/en/latest/) y [PyTorch](https://docs.pytorch.org/tutorials/beginner/basics/quickstart_tutorial.html).
