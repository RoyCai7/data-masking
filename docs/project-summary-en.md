# Data Masking Service (DMS) - Complete Solution

## Project Overview

| Item | Details |
|------|---------|
| **Timeline** | Feb 23, 2026 – Feb 22, 2027 (52 Weeks) |
| **Team** | Roy Cai, Richard Fan |

---

## 🎯 Project Vision & Goals

DMS aims to automate the manual, error-prone process of data masking. It transitions engineers from a 30–60 minute manual task to a **< 5-minute** automated workflow, ensuring 100% data privacy in the AI era.

- **Efficiency** — 90% reduction in manual review time
- **Reliability** — ≥ 95% masking accuracy
- **Scalability** — Processing 1GB files in under 5 minutes

---

## 🏗️ 3-Module Architecture

The solution provides three distinct channels to cover all user scenarios:

| Module | Target Users | Description |
|--------|-------------|-------------|
| **Web UI (File Upload)** | End Users | Drag-and-drop interface for standalone file processing. Real-time progress bars, result previews, and visual risk reports (charts/tables) |
| **REST API (Integration)** | Developers | Programmable endpoints (`/mask`, `/status`, `/rules`) for CI/CD pipelines and third-party tools. Powered by FastAPI with asynchronous task handling and rate limiting |
| **Tampermonkey Script (Browser Assistant)** | All Staff | Automatically detects and masks sensitive data during input/paste on sites like Bugzilla, ChatGPT, and Jira. Zero context switch — masks content directly within the browser before submission |

---

## 💻 Technology Stack

- **Backend**: Python 3.10+, FastAPI, SQLite (Rule Library), Docker
- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite
- **Masking Engine**: Regex-based matching supporting multiple strategies (Asterisk, Hash, Placeholder, Partial)
- **Performance**: 16-thread concurrency and stream processing for large archives (.zip, .tar.gz)

---

## 📅 Roadmap Highlights

| Phase | Period | Goals |
|-------|--------|-------|
| **Phase 1: Core Foundation** | W1–W8 | Build the FastAPI framework, regex engine, and basic Web UI (MVP **v0.5**) |
| **Phase 2: Feature Complete** | W9–W20 | Implement API authentication, multi-page script support, and QE integration testing |
| **Phase 3: Enhancement** | W21–W36 | Expand rule library (20+ types), optimize 1GB+ file handling, and refine UI/UX (**v1.0**) |
| **Phase 4: Launch** | W37–W52 | Security hardening, production deployment (Docker/K8s), and official user training |

---

## 📊 Key Performance Indicators (KPIs)

| Metric | Baseline (Manual) | Target (DMS v1.0) |
|--------|:-----------------:|:------------------:|
| Processing Speed | 30–60 min / 100MB | **< 30 sec / 100MB** |
| Detection Accuracy | ~80% | **≥ 95%** |
| Concurrent Tasks | N/A | **≥ 8 Tasks** |
| QE Team Adoption | 0 Teams | **≥ 2 Teams** |

---

## ✅ Success Criteria

- **Functional**: Support for `.log`, `.txt`, `.gz`, `.zip` formats; detailed risk scoring; custom rule management
- **Quality**: 100% fix rate for P0/P1 bugs; ≥ 70% unit test coverage
- **Security**: Data encryption in transit and storage; comprehensive audit logging

---

> **Next Step**: Complete W4 performance benchmarking and finalize the v0.5 MVP for initial QE feedback.
