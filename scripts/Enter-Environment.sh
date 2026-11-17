# Source with: source scripts/Enter-Environment.sh
# This shell only; never changes shell startup files or the global PATH.
WII_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export DEVKITPRO="$WII_PROJECT_ROOT/tools/linux/devkitpro-root/opt/devkitpro"
export DEVKITPPC="$DEVKITPRO/devkitPPC"
export PATH="$WII_PROJECT_ROOT/.venv-linux/bin:$DEVKITPPC/bin:$DEVKITPRO/tools/bin:$PATH"
printf '%s\n' 'Linux project environment loaded for this shell only.'
