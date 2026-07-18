# Remote Control + detección de presencia (Windows)

Guía para usar **Remote Control** de Claude Code (controlar una sesión local desde
el móvil o el navegador) y para que las **notificaciones push** solo lleguen al
teléfono cuando **no** estás delante del portátil.

> Remote Control ejecuta la sesión en **tu máquina** (no en la nube). El móvil o el
> navegador son solo una ventana a esa sesión local. Requiere plan Pro/Max/Team/
> Enterprise y login con cuenta de claude.ai (no API key).

## 1. Activar Remote Control

Dentro de una sesión de Claude Code en el terminal:

```text
/login            # elegir la opción claude.ai (no API key)
/remote-control   # (alias: /rc) arranca Remote Control conservando el historial
```

Para dejarlo **activo por defecto** en toda sesión interactiva:

```text
/config
# Enable Remote Control for all sessions = true
```

Para las push al móvil, en `/config` activar además:

- **Push when Claude decides** (avisos proactivos)
- **Push when actions required** (permisos y preguntas)

Instalar la app de Claude ([iOS](https://apps.apple.com/us/app/claude-by-anthropic/id6473753684) /
[Android](https://play.google.com/store/apps/details?id=com.anthropic.claude)) e
iniciar sesión con la misma cuenta. Si `/config` muestra *"No mobile registered"*,
abre la app una vez para que refresque su token.

## 2. Detección de presencia

Claude Code **silencia las push mientras existe** el fichero apuntado por la
variable de entorno `CLAUDE_CLIENT_PRESENCE_FILE` (requiere Claude Code
**v2.1.181+**). La estrategia:

- Pantalla **desbloqueada** → el fichero **existe** → estás presente → push silenciadas
- Pantalla **bloqueada** → el fichero **no existe** → no estás → push llegan al móvil

### Variable de entorno

Fichero marcador elegido:

```text
C:\Users\USER\.claude\presence.marker
```

Definido de dos formas (ambas necesarias):

1. **Variable de usuario persistente** de Windows — la leen las tareas programadas
   y cualquier `claude` lanzado fuera de PowerShell.
2. En el **perfil de PowerShell**
   `C:\Users\USER\Documents\PowerShell\Microsoft.PowerShell_profile.ps1`:

   ```powershell
   # Claude Code presence marker
   $env:CLAUDE_CLIENT_PRESENCE_FILE = "C:\Users\USER\.claude\presence.marker"
   ```

### Scripts

En `C:\Users\USER\.claude\presence\`:

| Script | Función |
| --- | --- |
| `Set-ClaudePresence.ps1` | Crea el marcador (presente) |
| `Clear-ClaudePresence.ps1` | Borra el marcador (ausente) |
| `Install-ClaudePresenceTasks.ps1` | Registra las tareas en el Programador de tareas |

### Tareas programadas

| Tarea | Disparador | Acción |
| --- | --- | --- |
| `ClaudeCodePresence-Unlock` | Desbloqueo de sesión | Crea el marcador |
| `ClaudeCodePresence-Lock` | Bloqueo de sesión | Borra el marcador |
| `ClaudeCodePresence-Logon` | Inicio de sesión de Windows | Crea el marcador |

## 3. Verificación

```powershell
# 1) Abrir una terminal NUEVA (para que cargue la variable)
# 2) El marcador debe existir estando presente:
Test-Path "$HOME\.claude\presence.marker"   # -> True

# 3) Bloquear con Win+L, luego desbloquear
# 4) Volver a comprobar:
Test-Path "$HOME\.claude\presence.marker"   # -> True (recreado al desbloquear)
```

Durante el bloqueo la tarea *Lock* debe borrarlo; al desbloquear, la tarea
*Unlock* debe recrearlo.

### Notas / casos a probar

- **Sesiones ya abiertas** no cogen la variable: Claude Code la lee al arrancar el
  proceso. Reinicia cualquier `claude` que ya estuviera corriendo.
- **Suspender/hibernar:** al reanudar, Windows suele dejar la sesión bloqueada y
  dispara *Unlock* al volver a entrar → recrea el marcador. Conviene probarlo en
  real con una tarea larga en marcha.
- Remote Control debe estar **activo** (`/rc active` en el footer) para que haya
  push desde el móvil.

## 4. Revertir

```powershell
Unregister-ScheduledTask -TaskName ClaudeCodePresence-Lock   -Confirm:$false
Unregister-ScheduledTask -TaskName ClaudeCodePresence-Unlock -Confirm:$false
Unregister-ScheduledTask -TaskName ClaudeCodePresence-Logon  -Confirm:$false

[Environment]::SetEnvironmentVariable("CLAUDE_CLIENT_PRESENCE_FILE", $null, "User")

Remove-Item -LiteralPath "$HOME\.claude\presence.marker" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$HOME\.claude\presence" -Recurse -Force
```

Y borra del perfil de PowerShell estas líneas:

```powershell
# Claude Code presence marker
$env:CLAUDE_CLIENT_PRESENCE_FILE = "C:\Users\USER\.claude\presence.marker"
```

## Referencias

- [Remote Control](https://code.claude.com/docs/en/remote-control)
- [Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web)
