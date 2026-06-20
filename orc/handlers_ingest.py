"""적재 루프 데모 핸들러 — 결정적(LLM·네트워크 불필요). INGEST_DEMO spec.

scripts/INGEST-AGENT.md의 자기검증 루프(Step->verify->유계재시도->차단기)를
로컬 파일 작업으로 재현한 인스턴스. 실 GCS·다운로드가 아니라 로컬 임시폴더라
키·네트워크 없이 샌드박스에서 그대로 돈다. silent mock이 아니라 실제 파일 I/O를
수행한다(체크섬·크기 대조가 진짜로 계산됨).

비교 작업과 액션·검수기·DIAGNOSIS가 전부 다르지만 *같은 엔진*에서 돈다 —
이게 도메인 무관(설정만 바꾸면 다른 작업)의 증거다.
"""
import glob as _glob
import hashlib
import os
import re as _re
import shutil
import subprocess as _sp
import tempfile
from .registry import action, acceptance
from .util import log, step_by_id, inject_fault


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@action("fetch_local")
async def _fetch(state, artifacts):
    items = state["constraints"]["definition"]["items"]
    wd = artifacts.get("workdir") or tempfile.mkdtemp(prefix="orc_ingest_")
    artifacts["workdir"] = wd
    payload = {}
    for it in items:
        data = (it * 1024).encode()                          # 결정적 바이트(재현 가능)
        path = os.path.join(wd, f"{it}.bin")
        with open(path, "wb") as f:
            f.write(data)
        payload[it] = {"path": path, "expected_sha": _sha(data), "size": len(data)}
    artifacts["payload"] = payload
    log(state, "TOOL", "fetch_local", "ok", rout=f"{len(payload)} items -> {wd}")


@action("verify_checksum")
async def _verify_cs(state, artifacts):
    step = step_by_id(state, state["cursor"])
    corrupt = inject_fault(state, step)                       # 의도적 실패: 검증값 어긋나게
    all_ok = True
    for meta in artifacts.get("payload", {}).values():
        with open(meta["path"], "rb") as f:
            actual = _sha(f.read())
        if corrupt:
            actual = "corrupted"
        all_ok = all_ok and (actual == meta["expected_sha"])
    artifacts["checksum_ok"] = all_ok
    log(state, "TOOL", "verify_checksum", "ok" if all_ok else "fail", rout=f"checksum_ok={all_ok}")


@action("store_local")
async def _store(state, artifacts):
    store = os.path.join(artifacts["workdir"], "store")
    os.makedirs(store, exist_ok=True)
    stored = {}
    for it, meta in artifacts.get("payload", {}).items():
        dst = os.path.join(store, os.path.basename(meta["path"]))
        shutil.copyfile(meta["path"], dst)
        stored[it] = {"path": dst, "size": os.path.getsize(dst), "expected_size": meta["size"]}
    artifacts["stored"] = stored
    log(state, "TOOL", "store_local", "ok", rout=f"{len(stored)} stored")


@acceptance("stored_size_match")
def _size_match(state, acc):
    """적재본 크기가 원본과 일치하는지(구조검증, 결정적). 적재 2게이트 중 크기대조."""
    stored = state["artifacts"].get("stored", {})
    ok = bool(stored) and all(s["size"] == s["expected_size"] for s in stored.values())
    return {"passed": ok, "cause": None if ok else acc["cause"]}


# ─────── 실 AI Hub 적재 (71918/71921) — INGEST_AIHUB spec용. 실 I/O(aihubshell/gsutil) ───────
# INGEST-AGENT.md의 download → unzip -t → upload → size-match(로컬==GCS) → delete + DIAGNOSIS·
# 차단기·HITL을 orc 액션으로 1:1 매핑. demo와 같은 엔진, 액션만 실 I/O. 안전: 삭제(g5)는
# 무결성(g2)·크기(g4) 게이트를 *모두 통과한 뒤*에만 step 순서상 도달한다(엔진이 pass에만 전진).
# INGEST_OFFLINE=1 또는 definition.offline → 결정적 시뮬(네트워크 불필요, 배선/차단기 검증용).

def _idef(state):
    return state["constraints"]["definition"]


def _offline(state):
    return bool(os.environ.get("INGEST_OFFLINE") or _idef(state).get("offline"))


def _sh(cmd, cwd=None):
    return _sp.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)


def _zips_in(dldir):
    return set(_glob.glob(os.path.join(dldir, "**", "*.zip"), recursive=True))


@action("aihub_download")
async def _aih_download(state, artifacts):
    d = _idef(state)
    step = step_by_id(state, state["cursor"])
    dldir = d["dldir"]; os.makedirs(dldir, exist_ok=True)
    artifacts["dldir"] = dldir
    fk, dsk = str(d["filekey"]), str(d["datasetkey"])
    if _offline(state):                               # 결정적 시뮬(차단기/회복 데모)
        import zipfile
        artifacts.pop("abort_reason", None)
        if inject_fault(state, step):                 # 첫 시도 실패 → 보정 후 성공(회복)
            artifacts["new_zips"] = []
        else:
            z = os.path.join(dldir, f"sim_{dsk}_{fk}.zip")
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr(f"{fk}.json", fk * 128)
            artifacts["new_zips"] = [z]
        log(state, "TOOL", "aihub_download", "ok", rout=f"offline new={len(artifacts['new_zips'])}")
        return
    key = os.environ.get("KEY", "")
    before = _zips_in(dldir)
    r = _sh(f'aihubshell -mode d -datasetkey {dsk} -aihubapikey "{key}" -filekey {fk}', cwd=dldir)
    out = (r.stdout or "") + (r.stderr or "")
    # 진짜 HTTP 502/해외차단/승인거부만 systemic abort(HITL). 바이트수치 "502M" 오매칭 아님.
    if _re.search(r"HTTP status 502|해외 다운로드 제한|국외|신청 및 승인", out):
        artifacts["abort_reason"] = "다운로드 거부(승인/해외/HTTP502) — 환경조치 필요(HITL)"
        artifacts["new_zips"] = []
    else:
        artifacts.pop("abort_reason", None)
        artifacts["new_zips"] = [z for z in (_zips_in(dldir) - before) if os.path.getsize(z) > 0]
    log(state, "TOOL", "aihub_download", "ok" if artifacts.get("new_zips") else "fail",
        rout=f"new={len(artifacts.get('new_zips', []))}")


@acceptance("download_ok")
def _dl_ok(state, acc):
    """성공=0바이트 아닌 새 zip 존재(로그 스크래핑 아님). abort면 비재시도 원인 분기."""
    a = state["artifacts"]
    if a.get("abort_reason"):
        return {"passed": False, "cause": "download_aborted", "detail": a["abort_reason"]}
    ok = bool(a.get("new_zips"))
    return {"passed": ok, "cause": None if ok else "download_empty"}


@action("aihub_integrity")
async def _aih_integrity(state, artifacts):
    import zipfile
    zips = artifacts.get("new_zips", [])
    ok = bool(zips)
    for z in zips:
        if _offline(state):
            ok = ok and zipfile.is_zipfile(z)
        else:
            ok = ok and (_sh(f'unzip -tqq "{z}"').returncode == 0)
    artifacts["integrity_ok"] = ok
    log(state, "TOOL", "aihub_integrity", "ok" if ok else "fail", rout=f"zips={len(zips)}")


@action("aihub_upload")
async def _aih_upload(state, artifacts):
    d = _idef(state); dldir = d["dldir"]
    bk = os.environ.get("BK", d.get("bk", ""))
    prefix = d["bk_prefix"].strip("/")
    uploaded, ok = [], True
    for z in artifacts.get("new_zips", []):
        rel = os.path.relpath(z, dldir)
        dst = f"{bk}/{prefix}/{rel}"
        if _offline(state):
            artifacts.setdefault("_sim_gcs", {})[dst] = os.path.getsize(z)
            uploaded.append([z, dst]); continue
        r = _sh(f'gsutil -q cp "{z}" "{dst}"')
        if r.returncode != 0:
            if _re.search(r"Anonymous|401|403|credential", (r.stdout or "") + (r.stderr or "")):
                artifacts["abort_reason"] = "업로드 인증 실패 — gcloud auth 필요(HITL)"
            ok = False; break
        uploaded.append([z, dst])
    artifacts["uploaded"] = uploaded
    artifacts["upload_ok"] = ok and bool(uploaded)
    log(state, "TOOL", "aihub_upload", "ok" if artifacts["upload_ok"] else "fail",
        rout=f"uploaded={len(uploaded)}")


@action("aihub_sizecheck")
async def _aih_sizecheck(state, artifacts):
    d = _idef(state)
    if state["scratch"].get("g4_retry") and not _offline(state):   # 보정: 재시도면 재업로드 먼저
        for z, dst in artifacts.get("uploaded", []):
            _sh(f'gsutil -q cp "{z}" "{dst}"')
    ok, total = bool(artifacts.get("uploaded")), 0
    for z, dst in artifacts.get("uploaded", []):
        local = os.path.getsize(z); total += local
        if _offline(state):
            remote = artifacts.get("_sim_gcs", {}).get(dst)
        else:
            remote = None
            for line in (_sh(f'gsutil stat "{dst}"').stdout or "").splitlines():
                if "Content-Length" in line:
                    remote = int(line.split(":")[1].strip())
        ok = ok and (remote == local)
    artifacts["size_ok"] = ok
    artifacts["zip_bytes"] = total
    log(state, "TOOL", "aihub_sizecheck", "ok" if ok else "fail", rout=f"bytes={total}")


@acceptance("size_match_gcs")
def _size_gcs(state, acc):
    ok = state["artifacts"].get("size_ok") is True
    return {"passed": ok, "cause": None if ok else "size_mismatch"}


# ─────── 외부 RAG 출처 적재 (manifest §4) — aihubshell 대신 curl. 같은 엔진/게이트/버킷 ───────
# AI Hub filekey가 아니라 직접 URL(PDF/HTML). download만 curl로 분기하고 무결성·업로드·크기검증·
# 삭제는 aihub_* 액션 그대로 재사용(artifacts["new_zips"]=다운로드 파일경로). 폴더는 rag-corpus/* prefix.
@action("url_download")
async def _url_download(state, artifacts):
    d = _idef(state); step = step_by_id(state, state["cursor"])
    dldir = d["dldir"]; os.makedirs(dldir, exist_ok=True)
    artifacts["dldir"] = dldir
    out = os.path.join(dldir, d["filename"])
    if _offline(state):
        artifacts.pop("abort_reason", None)
        if inject_fault(state, step):
            artifacts["new_zips"] = []
        else:
            with open(out, "w") as f:
                f.write("SIM " + d["filename"])
            artifacts["new_zips"] = [out]
        log(state, "TOOL", "url_download", "ok", rout=f"offline new={len(artifacts['new_zips'])}")
        return
    r = _sh(f'curl -sL --max-time 180 -A "Mozilla/5.0" -w "%{{http_code}}" -o "{out}" "{d["url"]}"')
    code = (r.stdout or "").strip()[-3:]
    size = os.path.getsize(out) if os.path.exists(out) else 0
    if code in ("401", "403"):                      # 차단(anti-bot/권한) → 비재시도 HITL
        artifacts["abort_reason"] = f"URL 차단 HTTP {code} — 브라우저/수동 다운로드 필요"
        artifacts["new_zips"] = []
    elif r.returncode != 0 or size == 0 or not code.startswith("2"):
        artifacts.pop("abort_reason", None)         # 일시 실패 → 재시도 가능
        artifacts["new_zips"] = []
    else:
        artifacts.pop("abort_reason", None)
        artifacts["new_zips"] = [out]
    log(state, "TOOL", "url_download", "ok" if artifacts.get("new_zips") else "fail",
        rout=f"http={code} bytes={size}")


@action("url_integrity")
async def _url_integrity(state, artifacts):
    """기대 타입(pdf/html)과 실제 매직바이트 대조 — 잘못된 콘텐츠(에러페이지) 적재 방지."""
    exp = _idef(state).get("ftype", "pdf")
    files = artifacts.get("new_zips", [])
    ok = bool(files)
    for f in files:
        if _offline(state):
            ok = ok and os.path.getsize(f) > 0; continue
        with open(f, "rb") as fh:
            head = fh.read(1024)
        if exp == "pdf":
            ok = ok and head.startswith(b"%PDF")
        else:                                        # html
            low = head.lower()
            ok = ok and (b"<html" in low or b"<!doctype" in low)
    artifacts["integrity_ok"] = ok
    log(state, "TOOL", "url_integrity", "ok" if ok else "fail", rout=f"type={exp}")


@action("aihub_delete")
async def _aih_delete(state, artifacts):
    """2게이트(무결성+크기) 통과 후에만 도달 — 로컬 zip+조각 삭제."""
    gone = bool(artifacts.get("new_zips"))
    for z in artifacts.get("new_zips", []):
        try:
            if os.path.exists(z):
                os.remove(z)
            for p in _glob.glob(z[:-4] + ".part*"):
                os.remove(p)
        except OSError:
            pass
        gone = gone and (not os.path.exists(z))
    artifacts["deleted_ok"] = gone
    log(state, "TOOL", "aihub_delete", "ok" if gone else "fail")
