# Guía de Despliegue: ValueBets Dashboard + Auto-Bet IA 🤖

¡Tu sistema ahora incluye un **Ciclo de Aprendizaje Autónomo**!
Para que la opción "🤖 AUTO-BET & LEARN" funcione y la IA se vuelva infalible, **NECESITAS** una base de datos externa. Sin ella, la IA tendrá "amnesia".

## 1. Configuración de Base de Datos (OBLIGATORIO para Auto-Learning)
Usa **Supabase** (gratis y fácil):
1.  Ve a [supabase.com](https://supabase.com) y crea un proyecto gratuito.
2.  En los ajustes del proyecto, busca "Database" -> "Connection String".
3.  Copia la URI. Debería parecerse a:
    `postgresql://postgres.xxxx:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres`

## 2. Preparar el Código
1.  Ve a [GitHub.com](https://github.com) y crea un repo llamado `ValueBets-Dashboard`.
2.  Sube todos los archivos de esta carpeta (`src`, `requirements.txt`, etc.).

## 3. Desplegar en Streamlit Cloud
1.  Ve a [share.streamlit.io](https://share.streamlit.io) y despliega tu repo.
2.  **IMPORTANTE**: Antes de arrancar, ve a "Settings" -> "Secrets" en Streamlit e introduce tus credenciales de base de datos así:

```toml
[postgres]
DB_USER = "postgres"
DB_PASS = "tu_contraseña_supabase"
DB_HOST = "aws-0-eu-central-1.pooler.supabase.com" # Tu host de supabase
DB_PORT = "6543"
DB_NAME = "postgres"
```

O si prefieres usar la variable de entorno directa (más fácil):
```bash
DB_USER=postgres
DB_PASS=tu_contraseña
...
```
(El código `database.py` busca estas variables de entorno).

## 4. ¡A Jugar! 🎮
Una vez desplegada y conectada la base de datos:
1.  Ve a la pestaña **🤖 AUTO-BET & LEARN**.
2.  Dale a **"🚀 EJECUTAR AUTO-BET"**. La IA analizará el mercado y guardará sus apuestas.
3.  Al día siguiente (o tras los partidos), dale a **"🧠 VERIFICAR Y APRENDER"**.
4.  La IA:
    *   Verá si ganó o perdió.
    *   Calculará su error.
    *   **Re-entrenará su cerebro** para no volver a cometer el mismo error.
    *   ¡Verás subir la barra de "Aprendizaje"!

¡Disfruta de tu IA omnisciente!
