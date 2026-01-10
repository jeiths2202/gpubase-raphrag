# TmaxSoft IMS API 구조 분석 및 요청 문서

## 분석 일자: 2025-01-09
## 분석 대상: https://ims.tmaxsoft.com

---

## 1. 개요

TmaxSoft IMS 시스템은 다음 기술 스택을 사용합니다:

| 구분 | 기술 |
|------|------|
| Backend | Java (Spring Framework 추정) |
| Frontend | JSP + jQuery 1.9.1 |
| RPC | DWR (Direct Web Remoting) 3.x |
| UI Components | DataTables, jQuery UI 1.12.1, Bootstrap Datepicker |
| 인증 | Session-based (Cookie: JSESSIONID) |

---

## 2. 발견된 API 엔드포인트

### 2.1 이슈 관리 (Issue Management)

| HTTP Method | Endpoint | 설명 | 주요 파라미터 |
|-------------|----------|------|---------------|
| GET | `/tody/ims/issue/issueSearchList.do` | 이슈 검색/목록 | searchType, menuCode, keyword, productCodes, pageIndex, pageSize |
| POST | `/tody/ims/issue/issueView.do` | 이슈 상세 조회 | issueId, menuCode |
| GET | `/tody/ims/issue/issueRegister.do` | 이슈 등록 화면 | - |
| POST | `/tody/ims/filterIssuesAjax.do` | 필터 기반 이슈 조회 (AJAX) | filterNo, filterType |

### 2.2 사용자 관리 (User Management)

| HTTP Method | Endpoint | 설명 |
|-------------|----------|------|
| GET | `/tody/ims/user/popupUserList.do` | 사용자 팝업 검색 |

### 2.3 마스터 데이터 (Master Data)

| HTTP Method | Endpoint | 설명 |
|-------------|----------|------|
| GET | `/tody/ims/common/product/productList.do` | 제품 목록 |
| GET | `/tody/ims/common/customer/customerList.do` | 고객사 목록 |
| GET | `/tody/ims/issue/popupProjectList.do` | 프로젝트 팝업 검색 |

### 2.4 인증 (Authentication)

| HTTP Method | Endpoint | 설명 |
|-------------|----------|------|
| GET/POST | `/tody/auth/login.do` | 로그인 |
| GET | `/tody/sso/ssoLogin.jsp` | SSO 로그인 |
| GET | `/tody/sso/ssoLoginReturn.jsp` | SSO 콜백 |

---

## 3. DWR (Direct Web Remoting) 서비스

DWR 엔드포인트: `/tody/dwr/`

### 3.1 IssueCategoryDwr - 이슈 카테고리 관리

```javascript
// 카테고리 조회
IssueCategoryDwr.findCategories(callback)
IssueCategoryDwr.findCategory(categoryId, callback)

// 카테고리 CRUD
IssueCategoryDwr.insertCategory(p0, p1, p2, callback)
IssueCategoryDwr.updateCategory(p0, p1, p2, callback)
IssueCategoryDwr.updateCategoryViewOrder(orderData, callback)
IssueCategoryDwr.deleteCategory(categoryId, callback)

// 활동(Activity) 관리
IssueCategoryDwr.findActivity(activityId, callback)
IssueCategoryDwr.findCateActivities(categoryId, callback)
IssueCategoryDwr.insertActivity(activityData, callback)
IssueCategoryDwr.updateActivity(activityData, callback)
IssueCategoryDwr.deleteActivity(activityId, callback)
```

### 3.2 ProductDwr - 제품/버전/모듈 관리

```javascript
// 버전 조회
ProductDwr.findVersions(productCode, callback)
ProductDwr.findSubVersions(productCode, mainVersion, callback)
ProductDwr.findRegMainVersions(p0, p1, p2, p3, callback)
ProductDwr.findRegSubVersions(p0, p1, p2, p3, callback)
ProductDwr.findSearchMainVersions(p0, p1, p2, callback)
ProductDwr.findSearchSubVersions(p0, p1, p2, p3, callback)

// 모듈 조회
ProductDwr.findModules(productCode, callback)
ProductDwr.findSimpleModules(productCode, callback)

// 제품 속성 설정
ProductDwr.findProductAttrCfg(p0, p1, callback)
ProductDwr.addProdAttributeConfig(p0, p1, p2, p3, callback)

// 담당자 변경
ProductDwr.changeToProductManager(p0, p1, p2, callback)
ProductDwr.changeToProductManagerAll(p0, p1, callback)
```

### 3.3 UserDwr - 사용자 조회

```javascript
// 사용자 검색
UserDwr.findUser(userId, callback)
UserDwr.findUsersByName(searchText, callback)
UserDwr.findUsersByNameAll(searchText, callback)

// 모듈 담당자 조회
UserDwr.findModuleManagers(p0, p1, p2, callback)
```

---

## 4. Form 파라미터 상세

### 4.1 issueSearchForm (이슈 검색 폼)

총 68개 필드가 발견되었습니다. 주요 필드:

| 필드명 | 타입 | 설명 |
|--------|------|------|
| searchType | hidden | 검색 타입 (1=일반검색) |
| pageIndex | hidden | 페이지 번호 |
| pageSize | select | 페이지 크기 (10,20,30,50,100,500,1000) |
| menuCode | hidden | 메뉴 코드 (issue_search) |
| keyword | text | 검색 키워드 |
| productCodes | multi-select | 제품 코드 (복수 선택) |
| paramProdCodes | hidden | 선택된 제품 코드 |
| orderType | hidden | 정렬 방식 |
| clickColumn | hidden | 정렬 컬럼 |
| reSearchYN | hidden | 재검색 여부 |

### 4.2 issueViewForm (이슈 조회 폼)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| issueId | hidden | 이슈 ID |
| menuCode | hidden | 메뉴 코드 |

---

## 5. 검색 결과 테이블 컬럼 구조

DataTables 사용, 31개 컬럼:

| Index | 컬럼명 | 설명 |
|-------|--------|------|
| 0 | No | 순번 |
| 1 | Issue Number | 이슈 번호 (ID) |
| 2 | Category | 이슈 유형 (기술지원, SR 등) |
| 3 | Product | 제품명 |
| 4 | Version | 버전 |
| 5 | Module | 모듈 |
| 6 | Subject | 제목 |
| 7 | Customer | 고객사 |
| 8 | Project | 프로젝트 |
| 9 | Reporter | 등록자 |
| 10 | Issued Date | 등록일 |
| ... | ... | (추가 컬럼 있음) |

---

## 6. JavaScript 함수 (Frontend API 호출)

### 6.1 이슈 조회/검색

```javascript
// 이슈 목록 검색 (폼 submit)
goReportSearch(form, searchType)

// 이슈 상세 팝업
popBlankIssueView(issueId, menuCode)
popupIssueView(issueId, menuCode)
viewIssue(issueId)

// 이슈 목록 이동
goIssueList()
goIssueSearch()
```

### 6.2 데이터 조회 (AJAX)

```javascript
// 필터 이슈 조회
filterIssuesAjax(filterNo, filterType)

// Excel 다운로드
ajaxExcelDown(...)
saveExcelSearch()
saveExcelList()

// 사용자 검색
fn_findUser(...)
```

### 6.3 리포트

```javascript
goIssueRegistReport()   // 등록 리포트
goIssueDispoReport()    // 처리 리포트
goIssueCmpReport()      // 완료 리포트
goIssueCmpBReport()     // 완료B 리포트
```

---

## 7. 제품 코드 목록 (OpenFrame 시리즈)

발견된 주요 제품 코드:

| 코드 | 제품명 |
|------|--------|
| 128 | OpenFrame AIM |
| 520 | OpenFrame ASM |
| 129 | OpenFrame Base |
| 123 | OpenFrame Batch |
| 500 | OpenFrame COBOL |
| 137 | OpenFrame Common |
| 141 | OpenFrame GW |
| 126 | OpenFrame HiDB |
| 147 | OpenFrame ISPF |
| 145 | OpenFrame Manager |
| 135 | OpenFrame Map GUI Editor |
| 143 | OpenFrame Miner |
| 138 | OpenFrame OSC |
| 134 | OpenFrame OSI |
| 142 | OpenFrame OpenStudio Web |
| 510 | OpenFrame PLI |
| 127 | OpenFrame Studio |
| 124 | OpenFrame TACF |
| 640 | ProSort |
| 425 | ProTrieve |

---

## 8. 관리자에게 요청할 사항

### 8.1 REST API 또는 데이터 추출 API 제공 요청

현재 IMS 시스템은 웹 UI 기반으로 설계되어 있어, 프로그래밍 방식의 데이터 접근이 어렵습니다.
다음 중 하나의 방식으로 API 접근 권한을 요청합니다:

#### Option A: REST API 제공 (권장)

```
GET /api/v1/issues?keyword=xxx&productCodes=128,129&page=1&size=100
GET /api/v1/issues/{issueId}
GET /api/v1/products
GET /api/v1/customers
```

#### Option B: DWR 직접 호출 허용

DWR 엔드포인트(`/tody/dwr/call/plaincall/`)에 대한 프로그래밍 방식 호출 허용 및 문서화

#### Option C: 데이터베이스 읽기 전용 접근

이슈 테이블에 대한 읽기 전용 DB 접근 권한

### 8.2 필요한 데이터 스키마 문서

1. **Issue 테이블 구조**
   - 모든 컬럼명과 데이터 타입
   - 상태값 코드 (OPEN, CLOSED, IN_PROGRESS 등)
   - 우선순위 코드

2. **Product/Module 관계 구조**
   - 제품 → 버전 → 모듈 계층 구조
   - 제품 코드 전체 목록

3. **User 테이블 구조**
   - 사용자 ID, 이름, 부서 등

4. **첨부파일 접근 방법**
   - 첨부파일 다운로드 API
   - 파일 저장 경로 규칙

### 8.3 인증 방식 문서화

1. **세션 기반 인증**
   - JSESSIONID 쿠키 유효 시간
   - 세션 갱신 방법

2. **API 토큰 발급** (가능하다면)
   - API 전용 인증 토큰 발급
   - 토큰 기반 인증 지원

---

## 9. 현재 크롤링 방식의 한계

| 문제점 | 설명 |
|--------|------|
| 속도 | 페이지 렌더링 대기로 인한 느린 처리 속도 |
| 안정성 | UI 변경 시 크롤러 수정 필요 |
| 서버 부하 | 불필요한 정적 리소스 로드 |
| 데이터 완전성 | HTML 파싱으로 인한 데이터 손실 가능성 |

API 직접 호출 방식이 제공되면 위 문제들을 해결할 수 있습니다.

---

## 10. 연락처

요청자: [이름]
부서: [부서명]
이메일: [이메일]
용도: Knowledge Management System 연동을 위한 이슈 데이터 자동 동기화

---

## 11. DWR API 직접 호출 방법 (검증됨)

### 11.1 DWR 호출 형식

IMS DWR은 **GET 방식** API를 사용합니다:

```
GET https://ims.tmaxsoft.com/tody/dwr/exec/{ServiceName}.{methodName}
```

### 11.2 Query Parameters

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| callCount | 호출 횟수 (항상 1) | `1` |
| c0-scriptName | 서비스 이름 | `ProductDwr` |
| c0-methodName | 메서드 이름 | `findVersions` |
| c0-id | 고유 호출 ID | `1234_1767932338763` |
| c0-param0 | 첫번째 파라미터 | `string:129` |
| c0-param1 | 두번째 파라미터 (있을 경우) | `string:value` |
| xml | 응답 형식 | `true` |

### 11.3 필수 헤더

```http
Cookie: JSESSIONID={session_id}
Referer: https://ims.tmaxsoft.com/tody/ims/issue/issueSearchList.do
```

### 11.4 Python 코드 예시

```python
import requests

# 1. 로그인
session = requests.Session()
login_url = "https://ims.tmaxsoft.com/tody/auth/login.do"
session.post(login_url, data={"id": "username", "password": "password"})

# 2. DWR API 호출
params = {
    'callCount': '1',
    'c0-scriptName': 'ProductDwr',
    'c0-methodName': 'findVersions',
    'c0-id': '1234',
    'c0-param0': 'string:129',
    'xml': 'true'
}
headers = {
    'Referer': 'https://ims.tmaxsoft.com/tody/ims/issue/issueSearchList.do'
}
response = session.get(
    'https://ims.tmaxsoft.com/tody/dwr/exec/ProductDwr.findVersions',
    params=params,
    headers=headers
)
print(response.text)
```

### 11.5 검증된 API 호출 예시

#### ProductDwr.findVersions(productCode)
```
GET /tody/dwr/exec/ProductDwr.findVersions?callCount=1&c0-scriptName=ProductDwr&c0-methodName=findVersions&c0-param0=string:129&xml=true
```
응답 (JavaScript):
```javascript
var s1 = new Object();
s1.productCode = "129";
s1.versionCode = "07300000";
s1.versionName = "7.3";
s1.releaseStatusName = "릴리즈후";
s1.subVersions = [...];
```

#### IssueCategoryDwr.findCategories()
```
GET /tody/dwr/exec/IssueCategoryDwr.findCategories?callCount=1&c0-scriptName=IssueCategoryDwr&c0-methodName=findCategories&xml=true
```
응답 데이터:
| categoryCode | categoryName |
|--------------|--------------|
| improve | Change Request |
| addition | Enhancement Request |
| inquiry | Technical Support |
| defect | Defect |
| request | Binary Request |
| patchFail | Patch Fail |
| manual | Manual |

#### UserDwr.findUsersByName(searchText)
```
GET /tody/dwr/exec/UserDwr.findUsersByName?callCount=1&c0-scriptName=UserDwr&c0-methodName=findUsersByName&c0-param0=string:shin&xml=true
```
응답 데이터:
```javascript
{
  id: "yijae.shin",
  name: "Yijae Shin",
  email: "yijae.shin@tmaxsoft.com",
  deptName: "Japan",
  companyNm: "티맥스글로벌"
}
```

---

## 12. 이슈 검색 Form Submit API

DWR은 마스터 데이터 조회용이고, 이슈 검색/조회는 Form Submit 방식입니다:

### 12.1 이슈 검색

```
GET https://ims.tmaxsoft.com/tody/ims/issue/issueSearchList.do
```

Query Parameters:
| 파라미터 | 설명 | 예시 |
|---------|------|------|
| searchType | 검색 타입 | `1` |
| menuCode | 메뉴 코드 | `issue_search` |
| keyword | 검색 키워드 | `OpenFrame` |
| productCodes | 제품 코드 (multi) | `129,128` |
| pageIndex | 페이지 번호 | `1` |
| pageSize | 페이지 크기 | `100` |

### 12.2 이슈 상세

```
POST https://ims.tmaxsoft.com/tody/ims/issue/issueView.do
```

Form Data:
| 파라미터 | 설명 |
|---------|------|
| issueId | 이슈 ID |
| menuCode | 메뉴 코드 |

---

## 13. Python 크롤러 구현 (Playwright 없이)

### 13.1 개요

Playwright(브라우저 자동화) 없이 `requests` + `BeautifulSoup`만으로 IMS 크롤링이 가능합니다.

**파일 위치**: `scripts/ims_requests_crawler.py`

### 13.2 핵심 발견 사항

이슈 검색 API 호출 시 **필수 파라미터**:

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| `reSearchYN` | `'Y'` | **필수!** 'N'이면 결과 없음 |
| `queryId` | `'ims.issueSearch.findIssueSearch'` | 검색 쿼리 ID |
| `searchType` | `'1'` | 검색 타입 |
| `productCodes` | `['128', '129', ...]` | 제품 코드 (복수 선택) |

### 13.3 데이터 클래스

```python
@dataclass
class IssueAction:
    """Issue Action/Comment"""
    action_id: str
    content: str
    user: str = ""
    date: str = ""

@dataclass
class RelatedIssue:
    """Related Issue"""
    issue_id: str
    issue_number: str
    subject: str
    relation_type: str = ""
    product: str = ""
    status: str = ""

@dataclass
class IMSIssue:
    """IMS Issue"""
    issue_id: str
    issue_number: str
    category: str
    product: str
    version: str
    module: str
    subject: str
    customer: str = ""
    project: str = ""
    reporter: str = ""
    issued_date: str = ""
    contents: str = ""
    status: str = ""
    issue_details: str = ""      # Issue Description
    actions: List[IssueAction] = None
    related_issues: List[RelatedIssue] = None
```

### 13.4 사용법

```python
from scripts.ims_requests_crawler import IMSCrawler

# 크롤러 초기화 및 로그인
crawler = IMSCrawler()
crawler.login("username", "password")

# 이슈 검색
issues = crawler.search_issues(
    keyword="oscboot",
    product_codes=['128', '129', '138'],  # OpenFrame 제품
    page_size=100
)

# 이슈 상세 조회 (Related Issues 포함)
detail = crawler.get_issue_detail(issues[0].issue_id)

print(f"Subject: {detail.subject}")
print(f"Category: {detail.category}")
print(f"Product: {detail.product}")
print(f"Issue Details: {detail.issue_details[:200]}...")
print(f"Actions: {len(detail.actions)}")
```

### 13.5 파싱 가능한 필드

| 필드 | 소스 | 설명 |
|------|------|------|
| issue_id | 검색 결과 | 이슈 ID |
| subject | `<td class="tableHeaderTitle">Subject</td>` | 이슈 제목 |
| category | `Category</td><td>` | 카테고리 (Technical Support 등) |
| product | `Product</td><td>` | 제품명 (OpenFrame OSC 등) |
| version | `Version</td><td>` | 버전 (7.1 등) |
| module | `Module</td><td>` | 모듈 (General 등) |
| status | `Status</td><td>` | 상태 (Open, Closed 등) |
| customer | `Customer</td><td>` | 고객사 |
| project | `Project</td><td>` | 프로젝트명 |
| reporter | `Reporter</td><td>` | 등록자 |
| issue_details | `#IssueDescriptionDiv` | 이슈 상세 설명 (버그 리포트 등) |
| actions | `<input name="actionId">` + `commDescTR_{id}` | 액션/코멘트 목록 |
| related_issues | `/ims/issue/findRelationIssues.do` (JSON) | 관련 이슈 |

### 13.6 이슈 검색 API 상세

```python
# 검색 요청 파라미터 (전체)
params = {
    'reSearchYN': 'Y',                              # 필수!
    'searchType': '1',
    'pageIndex': '1',
    'pageSize': '100',
    'keyword': 'oscboot',
    'menuCode': 'issue_search',
    'menuLink': '/ims/issue/issueSearchList.do',
    'moveSearchAction': 'ims/issue/issueSearchList.do',
    'orderType': 'desc',
    'listType': '1',
    'queryId': 'ims.issueSearch.findIssueSearch',   # 필수!
    'queryIdDetail': 'ims.profile.findUserIssueColumns',
    'reportType': 'R101',
    'reportLink': '/util/saveSearchList.do',
    'taggingWordOption': 'equals',
    'userId': 'yijae.shin',
    'userName': 'Yijae Shin',
    'userGrade': 'TMAX',
    'productCodes': ['128', '129', '138'],          # 복수 선택
}

response = session.get(
    'https://ims.tmaxsoft.com/tody/ims/issue/issueSearchList.do',
    params=params
)
```

### 13.7 이슈 상세 API

```python
# 이슈 상세 조회
response = session.post(
    'https://ims.tmaxsoft.com/tody/ims/issue/issueView.do',
    data={'issueId': '350386', 'menuCode': 'issue_search'}
)

# Related Issues 조회 (JSON API)
response = session.get(
    'https://ims.tmaxsoft.com/tody/ims/issue/findRelationIssues.do',
    params={'issueId': '350386'}
)
related = response.json()  # List of related issues
```

### 13.8 HTML 파싱 패턴

**Subject 추출**:
```python
# <td class="tableHeaderTitle">Subject</td><td>제목</td>
pattern = r'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*Subject\s*</td>\s*<td[^>]*>(.*?)</td>'
```

**Issue Details 추출**:
```python
# <div id="IssueDescriptionDiv">...</div>
pattern = r'id=["\']IssueDescriptionDiv["\'][^>]*>(.*?)</div>\s*<!--'
```

**Actions 추출**:
```python
# <input name="actionId" value="2264315">...<div id="commDescTR_2264315">내용</div>
pattern = r'<input[^>]*name=["\']actionId["\'][^>]*value=["\'](\d+)["\'][^>]*>.*?commDescTR_\1[^>]*>(.*?)</div>'
```

### 13.9 Playwright vs requests 비교

| 항목 | Playwright | requests |
|------|-----------|----------|
| 속도 | 느림 (브라우저 렌더링) | **빠름** (HTTP만) |
| 메모리 | 높음 (~500MB) | **낮음** (~50MB) |
| 설치 | 복잡 (Chromium 필요) | **간단** (pip install) |
| JavaScript | 실행 가능 | 불가 |
| 안정성 | UI 변경에 민감 | **HTML 구조만 의존** |
| IMS 크롤링 | OK | **OK (검증됨)** |

### 13.10 OpenFrame 제품 코드

```python
OPENFRAME_PRODUCTS = [
    '128',   # OpenFrame AIM
    '520',   # OpenFrame ASM
    '129',   # OpenFrame Base
    '123',   # OpenFrame Batch
    '500',   # OpenFrame COBOL
    '137',   # OpenFrame Common
    '141',   # OpenFrame GW
    '126',   # OpenFrame HiDB
    '147',   # OpenFrame ISPF
    '145',   # OpenFrame Manager
    '135',   # OpenFrame Map GUI Editor
    '143',   # OpenFrame Miner
    '138',   # OpenFrame OSC
    '134',   # OpenFrame OSI
    '142',   # OpenFrame OpenStudio Web
    '510',   # OpenFrame PLI
    '127',   # OpenFrame Studio
    '124',   # OpenFrame TACF
]
```

---

## 14. 테스트 결과 예시

```
Issue ID: 350386
Subject:  [일본 손보재팬] OSC 리젼 기동 후 Out of memory 발생 건
Category: Technical Support
Product:  OpenFrame OSC
Version:  7.1
Module:   General
Status:   Open
Customer: (주)티맥스소프트
Project:  GBSC 일본 손보재팬
Reporter: Kihong Kim ( kihong.kim@tmaxsoft.com)

Issue Details:
  ※작성 전 Product Notice 를 참고 하세요.※
  <버그 리포트>
  1. 이슈 설명 - OSC 리젼 (CICSFA) 기동 후, Out of memory 가 발생
  2. 이슈 발생 환경 정보 - 손보재팬 운용기 (PROD)
  3. 재현 절차 - oscboot -N ONLINE -r CICSFA -m -w 300
  4.1 기대 결과 - OSC 리젼 정상 작동
  4.2 현재 결과 - Out of memory 발생

Actions (5):
  - Action #2264315: @정우석 연구원님, 이명신 매니저님 말씀하신 버전 정보를 고객 측에 요청 중...
  - Action #2263979: 패치 버전은 이 쉘을 사용하여 확인 후 첨부 부탁 드립니다...
  - Action #2263972: 김기홍 매니저님 고객 환경의 바이너리 버전 정보...
  - Action #2263962: @정우석 연구원님 지적 감사드립니다...
  - Action #2263921: 안녕하세요. 정우석입니다. 이슈 등록 시 요청드린 버그 리포트를...
```

---

*본 문서는 실제 API 테스트를 통해 검증되었습니다. (2025-01-09)*
*Python 크롤러 구현 완료: `scripts/ims_requests_crawler.py`*
