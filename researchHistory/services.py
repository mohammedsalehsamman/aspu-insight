from researchHistory.models import ResearchHistory

def log_status_change(paper, from_status, to_status, changed_by=None, note=""):
    if from_status == to_status:
        return None
    return ResearchHistory.objects.create(
        paper=paper,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        note=note,
    )
