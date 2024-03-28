#!/usr/bin/env bash

if [[ ! -z $CONDA_PREFIX ]]; then
  (>&2 echo -e "\033[1;31mERROR: Please deactivate your conda environment before using this script. Use 'conda deactivate'.\033[0m") && exit 1
fi

OPT_DIR="./opt"
CONDA_DIR="$OPT_DIR/conda"

ARCH="$(uname -m)"

case "$ARCH" in
  x86_64)
    CONDA_ARCH="x86_64"
    CONDA_PKG_EXT="64"
    ;;
  aarch64)
    CONDA_ARCH="aarch64"
    CONDA_PKG_EXT="aarch64"
    ;;
  arm64)
    CONDA_ARCH="arm64"
    CONDA_PKG_EXT="arm64"
    ;;
  *)
    (>&2 echo -e "\033[1;31mERROR: Unknown architecture.\033[0m") && exit 1
esac

echo "CONDA_ARCH=$CONDA_ARCH"
echo "CONDA_PKG_EXT=$CONDA_PKG_EXT"

KERNEL="$(uname -s)"

case "$KERNEL" in
  Linux*)
    CONDA_OS="Linux"
    ;;
  Darwin*)
    CONDA_OS="MacOSX"
    ;;
  *)
    (>&2 echo -e "\033[1;31mERROR: Unknown kernel.\033[0m") && exit 1
    ;;
esac

echo "CONDA_OS=$CONDA_OS"

CONDA_INSTALLER="Miniforge3-$CONDA_OS-$CONDA_ARCH.sh"

echo "CONDA_INSTALLER=$CONDA_INSTALLER"

mkdir -p "$OPT_DIR"

if [[ ! -f "$OPT_DIR/$CONDA_INSTALLER" ]]; then

  echo -e "\033[1;34mDownload installer...\033[0m"

  MINIFORGE_URL="${MINIFORGE_URL:-https://github.com/conda-forge/miniforge/releases/latest/download}"
  CONDA_DOWNLOAD_URL="$MINIFORGE_URL/$CONDA_INSTALLER"

  curl $CURL_PARAMS \
    --location \
    --output "$OPT_DIR/$CONDA_INSTALLER" \
    "$CONDA_DOWNLOAD_URL"

else

  echo -e "\033[1;34mUsing existing installer.\033[0m"

fi

echo -e "\033[1;34mInstall conda...\033[0m"

bash "$OPT_DIR/$CONDA_INSTALLER" -b -p "$CONDA_DIR"

echo -e "\033[1;34mInstall dev activation script...\033[0m"

cat > "$CONDA_DIR/bin/activate_dev" << 'EOF'
#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/activate" "dev" || return $?
EOF

echo -e "\033[1;34mUpdate conda...\033[0m"

# "$CONDA_DIR/bin/mamba" update --name base --channel conda-forge --yes conda

# note! mamba: default timeout seems too short
# reference:
#   https://github.com/mamba-org/mamba/issues/2145
export MAMBA_NO_LOW_SPEED_LIMIT=1

CONDA_ENV="dev"

echo "CONDA_ENV=$CONDA_ENV"

if ! "$CONDA_DIR/bin/conda" env list | grep "^$CONDA_ENV" 2>&1 >/dev/null; then

  echo -e "\033[1;34mCreate '$CONDA_ENV' environment...\033[0m"

  if [[ -n "$ROOT_CERTIFICATE" ]]; then
      echo "conda config for root certificate $ROOT_CERTIFICATE"
      "$CONDA_DIR/bin/conda" config --set ssl_verify "$ROOT_CERTIFICATE"
  fi

  "$CONDA_DIR/bin/conda" create --name "$CONDA_ENV" --yes python=3.11

fi

echo -e "\033[1;34mInstall compiler...\033[0m"

# install compiler
case "$KERNEL" in
  Linux*)
    "$CONDA_DIR/bin/mamba" install --name "$CONDA_ENV" --freeze-installed --yes "gxx_linux-$CONDA_PKG_EXT>=13"
    ;;
  Darwin*)
    "$CONDA_DIR/bin/mamba" install --name "$CONDA_ENV" --freeze-installed --yes "clang_osx-$CONDA_PKG_EXT>=16,<17"
    ;;
esac

echo -e "\033[1;34mInstall toolchain...\033[0m"

"$CONDA_DIR/bin/mamba" install \
  --name "$CONDA_ENV" \
  --freeze-installed \
  --yes \
  'clangdev>=16,<17' \
  'cmake>=3.25' \
  make \
  pkg-config

echo -e "\033[1;34mInstall dependencies...\033[0m"

"$CONDA_DIR/bin/mamba" install \
  --name "$CONDA_ENV" \
  --freeze-installed \
  --yes \
  pybind11

echo -e "\033[1;34mInstall conda activation script...\033[0m"

CONDA_ACTIVATION_DIR="$CONDA_DIR/envs/$CONDA_ENV/etc/conda/activate.d"

mkdir -p "$CONDA_ACTIVATION_DIR"

CONDA_ACTIVATION_SCRIPT="$CONDA_ACTIVATION_DIR/phx.sh"

# note! copying CPPFLAGS to CXXFLAGS because cmake doesn't use CPPFLAGS

if [[ "$KERNEL" =~ .*Linux.* ]]; then
  case "$TARGET" in
    release)
      cat > "$CONDA_ACTIVATION_SCRIPT" << 'EOF'
CFLAGS="${CFLAGS/-march=nocona/-march=broadwell}"
CFLAGS="${CFLAGS/-mtune=haswell/-mtune=broadwell}"
CXXFLAGS="${CXXFLAGS/-march=nocona/-march=broadwell}"
CXXFLAGS="${CXXFLAGS/-mtune=haswell/-mtune=broadwell}"
export PREFIX="$CONDA_PREFIX"
export CFLAGS="$CFLAGS -O3"
export CPPFLAGS="$CPPFLAGS -Wall -Wextra -Wno-overloaded-virtual -O3"
export CXXFLAGS="$CXXFLAGS $CPPFLAGS"
export LDFLAGS="$LDFLAGS -L$PREFIX/lib"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export ROQ_BUILD_TYPE="Release"
EOF
      ;;
    debug)
      cat > "$CONDA_ACTIVATION_SCRIPT" << 'EOF'
export PREFIX="$CONDA_PREFIX"
export CFLAGS="$DEBUG_CFLAGS -fsanitize=address"
export CPPFLAGS="$DEBUG_CPPFLAGS -fsanitize=address -Wall -Wextra -Wno-overloaded-virtual"
export CXXFLAGS="$DEBUG_CXXFLAGS $CPPFLAGS"
export LDFLAGS="$LDFLAGS -L$PREFIX/lib"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export ROQ_BUILD_TYPE="Debug"
export ASAN_OPTIONS="strict_string_checks=1:detect_stack_use_after_return=1:check_initialization_order=1:strict_init_order=1:detect_leaks=1"
EOF
      ;;
  esac
fi

# note! -Wno-deprecated-builtins due to abseil-cpp and clang 15
if [[ "$KERNEL" =~ .*Darwin.* ]]; then
  case "$TARGET" in
    release)
      cat > "$CONDA_ACTIVATION_SCRIPT" << 'EOF'
export PREFIX="$CONDA_PREFIX"
export CFLAGS="$CFLAGS"
export CPPFLAGS="$CPPFLAGS -Wall -Wextra -Wno-deprecated-builtins -DFMT_USE_NONTYPE_TEMPLATE_ARGS=1"
export CXXFLAGS="$CXXFLAGS $CPPFLAGS"
export LDFLAGS="$LDFLAGS -L$PREFIX/lib"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export ROQ_BUILD_TYPE="Release"
EOF
      ;;
    debug)
      cat > "$CONDA_ACTIVATION_SCRIPT" << 'EOF'
export PREFIX="$CONDA_PREFIX"
export CFLAGS="$DEBUG_CFLAGS"
export CPPFLAGS="$DEBUG_CPPFLAGS -Wall -Wextra -Wno-deprecated-builtins -DFMT_USE_NONTYPE_TEMPLATE_ARGS=1"
export CXXFLAGS="$DEBUG_CXXFLAGS $CPPFLAGS"
export LDFLAGS="$LDFLAGS -L$PREFIX/lib"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export ROQ_BUILD_TYPE="Debug"
export ASAN_OPTIONS="strict_string_checks=1:detect_stack_use_after_return=1:check_initialization_order=1:strict_init_order=1:detect_leaks=1"
EOF
      ;;
  esac
fi

echo -e "\033[1;34mReady!\033[0m"
echo -e "\033[1;34mYou can now activate your conda environment using 'source $CONDA_DIR/bin/activate $CONDA_ENV'.\033[0m"