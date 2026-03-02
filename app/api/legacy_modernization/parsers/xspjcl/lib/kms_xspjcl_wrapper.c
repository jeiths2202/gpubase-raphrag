/**
 * @file    kms_xspjcl_wrapper.c
 * @brief   KMS Python 연동을 위한 OF7 XSP JCL C 파서 래퍼.
 *
 * OF7 xspjcl C 파서의 모든 기능을 JSON으로 직렬화하여 Python ctypes로 전달.
 *
 * 래핑 대상 기능 전체:
 *   - xspmac_parse(): 매크로 확장 + SCF 변수 치환
 *   - xspjcl_parse(): JCL 파싱 (43개 statement 타입)
 *   - jcl_tree 워킹: 계층 AST (JOBG→JOB→stmts)
 *   - 파라미터: P_PARAM/K_PARAM + subparam (VAL_STR/VAL_SUBPARAMS/VAL_DATA/VAL_RELEX)
 *   - Instream 데이터: p_data_t (FD *, FDDS~FDDE, DATA~END)
 *   - Relational expression: relex_t 트리 (SW/IF 조건식)
 *   - Line range: !!RANGE!! → first_line, last_line
 *   - Stream: 원본 소스 라인 + 에러 주석
 *   - 21개 에러 타입 감지 + 설명
 *   - SYSIN 파일 포함
 *
 * 빌드:
 *   gcc -shared -fPIC -o libxspjcl_kms.so kms_xspjcl_wrapper.c \
 *       -I$(OF7_HOME)/base/include -L$(OF7_HOME)/lib \
 *       -lxspjcl -lxspmac -ljclcom -lams -lofcom
 *
 * @author  KMS Team
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "jclcom.h"
#include "xspjcl.h"
#include "xspmac.h"

/* ──────────────────── JSON 버퍼 관리 ──────────────────── */

#define JSON_BUF_INIT_SIZE  (64 * 1024)  /* 64KB initial */
#define JSON_BUF_GROW_SIZE  (32 * 1024)  /* 32KB growth */

typedef struct {
    char *buf;
    int   size;
    int   pos;
} json_buf_t;

static json_buf_t g_result = {NULL, 0, 0};

static void jbuf_init(json_buf_t *jb)
{
    if (jb->buf) {
        free(jb->buf);
    }
    jb->size = JSON_BUF_INIT_SIZE;
    jb->buf = (char *)malloc(jb->size);
    jb->pos = 0;
    if (jb->buf) jb->buf[0] = '\0';
}

static void jbuf_ensure(json_buf_t *jb, int need)
{
    while (jb->pos + need >= jb->size) {
        jb->size += JSON_BUF_GROW_SIZE;
        jb->buf = (char *)realloc(jb->buf, jb->size);
    }
}

static void jbuf_append(json_buf_t *jb, const char *s)
{
    int len = strlen(s);
    jbuf_ensure(jb, len + 1);
    memcpy(jb->buf + jb->pos, s, len);
    jb->pos += len;
    jb->buf[jb->pos] = '\0';
}

static void jbuf_appendf(json_buf_t *jb, const char *fmt, ...)
{
    char tmp[4096];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(tmp, sizeof(tmp), fmt, ap);
    va_end(ap);
    jbuf_append(jb, tmp);
}

/* JSON 문자열 이스케이프 */
static void jbuf_append_escaped(json_buf_t *jb, const char *s)
{
    if (!s) {
        jbuf_append(jb, "null");
        return;
    }
    jbuf_append(jb, "\"");
    while (*s) {
        switch (*s) {
        case '"':  jbuf_append(jb, "\\\""); break;
        case '\\': jbuf_append(jb, "\\\\"); break;
        case '\n': jbuf_append(jb, "\\n"); break;
        case '\r': jbuf_append(jb, "\\r"); break;
        case '\t': jbuf_append(jb, "\\t"); break;
        case '\b': jbuf_append(jb, "\\b"); break;
        case '\f': jbuf_append(jb, "\\f"); break;
        default:
            if ((unsigned char)*s < 0x20) {
                jbuf_appendf(jb, "\\u%04x", (unsigned char)*s);
            } else {
                jbuf_ensure(jb, 2);
                jb->buf[jb->pos++] = *s;
                jb->buf[jb->pos] = '\0';
            }
            break;
        }
        s++;
    }
    jbuf_append(jb, "\"");
}

/* ──────────────────── Statement 타입 이름 매핑 ──────────────────── */

static const char *stmt_type_name(int type)
{
    switch (type) {
    case STMT_NULL:     return "STMT_NULL";
    case STMT_JOBG:     return "STMT_JOBG";
    case STMT_CODE:     return "STMT_CODE";
    case STMT_JOB:      return "STMT_JOB";
    case STMT_EX:       return "STMT_EX";
    case STMT_PARA:     return "STMT_PARA";
    case STMT_FD:       return "STMT_FD";
    case STMT_SW:       return "STMT_SW";
    case STMT_PAUSE:    return "STMT_PAUSE";
    case STMT_MSG:      return "STMT_MSG";
    case STMT_NOTE:     return "STMT_NOTE";
    case STMT_JEND:     return "STMT_JEND";
    case STMT_JGEND:    return "STMT_JGEND";
    case STMT_FIN:      return "STMT_FIN";
    case STMT_SYSIN:    return "STMT_SYSIN";
    case STMT_EX_MACRO: return "STMT_EX_MACRO";
    case STMT_CHAM:     return "STMT_CHAM";
    case STMT_MACRO:    return "STMT_MACRO";
    case STMT_MEND:     return "STMT_MEND";
    case STMT_FDR:      return "STMT_FDR";
    case STMT_FDDS:     return "STMT_FDDS";
    case STMT_FDDE:     return "STMT_FDDE";
    case STMT_STACK:    return "STMT_STACK";
    case STMT_CAT:      return "STMT_CAT";
    case STMT_UNCAT:    return "STMT_UNCAT";
    case STMT_DATA:     return "STMT_DATA";
    case STMT_END:      return "STMT_END";
    case STMT_SCAN:     return "STMT_SCAN";
    case STMT_SCEND:    return "STMT_SCEND";
    case STMT_USER:     return "STMT_USER";
    case STMT_UEND:     return "STMT_UEND";
    case STMT_NOP:      return "STMT_NOP";
    case STMT_COMMAND:  return "STMT_COMMAND";
    case STMT_ERROR:    return "STMT_ERROR";
    case MSTMT_DEFINE:  return "MSTMT_DEFINE";
    case MSTMT_SKIP:    return "MSTMT_SKIP";
    case MSTMT_IF:      return "MSTMT_IF";
    case MSTMT_IFN:     return "MSTMT_IFN";
    case MSTMT_SET:     return "MSTMT_SET";
    case MSTMT_MSG:     return "MSTMT_MSG";
    case MSTMT_WTO:     return "MSTMT_WTO";
    case MSTMT_WTOR:    return "MSTMT_WTOR";
    case MSTMT_NOP:     return "MSTMT_NOP";
    case MSTMT_DEXIT:   return "MSTMT_DEXIT";
    case MSTMT_DEFEND:  return "MSTMT_DEFEND";
    case STMT_OTHER:    return "STMT_OTHER";
    default:            return "STMT_UNKNOWN";
    }
}

/* ──────────────────── Relex 직렬화 ──────────────────── */

static const char *relex_comp_op_name(int type)
{
    switch (type) {
    case RELEX_COMP_GT: return "GT";
    case RELEX_COMP_LT: return "LT";
    case RELEX_COMP_NG: return "NG";
    case RELEX_COMP_NL: return "NL";
    case RELEX_COMP_EQ: return "EQ";
    case RELEX_COMP_NE: return "NE";
    case RELEX_COMP_GE: return "GE";
    case RELEX_COMP_LE: return "LE";
    default:            return "UNKNOWN";
    }
}

static const char *relex_logic_op_name(int type)
{
    switch (type) {
    case RELEX_LOGIC_NOT: return "NOT";
    case RELEX_LOGIC_AND: return "AND";
    case RELEX_LOGIC_OR:  return "OR";
    default:              return "UNKNOWN";
    }
}

/* Forward declaration */
static void serialize_relex(json_buf_t *jb, relex_t *rx);

static void serialize_relex_key(json_buf_t *jb, relex_key_t *key)
{
    if (!key) { jbuf_append(jb, "null"); return; }
    jbuf_append(jb, "{\"name\":");
    jbuf_append_escaped(jb, key->name);
    jbuf_appendf(jb, ",\"value\":%d}", key->value);
}

static void serialize_relex(json_buf_t *jb, relex_t *rx)
{
    if (!rx) { jbuf_append(jb, "null"); return; }

    jbuf_append(jb, "{");

    switch (rx->type) {
    case RELEX_KEY:
    case RELEX_KEY_SW:
        jbuf_appendf(jb, "\"type\":\"%s\",\"key\":",
                      rx->type == RELEX_KEY ? "RELEX_KEY" : "RELEX_KEY_SW");
        serialize_relex_key(jb, (relex_key_t *)rx->node);
        break;

    case RELEX_COMP: {
        relex_comp_t *comp = (relex_comp_t *)rx->node;
        jbuf_appendf(jb, "\"type\":\"RELEX_COMP\",\"comp\":{\"operator\":\"%s\",\"operands\":[",
                      relex_comp_op_name(comp->type));
        serialize_relex_key(jb, comp->operand[0]);
        jbuf_append(jb, ",");
        serialize_relex_key(jb, comp->operand[1]);
        jbuf_append(jb, "]}");
        break;
    }

    case RELEX_LOGIC: {
        relex_logic_t *logic = (relex_logic_t *)rx->node;
        jbuf_appendf(jb, "\"type\":\"RELEX_LOGIC\",\"logic\":{\"operator\":\"%s\",\"operands\":[",
                      relex_logic_op_name(logic->type));
        serialize_relex(jb, logic->operand[0]);
        jbuf_append(jb, ",");
        serialize_relex(jb, logic->operand[1]);
        jbuf_append(jb, "]}");
        break;
    }

    default:
        jbuf_append(jb, "\"type\":\"UNKNOWN\"");
        break;
    }

    jbuf_append(jb, "}");
}

/* ──────────────────── 파라미터 직렬화 ──────────────────── */

static void serialize_subparam(json_buf_t *jb, jclcom_subparam_t *sp);
static void serialize_param_list(json_buf_t *jb, jclcom_param_t *param_list);

static void serialize_subparam(json_buf_t *jb, jclcom_subparam_t *sp)
{
    if (!sp) { jbuf_append(jb, "null"); return; }

    jbuf_append(jb, "{");

    switch (sp->type) {
    case VAL_NULL:
        jbuf_append(jb, "\"val_type\":\"VAL_NULL\"");
        break;

    case VAL_STR:
        jbuf_append(jb, "\"val_type\":\"VAL_STR\",\"str_val\":");
        jbuf_append_escaped(jb, sp->val.sval);
        break;

    case VAL_SUBPARAMS:
        jbuf_append(jb, "\"val_type\":\"VAL_SUBPARAMS\",\"sub_params\":");
        serialize_param_list(jb, sp->val.param_list);
        break;

    case VAL_DATA: {
        p_data_t *data = sp->val.data;
        jbuf_append(jb, "\"val_type\":\"VAL_DATA\",\"instream_data\":{");
        jbuf_appendf(jb, "\"count\":%d,\"lines\":[", data ? data->count : 0);
        if (data) {
            int i;
            for (i = 0; i < data->count; i++) {
                if (i > 0) jbuf_append(jb, ",");
                jbuf_append_escaped(jb, data->datav[i]);
            }
        }
        jbuf_append(jb, "]}");
        break;
    }

    case VAL_RELEX:
        jbuf_append(jb, "\"val_type\":\"VAL_RELEX\",\"relex\":");
        serialize_relex(jb, sp->val.relex);
        break;

    default:
        jbuf_appendf(jb, "\"val_type\":\"UNKNOWN(%d)\"", sp->type);
        break;
    }

    jbuf_append(jb, "}");
}

static void serialize_param(json_buf_t *jb, jclcom_param_t *p)
{
    if (!p) { jbuf_append(jb, "null"); return; }

    jbuf_append(jb, "{");
    jbuf_appendf(jb, "\"type\":\"%s\",\"position\":%d",
                  p->type == K_PARAM ? "K_PARAM" : "P_PARAM",
                  p->position);

    if (p->keyword) {
        jbuf_append(jb, ",\"keyword\":");
        jbuf_append_escaped(jb, p->keyword);
    }

    if (p->subparam) {
        jbuf_append(jb, ",\"subparam\":");
        serialize_subparam(jb, p->subparam);
    }

    jbuf_append(jb, "}");
}

static void serialize_param_list(json_buf_t *jb, jclcom_param_t *param_list)
{
    jclcom_param_t *p;
    int first = 1;

    jbuf_append(jb, "[");

    if (!param_list) {
        jbuf_append(jb, "]");
        return;
    }

    p = list_first(param_list, jclcom_param_t, param_link);
    while (p) {
        if (!first) jbuf_append(jb, ",");
        first = 0;
        serialize_param(jb, p);

        if (p == list_last(param_list, jclcom_param_t, param_link))
            break;
        p = list_next(p, jclcom_param_t, param_link);
    }

    jbuf_append(jb, "]");
}

/* ──────────────────── Statement 직렬화 ──────────────────── */

static int g_stmt_count = 0;

static void serialize_stmt(json_buf_t *jb, jclcom_stmt_t *stmt)
{
    const char *type_name;
    const char *type_str;
    jclcom_stmt_t *child;
    jclcom_param_t *range_param;
    int first;

    if (!stmt) { jbuf_append(jb, "null"); return; }

    g_stmt_count++;

    type_name = stmt_type_name(stmt->type);
    type_str = xspjcl_stmt_type((xspjcl_stmt_type_t)stmt->type);

    jbuf_append(jb, "{");

    /* type */
    jbuf_appendf(jb, "\"type\":\"%s\"", type_name);

    /* type_str */
    if (type_str) {
        jbuf_append(jb, ",\"type_str\":");
        jbuf_append_escaped(jb, type_str);
    }

    /* name */
    if (stmt->name) {
        jbuf_append(jb, ",\"name\":");
        jbuf_append_escaped(jb, stmt->name);
    }

    /* lineno */
    jbuf_appendf(jb, ",\"lineno\":%d", stmt->lineno);

    /* lineno_str (매크로 확장 라인 추적) */
    if (stmt->lineno_str[0]) {
        jbuf_append(jb, ",\"lineno_str\":");
        jbuf_append_escaped(jb, stmt->lineno_str);
    }

    /* line_range from !!RANGE!! param */
    if (stmt->param_list) {
        range_param = list_first(stmt->param_list, jclcom_param_t, param_link);
        if (range_param && range_param->type == K_PARAM &&
            range_param->keyword && strcmp(range_param->keyword, "!!RANGE!!") == 0 &&
            range_param->subparam && range_param->subparam->type == VAL_STR) {
            int from_line = 0, to_line = 0;
            if (sscanf(range_param->subparam->val.sval, "%d,%d", &from_line, &to_line) == 2) {
                jbuf_appendf(jb, ",\"line_range\":[%d,%d]", from_line, to_line);
            }
        }
    }

    /* params (!!RANGE!! 제외) */
    jbuf_append(jb, ",\"params\":");
    if (stmt->param_list) {
        jclcom_param_t *p;
        int skip_first = 0;

        /* !!RANGE!!가 첫 번째 파라미터이면 건너뜀 */
        p = list_first(stmt->param_list, jclcom_param_t, param_link);
        if (p && p->type == K_PARAM && p->keyword &&
            strcmp(p->keyword, "!!RANGE!!") == 0) {
            skip_first = 1;
            p = (p == list_last(stmt->param_list, jclcom_param_t, param_link))
                ? NULL
                : list_next(p, jclcom_param_t, param_link);
        }

        jbuf_append(jb, "[");
        first = 1;
        while (p) {
            if (!first) jbuf_append(jb, ",");
            first = 0;
            serialize_param(jb, p);

            if (p == list_last(stmt->param_list, jclcom_param_t, param_link))
                break;
            p = list_next(p, jclcom_param_t, param_link);
        }
        jbuf_append(jb, "]");
    } else {
        jbuf_append(jb, "[]");
    }

    /* children (재귀) */
    jbuf_append(jb, ",\"children\":[");
    first = 1;
    if (stmt->child_list) {
        child = list_first(stmt->child_list, jclcom_stmt_t, child_link);
        while (child) {
            if (!first) jbuf_append(jb, ",");
            first = 0;
            serialize_stmt(jb, child);

            if (child == list_last(stmt->child_list, jclcom_stmt_t, child_link))
                break;
            child = list_next(child, jclcom_stmt_t, child_link);
        }
    }
    jbuf_append(jb, "]");

    jbuf_append(jb, "}");
}

/* ──────────────────── Stream 직렬화 ──────────────────── */

extern jclcom_stream_t jcl_stream;

static void serialize_stream(json_buf_t *jb)
{
    int i;
    int first = 1;

    jbuf_append(jb, "[");

    if (jcl_stream.init == 1) {
        for (i = 0; i <= jcl_stream.stmt_number; i++) {
            if (jcl_stream.stmt_string[i]) {
                if (!first) jbuf_append(jb, ",");
                first = 0;

                jbuf_appendf(jb, "{\"lineno\":%d,\"text\":", i);
                jbuf_append_escaped(jb, jcl_stream.stmt_string[i]);

                if (jcl_stream.error[i]) {
                    jbuf_append(jb, ",\"error\":");
                    jbuf_append_escaped(jb, jcl_stream.error[i]);
                }

                jbuf_append(jb, "}");
            }
        }
    }

    jbuf_append(jb, "]");
}

/* ──────────────────── 에러 직렬화 ──────────────────── */

static void serialize_errors(json_buf_t *jb)
{
    int i;
    int first = 1;

    jbuf_append(jb, "[");

    if (jcl_stream.init == 1) {
        for (i = 0; i <= jcl_stream.stmt_number; i++) {
            if (jcl_stream.error[i]) {
                if (!first) jbuf_append(jb, ",");
                first = 0;

                jbuf_appendf(jb, "{\"lineno\":%d", i);
                jbuf_appendf(jb, ",\"error_code\":%d", jcl_errno);
                jbuf_append(jb, ",\"error_name\":");
                /* 에러 코드 이름은 jcl_errno 기반 */
                switch (jcl_errno) {
                case 0:  jbuf_append(jb, "\"JCL_ERROR_OK\""); break;
                case 1:  jbuf_append(jb, "\"SCAN_ERROR\""); break;
                case 2:  jbuf_append(jb, "\"SCAN_ERROR_UNEXPECTED_INPUT\""); break;
                case 3:  jbuf_append(jb, "\"SCAN_ERROR_UNKNOWN_OPERATION_FIELD\""); break;
                case 4:  jbuf_append(jb, "\"SCAN_ERROR_MACRO_INPUT_PARAMETER_OVERFLOWED\""); break;
                case 5:  jbuf_append(jb, "\"SCAN_ERROR_MACRO_INPUT_PARAMETER_INVALID\""); break;
                case 6:  jbuf_append(jb, "\"SCAN_ERROR_SYSIN_FILE_NOT_FOUND\""); break;
                case 7:  jbuf_append(jb, "\"SCAN_ERROR_NOT_SUPPORTED_STATEMENT\""); break;
                case 8:  jbuf_append(jb, "\"SCAN_ERROR_UNKNOWN_MACRO_STATEMENT\""); break;
                case 9:  jbuf_append(jb, "\"SCAN_ERROR_MACRO_FILE_OPEN_FAIL\""); break;
                case 14: jbuf_append(jb, "\"PARSE_ERROR\""); break;
                case 15: jbuf_append(jb, "\"PARSE_ERROR_NO_JOB_IN_JOBG\""); break;
                case 16: jbuf_append(jb, "\"PARSE_ERROR_NO_STMT_IN_JOB\""); break;
                default: jbuf_appendf(jb, "\"ERROR_%d\"", jcl_errno); break;
                }
                jbuf_append(jb, ",\"message\":");
                jbuf_append_escaped(jb, jcl_stream.error[i]);
                jbuf_append(jb, ",\"line_text\":");
                jbuf_append_escaped(jb, jcl_stream.stmt_string[i]);
                jbuf_append(jb, "}");
            }
        }
    }

    jbuf_append(jb, "]");
}

/* ──────────────────── 전체 결과 직렬화 ──────────────────── */

static void serialize_result(json_buf_t *jb, int flags, int parse_rc)
{
    jclcom_stmt_t *jobg;
    int first = 1;
    int error_count;

    jbuf_append(jb, "{");

    /* success / error_count */
    error_count = jcl_stream_check_error();
    jbuf_appendf(jb, "\"success\":%s", (parse_rc == 0 && error_count == 0) ? "true" : "false");
    jbuf_appendf(jb, ",\"error_count\":%d", error_count);

    /* jcl_errno */
    jbuf_appendf(jb, ",\"jcl_errno\":%d", jcl_errno);
    jbuf_append(jb, ",\"jcl_errno_name\":");
    jbuf_append_escaped(jb, jcl_errno == 0 ? "JCL_ERROR_OK" : "");
    jbuf_append(jb, ",\"jcl_errno_desc\":");
    jbuf_append_escaped(jb, jcl_strerr(jcl_errno));

    /* flags */
    jbuf_appendf(jb, ",\"flags\":%d", flags);

    /* statements: jcl_tree.job_list 워킹 */
    g_stmt_count = 0;
    jbuf_append(jb, ",\"statements\":[");
    if (jcl_tree.job_list) {
        jobg = list_first(jcl_tree.job_list, jclcom_stmt_t, child_link);
        while (jobg) {
            if (!first) jbuf_append(jb, ",");
            first = 0;
            serialize_stmt(jb, jobg);

            if (jobg == list_last(jcl_tree.job_list, jclcom_stmt_t, child_link))
                break;
            jobg = list_next(jobg, jclcom_stmt_t, child_link);
        }
    }
    jbuf_append(jb, "]");

    /* errors */
    jbuf_append(jb, ",\"errors\":");
    serialize_errors(jb);

    /* stream */
    jbuf_append(jb, ",\"stream\":");
    serialize_stream(jb);

    /* total_lines */
    jbuf_appendf(jb, ",\"total_lines\":%d", jcl_stream.stmt_number);

    /* stmt_count */
    jbuf_appendf(jb, ",\"stmt_count\":%d", g_stmt_count);

    /* parser_version */
    {
        extern char *xspjcl_version;
        jbuf_append(jb, ",\"parser_version\":");
        jbuf_append_escaped(jb, xspjcl_version);
    }

    jbuf_append(jb, "}");
}

/* ──────────────────── 공개 API ──────────────────── */

/**
 * 문자열 소스를 파싱하여 JSON 결과 반환.
 *
 * 내부 수행 순서:
 *   1. 소스를 임시 파일에 기록
 *   2. xspmac_parse() — 매크로 확장 + SCF 변수 치환
 *   3. xspjcl_parse() — JCL 파싱
 *   4. 결과 직렬화 (AST + params + relex + instream + stream + errors)
 *
 * @param source  UTF-8 XSP JCL 소스 문자열
 * @param flags   0=default, 1=no_print, 2=always
 * @return JSON 문자열 (kms_xspjcl_free()로 해제)
 */
const char *kms_xspjcl_parse_string(const char *source, int flags)
{
    FILE *fp;
    char tmpfile[256];
    int rc;

    if (!source) return NULL;

    /* 임시 파일 생성 */
    snprintf(tmpfile, sizeof(tmpfile), "/tmp/kms_xspjcl_%d.jcl", getpid());
    fp = fopen(tmpfile, "w");
    if (!fp) return NULL;
    fprintf(fp, "%s", source);
    fclose(fp);

    /* 파싱 */
    fp = fopen(tmpfile, "r");
    if (!fp) {
        remove(tmpfile);
        return NULL;
    }

    rc = xspjcl_parse(flags, fp);
    fclose(fp);
    remove(tmpfile);

    /* JSON 직렬화 */
    jbuf_init(&g_result);
    serialize_result(&g_result, flags, rc);

    /* 파서 트리 정리 */
    jclcom_tree_delete(&jcl_tree);

    return g_result.buf;
}

/**
 * 파일 경로 기반 파싱.
 * SYSIN 포함 시 상대경로 해석이 가능하므로 파일 기반 파싱이 더 정확.
 */
const char *kms_xspjcl_parse_file(const char *file_path, int flags)
{
    FILE *fp;
    int rc;

    if (!file_path) return NULL;

    fp = fopen(file_path, "r");
    if (!fp) return NULL;

    rc = xspjcl_parse(flags, fp);
    fclose(fp);

    /* JSON 직렬화 */
    jbuf_init(&g_result);
    serialize_result(&g_result, flags, rc);

    /* 파서 트리 정리 */
    jclcom_tree_delete(&jcl_tree);

    return g_result.buf;
}

/**
 * 마지막 결과 버퍼 해제.
 */
void kms_xspjcl_free(void)
{
    if (g_result.buf) {
        free(g_result.buf);
        g_result.buf = NULL;
        g_result.size = 0;
        g_result.pos = 0;
    }
}

/**
 * 파서 빌드 버전 반환.
 */
const char *kms_xspjcl_version(void)
{
    extern char *xspjcl_version;
    return xspjcl_version;
}

/**
 * 에러 코드 → 설명 문자열.
 */
const char *kms_xspjcl_error_desc(int error_code)
{
    if (error_code < 0 || error_code > _JCL_ERROR_LAST)
        return "Unknown error";
    return jcl_strerr(error_code);
}

/**
 * 지원 statement 타입 JSON 배열 반환.
 */
static char g_stmt_types_buf[4096] = {0};

const char *kms_xspjcl_stmt_types(void)
{
    if (g_stmt_types_buf[0]) return g_stmt_types_buf;

    snprintf(g_stmt_types_buf, sizeof(g_stmt_types_buf),
        "[\"STMT_JOBG\",\"STMT_CODE\",\"STMT_JOB\",\"STMT_EX\","
        "\"STMT_PARA\",\"STMT_FD\",\"STMT_SW\",\"STMT_PAUSE\","
        "\"STMT_MSG\",\"STMT_NOTE\",\"STMT_JEND\",\"STMT_JGEND\","
        "\"STMT_FIN\",\"STMT_SYSIN\",\"STMT_EX_MACRO\",\"STMT_CHAM\","
        "\"STMT_MACRO\",\"STMT_MEND\",\"STMT_FDR\",\"STMT_FDDS\","
        "\"STMT_FDDE\",\"STMT_STACK\",\"STMT_CAT\",\"STMT_UNCAT\","
        "\"STMT_DATA\",\"STMT_END\",\"STMT_COMMAND\","
        "\"STMT_SCAN\",\"STMT_SCEND\",\"STMT_USER\",\"STMT_UEND\","
        "\"STMT_NOP\",\"STMT_ERROR\","
        "\"MSTMT_DEFINE\",\"MSTMT_SKIP\",\"MSTMT_IF\",\"MSTMT_IFN\","
        "\"MSTMT_SET\",\"MSTMT_MSG\",\"MSTMT_WTO\",\"MSTMT_WTOR\","
        "\"MSTMT_NOP\",\"MSTMT_DEXIT\",\"MSTMT_DEFEND\"]"
    );

    return g_stmt_types_buf;
}

/* vim:set ts=4 sw=4 cin et: */
