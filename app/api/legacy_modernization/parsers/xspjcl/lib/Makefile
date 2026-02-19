# KMS XSP JCL C Parser Wrapper - Makefile
#
# OF7 xspjcl C 파서를 래핑하는 공유 라이브러리 빌드.
# 모든 파서 기능 (43 stmt, params, relex, instream, macro, stream, errors) 포함.
#
# 사용법:
#   make                    # 기본 빌드
#   make OF7_HOME=/opt/of7  # OF7 경로 지정
#   make clean              # 정리
#   make install            # lib/ 디렉토리에 설치

# OF7 설치 경로 (환경변수 또는 기본값)
OF7_HOME ?= /opt/tmaxapp/OpenFrame

CC       = gcc
CFLAGS   = -fPIC -Wall -O2
LDFLAGS  = -shared

# OF7 헤더 및 라이브러리
OF7_INC  = -I$(OF7_HOME)/base/include -I$(OF7_HOME)/core/include
OF7_LIB  = -L$(OF7_HOME)/lib -lxspjcl -lxspmac -ljclcom -lams -lofcom

# 소스 및 타겟
SRC      = kms_xspjcl_wrapper.c
OBJ      = $(SRC:.c=.o)
TARGET   = libxspjcl_kms.so

.PHONY: all clean install check

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(LDFLAGS) -o $@ $^ $(OF7_LIB)
	@echo "Built: $(TARGET)"

%.o: %.c
	$(CC) $(CFLAGS) $(OF7_INC) -c -o $@ $<

clean:
	rm -f $(OBJ) $(TARGET)

install: $(TARGET)
	cp $(TARGET) .
	@echo "Installed: $(TARGET) -> lib/"

check:
	@echo "OF7_HOME = $(OF7_HOME)"
	@test -d "$(OF7_HOME)/base/include" && echo "Headers: OK" || echo "Headers: NOT FOUND"
	@test -f "$(OF7_HOME)/lib/libxspjcl.so" && echo "libxspjcl: OK" || echo "libxspjcl: NOT FOUND"
	@test -f "$(OF7_HOME)/lib/libxspmac.so" && echo "libxspmac: OK" || echo "libxspmac: NOT FOUND"
	@test -f "$(OF7_HOME)/lib/libjclcom.so" && echo "libjclcom: OK" || echo "libjclcom: NOT FOUND"
