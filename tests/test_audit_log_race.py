"""Regressão D16 — hash chain da auditoria não bifurca sob escrita concorrente.

Antes do fix, `_write` lia `last_hash` do arquivo FORA do _lock; duas
threads podiam ler o mesmo valor e gravar o mesmo previous_hash (fork).
Agora a cauda fica em memória sob o mesmo lock.
"""
import threading

from huawei_manager.audit_log import AuditLogger


def test_concurrent_writes_keep_chain_intact(tmp_path):
    logger = AuditLogger(str(tmp_path / "audit.jsonl"))
    threads = 10
    writes = 20

    def worker() -> None:
        for i in range(writes):
            logger.log_operation(
                "cli-rpc", user=f"u{i}", host="10.0.0.1",
                status="ok", op_index=i,
            )

    ts = [threading.Thread(target=worker) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert AuditLogger.verify_chain(str(logger._path)) is True


def test_concurrent_timed_writes_keep_chain_intact(tmp_path):
    logger = AuditLogger(str(tmp_path / "audit.jsonl"))
    threads = 6
    writes = 15

    def worker() -> None:
        for _ in range(writes):
            with logger.timed("get", user="admin", host="10.0.0.1"):
                pass

    ts = [threading.Thread(target=worker) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert AuditLogger.verify_chain(str(logger._path)) is True


def test_appending_to_existing_chain_seeds_from_file(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger1 = AuditLogger(str(path))
    logger1.log_operation("connect", user="a", host="h", status="ok")

    logger2 = AuditLogger(str(path))
    logger2.log_operation("get", user="b", host="h", status="ok")

    assert AuditLogger.verify_chain(str(path)) is True
