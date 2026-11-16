# TociKO — agente visual para Roblox

Agente experimental para Windows que aprende de tus partidas y después ejecuta sus propias decisiones de teclado y mouse en un bucle de observación y acción. Una red temporal recibe los cuatro fotogramas recientes, elige acciones y actualiza los controles sin que tengas que indicarle cada movimiento.

**Estado real:** el bucle autónomo está implementado; no se distribuye un modelo entrenado. Necesitas grabar demostraciones y entrenar antes de jugar. No tiene inteligencia general, memoria a largo plazo ni una comprensión verificada de zombis, inventario o salud. No se ha demostrado supervivencia en el juego. No aprende de sus propios resultados durante `play`: para mejorar, graba ejemplos nuevos y vuelve a entrenar. No usa claves de API ni tu contraseña de Roblox.

## Preparación

Abre PowerShell en `C:\Users\Ryota\Documents\rbx\bot`:

```powershell
Set-Location C:\Users\Ryota\Documents\rbx\bot
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

El script crea `.venv` si falta, instala dependencias y ejecuta las pruebas. Si no hay un entorno creado, necesita Python 3.11 o 3.12 instalado y agregado a PATH. Descarga Python desde https://www.python.org/downloads/windows/. No cambia la política de ejecución permanente del equipo.

## 1. Enseñarle

```powershell
.\.venv\Scripts\python.exe bot.py record
```

Entra en la partida y suelta **F8** para empezar. F8 pausa y **F9** termina la sesión. Graba al menos dos sesiones distintas. Incluye caminar, girar, evitar zombis, combatir, recargar y escapar. Mantén la misma configuración de cámara, resolución y sensibilidad; usa preferiblemente una ventana de tamaño constante.

Captura únicamente el área cliente de la ventana activa del proceso `RobloxPlayerBeta.exe`, no el monitor entero. Usa Raw Input para registrar movimiento relativo del mouse incluso con el cursor bloqueado. Se registran W/A/S/D, espacio, Shift, E, R, 1/2/3 y botones izquierdo/derecho. La rueda se guarda, pero esta versión no la aprende ni la reproduce. Otros controles tampoco están incluidos.

Las muestras relacionan la imagen al inicio del intervalo con las acciones del intervalo siguiente. Las pausas y cambios de ventana separan la memoria temporal. Al salir de Roblox se pausa y debes volver a activar F8. No registra texto libre ni audio; las imágenes sí pueden contener chat o información visible en el juego.

Graba siempre a la misma frecuencia (10 FPS por defecto). Para cambiarla: `bot.py record --fps 15`. Las sesiones y modelos v1 no son compatibles: esta versión requiere grabaciones nuevas.

## 2. Entrenar

```powershell
.\.venv\Scripts\python.exe bot.py train --epochs 10
```

Reserva sesiones completas para validación; no mezcla fotogramas vecinos entre entrenamiento y validación. Entrena botones y movimiento de cámara, compensa parcialmente acciones poco frecuentes y guarda el mejor modelo en `models/policy.pt`. Muestra pérdida y F1 de acciones; ninguna de estas métricas mide supervivencia.

El modelo usa GPU si la instalación de PyTorch detecta CUDA y CPU en caso contrario. Las cuatro imágenes equivalen a unos 0.3 segundos de historia a 10 FPS; no son memoria persistente. Necesitarás experimentar con cantidad y variedad de datos. Si tarda demasiado, prueba `--batch-size 8` al entrenar. Para GPU, consulta la instalación oficial en https://pytorch.org/get-started/locally/.

## 3. Observar sus decisiones

```powershell
.\.venv\Scripts\python.exe bot.py play
```

Entra en Roblox y pulsa F8. Este comando procesa imágenes y escribe las decisiones en `runs/`, sin enviar controles. F9 termina. Para probar una imagen aislada:

```powershell
.\.venv\Scripts\python.exe bot.py predict data\SESION\00000000.jpg
```

Sustituye SESION por el nombre de una carpeta creada al grabar. En una imagen aislada se repite la misma imagen cuatro veces, por lo que no se evalúa movimiento temporal real.

## 4. Jugar autónomamente

```powershell
.\.venv\Scripts\python.exe bot.py play --execute
```

Entra en la partida, coloca al personaje y pulsa **F8**. A partir de ahí, el modelo observa la pantalla y decide los controles en cada ciclo. **F8 pausa; F9 termina.** Al perder el foco de Roblox o pasar 0.5 segundos sin una decisión válida, el watchdog libera los controles y pausa; reactiva con F8. Ctrl+C también ejecuta la limpieza. Un cierre forzado del proceso o fallo del sistema queda fuera de esa garantía.

El agente evita pulsar direcciones opuestas y seleccionar varias armas a la vez. Limita el movimiento de cámara a 40 unidades relativas por ciclo. Opciones:

```powershell
.\.venv\Scripts\python.exe bot.py play --execute --threshold 0.65 --mouse-scale 0.5
```

Un umbral mayor exige más confianza para pulsar botones; `--mouse-scale` ajusta la cámara y `--mouse-scale 0` la desactiva. El registro de cada decisión contiene probabilidades, acciones, latencia y si se aplicó. No contiene capturas de pantalla. No ejecutes `record` y `play --execute` a la vez: acabarías usando acciones del propio modelo como demostraciones humanas.

No reconoce de manera fiable muerte, menús o chat: pausa manualmente al abrirlos. No reinicia partidas por sí solo. Las entradas de Windows pueden no ser aceptadas por todos los juegos. No incluye modificación del cliente, lectura de memoria ni evasión de sistemas antitrampas. Comprueba que el entorno donde lo uses permita automatización.

## Privacidad y pruebas

Todo se procesa localmente. `data/`, `models/`, `runs/`, `.venv/` y archivos `.env` están excluidos de Git. La grabación solo funciona al ejecutar `record` y activar F8; no hay servicio de inicio automático. Revisa espacio en disco durante sesiones largas.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas cubren entrenamiento con datos sintéticos, separación de sesiones y pausas, carga del modelo, decisiones incompatibles, pausa por foco o datos obsoletos, resultados atrasados, ciclo autónomo con controles simulados y ciclo de vida de Raw Input en Windows. No sustituyen una prueba de habilidad en Roblox. GitHub Actions ejecuta las pruebas en Windows.

Referencias técnicas: [PyTorch](https://docs.pytorch.org/tutorials/beginner/basics/quickstart_tutorial.html), [pynput](https://pynput.readthedocs.io/en/latest/), [MSS](https://python-mss.readthedocs.io/stable/), [Windows SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).
