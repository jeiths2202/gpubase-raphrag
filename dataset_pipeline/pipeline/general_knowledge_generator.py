"""General knowledge Q&A generator for SFT dataset.

Generates IT/CS general knowledge Q&A pairs in ja/ko/en to prevent
catastrophic forgetting during QLoRA fine-tuning. The general knowledge
covers fundamental topics that complement the TmaxSoft domain-specific
training data.
"""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Tuple

from .config import GenerationConfig
from .models import ItemType, Language, SFTCategory, SFTRecord

logger = logging.getLogger(__name__)

# System prompts per language for general knowledge
_SYSTEM_PROMPTS: Dict[Language, str] = {
    Language.JA: (
        "あなたはITインフラストラクチャとエンタープライズシステムに精通した"
        "技術エキスパートです。正確かつ簡潔に回答してください。"
    ),
    Language.KO: (
        "당신은 IT 인프라 및 엔터프라이즈 시스템에 정통한 "
        "기술 전문가입니다. 정확하고 간결하게 답변해주세요."
    ),
    Language.EN: (
        "You are a technical expert well-versed in IT infrastructure "
        "and enterprise systems. Answer accurately and concisely."
    ),
}

# ── General Knowledge Q&A Bank ────────────────────────────────────────
# Structure: List of (category, language, question, answer) tuples
# Each entry is a self-contained Q&A pair.

GeneralQA = Tuple[str, Language, str, str]


def _build_qa_bank() -> List[GeneralQA]:
    """Build the curated general knowledge Q&A bank."""
    bank: List[GeneralQA] = []

    # ── 1. Database Fundamentals ──────────────────────────────────────

    bank.extend([
        ("database", Language.JA,
         "RDBMSとNoSQLデータベースの違いを説明してください。",
         "RDBMS（リレーショナルデータベース管理システム）はテーブル形式でデータを管理し、"
         "SQLでデータを操作します。ACID特性（原子性、一貫性、分離性、耐久性）を保証し、"
         "データの整合性が高いのが特徴です。Oracle、PostgreSQL、MySQL等が代表的です。\n\n"
         "NoSQLデータベースは、ドキュメント型（MongoDB）、キーバリュー型（Redis）、"
         "カラムファミリー型（Cassandra）、グラフ型（Neo4j）など多様なデータモデルを提供します。"
         "スキーマレスで柔軟性が高く、水平スケーリングに適していますが、"
         "トランザクションの一貫性はRDBMSほど厳密ではない場合があります。"),

        ("database", Language.KO,
         "RDBMS와 NoSQL 데이터베이스의 차이점을 설명해주세요.",
         "RDBMS(관계형 데이터베이스 관리 시스템)는 테이블 형태로 데이터를 관리하며 "
         "SQL로 데이터를 조작합니다. ACID 특성(원자성, 일관성, 고립성, 지속성)을 보장하여 "
         "데이터 무결성이 높은 것이 특징입니다. Oracle, PostgreSQL, MySQL 등이 대표적입니다.\n\n"
         "NoSQL 데이터베이스는 문서형(MongoDB), 키-값형(Redis), 컬럼패밀리형(Cassandra), "
         "그래프형(Neo4j) 등 다양한 데이터 모델을 제공합니다. 스키마리스로 유연성이 높고 "
         "수평 확장에 적합하지만, 트랜잭션 일관성은 RDBMS만큼 엄격하지 않을 수 있습니다."),

        ("database", Language.EN,
         "Explain the differences between RDBMS and NoSQL databases.",
         "RDBMS (Relational Database Management System) manages data in table format "
         "and uses SQL for data operations. It guarantees ACID properties (Atomicity, "
         "Consistency, Isolation, Durability) with high data integrity. Examples include "
         "Oracle, PostgreSQL, and MySQL.\n\n"
         "NoSQL databases provide diverse data models: document (MongoDB), key-value "
         "(Redis), column-family (Cassandra), and graph (Neo4j). They are schema-less, "
         "highly flexible, and suitable for horizontal scaling, though transaction "
         "consistency may not be as strict as RDBMS."),

        ("database", Language.JA,
         "データベースのACID特性について説明してください。",
         "ACID特性はデータベーストランザクションの信頼性を保証する4つの特性です。\n\n"
         "**原子性（Atomicity）**: トランザクション内の操作はすべて実行されるか、"
         "まったく実行されないかのいずれかです。部分的な実行はありません。\n\n"
         "**一貫性（Consistency）**: トランザクション前後でデータベースは"
         "整合性制約を満たした状態を維持します。\n\n"
         "**分離性（Isolation）**: 同時に実行されるトランザクションは互いに影響しません。"
         "分離レベルにはRead Uncommitted、Read Committed、Repeatable Read、"
         "Serializableの4段階があります。\n\n"
         "**耐久性（Durability）**: コミットされたトランザクションの結果は、"
         "システム障害が発生しても永続的に保存されます。"),

        ("database", Language.KO,
         "데이터베이스의 ACID 특성에 대해 설명해주세요.",
         "ACID 특성은 데이터베이스 트랜잭션의 신뢰성을 보장하는 4가지 속성입니다.\n\n"
         "**원자성(Atomicity)**: 트랜잭션 내의 모든 연산은 전부 실행되거나 "
         "전혀 실행되지 않습니다.\n\n"
         "**일관성(Consistency)**: 트랜잭션 전후로 데이터베이스는 "
         "무결성 제약조건을 만족하는 상태를 유지합니다.\n\n"
         "**고립성(Isolation)**: 동시에 실행되는 트랜잭션들은 서로 영향을 미치지 않습니다. "
         "격리 수준에는 Read Uncommitted, Read Committed, Repeatable Read, "
         "Serializable의 4단계가 있습니다.\n\n"
         "**지속성(Durability)**: 커밋된 트랜잭션의 결과는 시스템 장애가 발생하더라도 "
         "영구적으로 저장됩니다."),

        ("database", Language.JA,
         "データベースの正規化（第1正規形〜第3正規形）を説明してください。",
         "正規化はデータの冗長性を排除し、整合性を向上させるプロセスです。\n\n"
         "**第1正規形（1NF）**: すべての属性が原子値（分割不可能な値）を持つ。"
         "繰り返しグループや複数値属性を排除します。\n\n"
         "**第2正規形（2NF）**: 1NFを満たし、かつすべての非キー属性が主キー全体に"
         "完全関数従属する。部分関数従属を排除します。\n\n"
         "**第3正規形（3NF）**: 2NFを満たし、かつすべての非キー属性が主キーに"
         "直接依存する。推移的関数従属を排除します。\n\n"
         "正規化により更新異常や削除異常を防止できますが、過度な正規化は"
         "結合操作が増えパフォーマンスに影響するため、適切なバランスが重要です。"),

        ("database", Language.KO,
         "데이터베이스 정규화(제1정규형~제3정규형)를 설명해주세요.",
         "정규화는 데이터의 중복을 제거하고 무결성을 향상시키는 프로세스입니다.\n\n"
         "**제1정규형(1NF)**: 모든 속성이 원자값(더 이상 분리 불가능한 값)을 가집니다. "
         "반복 그룹이나 다중값 속성을 제거합니다.\n\n"
         "**제2정규형(2NF)**: 1NF를 만족하고, 모든 비키 속성이 기본키 전체에 "
         "완전 함수 종속합니다. 부분 함수 종속을 제거합니다.\n\n"
         "**제3정규형(3NF)**: 2NF를 만족하고, 모든 비키 속성이 기본키에 "
         "직접 종속합니다. 이행적 함수 종속을 제거합니다.\n\n"
         "정규화로 갱신 이상이나 삭제 이상을 방지할 수 있지만, 과도한 정규화는 "
         "조인 연산이 증가하여 성능에 영향을 줄 수 있어 적절한 균형이 중요합니다."),

        ("database", Language.JA,
         "データベースインデックスの種類と仕組みを説明してください。",
         "インデックスはデータベースの検索性能を向上させるデータ構造です。\n\n"
         "**B-Treeインデックス**: 最も一般的なインデックス。バランス木構造で、"
         "等価検索と範囲検索の両方に効率的です。\n\n"
         "**ハッシュインデックス**: ハッシュ関数を使用。等価検索に非常に高速ですが、"
         "範囲検索には使用できません。\n\n"
         "**ビットマップインデックス**: カーディナリティの低い列に適しています。"
         "ビット演算で高速なAND/OR結合が可能です。\n\n"
         "**全文検索インデックス**: テキストデータの全文検索用。転置インデックス"
         "構造を使用します。\n\n"
         "インデックスは検索を高速化しますが、INSERT/UPDATE/DELETEの際に"
         "インデックスの更新コストが発生するため、適切な列のみに作成することが重要です。"),

        ("database", Language.EN,
         "Explain the types and mechanisms of database indexes.",
         "Indexes are data structures that improve database search performance.\n\n"
         "**B-Tree Index**: The most common index type. Uses a balanced tree structure, "
         "efficient for both equality and range queries.\n\n"
         "**Hash Index**: Uses hash functions. Extremely fast for equality lookups "
         "but cannot be used for range queries.\n\n"
         "**Bitmap Index**: Suitable for low-cardinality columns. Enables fast "
         "AND/OR combinations using bit operations.\n\n"
         "**Full-Text Index**: For full-text search on text data. Uses inverted "
         "index structures.\n\n"
         "While indexes speed up reads, they incur update costs on INSERT/UPDATE/DELETE "
         "operations, so it is important to create indexes only on appropriate columns."),

        ("database", Language.JA,
         "SQLのJOIN（結合）の種類を説明してください。",
         "SQLのJOINは複数のテーブルを結合してデータを取得する操作です。\n\n"
         "**INNER JOIN（内部結合）**: 両方のテーブルに一致するレコードのみを返します。\n\n"
         "**LEFT JOIN（左外部結合）**: 左テーブルのすべてのレコードと、"
         "右テーブルの一致するレコードを返します。一致がない場合はNULLになります。\n\n"
         "**RIGHT JOIN（右外部結合）**: 右テーブルのすべてのレコードと、"
         "左テーブルの一致するレコードを返します。\n\n"
         "**FULL OUTER JOIN（完全外部結合）**: 両方のテーブルのすべてのレコードを返し、"
         "一致がない部分はNULLになります。\n\n"
         "**CROSS JOIN（交差結合）**: 両テーブルのすべての組み合わせ（直積）を返します。"),

        ("database", Language.KO,
         "SQL JOIN(결합)의 종류를 설명해주세요.",
         "SQL JOIN은 여러 테이블을 결합하여 데이터를 조회하는 연산입니다.\n\n"
         "**INNER JOIN(내부 결합)**: 양쪽 테이블에 일치하는 레코드만 반환합니다.\n\n"
         "**LEFT JOIN(왼쪽 외부 결합)**: 왼쪽 테이블의 모든 레코드와 "
         "오른쪽 테이블의 일치하는 레코드를 반환합니다. 일치하지 않으면 NULL입니다.\n\n"
         "**RIGHT JOIN(오른쪽 외부 결합)**: 오른쪽 테이블의 모든 레코드와 "
         "왼쪽 테이블의 일치하는 레코드를 반환합니다.\n\n"
         "**FULL OUTER JOIN(완전 외부 결합)**: 양쪽 테이블의 모든 레코드를 반환하며, "
         "일치하지 않는 부분은 NULL입니다.\n\n"
         "**CROSS JOIN(교차 결합)**: 양쪽 테이블의 모든 조합(카르테시안 곱)을 반환합니다."),

        ("database", Language.JA,
         "データベースのデッドロックとその対策を説明してください。",
         "デッドロックは、2つ以上のトランザクションが互いに相手が保持するロックの"
         "解放を待ち続け、どちらも進行できなくなる状態です。\n\n"
         "**発生条件（コフマンの4条件）**:\n"
         "1. 相互排除: リソースは同時に1つのトランザクションのみ使用可能\n"
         "2. 保持と待機: ロックを保持したまま他のロックを待つ\n"
         "3. 横取り不可: 他者のロックを強制解除できない\n"
         "4. 循環待ち: トランザクション間で循環的な待ちが発生\n\n"
         "**対策**:\n"
         "- ロック順序の統一: すべてのトランザクションで同じ順序でロックを取得\n"
         "- タイムアウト設定: 一定時間後にトランザクションを自動ロールバック\n"
         "- デッドロック検出: 待ちグラフを監視し、検出時に一方をロールバック\n"
         "- トランザクションの短縮: ロック保持時間を最小化"),

        ("database", Language.EN,
         "Explain database deadlocks and how to prevent them.",
         "A deadlock occurs when two or more transactions are waiting for each other "
         "to release locks, causing none of them to proceed.\n\n"
         "**Coffman's Four Conditions**:\n"
         "1. Mutual exclusion: A resource can only be used by one transaction at a time\n"
         "2. Hold and wait: A transaction holds locks while waiting for others\n"
         "3. No preemption: Locks cannot be forcibly taken from a transaction\n"
         "4. Circular wait: A circular chain of transactions exists\n\n"
         "**Prevention strategies**:\n"
         "- Lock ordering: Always acquire locks in the same order\n"
         "- Timeout: Automatically rollback transactions after a timeout\n"
         "- Deadlock detection: Monitor wait-for graphs and rollback one transaction\n"
         "- Short transactions: Minimize lock holding time"),
    ])

    # ── 2. Operating Systems ──────────────────────────────────────────

    bank.extend([
        ("os", Language.JA,
         "プロセスとスレッドの違いを説明してください。",
         "プロセスはOSが管理するプログラムの実行単位で、独立したメモリ空間（コード、データ、"
         "ヒープ、スタック）を持ちます。プロセス間通信（IPC）にはパイプ、ソケット、"
         "共有メモリなどを使用します。\n\n"
         "スレッドはプロセス内の実行単位で、同一プロセスのメモリ空間（コード、データ、ヒープ）を"
         "共有し、各スレッドは独自のスタックとレジスタを持ちます。\n\n"
         "**主な違い**:\n"
         "- メモリ: プロセスは独立、スレッドは共有\n"
         "- 生成コスト: プロセスは高い、スレッドは低い\n"
         "- コンテキストスイッチ: プロセスは重い、スレッドは軽い\n"
         "- 障害影響: プロセスは他に影響しない、スレッドは同一プロセス内に影響する可能性"),

        ("os", Language.KO,
         "프로세스와 스레드의 차이점을 설명해주세요.",
         "프로세스는 OS가 관리하는 프로그램의 실행 단위로, 독립된 메모리 공간(코드, 데이터, "
         "힙, 스택)을 가집니다. 프로세스 간 통신(IPC)에는 파이프, 소켓, "
         "공유 메모리 등을 사용합니다.\n\n"
         "스레드는 프로세스 내의 실행 단위로, 같은 프로세스의 메모리 공간(코드, 데이터, 힙)을 "
         "공유하며, 각 스레드는 자체 스택과 레지스터를 가집니다.\n\n"
         "**주요 차이점**:\n"
         "- 메모리: 프로세스는 독립, 스레드는 공유\n"
         "- 생성 비용: 프로세스는 높음, 스레드는 낮음\n"
         "- 컨텍스트 스위치: 프로세스는 무거움, 스레드는 가벼움\n"
         "- 장애 영향: 프로세스는 서로 영향 없음, 스레드는 같은 프로세스 내에 영향 가능"),

        ("os", Language.EN,
         "Explain the differences between processes and threads.",
         "A process is an OS-managed execution unit with independent memory space "
         "(code, data, heap, stack). Inter-process communication (IPC) uses pipes, "
         "sockets, or shared memory.\n\n"
         "A thread is an execution unit within a process, sharing the same memory space "
         "(code, data, heap) while each thread has its own stack and registers.\n\n"
         "**Key differences**:\n"
         "- Memory: Processes are independent; threads share memory\n"
         "- Creation cost: Processes are heavy; threads are lightweight\n"
         "- Context switch: Processes are expensive; threads are cheap\n"
         "- Fault isolation: Process crashes don't affect others; thread crashes "
         "can affect the entire process"),

        ("os", Language.JA,
         "仮想メモリの仕組みとページングを説明してください。",
         "仮想メモリは、物理メモリ（RAM）よりも大きなアドレス空間をプロセスに提供する技術です。"
         "OSがディスクの一部をメモリの延長として使用します。\n\n"
         "**ページング**: メモリを固定サイズのページ（通常4KB）に分割し、"
         "物理メモリのページフレームにマッピングします。ページテーブルが"
         "仮想アドレスと物理アドレスの対応関係を管理します。\n\n"
         "**ページフォルト**: アクセスしたページが物理メモリにない場合に発生。"
         "OSがディスクからページを読み込みます。\n\n"
         "**ページ置換アルゴリズム**:\n"
         "- LRU（Least Recently Used）: 最も長時間使われていないページを置換\n"
         "- FIFO: 最も古いページを置換\n"
         "- Clock: LRUの近似アルゴリズム\n\n"
         "TLB（Translation Lookaside Buffer）はページテーブルのキャッシュで、"
         "アドレス変換を高速化します。"),

        ("os", Language.KO,
         "가상 메모리의 원리와 페이징을 설명해주세요.",
         "가상 메모리는 물리 메모리(RAM)보다 큰 주소 공간을 프로세스에 제공하는 기술입니다. "
         "OS가 디스크의 일부를 메모리의 확장으로 사용합니다.\n\n"
         "**페이징**: 메모리를 고정 크기 페이지(보통 4KB)로 분할하고 "
         "물리 메모리의 페이지 프레임에 매핑합니다. 페이지 테이블이 "
         "가상 주소와 물리 주소의 대응 관계를 관리합니다.\n\n"
         "**페이지 폴트**: 접근한 페이지가 물리 메모리에 없을 때 발생합니다. "
         "OS가 디스크에서 페이지를 로드합니다.\n\n"
         "**페이지 교체 알고리즘**:\n"
         "- LRU(Least Recently Used): 가장 오래 사용되지 않은 페이지 교체\n"
         "- FIFO: 가장 오래된 페이지 교체\n"
         "- Clock: LRU의 근사 알고리즘\n\n"
         "TLB(Translation Lookaside Buffer)는 페이지 테이블의 캐시로, "
         "주소 변환을 고속화합니다."),

        ("os", Language.JA,
         "ファイルシステムの基本構造と種類を説明してください。",
         "ファイルシステムはストレージデバイス上のデータを構造化して管理する仕組みです。\n\n"
         "**基本構造**:\n"
         "- スーパーブロック: ファイルシステム全体の情報（サイズ、ブロック数等）\n"
         "- iノード: ファイルのメタデータ（権限、サイズ、データブロックへのポインタ）\n"
         "- データブロック: 実際のファイルデータ\n"
         "- ディレクトリ: ファイル名とiノード番号の対応表\n\n"
         "**主要なファイルシステム**:\n"
         "- ext4: Linuxの標準。ジャーナリング、エクステント対応\n"
         "- XFS: 大容量ファイルに最適。高パフォーマンス\n"
         "- NTFS: Windowsの標準。ACL、暗号化、圧縮対応\n"
         "- ZFS: コピーオンライト、スナップショット、データ整合性検証\n"
         "- Btrfs: ZFSに似た機能をLinuxで提供"),

        ("os", Language.EN,
         "Explain the basic structure and types of file systems.",
         "A file system structures and manages data on storage devices.\n\n"
         "**Basic structure**:\n"
         "- Superblock: Overall file system info (size, block count, etc.)\n"
         "- Inode: File metadata (permissions, size, pointers to data blocks)\n"
         "- Data blocks: Actual file data\n"
         "- Directories: Mapping of filenames to inode numbers\n\n"
         "**Major file systems**:\n"
         "- ext4: Linux standard with journaling and extents\n"
         "- XFS: Optimized for large files with high performance\n"
         "- NTFS: Windows standard with ACLs, encryption, compression\n"
         "- ZFS: Copy-on-write, snapshots, data integrity verification\n"
         "- Btrfs: ZFS-like features for Linux"),

        ("os", Language.JA,
         "CPUスケジューリングアルゴリズムの種類を説明してください。",
         "CPUスケジューリングはプロセスにCPU時間を割り当てるOSの機能です。\n\n"
         "**非プリエンプティブ方式**:\n"
         "- FCFS（First Come First Served）: 到着順に処理。コンボイ効果の問題あり\n"
         "- SJF（Shortest Job First）: 実行時間が短い順に処理。最適だが予測が困難\n\n"
         "**プリエンプティブ方式**:\n"
         "- ラウンドロビン: 各プロセスに均等なタイムスライスを割当。公平だが切替コストあり\n"
         "- 優先度スケジューリング: 優先度の高いプロセスから処理。飢餓問題が発生する可能性\n"
         "- SRTF（Shortest Remaining Time First）: 残り時間が最短のプロセスを優先\n"
         "- マルチレベルキュー: 複数のキューに優先度を設定して管理\n\n"
         "現代のOSはこれらを組み合わせたハイブリッド方式を使用しています。"),

        ("os", Language.KO,
         "CPU 스케줄링 알고리즘의 종류를 설명해주세요.",
         "CPU 스케줄링은 프로세스에 CPU 시간을 할당하는 OS의 기능입니다.\n\n"
         "**비선점형 방식**:\n"
         "- FCFS(First Come First Served): 도착 순서대로 처리. 호위 효과 문제 있음\n"
         "- SJF(Shortest Job First): 실행 시간이 짧은 순서로 처리. 최적이나 예측 곤란\n\n"
         "**선점형 방식**:\n"
         "- 라운드 로빈: 각 프로세스에 균등한 타임슬라이스 할당. 공정하나 전환 비용 있음\n"
         "- 우선순위 스케줄링: 우선순위가 높은 프로세스부터 처리. 기아 문제 발생 가능\n"
         "- SRTF(Shortest Remaining Time First): 남은 시간이 가장 짧은 프로세스 우선\n"
         "- 다단계 큐: 여러 큐에 우선순위를 설정하여 관리\n\n"
         "현대 OS는 이들을 조합한 하이브리드 방식을 사용합니다."),
    ])

    # ── 3. Networking ─────────────────────────────────────────────────

    bank.extend([
        ("networking", Language.JA,
         "OSI参照モデルの7層を説明してください。",
         "OSI参照モデルはネットワーク通信を7つの層に分けた標準モデルです。\n\n"
         "**第1層 物理層**: ビットの伝送（ケーブル、電圧、光信号）\n"
         "**第2層 データリンク層**: フレーム伝送、MAC制御（Ethernet、Wi-Fi）\n"
         "**第3層 ネットワーク層**: パケットルーティング（IP、ICMP）\n"
         "**第4層 トランスポート層**: 端末間の通信制御（TCP、UDP）\n"
         "**第5層 セッション層**: セッションの管理\n"
         "**第6層 プレゼンテーション層**: データ形式変換、暗号化\n"
         "**第7層 アプリケーション層**: アプリケーションのプロトコル（HTTP、SMTP、FTP）\n\n"
         "実際のTCP/IPモデルでは4層（ネットワークインターフェース、インターネット、"
         "トランスポート、アプリケーション）に簡略化されています。"),

        ("networking", Language.KO,
         "OSI 참조 모델의 7계층을 설명해주세요.",
         "OSI 참조 모델은 네트워크 통신을 7개 계층으로 나눈 표준 모델입니다.\n\n"
         "**제1계층 물리 계층**: 비트 전송 (케이블, 전압, 광신호)\n"
         "**제2계층 데이터 링크 계층**: 프레임 전송, MAC 제어 (Ethernet, Wi-Fi)\n"
         "**제3계층 네트워크 계층**: 패킷 라우팅 (IP, ICMP)\n"
         "**제4계층 전송 계층**: 종단 간 통신 제어 (TCP, UDP)\n"
         "**제5계층 세션 계층**: 세션 관리\n"
         "**제6계층 표현 계층**: 데이터 형식 변환, 암호화\n"
         "**제7계층 응용 계층**: 애플리케이션 프로토콜 (HTTP, SMTP, FTP)\n\n"
         "실제 TCP/IP 모델에서는 4계층(네트워크 인터페이스, 인터넷, "
         "전송, 응용)으로 간소화됩니다."),

        ("networking", Language.EN,
         "Explain the 7 layers of the OSI reference model.",
         "The OSI model divides network communication into 7 layers:\n\n"
         "**Layer 1 Physical**: Bit transmission (cables, voltages, optical signals)\n"
         "**Layer 2 Data Link**: Frame transmission, MAC control (Ethernet, Wi-Fi)\n"
         "**Layer 3 Network**: Packet routing (IP, ICMP)\n"
         "**Layer 4 Transport**: End-to-end communication (TCP, UDP)\n"
         "**Layer 5 Session**: Session management\n"
         "**Layer 6 Presentation**: Data format conversion, encryption\n"
         "**Layer 7 Application**: Application protocols (HTTP, SMTP, FTP)\n\n"
         "The TCP/IP model simplifies this into 4 layers: Network Interface, "
         "Internet, Transport, and Application."),

        ("networking", Language.JA,
         "TCPとUDPの違いを説明してください。",
         "TCP（Transmission Control Protocol）とUDP（User Datagram Protocol）は"
         "トランスポート層の主要プロトコルです。\n\n"
         "**TCP**:\n"
         "- コネクション型（3ウェイハンドシェイク）\n"
         "- 信頼性保証（再送制御、順序保証、フロー制御）\n"
         "- ヘッダサイズ: 20バイト以上\n"
         "- 用途: Web（HTTP/HTTPS）、メール、ファイル転送\n\n"
         "**UDP**:\n"
         "- コネクションレス型\n"
         "- 信頼性なし（再送なし、順序保証なし）\n"
         "- ヘッダサイズ: 8バイト（軽量）\n"
         "- 用途: DNS、動画ストリーミング、VoIP、オンラインゲーム\n\n"
         "TCPは信頼性が必要な通信、UDPはリアルタイム性が重要な通信に適しています。"),

        ("networking", Language.KO,
         "TCP와 UDP의 차이점을 설명해주세요.",
         "TCP(Transmission Control Protocol)와 UDP(User Datagram Protocol)는 "
         "전송 계층의 주요 프로토콜입니다.\n\n"
         "**TCP**:\n"
         "- 연결 지향형 (3-way handshake)\n"
         "- 신뢰성 보장 (재전송 제어, 순서 보장, 흐름 제어)\n"
         "- 헤더 크기: 20바이트 이상\n"
         "- 용도: Web(HTTP/HTTPS), 이메일, 파일 전송\n\n"
         "**UDP**:\n"
         "- 비연결형\n"
         "- 신뢰성 없음 (재전송 없음, 순서 보장 없음)\n"
         "- 헤더 크기: 8바이트 (경량)\n"
         "- 용도: DNS, 동영상 스트리밍, VoIP, 온라인 게임\n\n"
         "TCP는 신뢰성이 필요한 통신, UDP는 실시간성이 중요한 통신에 적합합니다."),

        ("networking", Language.JA,
         "HTTPSとTLS/SSLの仕組みを説明してください。",
         "HTTPS（HTTP over TLS/SSL）は、HTTP通信を暗号化して安全にするプロトコルです。\n\n"
         "**TLSハンドシェイク手順**:\n"
         "1. ClientHello: クライアントがサポートする暗号スイートを送信\n"
         "2. ServerHello: サーバーが暗号スイートを選択し、証明書を送信\n"
         "3. 証明書検証: クライアントがCA署名を検証\n"
         "4. 鍵交換: プリマスターシークレットを共有（RSAまたはDHE/ECDHE）\n"
         "5. セッション鍵生成: 共通鍵暗号（AES等）用の鍵を導出\n"
         "6. 暗号化通信開始\n\n"
         "**TLS 1.3の改良点**:\n"
         "- ハンドシェイクが1-RTTに短縮（1.2は2-RTT）\n"
         "- 脆弱な暗号スイート（RC4、SHA-1等）を廃止\n"
         "- 0-RTTモード（セッション再開時）のサポート"),

        ("networking", Language.EN,
         "Explain how HTTPS and TLS/SSL work.",
         "HTTPS (HTTP over TLS/SSL) encrypts HTTP communications for security.\n\n"
         "**TLS Handshake Process**:\n"
         "1. ClientHello: Client sends supported cipher suites\n"
         "2. ServerHello: Server selects cipher suite and sends certificate\n"
         "3. Certificate verification: Client validates CA signature\n"
         "4. Key exchange: Share pre-master secret (RSA or DHE/ECDHE)\n"
         "5. Session key derivation: Generate symmetric key (AES, etc.)\n"
         "6. Encrypted communication begins\n\n"
         "**TLS 1.3 Improvements**:\n"
         "- Handshake reduced to 1-RTT (1.2 required 2-RTT)\n"
         "- Removed weak cipher suites (RC4, SHA-1, etc.)\n"
         "- 0-RTT mode support for session resumption"),

        ("networking", Language.JA,
         "DNSの仕組みと名前解決プロセスを説明してください。",
         "DNS（Domain Name System）はドメイン名をIPアドレスに変換するシステムです。\n\n"
         "**名前解決プロセス**:\n"
         "1. ブラウザキャッシュを確認\n"
         "2. OSのhostsファイルを確認\n"
         "3. ローカルDNSリゾルバ（ISP提供）に問い合わせ\n"
         "4. ルートDNSサーバー（.の管理）に問い合わせ\n"
         "5. TLDサーバー（.com、.jpの管理）に問い合わせ\n"
         "6. 権威DNSサーバー（実際のレコード管理）が応答\n\n"
         "**主なレコードタイプ**:\n"
         "- A: IPv4アドレス\n"
         "- AAAA: IPv6アドレス\n"
         "- CNAME: エイリアス（別名）\n"
         "- MX: メールサーバー\n"
         "- TXT: テキスト情報（SPF、DKIM等）\n"
         "- NS: ネームサーバー\n\n"
         "TTL（Time To Live）はレコードのキャッシュ有効期間を制御します。"),

        ("networking", Language.KO,
         "DNS의 원리와 이름 해석 프로세스를 설명해주세요.",
         "DNS(Domain Name System)는 도메인명을 IP 주소로 변환하는 시스템입니다.\n\n"
         "**이름 해석 프로세스**:\n"
         "1. 브라우저 캐시 확인\n"
         "2. OS의 hosts 파일 확인\n"
         "3. 로컬 DNS 리졸버(ISP 제공)에 질의\n"
         "4. 루트 DNS 서버(. 관리)에 질의\n"
         "5. TLD 서버(.com, .kr 관리)에 질의\n"
         "6. 권한 DNS 서버(실제 레코드 관리)가 응답\n\n"
         "**주요 레코드 타입**:\n"
         "- A: IPv4 주소\n"
         "- AAAA: IPv6 주소\n"
         "- CNAME: 별칭(Alias)\n"
         "- MX: 메일 서버\n"
         "- TXT: 텍스트 정보 (SPF, DKIM 등)\n"
         "- NS: 네임서버\n\n"
         "TTL(Time To Live)은 레코드의 캐시 유효 기간을 제어합니다."),
    ])

    # ── 4. Security ───────────────────────────────────────────────────

    bank.extend([
        ("security", Language.JA,
         "対称鍵暗号と非対称鍵暗号の違いを説明してください。",
         "**対称鍵暗号**:\n"
         "暗号化と復号に同じ鍵を使用します。処理が高速で大量データの暗号化に適しています。\n"
         "- AES: 現在の標準（128/192/256ビット鍵）\n"
         "- 3DES: DESの後継（レガシーシステムで使用）\n"
         "- 課題: 鍵の安全な共有方法\n\n"
         "**非対称鍵暗号（公開鍵暗号）**:\n"
         "公開鍵と秘密鍵のペアを使用。公開鍵で暗号化、秘密鍵で復号します。\n"
         "- RSA: 最も普及（2048/4096ビット鍵）\n"
         "- ECC: 楕円曲線暗号（短い鍵長で同等のセキュリティ）\n"
         "- 課題: 対称鍵より処理が遅い\n\n"
         "**ハイブリッド方式**: TLS等では非対称鍵で鍵交換を行い、"
         "実際のデータ暗号化には対称鍵を使用するハイブリッド方式が一般的です。"),

        ("security", Language.KO,
         "대칭키 암호와 비대칭키 암호의 차이점을 설명해주세요.",
         "**대칭키 암호**:\n"
         "암호화와 복호화에 같은 키를 사용합니다. 처리가 빠르고 대용량 데이터 암호화에 적합합니다.\n"
         "- AES: 현재 표준 (128/192/256비트 키)\n"
         "- 3DES: DES 후계 (레거시 시스템에서 사용)\n"
         "- 과제: 키의 안전한 공유 방법\n\n"
         "**비대칭키 암호(공개키 암호)**:\n"
         "공개키와 개인키 쌍을 사용합니다. 공개키로 암호화, 개인키로 복호화합니다.\n"
         "- RSA: 가장 보편적 (2048/4096비트 키)\n"
         "- ECC: 타원곡선 암호 (짧은 키 길이로 동등한 보안성)\n"
         "- 과제: 대칭키보다 처리 속도가 느림\n\n"
         "**하이브리드 방식**: TLS 등에서는 비대칭키로 키 교환을 하고, "
         "실제 데이터 암호화에는 대칭키를 사용하는 하이브리드 방식이 일반적입니다."),

        ("security", Language.EN,
         "Explain the differences between symmetric and asymmetric encryption.",
         "**Symmetric Encryption**:\n"
         "Uses the same key for encryption and decryption. Fast processing, "
         "suitable for encrypting large data.\n"
         "- AES: Current standard (128/192/256-bit keys)\n"
         "- 3DES: DES successor (used in legacy systems)\n"
         "- Challenge: Secure key distribution\n\n"
         "**Asymmetric Encryption (Public Key Cryptography)**:\n"
         "Uses a public-private key pair. Encrypt with public key, decrypt with private.\n"
         "- RSA: Most widely used (2048/4096-bit keys)\n"
         "- ECC: Elliptic Curve Cryptography (equivalent security with shorter keys)\n"
         "- Challenge: Slower than symmetric encryption\n\n"
         "**Hybrid approach**: TLS uses asymmetric encryption for key exchange and "
         "symmetric encryption for actual data transfer."),

        ("security", Language.JA,
         "認証と認可の違いを説明してください。",
         "**認証（Authentication）**: ユーザーが本人であることを確認するプロセスです。\n"
         "- パスワード認証: 知識要素\n"
         "- 多要素認証（MFA）: 知識+所持+生体\n"
         "- OAuth 2.0 / OpenID Connect: トークンベース認証\n"
         "- 証明書認証: X.509証明書\n\n"
         "**認可（Authorization）**: 認証されたユーザーが何にアクセスできるかを"
         "制御するプロセスです。\n"
         "- RBAC（Role-Based Access Control）: ロール単位のアクセス制御\n"
         "- ABAC（Attribute-Based Access Control）: 属性ベースのアクセス制御\n"
         "- ACL（Access Control List）: リソースごとの権限リスト\n\n"
         "認証は「あなたは誰か」、認可は「何ができるか」を決定します。"
         "認証が先に行われ、その後認可が適用されます。"),

        ("security", Language.KO,
         "인증과 인가의 차이를 설명해주세요.",
         "**인증(Authentication)**: 사용자가 본인임을 확인하는 프로세스입니다.\n"
         "- 비밀번호 인증: 지식 요소\n"
         "- 다중 인증(MFA): 지식+소유+생체\n"
         "- OAuth 2.0 / OpenID Connect: 토큰 기반 인증\n"
         "- 인증서 인증: X.509 인증서\n\n"
         "**인가(Authorization)**: 인증된 사용자가 무엇에 접근할 수 있는지 "
         "제어하는 프로세스입니다.\n"
         "- RBAC(Role-Based Access Control): 역할 단위 접근 제어\n"
         "- ABAC(Attribute-Based Access Control): 속성 기반 접근 제어\n"
         "- ACL(Access Control List): 리소스별 권한 목록\n\n"
         "인증은 '당신이 누구인가', 인가는 '무엇을 할 수 있는가'를 결정합니다. "
         "인증이 먼저 수행되고, 이후 인가가 적용됩니다."),
    ])

    # ── 5. Software Engineering ───────────────────────────────────────

    bank.extend([
        ("software_engineering", Language.JA,
         "CI/CDパイプラインとは何ですか？",
         "CI/CD（継続的インテグレーション/継続的デリバリー）は、ソフトウェアの"
         "ビルド、テスト、デプロイを自動化するプラクティスです。\n\n"
         "**CI（継続的インテグレーション）**:\n"
         "- 開発者がコードを頻繁にメインブランチにマージ\n"
         "- 自動ビルドとテストが実行される\n"
         "- 問題を早期に検出して修正\n\n"
         "**CD（継続的デリバリー/デプロイメント）**:\n"
         "- 継続的デリバリー: 本番環境へのデプロイは手動承認\n"
         "- 継続的デプロイメント: テスト通過後に自動で本番へデプロイ\n\n"
         "**パイプラインの典型的なステージ**:\n"
         "1. ソースコードチェックアウト\n"
         "2. ビルド（コンパイル、パッケージング）\n"
         "3. ユニットテスト\n"
         "4. 統合テスト\n"
         "5. ステージング環境デプロイ\n"
         "6. E2Eテスト\n"
         "7. 本番環境デプロイ\n\n"
         "代表的なツール: Jenkins, GitLab CI, GitHub Actions, CircleCIなど。"),

        ("software_engineering", Language.KO,
         "CI/CD 파이프라인이란 무엇인가요?",
         "CI/CD(지속적 통합/지속적 전달)는 소프트웨어의 빌드, 테스트, "
         "배포를 자동화하는 프랙티스입니다.\n\n"
         "**CI(지속적 통합)**:\n"
         "- 개발자가 코드를 자주 메인 브랜치에 머지\n"
         "- 자동 빌드와 테스트 실행\n"
         "- 문제를 조기 발견하여 수정\n\n"
         "**CD(지속적 전달/배포)**:\n"
         "- 지속적 전달: 프로덕션 배포는 수동 승인\n"
         "- 지속적 배포: 테스트 통과 후 자동으로 프로덕션에 배포\n\n"
         "**파이프라인의 일반적인 스테이지**:\n"
         "1. 소스코드 체크아웃\n"
         "2. 빌드 (컴파일, 패키징)\n"
         "3. 단위 테스트\n"
         "4. 통합 테스트\n"
         "5. 스테이징 환경 배포\n"
         "6. E2E 테스트\n"
         "7. 프로덕션 배포\n\n"
         "대표적인 도구: Jenkins, GitLab CI, GitHub Actions, CircleCI 등."),

        ("software_engineering", Language.EN,
         "What is a CI/CD pipeline?",
         "CI/CD (Continuous Integration/Continuous Delivery) automates "
         "software building, testing, and deployment.\n\n"
         "**CI (Continuous Integration)**:\n"
         "- Developers frequently merge code to the main branch\n"
         "- Automated builds and tests are triggered\n"
         "- Issues are detected and fixed early\n\n"
         "**CD (Continuous Delivery/Deployment)**:\n"
         "- Continuous Delivery: Production deployment requires manual approval\n"
         "- Continuous Deployment: Automatically deploys to production after tests pass\n\n"
         "**Typical pipeline stages**:\n"
         "1. Source code checkout\n"
         "2. Build (compile, package)\n"
         "3. Unit tests\n"
         "4. Integration tests\n"
         "5. Staging deployment\n"
         "6. E2E tests\n"
         "7. Production deployment\n\n"
         "Popular tools: Jenkins, GitLab CI, GitHub Actions, CircleCI."),

        ("software_engineering", Language.JA,
         "デザインパターンの主要な種類を説明してください。",
         "デザインパターンはソフトウェア設計の再利用可能な解決策です。\n\n"
         "**生成パターン**:\n"
         "- Singleton: インスタンスを1つに制限\n"
         "- Factory Method: オブジェクト生成をサブクラスに委譲\n"
         "- Builder: 複雑なオブジェクトを段階的に構築\n"
         "- Abstract Factory: 関連オブジェクト群の生成\n\n"
         "**構造パターン**:\n"
         "- Adapter: インターフェースの変換\n"
         "- Decorator: 機能の動的追加\n"
         "- Facade: サブシステムの統一インターフェース\n"
         "- Proxy: オブジェクトへのアクセス制御\n\n"
         "**振る舞いパターン**:\n"
         "- Observer: 状態変化の通知\n"
         "- Strategy: アルゴリズムの切り替え\n"
         "- Template Method: アルゴリズムの骨格定義\n"
         "- Command: 操作のオブジェクト化"),

        ("software_engineering", Language.KO,
         "디자인 패턴의 주요 종류를 설명해주세요.",
         "디자인 패턴은 소프트웨어 설계의 재사용 가능한 해결책입니다.\n\n"
         "**생성 패턴**:\n"
         "- Singleton: 인스턴스를 하나로 제한\n"
         "- Factory Method: 객체 생성을 서브클래스에 위임\n"
         "- Builder: 복잡한 객체를 단계적으로 구축\n"
         "- Abstract Factory: 관련 객체 그룹의 생성\n\n"
         "**구조 패턴**:\n"
         "- Adapter: 인터페이스 변환\n"
         "- Decorator: 기능의 동적 추가\n"
         "- Facade: 서브시스템의 통합 인터페이스\n"
         "- Proxy: 객체 접근 제어\n\n"
         "**행위 패턴**:\n"
         "- Observer: 상태 변화 통보\n"
         "- Strategy: 알고리즘 교체\n"
         "- Template Method: 알고리즘 골격 정의\n"
         "- Command: 연산의 객체화"),

        ("software_engineering", Language.JA,
         "マイクロサービスとモノリスの違いを説明してください。",
         "**モノリシックアーキテクチャ**:\n"
         "- アプリケーション全体が1つのデプロイ単位\n"
         "- 全コンポーネントが同じプロセスで実行\n"
         "- メリット: シンプル、デプロイ容易、テスト容易\n"
         "- デメリット: スケーリングが困難、技術選択が制限、大規模チームで開発困難\n\n"
         "**マイクロサービスアーキテクチャ**:\n"
         "- 機能ごとに独立したサービスとしてデプロイ\n"
         "- 各サービスが独自のDB、技術スタックを持てる\n"
         "- API（REST/gRPC）やメッセージキューで連携\n"
         "- メリット: 独立スケーリング、技術多様性、チーム独立性\n"
         "- デメリット: 分散システムの複雑さ、ネットワーク通信コスト、"
         "データ一貫性の確保が困難\n\n"
         "選択基準: 小〜中規模はモノリス、大規模で独立スケーリングが必要なら"
         "マイクロサービスが適しています。"),

        ("software_engineering", Language.EN,
         "Explain the differences between microservices and monolithic architecture.",
         "**Monolithic Architecture**:\n"
         "- Entire application deployed as a single unit\n"
         "- All components run in the same process\n"
         "- Pros: Simple, easy to deploy and test\n"
         "- Cons: Hard to scale, limited technology choices, difficult for large teams\n\n"
         "**Microservices Architecture**:\n"
         "- Functions deployed as independent services\n"
         "- Each service can have its own DB and tech stack\n"
         "- Communication via APIs (REST/gRPC) or message queues\n"
         "- Pros: Independent scaling, technology diversity, team autonomy\n"
         "- Cons: Distributed system complexity, network overhead, "
         "data consistency challenges\n\n"
         "Guideline: Monolith for small-to-medium scale; microservices when "
         "independent scaling is required at large scale."),
    ])

    # ── 6. Cloud & Infrastructure ─────────────────────────────────────

    bank.extend([
        ("cloud", Language.JA,
         "コンテナとVMの違いを説明してください。",
         "**仮想マシン（VM）**:\n"
         "- ハイパーバイザー上でゲストOSを含む完全な仮想環境を実行\n"
         "- 各VMが独自のカーネルを持つ\n"
         "- メモリ: GB単位、起動: 分単位\n"
         "- 完全な分離性（セキュリティが高い）\n"
         "- 例: VMware、KVM、Hyper-V\n\n"
         "**コンテナ**:\n"
         "- ホストOSのカーネルを共有し、プロセスレベルで分離\n"
         "- 軽量でオーバーヘッドが少ない\n"
         "- メモリ: MB単位、起動: 秒単位\n"
         "- カーネル共有のため分離性はVMより低い\n"
         "- 例: Docker、containerd、Podman\n\n"
         "**使い分け**: VMは強い分離性が必要な場合、コンテナは軽量で素早い"
         "デプロイが必要なマイクロサービスに適しています。"),

        ("cloud", Language.KO,
         "컨테이너와 VM의 차이점을 설명해주세요.",
         "**가상 머신(VM)**:\n"
         "- 하이퍼바이저 위에서 게스트 OS를 포함한 완전한 가상 환경 실행\n"
         "- 각 VM이 자체 커널을 보유\n"
         "- 메모리: GB 단위, 부팅: 분 단위\n"
         "- 완전한 격리성 (보안성 높음)\n"
         "- 예: VMware, KVM, Hyper-V\n\n"
         "**컨테이너**:\n"
         "- 호스트 OS의 커널을 공유하고 프로세스 수준으로 격리\n"
         "- 경량이며 오버헤드가 적음\n"
         "- 메모리: MB 단위, 부팅: 초 단위\n"
         "- 커널 공유로 격리성은 VM보다 낮음\n"
         "- 예: Docker, containerd, Podman\n\n"
         "**사용 구분**: VM은 강한 격리성이 필요한 경우, 컨테이너는 경량으로 빠른 "
         "배포가 필요한 마이크로서비스에 적합합니다."),

        ("cloud", Language.EN,
         "Explain the differences between containers and virtual machines.",
         "**Virtual Machines (VMs)**:\n"
         "- Run complete virtual environments with guest OS on a hypervisor\n"
         "- Each VM has its own kernel\n"
         "- Memory: GB-scale, Boot: minutes\n"
         "- Complete isolation (high security)\n"
         "- Examples: VMware, KVM, Hyper-V\n\n"
         "**Containers**:\n"
         "- Share host OS kernel, isolated at process level\n"
         "- Lightweight with minimal overhead\n"
         "- Memory: MB-scale, Boot: seconds\n"
         "- Weaker isolation due to kernel sharing\n"
         "- Examples: Docker, containerd, Podman\n\n"
         "**When to use**: VMs for strong isolation needs; containers for lightweight "
         "and fast deployment in microservices."),

        ("cloud", Language.JA,
         "Kubernetesの基本概念とアーキテクチャを説明してください。",
         "Kubernetes（K8s）はコンテナオーケストレーションプラットフォームです。\n\n"
         "**主要コンポーネント**:\n"
         "- Pod: 最小デプロイ単位（1つ以上のコンテナ）\n"
         "- Deployment: Podのレプリカ管理とローリングアップデート\n"
         "- Service: Podへのネットワークアクセス（ClusterIP、NodePort、LoadBalancer）\n"
         "- Ingress: L7ロードバランシングとルーティング\n"
         "- ConfigMap/Secret: 設定とシークレットの管理\n"
         "- PersistentVolume: 永続ストレージ\n\n"
         "**コントロールプレーン**:\n"
         "- API Server: RESTful API（全通信のゲートウェイ）\n"
         "- etcd: 分散KVストア（クラスタ状態の保存）\n"
         "- Scheduler: Podの配置決定\n"
         "- Controller Manager: 望ましい状態の維持\n\n"
         "**ノード（Worker）**:\n"
         "- kubelet: コンテナの実行管理\n"
         "- kube-proxy: ネットワークルール管理"),

        ("cloud", Language.KO,
         "Kubernetes의 기본 개념과 아키텍처를 설명해주세요.",
         "Kubernetes(K8s)는 컨테이너 오케스트레이션 플랫폼입니다.\n\n"
         "**주요 컴포넌트**:\n"
         "- Pod: 최소 배포 단위 (1개 이상의 컨테이너)\n"
         "- Deployment: Pod 레플리카 관리 및 롤링 업데이트\n"
         "- Service: Pod 네트워크 접근 (ClusterIP, NodePort, LoadBalancer)\n"
         "- Ingress: L7 로드밸런싱과 라우팅\n"
         "- ConfigMap/Secret: 설정과 시크릿 관리\n"
         "- PersistentVolume: 영구 스토리지\n\n"
         "**컨트롤 플레인**:\n"
         "- API Server: RESTful API (모든 통신의 게이트웨이)\n"
         "- etcd: 분산 KV 스토어 (클러스터 상태 저장)\n"
         "- Scheduler: Pod 배치 결정\n"
         "- Controller Manager: 원하는 상태 유지\n\n"
         "**노드(Worker)**:\n"
         "- kubelet: 컨테이너 실행 관리\n"
         "- kube-proxy: 네트워크 규칙 관리"),
    ])

    # ── 7. Programming Concepts ───────────────────────────────────────

    bank.extend([
        ("programming", Language.JA,
         "オブジェクト指向プログラミングの4大原則を説明してください。",
         "OOP（オブジェクト指向プログラミング）の4大原則:\n\n"
         "**1. カプセル化（Encapsulation）**:\n"
         "データとそのデータを操作するメソッドを1つのクラスにまとめ、"
         "外部からのアクセスをアクセス修飾子（public/private/protected）で制御します。\n\n"
         "**2. 継承（Inheritance）**:\n"
         "既存クラス（親クラス）の属性とメソッドを新しいクラス（子クラス）が"
         "引き継ぎます。コードの再利用性を向上させます。\n\n"
         "**3. ポリモーフィズム（Polymorphism）**:\n"
         "同じインターフェースで異なる動作を実現します。メソッドのオーバーライド"
         "（実行時多態性）とオーバーロード（コンパイル時多態性）があります。\n\n"
         "**4. 抽象化（Abstraction）**:\n"
         "複雑な実装を隠し、必要なインターフェースのみを公開します。"
         "抽象クラスやインターフェースで実現します。"),

        ("programming", Language.KO,
         "객체지향 프로그래밍의 4대 원칙을 설명해주세요.",
         "OOP(객체지향 프로그래밍)의 4대 원칙:\n\n"
         "**1. 캡슐화(Encapsulation)**:\n"
         "데이터와 그 데이터를 조작하는 메서드를 하나의 클래스에 묶고, "
         "외부에서의 접근을 접근 제한자(public/private/protected)로 제어합니다.\n\n"
         "**2. 상속(Inheritance)**:\n"
         "기존 클래스(부모 클래스)의 속성과 메서드를 새로운 클래스(자식 클래스)가 "
         "물려받습니다. 코드 재사용성을 향상시킵니다.\n\n"
         "**3. 다형성(Polymorphism)**:\n"
         "같은 인터페이스로 다른 동작을 구현합니다. 오버라이딩(런타임 다형성)과 "
         "오버로딩(컴파일타임 다형성)이 있습니다.\n\n"
         "**4. 추상화(Abstraction)**:\n"
         "복잡한 구현을 숨기고 필요한 인터페이스만 공개합니다. "
         "추상 클래스나 인터페이스로 구현합니다."),

        ("programming", Language.EN,
         "Explain the four pillars of Object-Oriented Programming.",
         "The four pillars of OOP:\n\n"
         "**1. Encapsulation**:\n"
         "Bundles data and methods into a class, controlling external access "
         "with access modifiers (public/private/protected).\n\n"
         "**2. Inheritance**:\n"
         "A child class inherits attributes and methods from a parent class, "
         "improving code reusability.\n\n"
         "**3. Polymorphism**:\n"
         "Same interface, different behavior. Includes method overriding "
         "(runtime polymorphism) and overloading (compile-time polymorphism).\n\n"
         "**4. Abstraction**:\n"
         "Hides complex implementation, exposing only necessary interfaces. "
         "Achieved through abstract classes and interfaces."),

        ("programming", Language.JA,
         "REST APIの設計原則を説明してください。",
         "REST（Representational State Transfer）はWebサービス設計のアーキテクチャスタイルです。\n\n"
         "**6つの制約条件**:\n"
         "1. クライアント-サーバー分離\n"
         "2. ステートレス: 各リクエストが必要な情報をすべて含む\n"
         "3. キャッシュ可能: レスポンスのキャッシュ制御\n"
         "4. 統一インターフェース: リソース識別、自己記述メッセージ、HATEOAS\n"
         "5. レイヤードシステム: 中間層（LB、キャッシュ等）の透過性\n"
         "6. コードオンデマンド（オプション）\n\n"
         "**HTTPメソッドの使い分け**:\n"
         "- GET: リソース取得（冪等、安全）\n"
         "- POST: リソース作成\n"
         "- PUT: リソース全体更新（冪等）\n"
         "- PATCH: リソース部分更新\n"
         "- DELETE: リソース削除（冪等）\n\n"
         "**ステータスコード**: 200(成功), 201(作成), 400(不正リクエスト), "
         "401(未認証), 403(禁止), 404(未検出), 500(サーバーエラー)"),

        ("programming", Language.KO,
         "REST API 설계 원칙을 설명해주세요.",
         "REST(Representational State Transfer)는 웹 서비스 설계의 아키텍처 스타일입니다.\n\n"
         "**6가지 제약 조건**:\n"
         "1. 클라이언트-서버 분리\n"
         "2. 무상태성: 각 요청이 필요한 정보를 모두 포함\n"
         "3. 캐시 가능: 응답의 캐시 제어\n"
         "4. 통일 인터페이스: 리소스 식별, 자기 서술적 메시지, HATEOAS\n"
         "5. 계층화 시스템: 중간층(LB, 캐시 등)의 투명성\n"
         "6. 코드 온 디맨드 (선택 사항)\n\n"
         "**HTTP 메서드 사용법**:\n"
         "- GET: 리소스 조회 (멱등, 안전)\n"
         "- POST: 리소스 생성\n"
         "- PUT: 리소스 전체 업데이트 (멱등)\n"
         "- PATCH: 리소스 부분 업데이트\n"
         "- DELETE: 리소스 삭제 (멱등)\n\n"
         "**상태 코드**: 200(성공), 201(생성), 400(잘못된 요청), "
         "401(미인증), 403(금지), 404(미발견), 500(서버 에러)"),
    ])

    # ── 8. Data Structures & Algorithms ───────────────────────────────

    bank.extend([
        ("algorithms", Language.JA,
         "主要なソートアルゴリズムの比較を説明してください。",
         "**バブルソート**: O(n²) 平均/最悪。隣接要素を比較・交換。教育用。\n\n"
         "**選択ソート**: O(n²) 平均/最悪。最小値を選んで先頭に配置。不安定。\n\n"
         "**挿入ソート**: O(n²) 平均、O(n) 最良。ほぼ整列済みデータに効率的。安定。\n\n"
         "**マージソート**: O(n log n) 全ケース。分割統治法。安定。追加メモリO(n)必要。\n\n"
         "**クイックソート**: O(n log n) 平均、O(n²) 最悪。ピボット選択で分割。"
         "実用上最も高速だが不安定。\n\n"
         "**ヒープソート**: O(n log n) 全ケース。ヒープ構造利用。インプレースだが不安定。\n\n"
         "**ティムソート**: O(n log n) 平均、O(n) 最良。マージソート+挿入ソートの"
         "ハイブリッド。Python、Java等の標準ソート。安定。"),

        ("algorithms", Language.KO,
         "주요 정렬 알고리즘의 비교를 설명해주세요.",
         "**버블 정렬**: O(n²) 평균/최악. 인접 원소를 비교·교환. 교육용.\n\n"
         "**선택 정렬**: O(n²) 평균/최악. 최솟값을 선택하여 앞에 배치. 불안정.\n\n"
         "**삽입 정렬**: O(n²) 평균, O(n) 최선. 거의 정렬된 데이터에 효율적. 안정.\n\n"
         "**병합 정렬**: O(n log n) 전 케이스. 분할 정복법. 안정. 추가 메모리 O(n) 필요.\n\n"
         "**퀵 정렬**: O(n log n) 평균, O(n²) 최악. 피벗 선택으로 분할. "
         "실용적으로 가장 빠르지만 불안정.\n\n"
         "**힙 정렬**: O(n log n) 전 케이스. 힙 구조 이용. 제자리이나 불안정.\n\n"
         "**팀 정렬**: O(n log n) 평균, O(n) 최선. 병합 정렬+삽입 정렬의 "
         "하이브리드. Python, Java 등의 표준 정렬. 안정."),

        ("algorithms", Language.EN,
         "Compare the major sorting algorithms.",
         "**Bubble Sort**: O(n²) average/worst. Compares adjacent elements. Educational.\n\n"
         "**Selection Sort**: O(n²) average/worst. Selects minimum and places it first. Unstable.\n\n"
         "**Insertion Sort**: O(n²) average, O(n) best. Efficient for nearly sorted data. Stable.\n\n"
         "**Merge Sort**: O(n log n) all cases. Divide-and-conquer. Stable. Requires O(n) extra memory.\n\n"
         "**Quick Sort**: O(n log n) average, O(n²) worst. Pivot-based partitioning. "
         "Fastest in practice but unstable.\n\n"
         "**Heap Sort**: O(n log n) all cases. Uses heap structure. In-place but unstable.\n\n"
         "**Tim Sort**: O(n log n) average, O(n) best. Hybrid of merge sort and insertion sort. "
         "Standard sort in Python and Java. Stable."),

        ("algorithms", Language.JA,
         "ハッシュテーブルの仕組みと衝突解決方法を説明してください。",
         "ハッシュテーブルはキーをハッシュ関数でインデックスに変換し、"
         "O(1)の平均時間でデータにアクセスするデータ構造です。\n\n"
         "**ハッシュ関数の条件**:\n"
         "- 決定性: 同じキーは常に同じハッシュ値\n"
         "- 均一分布: ハッシュ値が均等に分布\n"
         "- 高速計算\n\n"
         "**衝突（Collision）解決方法**:\n\n"
         "1. **チェイニング（連鎖法）**:\n"
         "   - 各バケットにリンクリストを格納\n"
         "   - 最悪O(n)だが実装が簡単\n"
         "   - 負荷率が高くても性能低下が緩やか\n\n"
         "2. **オープンアドレッシング**:\n"
         "   - 線形探索法: 次のスロットを順に探索（クラスタリング問題あり）\n"
         "   - 二次探索法: 二次関数で探索位置を決定\n"
         "   - ダブルハッシング: 2つ目のハッシュ関数で探索間隔を決定\n\n"
         "負荷率（要素数/バケット数）が0.7-0.75を超えるとリハッシュ"
         "（テーブル拡張）を行い性能を維持します。"),

        ("algorithms", Language.KO,
         "해시 테이블의 원리와 충돌 해결 방법을 설명해주세요.",
         "해시 테이블은 키를 해시 함수로 인덱스로 변환하여 "
         "O(1) 평균 시간으로 데이터에 접근하는 자료구조입니다.\n\n"
         "**해시 함수 조건**:\n"
         "- 결정성: 같은 키는 항상 같은 해시값\n"
         "- 균등 분포: 해시값이 고르게 분포\n"
         "- 빠른 계산\n\n"
         "**충돌(Collision) 해결 방법**:\n\n"
         "1. **체이닝(연쇄법)**:\n"
         "   - 각 버킷에 연결 리스트 저장\n"
         "   - 최악 O(n)이나 구현이 간단\n"
         "   - 부하율이 높아도 성능 저하가 완만\n\n"
         "2. **개방 주소법**:\n"
         "   - 선형 탐사: 다음 슬롯을 순차 탐색 (클러스터링 문제 있음)\n"
         "   - 이차 탐사: 이차 함수로 탐색 위치 결정\n"
         "   - 이중 해싱: 두 번째 해시 함수로 탐색 간격 결정\n\n"
         "부하율(요소 수/버킷 수)이 0.7-0.75를 초과하면 리해싱"
         "(테이블 확장)을 수행하여 성능을 유지합니다."),
    ])

    # ── 9. Enterprise IT / Middleware ──────────────────────────────────

    bank.extend([
        ("enterprise", Language.JA,
         "メッセージキューの役割と代表的な製品を説明してください。",
         "メッセージキューは、非同期通信でアプリケーション間のメッセージを仲介するミドルウェアです。\n\n"
         "**主な役割**:\n"
         "- 非同期処理: 送信側は応答を待たずに次の処理に進める\n"
         "- 負荷分散: メッセージをワーカーに均等に分配\n"
         "- 疎結合: プロデューサーとコンシューマーが直接依存しない\n"
         "- バッファリング: トラフィックスパイクの吸収\n"
         "- 信頼性: メッセージの永続化と再配送\n\n"
         "**代表的な製品**:\n"
         "- Apache Kafka: 高スループット分散ストリーミング、イベント駆動\n"
         "- RabbitMQ: AMQPプロトコル、柔軟なルーティング\n"
         "- Amazon SQS: マネージドサービス、スケーラブル\n"
         "- Apache ActiveMQ: JMS準拠、エンタープライズ統合\n"
         "- Redis Streams: インメモリ高速処理\n\n"
         "パターン: Point-to-Point（1対1）とPub/Sub（1対多）があります。"),

        ("enterprise", Language.KO,
         "메시지 큐의 역할과 대표적인 제품을 설명해주세요.",
         "메시지 큐는 비동기 통신으로 애플리케이션 간 메시지를 중개하는 미들웨어입니다.\n\n"
         "**주요 역할**:\n"
         "- 비동기 처리: 송신 측이 응답을 기다리지 않고 다음 처리 진행\n"
         "- 부하 분산: 메시지를 워커에 균등 분배\n"
         "- 느슨한 결합: 프로듀서와 컨슈머가 직접 의존하지 않음\n"
         "- 버퍼링: 트래픽 스파이크 흡수\n"
         "- 신뢰성: 메시지 영속화 및 재전송\n\n"
         "**대표적인 제품**:\n"
         "- Apache Kafka: 고처리량 분산 스트리밍, 이벤트 구동\n"
         "- RabbitMQ: AMQP 프로토콜, 유연한 라우팅\n"
         "- Amazon SQS: 관리형 서비스, 스케일러블\n"
         "- Apache ActiveMQ: JMS 준수, 엔터프라이즈 통합\n"
         "- Redis Streams: 인메모리 고속 처리\n\n"
         "패턴: Point-to-Point(1대1)와 Pub/Sub(1대다)가 있습니다."),

        ("enterprise", Language.EN,
         "Explain the role of message queues and their major products.",
         "Message queues are middleware that broker messages between applications "
         "using asynchronous communication.\n\n"
         "**Key roles**:\n"
         "- Asynchronous processing: Sender proceeds without waiting for response\n"
         "- Load balancing: Distributes messages evenly to workers\n"
         "- Loose coupling: Producers and consumers are independent\n"
         "- Buffering: Absorbs traffic spikes\n"
         "- Reliability: Message persistence and redelivery\n\n"
         "**Major products**:\n"
         "- Apache Kafka: High-throughput distributed streaming, event-driven\n"
         "- RabbitMQ: AMQP protocol, flexible routing\n"
         "- Amazon SQS: Managed service, scalable\n"
         "- Apache ActiveMQ: JMS-compliant, enterprise integration\n"
         "- Redis Streams: In-memory high-speed processing\n\n"
         "Patterns: Point-to-Point (1:1) and Pub/Sub (1:many)."),

        ("enterprise", Language.JA,
         "ロードバランシングの方式を説明してください。",
         "ロードバランシングはトラフィックを複数のサーバーに分散させる技術です。\n\n"
         "**L4ロードバランサー（トランスポート層）**:\n"
         "- IP/ポートベースの振り分け\n"
         "- 高速だがコンテンツは考慮しない\n"
         "- 例: HAProxy（L4モード）、AWS NLB\n\n"
         "**L7ロードバランサー（アプリケーション層）**:\n"
         "- HTTP/HTTPSヘッダ、URL、Cookieベースの振り分け\n"
         "- コンテンツベースルーティングが可能\n"
         "- 例: Nginx、HAProxy（L7モード）、AWS ALB\n\n"
         "**分散アルゴリズム**:\n"
         "- ラウンドロビン: 順番に振り分け\n"
         "- 加重ラウンドロビン: サーバー性能に応じて重み付け\n"
         "- 最少接続: 接続数が最も少ないサーバーに振り分け\n"
         "- IPハッシュ: クライアントIPでサーバーを決定（セッション固定）\n"
         "- 最速応答: レスポンスタイムが最短のサーバーに振り分け"),

        ("enterprise", Language.KO,
         "로드 밸런싱의 방식을 설명해주세요.",
         "로드 밸런싱은 트래픽을 여러 서버에 분산시키는 기술입니다.\n\n"
         "**L4 로드밸런서(전송 계층)**:\n"
         "- IP/포트 기반 분배\n"
         "- 고속이나 콘텐츠는 고려하지 않음\n"
         "- 예: HAProxy(L4 모드), AWS NLB\n\n"
         "**L7 로드밸런서(응용 계층)**:\n"
         "- HTTP/HTTPS 헤더, URL, Cookie 기반 분배\n"
         "- 콘텐츠 기반 라우팅 가능\n"
         "- 예: Nginx, HAProxy(L7 모드), AWS ALB\n\n"
         "**분산 알고리즘**:\n"
         "- 라운드 로빈: 순서대로 분배\n"
         "- 가중 라운드 로빈: 서버 성능에 따라 가중치 부여\n"
         "- 최소 연결: 연결 수가 가장 적은 서버에 분배\n"
         "- IP 해시: 클라이언트 IP로 서버 결정 (세션 고정)\n"
         "- 최빠 응답: 응답 시간이 가장 짧은 서버에 분배"),
    ])

    # ── 10. General Computing ─────────────────────────────────────────

    bank.extend([
        ("computing", Language.JA,
         "文字エンコーディング（UTF-8、Shift_JIS、EUC-JP）の違いを説明してください。",
         "文字エンコーディングは文字をバイト列に変換する規則です。\n\n"
         "**UTF-8**:\n"
         "- Unicodeの可変長エンコーディング（1〜4バイト）\n"
         "- ASCIIと互換性あり（ASCII文字は1バイト）\n"
         "- 日本語は3バイト\n"
         "- Web標準（世界の98%以上のWebページで使用）\n\n"
         "**Shift_JIS**:\n"
         "- 日本語用の文字コード（MicrosoftがJIS X 0208を拡張）\n"
         "- ASCII互換（1バイト）＋日本語（2バイト）\n"
         "- Windows日本語環境で広く使用（歴史的）\n"
         "- 一部のバイト列がASCIIの`\\`や`~`と衝突する問題\n\n"
         "**EUC-JP**:\n"
         "- UNIX/Linux日本語環境の標準\n"
         "- JIS X 0208/0212に対応\n"
         "- ASCII互換（1バイト）＋日本語（2バイト）\n\n"
         "現在はUTF-8への統一が推奨されています。レガシーシステムでは"
         "Shift_JISやEUC-JPが残存しており、移行時に文字化けに注意が必要です。"),

        ("computing", Language.KO,
         "문자 인코딩(UTF-8, EUC-KR, CP949)의 차이점을 설명해주세요.",
         "문자 인코딩은 문자를 바이트 열로 변환하는 규칙입니다.\n\n"
         "**UTF-8**:\n"
         "- Unicode의 가변 길이 인코딩 (1~4바이트)\n"
         "- ASCII와 호환 (ASCII 문자는 1바이트)\n"
         "- 한글은 3바이트\n"
         "- 웹 표준 (전 세계 98% 이상의 웹페이지에서 사용)\n\n"
         "**EUC-KR**:\n"
         "- 한국어용 문자 코드 (KS X 1001 기반)\n"
         "- 완성형 한글 2,350자 지원\n"
         "- Unix/Linux 한국어 환경에서 사용\n\n"
         "**CP949 (MS949)**:\n"
         "- Microsoft가 EUC-KR을 확장\n"
         "- 완성형 한글 11,172자 전체 지원\n"
         "- Windows 한국어 환경에서 사용\n\n"
         "현재는 UTF-8로의 통일이 권장됩니다. 레거시 시스템에서는 "
         "EUC-KR/CP949가 남아있어 마이그레이션 시 인코딩 변환에 주의가 필요합니다."),

        ("computing", Language.EN,
         "Explain the differences between character encodings (UTF-8, ASCII, ISO-8859-1).",
         "Character encoding converts characters to byte sequences.\n\n"
         "**ASCII**:\n"
         "- 7-bit encoding (128 characters)\n"
         "- English letters, digits, basic punctuation\n"
         "- 1 byte per character\n"
         "- Foundation for all modern encodings\n\n"
         "**ISO-8859-1 (Latin-1)**:\n"
         "- 8-bit extension of ASCII (256 characters)\n"
         "- Supports Western European languages\n"
         "- 1 byte per character\n\n"
         "**UTF-8**:\n"
         "- Variable-length Unicode encoding (1-4 bytes)\n"
         "- ASCII-compatible (ASCII characters use 1 byte)\n"
         "- Supports all Unicode characters (150,000+)\n"
         "- Web standard (used by 98%+ of web pages)\n"
         "- CJK characters use 3 bytes\n\n"
         "UTF-8 is the recommended encoding for all modern systems. "
         "Legacy systems may still use regional encodings, requiring "
         "careful conversion during migration."),

        ("computing", Language.JA,
         "キャッシュの仕組みと戦略を説明してください。",
         "キャッシュは頻繁にアクセスされるデータを高速な記憶装置に保存して"
         "アクセス速度を向上させる技術です。\n\n"
         "**キャッシュ階層（CPUの場合）**:\n"
         "- L1キャッシュ: 最速（1-3ns）、容量小（32-64KB）\n"
         "- L2キャッシュ: 中速（3-10ns）、中容量（256KB-1MB）\n"
         "- L3キャッシュ: やや遅い（10-20ns）、大容量（数MB-数十MB）\n"
         "- メインメモリ: 遅い（50-100ns）\n\n"
         "**アプリケーションキャッシュ戦略**:\n"
         "- Cache Aside: アプリケーションがキャッシュを直接管理\n"
         "- Read Through: キャッシュがDBからデータを自動取得\n"
         "- Write Through: 書き込み時にキャッシュとDBを同時更新\n"
         "- Write Behind: 書き込みをキャッシュに行い、非同期でDBに反映\n\n"
         "**キャッシュ無効化**:\n"
         "- TTL（Time To Live）: 有効期限で自動無効化\n"
         "- イベント駆動: データ変更時に明示的に無効化\n"
         "- LRU（Least Recently Used）: 最も古いエントリを削除"),

        ("computing", Language.KO,
         "캐시의 원리와 전략을 설명해주세요.",
         "캐시는 자주 접근하는 데이터를 고속 저장 장치에 보관하여 "
         "접근 속도를 향상시키는 기술입니다.\n\n"
         "**캐시 계층(CPU의 경우)**:\n"
         "- L1 캐시: 최고속(1-3ns), 소용량(32-64KB)\n"
         "- L2 캐시: 중속(3-10ns), 중용량(256KB-1MB)\n"
         "- L3 캐시: 약간 느림(10-20ns), 대용량(수MB-수십MB)\n"
         "- 메인 메모리: 느림(50-100ns)\n\n"
         "**애플리케이션 캐시 전략**:\n"
         "- Cache Aside: 애플리케이션이 캐시를 직접 관리\n"
         "- Read Through: 캐시가 DB에서 데이터를 자동 조회\n"
         "- Write Through: 쓰기 시 캐시와 DB를 동시 갱신\n"
         "- Write Behind: 쓰기를 캐시에 수행하고 비동기로 DB에 반영\n\n"
         "**캐시 무효화**:\n"
         "- TTL(Time To Live): 유효 기간으로 자동 무효화\n"
         "- 이벤트 기반: 데이터 변경 시 명시적 무효화\n"
         "- LRU(Least Recently Used): 가장 오래된 항목 삭제"),

        ("computing", Language.JA,
         "GitのブランチモデルとGit Flowを説明してください。",
         "Gitはバージョン管理システムで、ブランチを使って並行開発を行います。\n\n"
         "**Git Flowモデル**:\n"
         "- main（master）: リリース済みの安定バージョン\n"
         "- develop: 開発中の最新コード\n"
         "- feature/*: 新機能開発用ブランチ（developから分岐）\n"
         "- release/*: リリース準備用ブランチ（developから分岐）\n"
         "- hotfix/*: 緊急修正用ブランチ（mainから分岐）\n\n"
         "**トランクベース開発**:\n"
         "- 短命ブランチ（1-2日）でmainに直接マージ\n"
         "- フィーチャーフラグで未完成機能を制御\n"
         "- CI/CDとの相性が良い\n\n"
         "**GitHub Flow**:\n"
         "- mainブランチ＋featureブランチのシンプルモデル\n"
         "- プルリクエストでコードレビュー後マージ\n"
         "- 小規模〜中規模チームに適しています"),

        ("computing", Language.EN,
         "Explain Git branching models and Git Flow.",
         "Git is a version control system that uses branches for parallel development.\n\n"
         "**Git Flow Model**:\n"
         "- main (master): Stable released versions\n"
         "- develop: Latest development code\n"
         "- feature/*: New feature branches (from develop)\n"
         "- release/*: Release preparation branches (from develop)\n"
         "- hotfix/*: Emergency fix branches (from main)\n\n"
         "**Trunk-Based Development**:\n"
         "- Short-lived branches (1-2 days) merged directly to main\n"
         "- Feature flags control incomplete features\n"
         "- Works well with CI/CD\n\n"
         "**GitHub Flow**:\n"
         "- Simple model: main + feature branches\n"
         "- Pull requests for code review before merging\n"
         "- Suitable for small to medium teams"),
    ])

    return bank


class GeneralKnowledgeGenerator:
    """Generate general IT/CS knowledge SFT records."""

    def __init__(self, config: GenerationConfig):
        self.config = config
        self._bank = _build_qa_bank()

    def generate(self, target_count: int) -> List[SFTRecord]:
        """Generate target_count general knowledge SFT records.

        Records are distributed across languages matching the bank distribution,
        then scaled to target_count via repetition with shuffle.
        """
        # Build base records from the Q&A bank
        base_records: List[SFTRecord] = []
        for category, lang, question, answer in self._bank:
            system_prompt = _SYSTEM_PROMPTS.get(lang, _SYSTEM_PROMPTS[Language.EN])
            record = SFTRecord(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                product="general_knowledge",
                language=lang,
                category=SFTCategory.GENERAL_KNOWLEDGE,
                item_type=ItemType.GENERAL,
                source_file=f"general_knowledge/{category}",
                source_page=0,
                products_involved=[],
            )
            base_records.append(record)

        logger.info(
            "General knowledge bank: %d unique Q&A pairs", len(base_records)
        )

        if not base_records:
            return []

        # Scale to target count
        if len(base_records) >= target_count:
            random.shuffle(base_records)
            return base_records[:target_count]

        # Repeat + shuffle to reach target count
        result: List[SFTRecord] = []
        while len(result) < target_count:
            batch = list(base_records)
            random.shuffle(batch)
            result.extend(batch)

        result = result[:target_count]
        random.shuffle(result)

        logger.info(
            "General knowledge: %d records generated (target=%d)",
            len(result), target_count,
        )
        return result
