# Fujitsu XSP/AIM Quick Reference Guide

**Quick Navigation for Developers & Migration Engineers**

---

## At a Glance

### Fujitsu XSP (OSIV/XSP)
- **Type**: Mid-range general-purpose operating system
- **Release**: November 1990
- **Predecessors**: OSIV/ESPIII (medium) + OSIV/X8 FSP (large)
- **Purpose**: Integrated database processing + distributed computing
- **Platform**: Fujitsu M Series computers, GlobalServer GS series

### AIM (Advanced Information Manager)
- **Original Release**: 1977 (FACOM M series)
- **Components**:
  - **AIM/DB**: Network CODASYL database management system
  - **AIM/DC**: DB/DC (database + data communication) system
  - **IDCM**: Integrated Data Communication Monitor (inter-program communication)

### Fujitsu Architecture Foundation
- **Processor**: IBM System/370 architecture (intentional compatibility)
- **Performance**: 2-3× faster than IBM 370/168
- **Database**: SymfoWARE relational system (1995+)
- **Networking**: VTAM-G V30 (multi-vendor, TCP/IP capable)

---

## System Components Quick Map

```
OSIV/XSP Architecture:
┌─ Batch Processing (JES) ─────────────────────┐
├─ Online Processing (AIM/DC + IDCM) ──────────┤
├─ Database (AIM/DB + SymfoWARE) ──────────────┤
├─ Networking (VTAM-G + TCP/IP) ────────────────┤
├─ Development (SDAS) ─────────────────────────┤
└─ System Management (Operation Manager) ──────┘
```

---

## File Systems Supported

| Type | Name | Use Case | Subtypes |
|------|------|----------|----------|
| Index | VSAM | Online databases | KSDS, ESDS, LDS |
| Member | PDS | Program libraries | Standard PDS, PDSE |
| Sequential | PS | Batch files | Fixed/variable length |

**Key Tools**:
- IDCAMS: VSAM management
- IEBGENER: Sequential file operations
- IEBCOPY: PDS member operations

---

## Job Scheduling and Batch

**Components**:
- JCL: Job Control Language (JOB, EXEC, DD statements)
- JES: Job Entry Subsystem (job queuing & execution)
- EXCEL BATCH: Concurrent execution with optimized I/O
- Systemwalker: Advanced job scheduling and monitoring

---

## Character Encoding

**Primary**: EBCDIC with JEF (Japanese Extended Feature)
- JEF Codepage: EBCDIC + JIS X 0208 + Fujitsu extensions
- Released: April 1979
- Structure: Stateful two-byte encoding
- Conversion: JEF ↔ Unicode via TF-MDPORT

**For Japanese data migration**:
```
Fujitsu System (JEF/EBCDIC)
         ↓
Unicode Conversion (TF-MDPORT)
         ↓
Linux/Cloud System (UTF-8)
```

---

## FACOM M Series Models

| Generation | Model | Year | Scale | Performance |
|-----------|-------|------|-------|-------------|
| Phase 1 | M-190 | 1974 | Ultra-large | 2-3× IBM 370/168 |
| Phase 1 | M-160/180 | 1974 | Large | High |
| Phase 2 | M-100 Series | 1977 | Mid-range | Scalable |
| Phase 3 | M-300 Series | 1980s | Enhanced | Improved |
| Phase 3 | M-700 Series | 1980s | Enhanced | Advanced |

All supported OSIV series:
- OSII, OSIV/F2, OSIV/F4, OSIV/ESPIII, OSIV/X8 FSP
- OSIV/XSP (1990, integrated), OSIV/MSP (large-scale)

---

## GlobalServer GS21 Lineup

| Model | Memory | Scale | Use Case |
|-------|--------|-------|----------|
| GS21-400 | Scalable | Department | Mid-scale |
| GS21-500 | 64 GB | Enterprise | Large |
| GS21-900+ | Scalable | Enterprise | High throughput |
| GS21-2400 | Scalable | Ultra-large | Mission-critical |
| GS21-2600 | Scalable | Ultra-large | Maximum performance |

**Features**: System-on-chip, CMOS, 50% power reduction, 24×7 availability

---

## AIM/DB Key Features

```
Network Database Model (CODASYL):
- Set definitions (hierarchical relationships)
- Record types (structured data)
- DML queries (data manipulation)
- Extended indexes (key-based access)
- Database support functions (recovery, locks)
```

**Capabilities**:
- Cluster-shared databases (1989)
- Hot standby with System Storage Units
- Remote database backup (1995)
- Web linkage and application integration (1996+)
- Real-time replication

**Migration Path**:
- AIM/DB → IBM DB2 (requires specialized conversion tools)
- AIM/DB → SQL databases (schema and data extraction)

---

## AIM/DC and IDCM

**AIM/DC Purpose**: Unified database + data communication

**IDCM (Integrated Data Communication Monitor)**:
- Inter-program communication broker
- TCP/IP + OSI network support
- Peer-to-peer distributed processing
- Transaction coordination
- Message routing and queuing

---

## Networking Components

**VTAM-G V30**:
- FNA5 (Fujitsu Network Architecture 5) core
- OSI component support
- Multi-vendor interoperability

**VTAM-G TISP**:
- TCP/IP connectivity
- UNIX/workstation support
- Ethernet 802.3 + FDDI support

**Result**: GlobalServer can integrate with:
- Other Fujitsu systems
- IBM mainframes
- UNIX servers
- PC networks
- Cloud infrastructure

---

## SymfoWARE Relational Database

- **Release**: 1995 (evolved from RDB II)
- **Architecture**: Hybrid (Fujitsu tech + PostgreSQL open source)
- **Platforms**: Mainframe, UNIX, PC
- **Management**: GUI Object Manager (cross-platform)
- **Compliance**: ODBC for client access

---

## OSIV/MSP (Super-Large Scale)

- **Release**: June 1989
- **Purpose**: Ultra-large enterprise systems
- **Architecture**: EXA (Extended Architecture)
- **Enhancements**:
  - 16 TB virtual memory (1990)
  - SURE SYSTEM 2000 support
  - EXCEL BATCH processing
  - Disaster recovery (1997)

---

## Migration to OpenFrame

### Compatibility Strength
- IBM System/370 architecture → High source code compatibility
- Standard file formats → Minimal conversion
- JCL → Well-understood by OpenFrame
- COBOL → Wide tool support

### Key Migration Steps

```
Fujitsu System Analysis
    ├─ Inventory COBOL (NetCOBOL support via ofcbppf)
    ├─ Document AIM/DB schema
    ├─ Catalog character encoding (JEF → Unicode)
    ├─ Map IDCM implementations
    ├─ Plan SymfoWARE migration (→ PostgreSQL/SQL)
    └─ Test file format conversions

OpenFrame Rehosting
    ├─ Code conversion (PROGRESSION tool or manual)
    ├─ Data migration (schema + character set)
    ├─ Database layer setup
    ├─ Job scheduling reconfiguration
    ├─ Online transaction layer mapping
    └─ Testing and validation

Cloud Deployment
    ├─ Linux/container preparation
    ├─ Performance tuning
    ├─ High availability setup
    └─ Operational handoff
```

### Fujitsu Modernization Tools
- **PROGRESSION**: 100% automatic COBOL → C#/.NET/Java, 80% cost reduction
- **NetCOBOL Compatibility**: Maintains IBM extensions during migration
- **Character Set Conversion**: TF-MDPORT for encoding transformations

### OpenFrame Documentation
- [Official Migration Guide](https://docs.tmaxsoft.com/en/openframe_common/7.1_MVS/migration-guide/chapter-application-migration-mvs.html)
- [Getting Started Guide](https://docs.tmaxsoft.com/en/openframe_common/7.1_MVS/getting-started-guide/chapter-openframe-migration-mvs.html)

---

## Troubleshooting & Known Issues

| Issue | Fujitsu-Specific | Solution |
|-------|-----------------|----------|
| COBOL dialect incompatibility | NetCOBOL extensions | Use ofcbppf, compatibility layer |
| Character corruption | JEF ↔ UTF-8 mismatch | TF-MDPORT conversion |
| AIM/DB data loss | Network DB schema | Dump-and-restore approach |
| IDCM protocol issues | Custom messaging | Protocol bridge or rewrite |
| Performance degradation | SymfoWARE tuning | SQL optimization, indexing |

---

## Key Contacts and Resources

### Official Documentation
- **Fujitsu GlobalServer**: https://www.fujitsu.com/global/products/computing/servers/mainframe/globalserver/
- **GS21 Series**: https://www.fujitsu.com/global/products/computing/servers/mainframe/globalserver/lineup/
- **Software Stack**: https://www.fujitsu.com/global/products/computing/servers/mainframe/globalserver/software/

### Technical Archives
- **IPSJ Computer Museum**: https://museum.ipsj.or.jp/en/computer/os/fujitsu/
- **OSIV/XSP Details**: https://museum.ipsj.or.jp/en/computer/os/fujitsu/0015.html
- **FACOM M Series**: http://museum.ipsj.or.jp/en/computer/main/0033.html

### Migration Services
- **TmaxSoft OpenFrame**: https://www.tmaxsoft.com/en/solution/view?solutionSeq=43
- **Fujitsu Modernization**: https://www.fujitsu.com/global/services/application-services/application-transformation/mainframe-modernization/

### Character Encoding
- **JEF Reference**: https://en.wikibooks.org/wiki/Character_Encodings/Code_Tables/EBCDIC/JEF_codepage
- **Japanese Encodings**: https://www.sljfaq.org/afaq/encodings.html

---

## Japanese Resources (Language-Specific)

| Resource | URL | Content |
|----------|-----|---------|
| Fujitsu AIM/DB JP | https://www.fujitsu.com/jp/products/computing/servers/mainframe/gs21/software/aim-db/ | Product details |
| Fujitsu IDCM JP | https://www.fujitsu.com/jp/products/computing/servers/mainframe/gs21/software/idcm/ | Monitor details |
| GS21 JP Details | https://www.fujitsu.com/jp/products/computing/servers/mainframe/gs21/ | Full lineup |
| Mainframe Architecture (Qiita) | https://qiita.com/tm-hack/items/afc801b05e2f8f4e9d18 | Community deep dives |

---

## Comparison: Fujitsu vs. IBM Mainframe

| Aspect | Fujitsu (FACOM/GlobalServer) | IBM (S/390/z/OS) |
|--------|-----|-----|
| **Architecture** | System/370 compatible | System/370 native |
| **Performance** | 2-3× faster | Reference baseline |
| **Database** | AIM/DB + SymfoWARE | DB2 + Information Management System |
| **Networking** | VTAM-G + OSI | VTAM + OSI |
| **Batch** | JES-like + EXCEL BATCH | JES |
| **TP Monitor** | AIM/DC + IDCM | CICS/IMS |
| **Operating System** | OSIV/XSP, OSIV/MSP | MVS/z/OS |
| **Character Sets** | JEF (EBCDIC+JIS) | EBCDIC + ASCII variants |

**Migration Implication**: High code compatibility due to shared System/370 architecture, but system-specific tools and libraries require adaptation.

---

## Version Compatibility Matrix

| OS | Release | Scale | Supported Hardware |
|----|---------|-------|-------------------|
| OSIV/ESPIII | 1980s | Medium | FACOM M-100/200 |
| OSIV/XSP | 1990+ | Mid-range | FACOM M-series, GS21 |
| OSIV/MSP | 1989+ | Large-scale | M-1800, GS21 large |
| OSIV/F4 | Earlier | Large | FACOM M-series |

**Implication**: XSP/MSP are current standards; migration should target these or modern GS21 platforms.

---

## Document Versions

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-18 | Initial comprehensive research compilation |

---

*Last Validated: 2026-02-18*
*Source: 20+ official and archival sources*
