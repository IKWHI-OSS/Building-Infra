"""실 AI Hub 적재 드라이버 — INGEST_AIHUB spec(orc 인스턴스)으로 큐를 무인 적재.

orc 엔진(build_app)은 filekey 1건 = 1 트랜잭션(process_fk)을 돈다. 이 드라이버는
INGEST-AGENT.md의 *바깥 루프*(preflight 1회 / 큐 / 멱등 상태 / 연속실패 차단기 / HITL ABORT)다.
엔진은 그대로 두고 데이터(spec)만 filekey마다 갈아끼운다 = 도메인 무관 인스턴스의 실증.

사용 (agents/ 에서, .venv):
  python -m orc.ingest_driver 71918 --only 565888           # 리허설 1건
  python -m orc.ingest_driver 71921 --only 567336
  python -m orc.ingest_driver 71918                         # 전량(큐 = filekeys.tsv)
  INGEST_OFFLINE=1 python -m orc.ingest_driver 71918 --only 565888   # 결정적 시뮬

출력: 작업 중 침묵. 종료 후 표 1개(| filekey | 파일크기 | 버킷 업로드 성공여부 |)만.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / "scripts" / ".env")
except Exception:
    pass

from .orchestrator import build_app
from .state import initial_state
from .specs import ingest_aihub_spec, ingest_url_spec

ROOT = Path(__file__).resolve().parent.parent.parent          # constgx/
DLDIR = os.environ.get("DLDIR", os.path.expanduser("~/aihub_dl"))
HALT_CONSEC = 3                                                # 연속 FAILED 차단기


def _tsv_path(sn):
    return ROOT / "scripts" / f"aihub-{sn}-filekeys.tsv"


def _load_queue(sn):
    """filekeys.tsv → [(filekey, name, size_str)]. (filekey \t cat \t mod \t name \t size)"""
    rows = []
    for line in _tsv_path(sn).read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) >= 5 and p[0].strip().isdigit():
            rows.append((p[0].strip(), p[3].strip(), p[4].strip()))
    return rows


def _state_file(sn):
    suffix = "_offline" if os.environ.get("INGEST_OFFLINE") else ""
    return Path(DLDIR) / f"ingest_orc_{sn}{suffix}.tsv"


def _rag_sources():
    """외부 RAG 출처 1순위(manifest §1·§2). kssn 2건(2순위·유료)은 제외. 폴더는 aihub-*와 분리."""
    P, E = "rag-corpus/properties", "rag-corpus/environment"
    return [
        {"key": "KC62619_KATS", "ftype": "pdf", "prefix": P,
         "filename": "KC62619_ESS_리튬이차전지_안전성_KATS.pdf",
         "url": "https://www.kats.go.kr/cwsboard/board.do?mode=download&bid=155&cid=21073&filename=21073_201910251526580981.pdf"},
        {"key": "ESS_시험방법", "ftype": "pdf", "prefix": P,
         "filename": "KS_ESS셀_열폭주유도_시험방법.pdf",
         "url": "https://www.standard.go.kr/KSCI/ct/ptl/download.do?fileSn=141674"},
        {"key": "LIB_벤트가스_ACS", "ftype": "pdf", "prefix": P,
         "filename": "ACSOmega_LIB_벤트가스_가연한계.pdf",
         "url": "https://pubs.acs.org/doi/pdf/10.1021/acsomega.0c03713"},
        {"key": "소방청_화재예방", "ftype": "pdf", "prefix": E,
         "filename": "소방청_리튬이온_화재예방대책.pdf",
         "url": "https://www.isafe.go.kr/DATA/bbs/86/20250825032929346.pdf"},
        {"key": "KFPA_리튬위험성", "ftype": "html", "prefix": E,
         "filename": "KFPA_리튬이온_화재위험성.html",
         "url": "https://www.kfpa.or.kr/webzine/202408/disaster1.html"},
        {"key": "KFPA_EV충전", "ftype": "html", "prefix": E,
         "filename": "KFPA_전기차_충전시설_안전기준.html",
         "url": "https://www.kfpa.or.kr/webzine/202304/disaster1.html"},
        {"key": "LiFePO4_ACS", "ftype": "pdf", "prefix": E,
         "filename": "ACSOmega_LiFePO4_열폭주가스_분산폭발시뮬.pdf",
         "url": "https://pubs.acs.org/doi/pdf/10.1021/acsomega.3c08709"},
    ]


def _load_state(sn):
    f = _state_file(sn)
    st = {}
    if f.exists():
        for line in f.read_text().splitlines():
            p = line.split("\t")
            if len(p) >= 2:
                st[p[0]] = p[1]                                # 마지막 값이 최종(append-only)
    return st


def _record(sn, fk, status):
    with open(_state_file(sn), "a") as f:
        f.write(f"{fk}\t{status}\n")


def _human_bytes(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n/1:.0f} {u}" if False else f"{n:.1f} {u}"
        n /= 1024


async def _preflight(sn):
    """INGEST-AGENT preflight: aihubshell 패치 / gsutil 버킷 / 디스크 / KEY·BK."""
    if os.environ.get("INGEST_OFFLINE"):
        return True, "offline"
    import subprocess
    sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True)
    if not os.environ.get("KEY"):
        return False, "KEY 미설정(.env)"
    bk = os.environ.get("BK", "")
    if not bk.startswith("gs://"):
        return False, f"BK 형식오류: {bk!r}"
    ash = "/usr/local/bin/aihubshell"
    if sh(f"grep -q 'ls .*part' {ash}").returncode != 0:
        return False, "aihubshell 병합패치 미적용(0바이트 위험)"
    if sh(f'gsutil ls -b "{bk}" >/dev/null 2>&1').returncode != 0:
        if sh(f'gsutil mb -l asia-northeast3 -b on "{bk}"').returncode != 0:
            return False, "버킷 접근/생성 실패(인증 의심)"
    return True, "ok"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sn")
    ap.add_argument("--only", default="", help="쉼표구분 filekey만 (리허설)")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만")
    args = ap.parse_args()
    sn = args.sn
    bk_prefix = f"aihub-{sn}"

    ok, why = await _preflight(sn)
    if not ok:
        print(f"PREFLIGHT 실패(HITL): {why}")
        sys.exit(1)

    is_rag = (sn == "rag")
    offline = bool(os.environ.get("INGEST_OFFLINE"))
    if is_rag:
        items = _rag_sources()
        if args.only:
            want = set(args.only.split(","))
            items = [it for it in items if it["key"] in want]
    else:
        rows = _load_queue(sn)
        if args.only:
            want = set(args.only.split(","))
            rows = [r for r in rows if r[0] in want]
        items = [{"key": fk, "size": size, "name": name} for fk, name, size in rows]
    if args.limit:
        items = items[: args.limit]

    state = _load_state(sn)
    app = await build_app()
    results = []                                               # (key, size_str, ok, note)
    consec = 0
    aborted = None

    for it in items:
        key = it["key"]
        if state.get(key) == "DONE":
            results.append((key, it.get("size", ""), True, "skip(DONE)")); continue
        if is_rag:
            spec = ingest_url_spec(it["url"], it["filename"], it["prefix"], DLDIR,
                                   ftype=it["ftype"], offline=offline)
        else:
            spec = ingest_aihub_spec(sn, key, bk_prefix, DLDIR, it.get("name", ""), offline=offline)
        cfg = {"recursion_limit": 100, "configurable": {"thread_id": f"{sn}-{key}"}}
        final = await app.ainvoke(initial_state(spec), config=cfg)
        art = final["artifacts"]
        status = final["scratch"].get("_status", "DONE")
        zb = art.get("zip_bytes", 0)
        disp = _human_bytes(zb) if zb else it.get("size", "")
        if status == "DONE":
            _record(sn, key, "DONE"); results.append((key, disp, True, "")); consec = 0
        else:
            note = art.get("abort_reason") or (final.get("verdict") or {}).get("cause") or "FAILED"
            _record(sn, key, "FAILED"); results.append((key, disp, False, note)); consec += 1
            if not is_rag and art.get("abort_reason"):            # AI Hub: systemic → 큐 중단
                aborted = (key, art["abort_reason"]); break
            if consec >= HALT_CONSEC and not is_rag:              # RAG 차단은 출처별이라 큐 유지
                aborted = (key, f"연속 FAILED {consec}회 — systemic 의심"); break

    # ── 최종 표 (3열) ──
    ok_n = sum(1 for r in results if r[2])
    label = "출처" if is_rag else "filekey"
    print(f"\n[적재 결과 {sn}]  성공 {ok_n}/{len(items)}")
    print(f"| {label} | 파일크기 | 버킷 업로드 성공여부 |")
    print("|---|---|---|")
    for key, size_str, up, _ in results:
        print(f"| {key} | {size_str or '-'} | {'성공' if up else '실패'} |")
    fails = [(k, n) for k, s, u, n in results if not u]
    if fails:
        print("\n실패/보류 사유(HITL):")
        for k, n in fails:
            print(f"  - {k}: {n}")
    if aborted:
        print(f"\nABORT/HALT @ {aborted[0]}: {aborted[1]}")


if __name__ == "__main__":
    asyncio.run(main())
