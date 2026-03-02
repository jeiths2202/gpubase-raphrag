#!/bin/bash
# KMS XSP JCL C Parser Wrapper - Build Script
#
# OF7 xspjcl C 파서 래퍼 공유 라이브러리 빌드.
# 모든 파서 기능 포함 (43 stmt, params, relex, instream, macro, stream, errors).
#
# 사용법:
#   ./build.sh                      # 기본 빌드
#   OF7_HOME=/opt/of7 ./build.sh    # OF7 경로 지정
#   ./build.sh clean                # 정리

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

OF7_HOME="${OF7_HOME:-/opt/tmaxapp/OpenFrame}"

echo "=== KMS XSP JCL C Parser Wrapper Build ==="
echo "OF7_HOME: $OF7_HOME"
echo ""

# 환경 확인
check_env() {
    local ok=1
    echo "Checking build environment..."

    if [ ! -d "$OF7_HOME/base/include" ]; then
        echo "  [FAIL] OF7 headers not found: $OF7_HOME/base/include"
        ok=0
    else
        echo "  [OK]   OF7 headers: $OF7_HOME/base/include"
    fi

    for lib in xspjcl xspmac jclcom; do
        if [ -f "$OF7_HOME/lib/lib${lib}.so" ]; then
            echo "  [OK]   lib${lib}.so found"
        else
            echo "  [WARN] lib${lib}.so not found (may be static)"
        fi
    done

    if ! command -v gcc &>/dev/null; then
        echo "  [FAIL] gcc not found"
        ok=0
    else
        echo "  [OK]   gcc: $(gcc --version | head -1)"
    fi

    echo ""
    return $ok
}

build() {
    echo "Building libxspjcl_kms.so..."
    make OF7_HOME="$OF7_HOME" all
    echo ""
    echo "=== Build Complete ==="
    ls -la libxspjcl_kms.so
}

clean() {
    echo "Cleaning..."
    make clean
    echo "Done."
}

case "${1:-build}" in
    clean)
        clean
        ;;
    check)
        check_env
        ;;
    build|*)
        if check_env; then
            build
        else
            echo "Build environment check failed. Fix issues above."
            exit 1
        fi
        ;;
esac
