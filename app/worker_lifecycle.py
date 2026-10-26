"""Defer window shutdown until owned Qt workers finish, without GUI waits."""


def workers_finished(owner, workers):
    pending = getattr(owner, '_closing_workers', None)
    if pending is None:
        pending = owner._closing_workers = set()
    running = False
    for worker in workers:
        if worker is None:
            continue
        try:
            if not worker.isRunning():continue
        except RuntimeError:continue
        running = True
        if worker in pending:
            continue
        pending.add(worker)

        def finished(current=worker):
            pending.discard(current)
            owner.close()

        worker.finished.connect(finished)
    return not running
